"""
其他功能接口模块
涵盖：涨停题材归纳、交易日期导航、缓存管理等
"""
import logging
from datetime import datetime
from flask import Blueprint, request
from utils.response import success_response, error_response
from utils.date_utils import get_next_trading_date, get_valid_trading_date, validate_and_get_trading_date
from utils.cache import clear_cache

logger = logging.getLogger(__name__)

stock_other_bp = Blueprint('stock_other', __name__)


def _normalize_code(code):
    return str(code).zfill(6)


def _json_value(value, default=0):
    if value is None:
        return default
    if hasattr(value, 'item'):
        return value.item()
    return value


def build_limit_up_theme_summary(limit_up_rows, code):
    """按题材/行业归纳涨停池，并标出当前股票所属题材"""
    normalized_code = _normalize_code(code)
    theme_map = {}
    current_stock = None

    for row in limit_up_rows:
        stock_code = _normalize_code(row.get('代码', ''))
        theme = row.get('所属行业') or '未分类'
        item = {
            'code': stock_code,
            'name': row.get('名称', ''),
            'price': _json_value(row.get('最新价'), 0),
            'limit_up_stat': row.get('涨停统计', ''),
            'consecutive_boards': int(_json_value(row.get('连板数'), 0) or 0),
            'seal_amount': _json_value(row.get('封板资金'), 0),
            'reason': f'{theme}题材涨停',
        }
        theme_map.setdefault(theme, {'theme': theme, 'count': 0, 'stocks': []})
        theme_map[theme]['count'] += 1
        theme_map[theme]['stocks'].append(item)
        if stock_code == normalized_code:
            current_stock = {**item, 'theme': theme}

    themes = sorted(theme_map.values(), key=lambda x: x['count'], reverse=True)
    for t in themes:
        cnt = len(t['stocks'])
        if cnt >= 4:
            t['linkage_score'] = round(min(cnt / 5, 1.0), 2)
            t['linkage_label'] = '强联动'
        elif cnt >= 2:
            t['linkage_score'] = round(cnt / 5, 2)
            t['linkage_label'] = '中等联动'
        else:
            t['linkage_score'] = 0.1
            t['linkage_label'] = '弱联动'

    lone_wolf = [s['code'] for t in themes if t['count'] == 1 for s in t['stocks']]
    current_theme = current_stock.get('theme') if current_stock else ''
    current_theme_count = theme_map.get(current_theme, {}).get('count', 0) if current_theme else 0

    return {
        'current_stock': current_stock or {
            'code': normalized_code,
            'name': '',
            'theme': '',
            'reason': '当前股票未在当日涨停池中，暂无涨停原因',
        },
        'current_theme': current_theme,
        'current_theme_count': current_theme_count,
        'themes': themes,
        'lone_wolf_stocks': lone_wolf,
    }


def _enrich_current_stock_info(data, code, ak):
    if data.get('current_theme'):
        return data
    try:
        info_df = ak.stock_individual_info_em(symbol=_normalize_code(code))
        info = dict(zip(info_df['item'], info_df['value']))
        theme = info.get('行业') or info.get('所属行业') or ''
        name = info.get('股票简称') or info.get('简称') or data['current_stock'].get('name', '')
        data['current_stock'] = {
            **data['current_stock'],
            'name': name,
            'theme': theme,
            'reason': f'当前股票属于{theme}行业，但未在当日涨停池中' if theme else data['current_stock']['reason'],
        }
        data['current_theme'] = theme
    except Exception as e:
        logger.warning(f"补充当前股票题材失败: {e}")
    return data


@stock_other_bp.route('/api/v1/limit_up_themes', methods=['GET'])
def get_limit_up_themes():
    """获取当前股票题材和当天涨停池按题材归纳
    优先使用数据库中的 AI 标签，没有则 fallback 到行业分类
    """
    code = request.args.get('code', '000001')
    dt = request.args.get('dt', datetime.now().strftime('%Y-%m-%d'))
    trade_date = dt.replace('-', '')

    try:
        import akshare as ak
        from services.theme_service import get_limit_up_stocks_by_date, get_tags_by_date

        # 优先从数据库读取 AI 标签数据
        db_stocks = get_limit_up_stocks_by_date(trade_date)
        db_tags = get_tags_by_date(trade_date)

        if db_stocks and db_tags:
            # 数据库有数据，使用 AI 标签
            data = _build_theme_summary_from_db(db_stocks, db_tags, code)
        else:
            # fallback: 用 akshare 原始行业分类
            df = ak.stock_zt_pool_em(date=trade_date)
            rows = df.to_dict('records') if df is not None else []
            data = build_limit_up_theme_summary(rows, code)
            data = _enrich_current_stock_info(data, code, ak)

        limit_down_count = 0
        try:
            dt_df = ak.stock_zt_pool_dtgc_em(date=trade_date)
            limit_down_count = len(dt_df) if dt_df is not None else 0
        except Exception:
            pass

        limit_up_count = sum(t['count'] for t in data.get('themes', []))
        if limit_up_count > limit_down_count * 5:
            sentiment_label = '强势'
        elif limit_up_count > limit_down_count * 2:
            sentiment_label = '偏强'
        elif limit_up_count > limit_down_count:
            sentiment_label = '中性'
        else:
            sentiment_label = '偏弱'

        data['market_sentiment'] = {
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'sentiment_label': sentiment_label,
            'lone_wolf_stocks': data.get('lone_wolf_stocks', []),
        }
        data['trade_date'] = dt
        data['data_source'] = 'database' if (db_stocks and db_tags) else 'akshare.stock_zt_pool_em'
        return success_response(data=data)
    except Exception as e:
        logger.error(f"获取涨停题材归纳失败: {e}", exc_info=True)
        return error_response(message=f'获取涨停题材归纳失败: {str(e)}')


