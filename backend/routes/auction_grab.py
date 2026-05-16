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

# 缓存：{date_type: {ts, data}}
_cache = {}
_CACHE_TTL = 60  # 60秒缓存


def _get_last_trading_day():
    """获取最近交易日（YYYYMMDD）"""
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d = d.replace(hour=0, minute=0, second=0)
        from datetime import timedelta
        d -= timedelta(days=1)
    elif dow == 6:
        from datetime import timedelta
        d -= timedelta(days=2)
    return d.strftime('%Y%m%d')


def _fetch_all_stocks():
    """从 push2 拉取全A股实时行情数据，使用子进程 curl 绕过 eventlet SSL 干扰"""
    import subprocess
    import json as _json
    from urllib.parse import urlencode

    base_url = 'https://push2.eastmoney.com/api/qt/clist/get'
    all_stocks = []
    page = 1
    while True:
        params = {
            'pn': page,
            'pz': 5000,
            'po': 1,
            'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2,
            'invt': 2,
            'fid': 'f6',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f2,f3,f5,f6,f12,f13,f14,f17,f18,f20,f21',
        }
        url = f"{base_url}?{urlencode(params)}"
        try:
            cmd = [
                'curl', '-s', '--max-time', '20',
                '-H', 'Referer: https://quote.eastmoney.com/',
                '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if result.returncode != 0 or not result.stdout.strip():
                logger.error(f"curl 失败 page={page}: rc={result.returncode}")
                break
            data = _json.loads(result.stdout)
            diff = data.get('data', {}).get('diff', [])
            if not diff:
                logger.warning(f"push2 clist 返回空数据 page={page}")
                break
            all_stocks.extend(diff)
            total = data.get('data', {}).get('total', 0)
            if len(all_stocks) >= total:
                break
            page += 1
        except Exception as e:
            logger.error(f"拉取股票列表失败 page={page}: {type(e).__name__}: {e}")
            break
    return all_stocks


def _compute_auction_grab(stocks, sort_by='wtje', sort_desc=True):
    """
    计算竞价抢筹指标
    - 开盘金额 ≈ 今开 × 成交量(按开盘价估算)（近似）
    - 抢算涨幅 = (今开 - 昨收) / 昨收 × 100%
    - 抢筹成交额 ≈ 开盘成交额（近似）
    - 抢筹委托金额 ≈ 开盘成交额 × 放大系数（需L2数据，此处近似）
    """
    results = []
    for s in stocks:
        code = str(s.get('f12', ''))
        name = s.get('f14', '')
        open_price = s.get('f17')      # 今开
        prev_close = s.get('f18')       # 昨收
        current = s.get('f2')           # 现价
        change_pct = s.get('f3')        # 涨跌幅
        volume = s.get('f5')            # 成交量（手）
        turnover = s.get('f6')          # 成交额
        market = s.get('f13', 0)        # 0=深圳 1=上海
        market_cap = s.get('f21')       # 流通市值

        # 过滤无效数据
        if not code or not name:
            continue
        if open_price is None or open_price == '-' or prev_close is None or prev_close == '-':
            continue
        if prev_close <= 0 or open_price <= 0:
            continue
        # 排除ST和退市
        if name.startswith('*') or name.startswith('退'):
            continue
        # 排除北交所
        if code.startswith('8') or code.startswith('4'):
            continue

        open_price = float(open_price)
        prev_close = float(prev_close)
        volume = int(volume) if volume and volume != '-' else 0
        turnover = float(turnover) if turnover and turnover != '-' else 0

        # 抢算涨幅
        grab_change_pct = round((open_price - prev_close) / prev_close * 100, 2)

        # 开盘金额近似：使用开盘价和流通市值估算换手
        # 简化为：假设竞价阶段成交额 ≈ 全天成交额 × 竞价占比（约3-10%）
        # 更精确的做法是从分时数据获取（但需逐个股获取，太慢）
        # 这里使用 turnover * auction_ratio 做近似
        auction_ratio = 0.05  # 假设竞价阶段约占全天5%
        open_amount = round(turnover * auction_ratio / 10000, 2)  # 万元

        # 抢筹成交额（近似）
        grab_turnover = open_amount

        # 抢筹委托金额（近似 = 成交额 × 委托放大倍数）
        # 实际L2数据中委托金额一般是成交额的 5-30 倍
        wtje_ratio = 15  # 近似放大系数
        grab_order_amount = round(open_amount * wtje_ratio, 2)

        # 只保留有意义的（涨幅>0 或 成交额较大的）
        if turnover <= 0:
            continue

        full_code = f"{code}.{'SH' if market == 1 else 'SZ'}"

        results.append({
            'code': code,
            'name': name,
            'full_code': full_code,
            'open_price': open_price,
            'prev_close': prev_close,
            'grab_change_pct': grab_change_pct,
            'open_amount': open_amount,          # 开盘金额（万）
            'grab_turnover': grab_turnover,      # 抢筹成交额（万）
            'grab_order_amount': grab_order_amount,  # 抢筹委托金额（万）
            'change_pct': change_pct if change_pct != '-' else 0,
            'turnover': round(turnover / 10000, 2),  # 全天成交额（万）
            'market_cap': market_cap,
        })

    # 排序
    sort_map = {
        'wtje': 'grab_order_amount',
        'cjje': 'grab_turnover',
        'kpje': 'open_amount',
        'zf': 'grab_change_pct',
    }
    sort_key = sort_map.get(sort_by, 'grab_order_amount')
    results.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=sort_desc)

    return results


