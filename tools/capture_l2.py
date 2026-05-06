"""
mitmproxy 插件：捕获东方财富桌面端 L2 数据流量

用法：
  mitmdump -s tools/capture_l2.py -p 8888 --set stream_large_bodies=0

然后在 macOS 系统代理中设置 HTTP/HTTPS 代理为 127.0.0.1:8888，
打开东方财富桌面端，查看任意个股的 L2 数据（委托队列、买卖力道等）。

抓包结果保存到 tools/captured_l2_apis.json
"""
import json
import os
import time
from datetime import datetime
from mitmproxy import http

# 目标域名关键词
TARGET_HOSTS = [
    'push2ex.eastmoney.com',
    'push2.eastmoney.com',
    'push2his.eastmoney.com',
    'emhsmarketdata',      # 桌面端可能的行情服务器
    'nufm.dfcfw.com',       # 东方财富另一个API域名
    'dcfm.eastmoney.com',
    'gw.eastmoney.com',
    'webquoteklinepic',
    'quantapi.eastmoney',
]

# L2 特征关键词（URL 或响应中出现即标记为 L2 相关）
L2_KEYWORDS = [
    'orderqueue', 'order_queue', 'OrderQueue',
    'buysellpower', 'BuySellPower', 'buy_sell',
    'l2', 'L2', 'level2', 'Level2',
    'wtdl',       # 委托队列拼音缩写
    'mmld',       # 买卖力道拼音缩写
    'entrust',    # 委托
    'queue',      # 队列
    'bigorder', 'bigdeal', 'BigOrder',
    'dadan',      # 大单
    'zhudan',     # 主单
    'DDX', 'DDY', 'DDZ',
    'getStockFenShi',
    'getOrderQueue',
    'getBuyAndSellPower',
]

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'captured_l2_apis.json')
ALL_TRAFFIC_FILE = os.path.join(OUTPUT_DIR, 'captured_all_em.json')

# 存储捕获的请求
captured_apis = []
all_em_traffic = []


def _is_target(host: str) -> bool:
    if not host:
        return False
    host = host.lower()
    return any(kw in host for kw in TARGET_HOSTS)


def _is_l2_related(url: str, body: str) -> bool:
    text = (url + ' ' + body).lower()
    return any(kw.lower() in text for kw in L2_KEYWORDS)


def _parse_query(url: str) -> dict:
    """提取 URL 中的查询参数"""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}


def response(flow: http.HTTPFlow):
    host = flow.request.pretty_host
    if not _is_target(host):
        return

    url = flow.request.pretty_url
    req_headers = dict(flow.request.headers)
    query_params = _parse_query(url)

    # 响应体
    resp_body = ''
    resp_json = None
    if flow.response and flow.response.content:
        try:
            resp_body = flow.response.content.decode('utf-8', errors='replace')
            resp_json = json.loads(resp_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    entry = {
        'timestamp': datetime.now().isoformat(),
        'method': flow.request.method,
        'url': url,
        'host': host,
        'path': flow.request.path,
        'query_params': query_params,
        'request_headers': req_headers,
        'response_status': flow.response.status_code if flow.response else None,
        'response_body_preview': resp_body[:2000] if resp_body else '',
        'response_json': resp_json if resp_json else None,
    }

    # 记录所有东方财富流量
    all_em_traffic.append(entry)
    _save_json(all_em_traffic, ALL_TRAFFIC_FILE)

    # 判断是否 L2 相关
    is_l2 = _is_l2_related(url, resp_body[:500])

    tag = '🔴 L2' if is_l2 else '⚪ EM'
    print(f"\n{'='*80}")
    print(f"{tag} [{flow.request.method}] {url}")
    print(f"    Host: {host}")
    print(f"    Params: {json.dumps(query_params, ensure_ascii=False)[:200]}")

    # 打印关键认证信息
    for key in ['Cookie', 'Authorization', 'Token', 'token',
                'ut', 'pi', 'pn', 'po', 'sid', 'appkey']:
        if key in req_headers:
            print(f"    Header[{key}]: {req_headers[key][:100]}")
        if key.lower() in query_params:
            print(f"    Param[{key}]: {str(query_params[key.lower()])[:100]}")

    if resp_json:
        # 打印响应结构（不打全部数据，只看 keys）
        if isinstance(resp_json, dict):
            print(f"    Response keys: {list(resp_json.keys())}")
            if 'data' in resp_json and isinstance(resp_json['data'], dict):
                print(f"    data keys: {list(resp_json['data'].keys())}")
        print(f"    Response preview: {resp_body[:300]}")
    elif resp_body:
        print(f"    Response (text): {resp_body[:300]}")

    if is_l2:
        entry['is_l2'] = True
        captured_apis.append(entry)
        _save_json(captured_apis, OUTPUT_FILE)
        print(f"    >>> L2 接口已捕获！共 {len(captured_apis)} 个 L2 请求")

    print(f"{'='*80}")


def _save_json(data, filepath):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"保存失败: {e}")


def done():
    """mitmproxy 退出时的总结"""
    print(f"\n\n{'#'*80}")
    print(f"抓包结束！")
    print(f"  所有东方财富流量: {len(all_em_traffic)} 个请求 → {ALL_TRAFFIC_FILE}")
    print(f"  L2 相关请求:      {len(captured_apis)} 个请求 → {OUTPUT_FILE}")

    if captured_apis:
        print(f"\nL2 接口摘要:")
        seen = set()
        for api in captured_apis:
            # 去掉查询参数，只看路径
            from urllib.parse import urlparse
            path = urlparse(api['url']).path
            if path not in seen:
                seen.add(path)
                print(f"  - [{api['method']}] {api['host']}{path}")
                print(f"    Params: {list(api['query_params'].keys())}")
    else:
        print("\n未捕获到 L2 相关请求。请确认：")
        print("  1. 东方财富桌面端已设置代理 127.0.0.1:8888")
        print("  2. 已安装 mitmproxy CA 证书")
        print("  3. 已在桌面端打开个股的 L2 数据（委托队列/买卖力道等）")
    print(f"{'#'*80}\n")