def _build_theme_summary_from_db(db_stocks, db_tags, code):
    """从数据库的 AI 标签构建题材归纳"""
    normalized_code = _normalize_code(code)
    reason_map = {t["tag_name"]: t.get("reason", "") for t in db_tags}

    theme_map = {}
    current_stock = None

    for s in db_stocks:
        stock_code = s.get("code", "")
        tag = s.get("tag_name") or s.get("industry") or "未分类"
        item = {
            "code": stock_code,
            "name": s.get("name", ""),
            "price": float(s.get("price", 0) or 0),
            "limit_up_stat": s.get("zt_stat", ""),
            "consecutive_boards": int(s.get("boards", 1) or 1),
            "seal_amount": float(s.get("seal_amount", 0) or 0),
            "reason": reason_map.get(tag, f"{tag}题材涨停"),
        }
        theme_map.setdefault(tag, {"theme": tag, "count": 0, "stocks": []})
        theme_map[tag]["count"] += 1
        theme_map[tag]["stocks"].append(item)
        if stock_code == normalized_code:
            current_stock = {**item, "theme": tag}

    themes = sorted(theme_map.values(), key=lambda x: x["count"], reverse=True)
    for t in themes:
        cnt = len(t["stocks"])
        t["reason"] = reason_map.get(t["theme"], "")
        if cnt >= 4:
            t["linkage_score"] = round(min(cnt / 5, 1.0), 2)
            t["linkage_label"] = "强联动"
        elif cnt >= 2:
            t["linkage_score"] = round(cnt / 5, 2)
            t["linkage_label"] = "中等联动"
        else:
            t["linkage_score"] = 0.1
            t["linkage_label"] = "弱联动"

    lone_wolf = [s["code"] for t in themes if t["count"] == 1 for s in t["stocks"]]
    current_theme = current_stock.get("theme") if current_stock else ""
    current_theme_count = theme_map.get(current_theme, {}).get("count", 0) if current_theme else 0

    return {
        "current_stock": current_stock or {
            "code": normalized_code,
            "name": "",
            "theme": "",
            "reason": "当前股票未在当日涨停池中，暂无涨停原因",
        },
        "current_theme": current_theme,
        "current_theme_count": current_theme_count,
        "themes": themes,
        "lone_wolf_stocks": lone_wolf,
        "total_limit_up_count": len(db_stocks),
    }


@stock_other_bp.route('/api/trading-date/navigate', methods=['GET'])
def navigate_trading_date():
    """交易日期导航"""
    current_date = request.args.get('date', request.args.get('current_date'))
    direction = request.args.get('direction', 'next')
    try:
        if not current_date:
            latest_date = get_valid_trading_date()
            return success_response(data={
                'date': latest_date,
                'is_latest': True,
                'message': f'当前最新交易日: {latest_date}',
                'direction': direction,
            })
        result = get_next_trading_date(current_date, direction == 'next')
        return success_response(data={
            'date': result['date'],
            'is_latest': result['is_latest'],
            'message': result['message'],
            'direction': direction,
        })
    except Exception as e:
        logger.error(f"交易日期导航失败: {e}")
        return error_response(message=f'日期导航失败: {str(e)}',
                              data={'date': current_date, 'is_latest': False})


@stock_other_bp.route('/api/trading-date/current', methods=['GET'])
def get_current_trading_date():
    """获取当前有效交易日"""
    try:
        current_date = get_valid_trading_date()
        today = datetime.now().strftime('%Y-%m-%d')
        return success_response(data={
            'date': current_date,
            'today': today,
            'is_today': current_date == today,
            'message': f'当前交易日: {current_date}',
        })
    except Exception as e:
        logger.error(f"获取当前交易日失败: {e}")
        today = datetime.now().strftime('%Y-%m-%d')
        return error_response(message=f'获取交易日失败: {str(e)}',
                              data={'date': today, 'today': today, 'is_today': True})


@stock_other_bp.route('/api/trading-date/validate', methods=['GET'])
def validate_trading_date():
    """验证并获取有效交易日"""
    target_date = request.args.get('date', request.args.get('target_date'))
    if not target_date:
        return error_response(message='请提供要验证的日期参数')
    try:
        valid_date = validate_and_get_trading_date(target_date)
        is_same = valid_date == target_date
        return success_response(data={
            'original_date': target_date,
            'valid_date': valid_date,
            'is_same': is_same,
            'message': f'有效交易日: {valid_date}' if is_same else f'调整为最近交易日: {valid_date}',
        })
    except Exception as e:
        logger.error(f"验证交易日失败: {e}")
        return error_response(message=f'验证失败: {str(e)}',
                              data={'original_date': target_date, 'valid_date': target_date})


@stock_other_bp.route('/api/cache/clear', methods=['POST'])
def clear_cache_api():
    """清理缓存"""
    try:
        clear_cache()
        return success_response(message='缓存已清理')
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")
        return error_response(message=f'清理缓存失败: {str(e)}')


@stock_other_bp.route('/api/cache/status', methods=['GET'])
def get_cache_status():
    """获取缓存状态"""
    try:
        from utils.cache import data_cache
        keys = list(data_cache.keys())
        return success_response(data={
            'cache_count': len(keys),
            'cache_keys': keys[:10],
            'total_keys': len(keys),
        })
    except Exception as e:
        logger.error(f"获取缓存状态失败: {e}")
        return error_response(message=f'获取缓存状态失败: {str(e)}',
                              data={'cache_count': 0})