def _compute_tail_grab(stocks, sort_by='wtje', sort_desc=True):
    """
    尾盘抢筹：计算尾盘阶段（14:57-15:00）的抢筹指标
    使用不同的近似估算比例
    """
    results = []
    for s in stocks:
        code = str(s.get('f12', ''))
        name = s.get('f14', '')
        open_price = s.get('f17')
        prev_close = s.get('f18')
        current = s.get('f2')
        change_pct = s.get('f3')
        volume = s.get('f5')
        turnover = s.get('f6')
        market = s.get('f13', 0)
        market_cap = s.get('f21')

        if not code or not name:
            continue
        if current is None or current == '-' or prev_close is None or prev_close == '-':
            continue
        if prev_close <= 0:
            continue
        if name.startswith('*') or name.startswith('退'):
            continue
        if code.startswith('8') or code.startswith('4'):
            continue

        current = float(current) if current and current != '-' else 0
        prev_close = float(prev_close)
        open_price = float(open_price) if open_price and open_price != '-' else 0
        volume = int(volume) if volume and volume != '-' else 0
        turnover = float(turnover) if turnover and turnover != '-' else 0
        change_pct = float(change_pct) if change_pct and change_pct != '-' else 0

        if turnover <= 0:
            continue

        # 尾盘竞价阶段约占全天 3%
        tail_ratio = 0.03
        tail_amount = round(turnover * tail_ratio / 10000, 2)
        grab_turnover = tail_amount
        grab_order_amount = round(tail_amount * 12, 2)

        # 尾盘涨幅 = 全天涨幅（近似）
        grab_change_pct = change_pct

        full_code = f"{code}.{'SH' if market == 1 else 'SZ'}"

        results.append({
            'code': code,
            'name': name,
            'full_code': full_code,
            'open_price': round(current, 2),  # 尾盘用收盘价
            'prev_close': prev_close,
            'grab_change_pct': grab_change_pct,
            'open_amount': tail_amount,
            'grab_turnover': grab_turnover,
            'grab_order_amount': grab_order_amount,
            'change_pct': change_pct,
            'turnover': round(turnover / 10000, 2),
            'market_cap': market_cap,
        })

    sort_map = {
        'wtje': 'grab_order_amount',
        'cjje': 'grab_turnover',
        'kpje': 'open_amount',
        'zf': 'grab_change_pct',
    }
    sort_key = sort_map.get(sort_by, 'grab_order_amount')
    results.sort(key=lambda x: x.get(sort_key, 0) or 0, reverse=sort_desc)

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

    # 缓存 key
    cache_key = f"{dt}_{grab_type}"
    now = time.time()

    # 检查缓存
    cached = _cache.get(cache_key)
    if cached and (now - cached['ts']) < _CACHE_TTL:
        all_results = cached['data']
    else:
        # 拉取全 A 股数据
        stocks = _fetch_all_stocks()
        if not stocks:
            return v1_error_response('拉取股票数据失败')

        if grab_type == '2':
            all_results = _compute_tail_grab(stocks)
        else:
            all_results = _compute_auction_grab(stocks)

        _cache[cache_key] = {'ts': now, 'data': all_results}

    # 重新排序（缓存存的是默认排序）
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
    paged_results = sorted_results[start:end]

    # 格式化输出
    items = []
    for r in paged_results:
        items.append({
            'code': r['code'],
            'name': r['name'],
            'open_amount': f"{r['open_amount']:.2f}",        # 开盘金额（万）
            'grab_change_pct': f"{r['grab_change_pct']:.2f}", # 抢算涨幅
            'grab_turnover': f"{r['grab_turnover']:.2f}",     # 抢筹成交额（万）
            'grab_order_amount': f"{r['grab_order_amount']:.2f}",  # 抢筹委托金额（万）
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
