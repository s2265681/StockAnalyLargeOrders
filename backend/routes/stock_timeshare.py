"""
股票分时数据接口模块
数据源：东方财富
"""
import logging
import json
import requests
from datetime import datetime
from flask import Blueprint, request
from utils.cache import cache_with_timeout
from utils.response import success_response, error_response, v1_success_response, v1_error_response
from utils.date_utils import validate_and_get_trading_date
from routes.stock_basic import get_stock_basic_data

logger = logging.getLogger(__name__)

stock_timeshare_bp = Blueprint('stock_timeshare', __name__)


def get_eastmoney_timeshare_data(code):
    """从东方财富获取实时分时数据"""
    try:
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        params = {
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': '7eea3edcaed734bea9cbfc24409ed989',
            'secid': market_code,
            'ndays': 1,
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com',
        }

        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            logger.warning(f"东方财富分时API响应错误: {response.status_code}")
            return None

        data = json.loads(response.text)
        if not data or 'data' not in data or not data['data']:
            logger.warning("东方财富分时数据响应格式错误")
            return None

        trends = data['data'].get('trends', [])
        if not trends or len(trends) <= 50:
            logger.warning(f"东方财富分时数据不足: {len(trends)} 个点")
            return None

        timeshare_data = []
        for trend in trends:
            parts = trend.split(',')
            if len(parts) < 8:
                continue
            datetime_str = parts[0]
            time_str = datetime_str.split(' ')[1] if ' ' in datetime_str else datetime_str
            # 跳过集合竞价阶段（09:15-09:29）
            if len(time_str) >= 5 and '09:15' <= time_str[:5] < '09:30':
                continue
            try:
                timeshare_data.append({
                    'time': time_str,
                    'price': float(parts[4]),
                    'volume': int(parts[5]) if parts[5] and parts[5] != '0' else 0,
                    'amount': float(parts[6]) if parts[6] and parts[6] != '0' else 0,
                    'avg_price': float(parts[7]) if parts[7] and parts[7] != '0' else float(parts[4]),
                })
            except (ValueError, IndexError):
                continue

        if not timeshare_data:
            return None

        stock_basic = get_stock_basic_data(code)
        prices = [d['price'] for d in timeshare_data]
        volumes = [d['volume'] for d in timeshare_data]

        return {
            'timeshare': timeshare_data,
            'statistics': {
                'current_price': stock_basic['current_price'],
                'yesterdayClose': stock_basic['yesterday_close'],
                'change_percent': stock_basic['change_percent'],
                'change_amount': stock_basic['change_amount'],
                'high': max(prices) if prices else stock_basic['high'],
                'low': min(prices) if prices else stock_basic['low'],
                'volume': sum(volumes) if volumes else stock_basic['volume'],
                'turnover': stock_basic['turnover'],
            },
        }
    except Exception as e:
        logger.warning(f"东方财富分时数据获取失败: {e}")
        return None


def get_eastmoney_l2_tick_data(code):
    """从东方财富获取当日逐笔大单数据（≥20万元）"""
    try:
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "http://push2.eastmoney.com/api/qt/stock/details/get"
        params = {
            'secid': market_code,
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': '-100000',
        }
        headers = {
            'Referer': 'http://quote.eastmoney.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            return None

        data = json.loads(response.text)
        if not data or 'data' not in data or not data['data']:
            return None

        details = data['data'].get('details', [])
        if not details or len(details) <= 10:
            return None

        tick_data = []
        for detail in details:
            if not isinstance(detail, str):
                continue
            parts = detail.split(',')
            if len(parts) < 5:
                continue
            try:
                price = float(parts[1])
                volume = int(parts[2])
                direction = int(parts[4])
                amount_yuan = price * volume * 100

                if amount_yuan < 200_000:
                    continue

                trade_type = {1: 1, 2: 3, 4: 4}.get(direction, 3)
                time_key = parts[0]
                # 跳过集合竞价
                if len(time_key) >= 5 and '09:15' <= time_key[:5] < '09:30':
                    continue

                tick_data.append({
                    'time': time_key,
                    'price': price,
                    'volume': volume * 100,
                    'amount': amount_yuan,
                    'trade_type': trade_type,
                })
            except (ValueError, IndexError):
                continue

        return tick_data if tick_data else None
    except Exception as e:
        logger.warning(f"东方财富逐笔数据获取失败: {e}")
        return None


def get_eastmoney_money_flow_data(code):
    """从东方财富获取主力/散户分钟级净流入数据"""
    try:
        market_code = f"1.{code}" if code.startswith('6') else f"0.{code}"
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            'fields1': 'f1,f2,f3,f7',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
            'klt': '1',
            'fqt': '1',
            'secid': market_code,
            'beg': '0',
            'end': '20500101',
            'lmt': '256',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com',
        }

        # eventlet.monkey_patch() 下裸 requests 偶发 SSL 递归崩溃，
        # 与仓库其它源一致：requests(eventlet超时) 失败回退 curl 子进程。
        data = None

        def _do():
            r = requests.get(url, params=params, headers=headers, timeout=10)
            r.raise_for_status()
            return json.loads(r.text)

        try:
            import eventlet
            with eventlet.Timeout(12):
                data = _do()
        except ImportError:
            try:
                data = _do()
            except Exception:
                data = None
        except Exception as e:
            logger.info(f"东财fflow requests失败，回退curl: {e}")

        if data is None:
            import subprocess
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            try:
                cp = subprocess.run(
                    ['curl', '-s', '--max-time', '10',
                     '-A', headers['User-Agent'], '-e', headers['Referer'], full_url],
                    capture_output=True, text=True, timeout=14,
                )
                if cp.returncode == 0 and cp.stdout.strip():
                    data = json.loads(cp.stdout)
            except Exception as e:
                logger.warning(f"东财fflow curl兜底失败: {e}")

        if not data or 'data' not in data or not data['data']:
            return None

        klines = data['data'].get('klines', [])
        if not klines:
            return None

        # kline字段: f51=时间, f52=主力净流入(超大+大单), f53=小单, f54=中单, f55=大单, f56=超大单
        # 数值为当日累计净流入（元）
        time_data = []
        zhuli_data = []     # 主力 = 超大单+大单
        sanhu_data = []     # 小单
        chaoda_data = []    # 超大单
        dadan_data = []     # 大单
        zhongdan_data = []  # 中单
        for kline in klines:
            parts = kline.split(',')
            zero = "0.000"
            raw_time = parts[0] if parts else ''
            time_data.append(raw_time.split(' ')[1] if ' ' in raw_time else raw_time)
            if len(parts) < 6:
                zhuli_data.append(zero)
                sanhu_data.append(zero)
                chaoda_data.append(zero)
                dadan_data.append(zero)
                zhongdan_data.append(zero)
                continue
            try:
                zhuli = float(parts[1] or 0)
                xiaodan = float(parts[2] or 0)
                zhongdan = float(parts[3] or 0)
                dadan = float(parts[4] or 0)
                chaoda = float(parts[5] or 0)
                zhuli_data.append(f"{zhuli / 10000:.3f}")
                sanhu_data.append(f"{xiaodan / 10000:.3f}")
                chaoda_data.append(f"{chaoda / 10000:.3f}")
                dadan_data.append(f"{dadan / 10000:.3f}")
                zhongdan_data.append(f"{zhongdan / 10000:.3f}")
            except (ValueError, IndexError):
                zhuli_data.append(zero)
                sanhu_data.append(zero)
                chaoda_data.append(zero)
                dadan_data.append(zero)
                zhongdan_data.append(zero)

        return {
            'time': time_data,
            'zhuli': zhuli_data,
            'sanhu': sanhu_data,
            'chaoda': chaoda_data,
            'dadan': dadan_data,
            'zhongdan': zhongdan_data,
        }
    except Exception as e:
        logger.warning(f"东方财富资金流向数据获取失败: {e}")
        return None


