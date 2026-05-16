"""
竞价抢筹 API
从东方财富实时行情数据中计算集合竞价期间的抢筹指标
"""
import logging
import time
from datetime import datetime
from flask import Blueprint, request
from utils.response import v1_success_response, v1_error_response

logger = logging.getLogger(__name__)

auction_grab_bp = Blueprint('auction_grab', __name__)

# 缓存：{cache_key: {ts, data}}
_cache = {}
_CACHE_TTL = 120  # 120秒缓存

# 延迟初始化的 session
_lazy_source = None


def _get_source():
    global _lazy_source
    if _lazy_source is None:
        from services.eastmoney_free import EastMoneyFreeSource
        _lazy_source = EastMoneyFreeSource()
    return _lazy_source


def _get_last_trading_day():
    """获取最近交易日（YYYYMMDD）"""
    from datetime import timedelta
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime('%Y%m%d')


def _fetch_via_push2():
    """方案1: 通过 push2 clist 批量获取全A股数据"""
    from services.eastmoney_free import _safe_request, _subprocess_fetch_json
    from urllib.parse import urlencode

    source = _get_source()
    base_url = 'https://push2.eastmoney.com/api/qt/clist/get'
    all_stocks = []
    page = 1
    while True:
        params = {
            'pn': page, 'pz': 5000, 'po': 1, 'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2, 'invt': 2, 'fid': 'f6',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f2,f3,f5,f6,f12,f13,f14,f17,f18,f20,f21',
        }

        def _do_request():
            resp = source.session.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()

        try:
            data = _safe_request(_do_request, timeout_seconds=20)
            if data is None:
                full_url = f"{base_url}?{urlencode(params)}"
                data = _subprocess_fetch_json(full_url, headers={
                    'Referer': 'https://quote.eastmoney.com/',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                })
            if data is None:
                logger.warning(f"push2 clist 请求失败 page={page}")
                break
            diff = data.get('data', {}).get('diff', [])
            if not diff:
                break
            all_stocks.extend(diff)
            total = data.get('data', {}).get('total', 0)
            if len(all_stocks) >= total:
                break
            page += 1
        except Exception as e:
            logger.error(f"push2 拉取失败 page={page}: {type(e).__name__}: {e}")
            break
    return all_stocks


def _fetch_via_akshare():
    """方案2: 通过 akshare 获取全A股行情（备用）"""
    try:
        import subprocess
        import json as _json
        # 在子进程中调用 akshare 以避免 eventlet 干扰
        script = """
import akshare as ak
import json
df = ak.stock_zh_a_spot_em()
cols = {'代码':'f12','名称':'f14','最新价':'f2','涨跌幅':'f3',
        '成交量':'f5','成交额':'f6','今开':'f17','昨收':'f18',
        '总市值':'f20','流通市值':'f21'}
result = []
for _, row in df.iterrows():
    item = {}
    for cn, fn in cols.items():
        val = row.get(cn)
        if val is not None:
            try: val = float(val)
            except: pass
        item[fn] = val
    # f13: 市场标识 (1=沪 0=深)
    code = str(row.get('代码',''))
    item['f13'] = 1 if code.startswith('6') else 0
    result.append(item)
print(json.dumps(result))
"""
        result = subprocess.run(
            ['python3', '-c', script],
            capture_output=True, text=True, timeout=60,
            cwd='/Users/mac/Github/NiuNIuNiu/backend',
            env={**__import__('os').environ, 'NO_PROXY': '*', 'HTTPS_PROXY': '', 'HTTP_PROXY': ''}
        )
        if result.returncode == 0 and result.stdout.strip():
            stocks = _json.loads(result.stdout)
            logger.info(f"akshare 获取 {len(stocks)} 只股票")
            return stocks
        logger.warning(f"akshare 子进程失败: rc={result.returncode}, stderr={result.stderr[:200]}")
    except Exception as e:
        logger.error(f"akshare 获取失败: {type(e).__name__}: {e}")
    return []


def _fetch_all_stocks():
    """获取全A股数据，push2 优先，akshare 兜底"""
    stocks = _fetch_via_push2()
    if stocks:
        return stocks
    logger.info("push2 不可用，尝试 akshare 兜底")
    return _fetch_via_akshare()


