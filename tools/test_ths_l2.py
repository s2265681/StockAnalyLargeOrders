"""
测试同花顺(10jqka) L2 数据接口
探测委托队列、大单方向、买卖力道等数据的可用性
"""
import json
import requests
import time

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://stockpage.10jqka.com.cn/',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
})

CODE = '605099'  # 测试股票


def test_endpoint(name, url, params=None, headers=None):
    """测试单个端点"""
    print(f"\n{'='*60}")
    print(f"[{name}]")
    print(f"  URL: {url}")
    try:
        resp = SESSION.get(url, params=params, headers=headers, timeout=10)
        print(f"  Status: {resp.status_code}")
        text = resp.text[:500]

        # 尝试 JSON 解析
        try:
            data = resp.json()
            print(f"  Type: JSON")
            if isinstance(data, dict):
                print(f"  Keys: {list(data.keys())}")
                if 'data' in data and isinstance(data['data'], dict):
                    print(f"  data.keys: {list(data['data'].keys())}")
                # 打印部分数据
                preview = json.dumps(data, ensure_ascii=False)[:400]
                print(f"  Preview: {preview}")
            elif isinstance(data, list):
                print(f"  List length: {len(data)}")
                if data:
                    print(f"  First item: {json.dumps(data[0], ensure_ascii=False)[:200]}")
            return data
        except (json.JSONDecodeError, ValueError):
            # 可能是 JSONP
            if text.startswith('(') or 'callback' in text.lower():
                print(f"  Type: JSONP")
                # 提取 JSONP 内容
                start = text.find('(')
                end = text.rfind(')')
                if start >= 0 and end > start:
                    inner = text[start+1:end]
                    try:
                        data = json.loads(inner)
                        print(f"  Parsed Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                        preview = json.dumps(data, ensure_ascii=False)[:400]
                        print(f"  Preview: {preview}")
                        return data
                    except:
                        pass
            print(f"  Type: Text")
            print(f"  Body: {text[:300]}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


print("=" * 60)
print("同花顺 L2 数据接口探测")
print("=" * 60)

# ── 1. 实时行情（基础）──
test_endpoint(
    "实时行情 (d.10jqka)",
    f"https://d.10jqka.com.cn/v2/realhead/hs_{CODE}/last.js",
)

# ── 2. 分时成交明细 ──
test_endpoint(
    "分时成交明细 (d.10jqka)",
    f"https://d.10jqka.com.cn/v2/time/hs_{CODE}/last.js",
)

# ── 3. 逐笔成交 ──
test_endpoint(
    "逐笔成交 (stockpage)",
    f"https://stockpage.10jqka.com.cn/HQ_v4.php",
    params={'type': 'tick', 'code': CODE, 'start': 0, 'count': 50},
)

# ── 4. 大单数据 (DDX/DDY/DDZ) ──
test_endpoint(
    "DDX 数据",
    f"https://d.10jqka.com.cn/v4/line/hs_{CODE}/21/last.js",
)

# ── 5. 资金流向（大单净额）──
test_endpoint(
    "资金流向",
    f"https://d.10jqka.com.cn/v2/moneyflow/hs_{CODE}/last.js",
)

# ── 6. 委托队列 (order queue) - L2 特有 ──
test_endpoint(
    "委托队列 (ifind)",
    f"https://ifind.10jqka.com.cn/l2/orderqueue",
    params={'code': CODE},
)

test_endpoint(
    "委托队列 (d.10jqka L2)",
    f"https://d.10jqka.com.cn/v2/l2/orderqueue/hs_{CODE}/last.js",
)

test_endpoint(
    "委托队列 (flash L2)",
    f"https://flash.10jqka.com.cn/l2/orderqueue/{CODE}",
)

# ── 7. 买卖力道 ──
test_endpoint(
    "买卖力道 (d.10jqka)",
    f"https://d.10jqka.com.cn/v2/l2/buysellpower/hs_{CODE}/last.js",
)

test_endpoint(
    "买卖力道 (flash)",
    f"https://flash.10jqka.com.cn/l2/buysellpower/{CODE}",
)

# ── 8. 大单统计 ──
test_endpoint(
    "大单统计 (stockpage)",
    f"https://stockpage.10jqka.com.cn/HQ_v4.php",
    params={'type': 'bigorder', 'code': CODE, 'start': 0, 'count': 50},
)

# ── 9. 主力资金 ──
test_endpoint(
    "主力资金流",
    f"https://data.10jqka.com.cn/funds/ggzjl/field/zljlr/order/desc/page/1/ajax/1/free/1/",
)

# ── 10. hexin 数据接口 ──
test_endpoint(
    "hexin 实时数据",
    f"https://hq.hexin.cn/real/{CODE}.js",
)

# ── 11. 同花顺 ifind L2 ──
test_endpoint(
    "ifind L2 data",
    f"https://dq.10jqka.com.cn/fenshicj/{CODE}",
)

# ── 12. 行情中心 L2 ──
test_endpoint(
    "行情中心分时",
    f"https://d.10jqka.com.cn/v6/line/hs_{CODE}/01/today.js",
)

# ── 13. 千档行情 / 十档盘口 ──
test_endpoint(
    "十档盘口",
    f"https://d.10jqka.com.cn/v2/fiverange/hs_{CODE}/last.js",
)

# ── 14. 逐笔委托 ──
test_endpoint(
    "逐笔委托 (flash)",
    f"https://flash.10jqka.com.cn/l2/entrust/{CODE}",
)

# ── 15. 大单追踪 ──
test_endpoint(
    "大单追踪 (stockpage)",
    f"https://stockpage.10jqka.com.cn/HQ_v4.php",
    params={'type': 'DDZZ', 'code': CODE},
)

print(f"\n\n{'='*60}")
print("探测完成！检查上方输出中哪些接口返回了有效数据。")
print("='*60")