@stock_timeshare_bp.route('/api/stock/timeshare', methods=['GET'])
def get_timeshare_data():
    """获取分时数据 - 东方财富数据源"""
    code = request.args.get('code', '000001')
    date_param = request.args.get('date', request.args.get('dt'))

    try:
        if len(code) > 6:
            code = code[-6:]
        trading_date = validate_and_get_trading_date(date_param)

        result = get_eastmoney_timeshare_data(code)
        if result:
            result['trading_date'] = trading_date
            return success_response(data=result, message=f'success ({trading_date})')

        return error_response(message=f'无法获取股票 {code} 的分时数据')
    except Exception as e:
        logger.error(f"获取分时数据异常: {e}")
        return error_response(message=f'获取分时数据失败: {str(e)}')


@cache_with_timeout(15)
def _get_quote_cached(code):
    """缓存版 quote 构建，避免同一时刻多次调用东方财富"""
    ts_data_wrap = get_eastmoney_timeshare_data(code)
    if not ts_data_wrap:
        return None

    ts_data = ts_data_wrap['timeshare']
    stats = ts_data_wrap['statistics']

    money_flow = get_eastmoney_money_flow_data(code)
    l2_tick = get_eastmoney_l2_tick_data(code)

    fenshi = []
    volume = []
    zhuli = []
    sanhu = []
    zhuli_raw = money_flow['zhuli'] if money_flow else []
    sanhu_raw = money_flow['sanhu'] if money_flow else []

    for i, item in enumerate(ts_data):
        fenshi.append(str(item['price']))
        volume.append(item['volume'] * 100)
        zhuli.append(zhuli_raw[i] if i < len(zhuli_raw) else "0.000")
        sanhu.append(sanhu_raw[i] if i < len(sanhu_raw) else "0.000")

    big_map = {}
    if l2_tick:
        for tick in l2_tick:
            time_key = tick['time'][:5]
            big_map.setdefault(time_key, []).append({
                't': tick['trade_type'],
                'v': str(int(tick['amount'] / 10000)),
            })
    else:
        for item in ts_data:
            big_map.setdefault(item['time'][:5], [])

    return {
        'base_info': {
            'd300ave_percent': f"{stats['change_percent']:.2f}%",
            'highPrice': str(stats['high']),
            'lowPrice': str(stats['low']),
            'prevClosePrice': str(stats['yesterdayClose']),
            'yi_dong': '',
        },
        'big_map': big_map,
        'fenshi': fenshi,
        'volume': volume,
        'sanhu': sanhu,
        'zhuli': zhuli,
    }


@stock_timeshare_bp.route('/api/v1/quote', methods=['GET'])
def get_quote():
    """竞品格式 - 行情接口"""
    code = request.args.get('code', '000001')
    if len(code) > 6:
        code = code[-6:]

    try:
        result = _get_quote_cached(code)
        if not result:
            return v1_error_response(message=f'无法获取股票 {code} 的行情数据')
        return v1_success_response(data=result)
    except Exception as e:
        logger.error(f"获取行情数据失败: {e}")
        return v1_error_response(message=f'获取行情数据失败: {str(e)}')