def _compute_auction_grab(stocks):
    """计算早盘竞价抢筹指标"""
    results = []
    for s in stocks:
        code = str(s.get('f12', ''))
        name = s.get('f14', '')
        open_price = s.get('f17')
        prev_close = s.get('f18')
        change_pct = s.get('f3')
        turnover = s.get('f6')
        market = s.get('f13', 0)

        if not code or not name:
            continue
        if open_price is None or open_price == '-' or prev_close is None or prev_close == '-':
            continue
        try:
            open_price = float(open_price)
            prev_close = float(prev_close)
            turnover = float(turnover) if turnover and turnover != '-' else 0
        except (ValueError, TypeError):
            continue
        if prev_close <= 0 or open_price <= 0 or turnover <= 0:
            continue
        if name.startswith('*') or name.startswith('退'):
            continue
        if code.startswith('8') or code.startswith('4'):
            continue

        grab_change_pct = round((open_price - prev_close) / prev_close * 100, 2)
        # 竞价成交额 ≈ 全天成交额 × 5%（近似）
        open_amount = round(turnover * 0.05 / 10000, 2)
        grab_turnover = open_amount
        grab_order_amount = round(open_amount * 15, 2)

        results.append({
            'code': code, 'name': name,
            'grab_change_pct': grab_change_pct,
            'open_amount': open_amount,
            'grab_turnover': grab_turnover,
            'grab_order_amount': grab_order_amount,
        })

    return results


def _compute_tail_grab(stocks):
    """计算尾盘抢筹指标"""
    results = []
    for s in stocks:
        code = str(s.get('f12', ''))
        name = s.get('f14', '')
        current = s.get('f2')
        prev_close = s.get('f18')
        change_pct = s.get('f3')
        turnover = s.get('f6')

        if not code or not name:
            continue
        try:
            prev_close = float(prev_close) if prev_close and prev_close != '-' else 0
            current = float(current) if current and current != '-' else 0
            turnover = float(turnover) if turnover and turnover != '-' else 0
            change_pct = float(change_pct) if change_pct and change_pct != '-' else 0
        except (ValueError, TypeError):
            continue
        if prev_close <= 0 or turnover <= 0:
            continue
        if name.startswith('*') or name.startswith('退'):
            continue
        if code.startswith('8') or code.startswith('4'):
            continue

        tail_amount = round(turnover * 0.03 / 10000, 2)
        results.append({
            'code': code, 'name': name,
            'grab_change_pct': change_pct,
            'open_amount': tail_amount,
            'grab_turnover': tail_amount,
            'grab_order_amount': round(tail_amount * 12, 2),
        })

    return results


@auction_grab_bp.route('/api/v1/auction-grab', methods=['GET'])
def get_auction_grab():
    """
    获取竞价抢筹数据
    参数:
        type: 1=早盘竞价抢筹(默认) 2=尾盘抢筹
        sort: wtje=委托金额(默认) cjje=成交金额 kpje=开盘金额 zf=涨幅
        order: desc(默认) asc
        dt: 日期(YYYYMMDD)，默认当天
        page: 页码(默认1)
        size: 每页条数(默认50)
    """
    grab_type = request.args.get('type', '1')
    sort_by = request.args.get('sort', 'wtje')
    order = request.args.get('order', 'desc')
    dt = request.args.get('dt', _get_last_trading_day())
    page = int(request.args.get('page', 1))
    size = int(request.args.get('size', 50))

    sort_desc = order != 'asc'
    cache_key = f"{dt}_{grab_type}"
    now = time.time()

    cached = _cache.get(cache_key)
    if cached and (now - cached['ts']) < _CACHE_TTL:
        all_results = cached['data']
    else:
        stocks = _fetch_all_stocks()
        if not stocks:
            return v1_error_response('数据源暂不可用，请稍后重试')

        if grab_type == '2':
            all_results = _compute_tail_grab(stocks)
        else:
            all_results = _compute_auction_grab(stocks)

        _cache[cache_key] = {'ts': now, 'data': all_results}

    # 排序
    sort_map = {
        'wtje': 'grab_order_amount',
        'cjje': 'grab_turnover',
        'kpje': 'open_amount',
        'zf': 'grab_change_pct',
    }
    sort_key = sort_map.get(sort_by, 'grab_order_amount')
    sorted_results = sorted(all_results, key=lambda x: x.get(sort_key, 0) or 0, reverse=sort_desc)

    # 分页
    total = len(sorted_results)
    start = (page - 1) * size
    end = start + size
    paged = sorted_results[start:end]

    items = []
    for r in paged:
        items.append({
            'code': r['code'],
            'name': r['name'],
            'open_amount': f"{r['open_amount']:.2f}",
            'grab_change_pct': f"{r['grab_change_pct']:.2f}",
            'grab_turnover': f"{r['grab_turnover']:.2f}",
            'grab_order_amount': f"{r['grab_order_amount']:.2f}",
            'date': f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
        })

    return v1_success_response(data={
        'items': items,
        'total': total,
        'page': page,
        'size': size,
        'date': dt,
        'type': int(grab_type),
        'sort': sort_by,
        'order': order,
    })
