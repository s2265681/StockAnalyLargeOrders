"""
同花顺资金分时数据源
获取每分钟的超大单/大单/中单/小单流入流出数据（免费接口）
"""
import json
import logging
import time

import requests

logger = logging.getLogger(__name__)

_CACHE = {}
_CACHE_TTL_TRADING = 60     # 交易时间 60 秒
_CACHE_TTL_CLOSED = 300     # 非交易时间 5 分钟

_SESSION = requests.Session()
# 同花顺 d.10jqka.com.cn 可直连。后端常被从带（已失效）代理的 shell 启动，
# trust_env=True 会让请求走死代理导致资金流“时有时无”，必须显式禁用环境代理。
_SESSION.trust_env = False
_SESSION.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://stockpage.10jqka.com.cn/',
    'Accept': '*/*',
})


def _is_trading_time() -> bool:
    from datetime import datetime
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= t <= (15 * 60 + 5)


def _cache_ttl() -> int:
    return _CACHE_TTL_TRADING if _is_trading_time() else _CACHE_TTL_CLOSED


def _parse_jsonp(text: str) -> dict:
    """解析同花顺 JSONP 响应"""
    start = text.find('(')
    end = text.rfind(')')
    if start < 0 or end <= start:
        raise ValueError(f"非 JSONP 格式: {text[:100]}")
    return json.loads(text[start + 1:end])


def _ths_code(code: str) -> str:
    """6位股票代码 → 同花顺格式 hs_XXXXXX"""
    return f'hs_{code}'


def get_moneyflow(code: str) -> dict:
    """获取同花顺资金分时数据

    Args:
        code: 6位股票代码

    Returns:
        {
            'success': True/False,
            'date': '20260430',
            'items': [
                {
                    'time': '0930',
                    'super_big_in': 0.0,      # 超大单流入（元，累计）
                    'super_big_out': 0.0,     # 超大单流出
                    'big_in': 1917230.0,      # 大单流入
                    'big_out': 2676040.0,     # 大单流出
                    'mid_in': 0.0,            # 中单流入
                    'mid_out': 0.0,           # 中单流出
                    'small_in': 933920.0,     # 小单流入
                    'small_out': 2105810.0,   # 小单流出
                },
                ...
            ],
            'summary': {
                'super_big_net': -335937000.0,  # 超大单净额（元）
                'big_net': -4509526000.0,       # 大单净额
                'main_net': ...,                # 主力净额 = 超大单+大单
                'mid_net': 0.0,
                'small_net': -6866630000.0,
            },
            'source': 'ths',
        }
    """
    now = time.time()
    cache_key = f'ths_mf_{code}'
    if cache_key in _CACHE:
        ts, data = _CACHE[cache_key]
        if now - ts < _cache_ttl():
            return data

    result = _fetch_moneyflow(code)
    _CACHE[cache_key] = (now, result)
    return result


def _fetch_jsonp_text(url: str) -> str:
    """取 JSONP 原始文本。

    eventlet.monkey_patch() 下，整进程内 requests/SSL 会偶发
    `maximum recursion depth exceeded`，导致资金流“时有时无”。
    与 eastmoney_free 同策略：requests 包在 eventlet 超时里，失败
    回退 curl 子进程，彻底绕过 monkey_patch 对 SSL 的干扰。
    """
    def _do():
        resp = _SESSION.get(url, timeout=8)
        resp.raise_for_status()
        return resp.text

    try:
        import eventlet
        with eventlet.Timeout(10):
            return _do()
    except ImportError:
        try:
            return _do()
        except Exception:
            pass
    except Exception as e:
        logger.info(f"同花顺 requests 失败，回退 curl: {e}")

    import subprocess
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '8',
             '-A', _SESSION.headers.get('User-Agent', 'Mozilla/5.0'),
             '-e', 'https://stockpage.10jqka.com.cn/', url],
            capture_output=True, text=True, timeout=12,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        logger.warning(f"同花顺 curl 兜底失败 rc={result.returncode}")
    except Exception as e:
        logger.warning(f"同花顺 curl 兜底异常: {e}")
    return ''


def _fetch_moneyflow(code: str) -> dict:
    """实际请求同花顺资金分时接口"""
    ths_code = _ths_code(code)
    url = f'https://d.10jqka.com.cn/v2/moneyflow/{ths_code}/last.js'

    try:
        text = _fetch_jsonp_text(url)
        if not text:
            return {'success': False, 'items': [], 'summary': {}, 'source': 'ths'}

        data = _parse_jsonp(text)
        info = data.get(ths_code, {})
        raw = info.get('data', '')

        if not raw:
            logger.info(f"同花顺资金分时数据为空 code={code}（可能非交易时间）")
            return {'success': False, 'items': [], 'summary': {}, 'source': 'ths'}

        items = []
        for tick in raw.split(';'):
            fields = tick.split(',')
            if len(fields) < 9:
                continue
            items.append({
                'time': fields[0],
                'super_big_in': float(fields[1]),
                'super_big_out': float(fields[2]),
                'big_in': float(fields[3]),
                'big_out': float(fields[4]),
                'mid_in': float(fields[5]),
                'mid_out': float(fields[6]),
                'small_in': float(fields[7]),
                'small_out': float(fields[8]),
            })

        # 汇总：取最后一条（累计值）
        summary = {}
        if items:
            last = items[-1]
            sb_net = last['super_big_in'] - last['super_big_out']
            big_net = last['big_in'] - last['big_out']
            mid_net = last['mid_in'] - last['mid_out']
            small_net = last['small_in'] - last['small_out']
            summary = {
                'super_big_net': sb_net,
                'big_net': big_net,
                'main_net': sb_net + big_net,   # 主力 = 超大单 + 大单
                'mid_net': mid_net,
                'small_net': small_net,
                # 万元单位（前端展示用）
                'super_big_net_wan': round(sb_net / 10000, 2),
                'big_net_wan': round(big_net / 10000, 2),
                'main_net_wan': round((sb_net + big_net) / 10000, 2),
                'mid_net_wan': round(mid_net / 10000, 2),
                'small_net_wan': round(small_net / 10000, 2),
            }

        return {
            'success': True,
            'date': info.get('date', ''),
            'items': items,
            'summary': summary,
            'source': 'ths',
        }

    except Exception as e:
        logger.warning(f"同花顺资金分时请求失败 code={code}: {e}")
        return {'success': False, 'items': [], 'summary': {}, 'source': 'ths'}
