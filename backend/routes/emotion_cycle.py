"""
情绪周期接口模块
- GET  /api/v1/emotion-cycle     代理 StockAPI 情绪周期数据
- POST /api/v1/emotion-analysis-with-storage  管理员全量分析
- POST /api/v1/emotion-intraday-refresh       刷新当天分析（可指定日期）
"""
import json
import logging
import os
import subprocess
from typing import Optional
from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from utils.auth_middleware import login_required, admin_required

logger = logging.getLogger(__name__)

emotion_cycle_bp = Blueprint('emotion_cycle', __name__)


def _init_emotion_analysis_table():
    """初始化情绪分析结果表"""
    from utils.db import execute_write
    sql = """
    CREATE TABLE IF NOT EXISTS emotion_analysis_results (
        id INT PRIMARY KEY AUTO_INCREMENT,
        date VARCHAR(8) UNIQUE NOT NULL,
        analysis_result_json LONGTEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """
    try:
        execute_write(sql)
        logger.info("emotion_analysis_results 表初始化成功")
    except Exception as e:
        logger.warning(f"emotion_analysis_results 表可能已存在: {e}")


def _migrate_emotion_intraday_columns():
    """为已有表补充当天分析字段（列名 intraday_* 保持兼容）"""
    from utils.db import execute_write
    migrations = [
        (
            "ALTER TABLE emotion_analysis_results "
            "ADD COLUMN intraday_result_json LONGTEXT NULL AFTER analysis_result_json"
        ),
        (
            "ALTER TABLE emotion_analysis_results "
            "ADD COLUMN intraday_updated_at TIMESTAMP NULL AFTER intraday_result_json"
        ),
    ]
    for sql in migrations:
        try:
            execute_write(sql)
        except Exception as e:
            if "Duplicate column" not in str(e):
                logger.warning(f"迁移 emotion 盘中字段: {e}")


# 模块加载时初始化
_init_emotion_analysis_table()
_migrate_emotion_intraday_columns()


# ---------- 常量 ----------
STOCKAPI_EMOTION_URL = (
    "http://user.stockapi.com.cn/v1/base/emotionalCycle"
    "?token=c6b042b0bc7178103985337e72c31b976264e6f85ce93b0e"
)
STOCKAPI_GN_URL = "http://user.stockapi.com.cn/v1/gnDataAi"
STOCKAPI_GN_TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
    "eyJleHAiOjE3ODEyNTM0NTksInVzZXJJZCI6IjIwNTQ0ODExMTk0OTk2MTIxNjIifQ."
    "-y6iLryNy1BDMHwKoQA0oPBhX1Bps523VZvyk9TDZCg"
)
from config.ai_prompts import (
    BATCH_ANALYSIS_PROMPT,
    DAILY_ANALYSIS_SYSTEM_PROMPT,
    EMOTION_CYCLE_DAILY_USER_SUFFIX,
    EMOTION_CYCLE_REALTIME_USER_SUFFIX,
    INTRADAY_SYSTEM_PROMPT,
    SINGLE_DATE_ANALYSIS_PROMPT,
    SYSTEM_PROMPT,
)
from utils.claude_client import call_claude_for_scenario
from utils.emotion_stage import calibrate_analysis_stage

# 列名 → 英文 key 的映射
COL_KEY_MAP = {
    "date1": "date",
    # szbl 原映射为上涨比例，但 StockAPI 数据口径不准，不再使用
    "lbjs": "consec_limit",
    "ylgd": "pressure_height",
    "zxgd": "latest_height",
    "dmqx": "big_loss_mood",
    "drqx": "big_profit_mood",
    "ztjs": "limit_up_count",
    "dbcgl": "board_hit_rate",
    "dtjs": "limit_down_count",
    "ygmc": "monster_stock",
    "zbjs": "broken_board_count",
}


def _curl_get_json(url: str, *, headers: dict = None, timeout: int = 15) -> dict:
    """curl 子进程发 GET 请求，避免 eventlet 下 requests 递归崩溃"""
    cmd = ["curl", "-s", "-k", "--noproxy", "*", "--max-time", str(timeout), url]
    if headers:
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
    env = {**os.environ, "no_proxy": "*", "NO_PROXY": "*"}
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 5, env=env,
        )
        if proc.returncode != 0:
            raise IOError(f"curl 失败 exit={proc.returncode}: {(proc.stderr or '')[:200]}")
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"curl 超时 {timeout}s")


def _safe_int(v) -> int:
    if v in (None, "-", "--", ""):
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


INTRADAY_SLOTS = ("0945", "1030", "1130", "1400", "1445", "close")
MORNING_SLOTS = frozenset({"0945", "1030", "1130"})


def _compute_rise_ratio(rise_count: int, fall_count: int) -> Optional[float]:
    """上涨比例 = 上涨家数 / 下跌家数"""
    if not rise_count or not fall_count:
        return None
    return round(rise_count / fall_count, 2)


def _apply_market_breadth(record: dict, rise_count: int, fall_count: int) -> None:
    record["rise_count"] = rise_count
    record["fall_count"] = fall_count
    record["rise_ratio"] = _compute_rise_ratio(rise_count, fall_count)


def _fetch_market_breadth() -> Optional[dict]:
    """获取全市场涨跌家数及上涨比例（上涨/下跌）。

    优先同花顺涨跌分布（口径与行情软件一致），备选东财沪/深指数 f104/f105 加总，
    最后尝试东财全 A 快照统计。
    """
    headers = {"Referer": "https://quote.eastmoney.com/"}
    ut = "ut=bd1d9ddb04089700cf9c27f6f7426281"

    try:
        body = _curl_get_json(
            "https://dq.10jqka.com.cn/fuyao/up_down_distribution/distribution/v2/realtime",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        up = (body.get("data") or {}).get("up")
        down = (body.get("data") or {}).get("down")
        if up is not None and int(up) > 0:
            rise_count = int(up)
            fall_count = int(down or 0)
            logger.info("同花顺涨跌分布: 上涨=%d 下跌=%d", rise_count, fall_count)
            return {
                "rise_count": rise_count,
                "fall_count": fall_count,
                "rise_ratio": _compute_rise_ratio(rise_count, fall_count),
            }
    except Exception as e:
        logger.debug("同花顺涨跌分布失败: %s", e)

    for host in ("82.push2", "push2", "80.push2"):
        try:
            url = (
                f"https://{host}.eastmoney.com/api/qt/ulist.np/get"
                f"?fltt=2&secids=1.000001,0.399001&fields=f104,f105,f106&{ut}"
            )
            body = _curl_get_json(url, headers=headers, timeout=10)
            diff = (body.get("data") or {}).get("diff") or []
            if not diff:
                continue
            rise_count = sum(_safe_int(item.get("f104")) for item in diff)
            fall_count = sum(_safe_int(item.get("f105")) for item in diff)
            if rise_count > 0:
                logger.info("东财指数统计: 上涨=%d 下跌=%d (沪+深)", rise_count, fall_count)
                return {
                    "rise_count": rise_count,
                    "fall_count": fall_count,
                    "rise_ratio": _compute_rise_ratio(rise_count, fall_count),
                }
        except Exception as e:
            logger.debug("东财指数涨跌家数 %s 失败: %s", host, e)

    try:
        url = (
            "https://82.push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=5000&po=1&np=1&fltt=2&invt=2&fid=f3"
            "&fs=m%3A0+t%3A6%2Cm%3A0+t%3A80%2Cm%3A1+t%3A2%2Cm%3A1+t%3A23%2Cm%3A0+t%3A81+s%3A2048"
            f"&fields=f3&{ut}"
        )
        body = _curl_get_json(url, headers=headers, timeout=15)
        items = (body.get("data") or {}).get("diff") or []
        if not items:
            return None
        rise_count = sum(1 for item in items if _safe_int(item.get("f3")) > 0)
        fall_count = sum(1 for item in items if _safe_int(item.get("f3")) < 0)
        if rise_count > 0:
            logger.info("东财全A快照: 上涨=%d 下跌=%d / %d", rise_count, fall_count, len(items))
            return {
                "rise_count": rise_count,
                "fall_count": fall_count,
                "rise_ratio": _compute_rise_ratio(rise_count, fall_count),
            }
    except Exception as e:
        logger.warning("获取涨跌家数失败: %s", e)
    return None


def _fetch_rise_count() -> Optional[int]:
    """兼容旧调用：仅返回上涨家数"""
    breadth = _fetch_market_breadth()
    return breadth.get("rise_count") if breadth else None


def _breadth_cache_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "cache", "market_breadth_history.json"
    )


def _legacy_rise_count_cache_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "cache", "rise_count_history.json"
    )


def _load_breadth_cache() -> dict:
    for path in (_breadth_cache_path(), _legacy_rise_count_cache_path()):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def _save_breadth_cache(cache: dict) -> None:
    path = _breadth_cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _normalize_breadth_entry(cached) -> Optional[dict]:
    if isinstance(cached, dict):
        rise = cached.get("rise_count")
        fall = cached.get("fall_count")
        ratio = cached.get("rise_ratio")
        if rise is not None:
            return {
                "rise_count": int(rise),
                "fall_count": int(fall or 0),
                "rise_ratio": ratio if ratio is not None else _compute_rise_ratio(int(rise), int(fall or 0)),
            }
        return None
    if isinstance(cached, (int, float)):
        return {"rise_count": int(cached), "fall_count": None, "rise_ratio": None}
    return None


def _merge_breadth_cache(records: list) -> list:
    """将本地缓存的历史涨跌数据合并进记录（StockAPI 不提供该字段）。"""
    cache = _load_breadth_cache()
    if not cache:
        return records
    for record in records:
        if record.get("rise_ratio") is not None:
            continue
        dt = str(record.get("date", "")).replace("-", "")
        entry = _normalize_breadth_entry(cache.get(dt))
        if not entry:
            continue
        if record.get("rise_count") is None and entry.get("rise_count") is not None:
            record["rise_count"] = entry["rise_count"]
        if record.get("fall_count") is None and entry.get("fall_count") is not None:
            record["fall_count"] = entry["fall_count"]
        if record.get("rise_ratio") is None and entry.get("rise_ratio") is not None:
            record["rise_ratio"] = entry["rise_ratio"]
    return records


def _persist_breadth(dt_display: str, breadth: dict) -> None:
    dt = dt_display.replace("-", "")
    cache = _load_breadth_cache()
    entry = {
        "rise_count": breadth.get("rise_count"),
        "fall_count": breadth.get("fall_count"),
        "rise_ratio": breadth.get("rise_ratio"),
    }
    if cache.get(dt) == entry:
        return
    cache[dt] = entry
    _save_breadth_cache(cache)


def _persist_rise_count(dt_display: str, rise_count: int) -> None:
    """兼容旧调用"""
    _persist_breadth(dt_display, {"rise_count": rise_count, "fall_count": None, "rise_ratio": None})


def _intraday_snapshot_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "cache", "emotion_intraday_snapshots.json"
    )


def _load_intraday_snapshots() -> dict:
    path = _intraday_snapshot_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_intraday_snapshots(cache: dict) -> None:
    path = _intraday_snapshot_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _current_intraday_slot(now=None) -> Optional[str]:
    """根据当前时间返回盘中时段键（与 cron 刷新点对齐）。"""
    from datetime import datetime

    t = now or datetime.now()
    hm = t.hour * 100 + t.minute
    if hm >= 1505:
        return "close"
    if hm >= 1445:
        return "1445"
    if hm >= 1400:
        return "1400"
    if hm >= 1130:
        return "1130"
    if hm >= 1030:
        return "1030"
    if hm >= 945:
        return "0945"
    return None


def _slot_display(slot: str) -> str:
    if slot == "close":
        return "收盘"
    return f"{slot[:2]}:{slot[2:]}"


def save_intraday_snapshot(record: dict, slot: Optional[str] = None) -> None:
    """保存当日某时段的情绪快照，供上午同时段对比使用。"""
    if not isinstance(record, dict):
        return
    dt = _record_date_key(record)
    if not dt:
        return
    slot = slot or _current_intraday_slot()
    if not slot:
        return
    cache = _load_intraday_snapshots()
    day = cache.setdefault(dt, {})
    day[slot] = {
        k: record.get(k)
        for k in (
            "date", "rise_count", "fall_count", "rise_ratio",
            "consec_limit", "pressure_height", "latest_height",
            "big_loss_mood", "big_profit_mood", "limit_up_count",
            "board_hit_rate", "limit_down_count", "broken_board_count",
            "monster_stock",
        )
    }
    _save_intraday_snapshots(cache)
    logger.info("情绪同时段快照: %s %s", dt, slot)


def _get_intraday_snapshot(dt: str, slot: str) -> Optional[dict]:
    dt = str(dt).replace("-", "")
    return (_load_intraday_snapshots().get(dt) or {}).get(slot)


def _build_same_slot_comparison_text(context_records: list, slot: Optional[str] = None) -> str:
    """上午分析：生成昨日同时段对比说明（避免与昨日收盘全天混比）。"""
    slot = slot or _current_intraday_slot()
    if not slot or slot not in MORNING_SLOTS or not context_records:
        return ""
    prev_dt = _record_date_key(context_records[-1])
    prev_slot = _get_intraday_snapshot(prev_dt, slot)
    if not prev_slot:
        return (
            f"【同时段对比说明】当前为上午时段 {_slot_display(slot)}，"
            f"暂无昨日同时段快照，请勿将今日盘中数据与昨日收盘全天数据直接对比。"
        )
    prev_close = _get_intraday_snapshot(prev_dt, "close") or context_records[-1]
    return (
        f"【同时段对比说明】当前为上午时段 {_slot_display(slot)}。"
        f"今日数据为盘中快照，须与昨日同时段对比，勿与昨日收盘全天对比。\n"
        f"昨日同时段({_slot_display(slot)})基准：\n"
        f"{json.dumps(prev_slot, ensure_ascii=False, indent=2)}\n"
        f"（参考）昨日收盘全天：\n"
        f"{json.dumps(prev_close, ensure_ascii=False, indent=2)}"
    )


def _fetch_zt_counts() -> dict:
    """用 akshare 涨停/跌停/炸板池获取当日家数，盘中实时可用。返回可能为空 dict。"""
    from utils.date_utils import get_valid_trading_date
    dt = get_valid_trading_date().replace("-", "")
    result = {}
    try:
        import akshare as ak
        df = ak.stock_zt_pool_em(date=dt)
        if df is not None:
            result["limit_up_count"] = len(df)
    except Exception as e:
        logger.debug("akshare 涨停池失败 %s: %s", dt, e)
    try:
        import akshare as ak
        df = ak.stock_zt_pool_dtgc_em(date=dt)
        if df is not None:
            result["limit_down_count"] = len(df)
    except Exception as e:
        logger.debug("akshare 跌停池失败 %s: %s", dt, e)
    try:
        import akshare as ak
        df = ak.stock_zt_pool_zbgc_em(date=dt)
        if df is not None:
            result["broken_board_count"] = len(df)
    except Exception as e:
        logger.debug("akshare 炸板池失败 %s: %s", dt, e)
    lu = result.get("limit_up_count")
    zb = result.get("broken_board_count")
    if lu is not None and zb is not None and (lu + zb) > 0:
        result["board_hit_rate"] = round(lu / (lu + zb) * 100, 2)
    return result


def _format_date(date_int: int) -> str:
    """将 20260515 转为 '2026-05-15'"""
    s = str(date_int)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _transform_row(col_names: list, row: list) -> dict:
    """将一行数据按列名映射转为字典，并格式化日期"""
    record = {}
    for col_name, value in zip(col_names, row):
        key = COL_KEY_MAP.get(col_name)
        if key is None:
            continue
        if col_name == "date1":
            value = _format_date(value)
        record[key] = value
    return record


# ---------- 1. 情绪周期数据 ----------

def _fetch_emotion_records():
    """从 StockAPI 拉取情绪周期原始记录列表；当日字段为 None 时用自有接口实时补填。"""
    body = _curl_get_json(
        STOCKAPI_EMOTION_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    if body.get("code") != 20000:
        raise ValueError(f"StockAPI 返回异常: code={body.get('code')}")
    data = body["data"]
    col_names = data["colNameList"]
    records = [_transform_row(col_names, row) for row in data["contentList"]]

    if not records:
        return records
    last = records[-1]

    # 上涨比例：StockAPI 不提供可靠数据，当日用实时接口补取
    if last.get("rise_ratio") is None:
        breadth = _fetch_market_breadth()
        if breadth:
            _apply_market_breadth(
                last,
                breadth["rise_count"],
                breadth.get("fall_count") or 0,
            )
            logger.info(
                "market_breadth 补取: %s → 涨=%d 跌=%d 比例=%s",
                last.get("date"),
                last.get("rise_count"),
                last.get("fall_count"),
                last.get("rise_ratio"),
            )
            _persist_breadth(last.get("date", ""), breadth)
            save_intraday_snapshot(last)

    # 涨停/跌停/炸板家数：有任一字段为 None 时用 akshare 涨停池补取
    zt_fields = ("limit_up_count", "limit_down_count", "broken_board_count", "board_hit_rate")
    if any(last.get(f) is None for f in zt_fields):
        zt = _fetch_zt_counts()
        if zt:
            for field in zt_fields:
                if last.get(field) is None and field in zt:
                    last[field] = zt[field]
            logger.info(
                "涨停池补取: %s zt=%s dt=%s zb=%s rate=%s",
                last.get("date"),
                last.get("limit_up_count"), last.get("limit_down_count"),
                last.get("broken_board_count"), last.get("board_hit_rate"),
            )

    return _merge_breadth_cache(records)


def _build_fallback_record(dt_str: str) -> dict:
    """StockAPI 无当日数据时，用 akshare + 梯队库构造兜底记录"""
    dt_clean = dt_str.replace("-", "")
    dt_display = f"{dt_clean[:4]}-{dt_clean[4:6]}-{dt_clean[6:8]}"

    record = {
        "date": dt_display,
        "rise_count": None,
        "fall_count": None,
        "rise_ratio": None,
        "consec_limit": None,
        "pressure_height": None,
        "latest_height": None,
        "big_loss_mood": None,
        "big_profit_mood": None,
        "limit_up_count": None,
        "board_hit_rate": None,
        "limit_down_count": None,
        "monster_stock": None,
        "broken_board_count": None,
    }

    # 1. akshare 涨停/跌停/炸板池
    try:
        import akshare as ak
        zt_df = ak.stock_zt_pool_em(date=dt_clean)
        if zt_df is not None and len(zt_df) > 0:
            record["limit_up_count"] = len(zt_df)
    except Exception as e:
        logger.debug("akshare 涨停池失败 %s: %s", dt_clean, e)

    try:
        import akshare as ak
        dt_df = ak.stock_zt_pool_dtgc_em(date=dt_clean)
        if dt_df is not None:
            record["limit_down_count"] = len(dt_df)
    except Exception as e:
        logger.debug("akshare 跌停池失败 %s: %s", dt_clean, e)

    try:
        import akshare as ak
        zb_df = ak.stock_zt_pool_zbgc_em(date=dt_clean)
        if zb_df is not None:
            record["broken_board_count"] = len(zb_df)
    except Exception as e:
        logger.debug("akshare 炸板池失败 %s: %s", dt_clean, e)

    lu = record["limit_up_count"]
    zb = record["broken_board_count"]
    if lu is not None and zb is not None and (lu + zb) > 0:
        record["board_hit_rate"] = round(lu / (lu + zb) * 100, 2)

    # 2. 梯队库：连板家数、最高板高、妖股名称
    try:
        from services.theme_service import load_echelon_from_db
        echelon_data = load_echelon_from_db(dt_clean)
        if echelon_data and echelon_data.get("stocks"):
            stocks = echelon_data["stocks"]
            boards_list = [s.get("boards", 1) for s in stocks if s.get("boards")]
            if boards_list:
                record["consec_limit"] = sum(1 for b in boards_list if b >= 2)
                max_b = max(boards_list)
                record["pressure_height"] = max_b
                record["latest_height"] = max_b
                top = next((s for s in stocks if s.get("boards") == max_b), None)
                if top:
                    record["monster_stock"] = top.get("name", "")
    except Exception as e:
        logger.debug("梯队库读取失败 %s: %s", dt_clean, e)

    logger.info("兜底情绪记录 %s: zt=%s dt=%s zb=%s consec=%s",
                dt_display,
                record["limit_up_count"], record["limit_down_count"],
                record["broken_board_count"], record["consec_limit"])
    return record


def inject_fallback_if_missing(records: list, dt_str: str) -> list:
    """若 dt_str 不在 records 中，构造兜底记录并追加。返回新列表。"""
    dt_clean = dt_str.replace("-", "")
    exists = any(
        (r.get("date") or "").replace("-", "") == dt_clean
        for r in records
    )
    if exists:
        return records
    logger.warning("%s 不在 StockAPI 记录中，注入兜底数据", dt_clean)
    fallback = _build_fallback_record(dt_str)
    return list(records) + [fallback]


@emotion_cycle_bp.route('/api/v1/emotion-cycle', methods=['GET'])
def get_emotion_cycle():
    """代理 StockAPI 情绪周期数据并转换格式"""
    try:
        from utils.date_utils import get_valid_trading_date
        records = _fetch_emotion_records()
        today = get_valid_trading_date().replace("-", "")
        today_in_records = any(
            (r.get("date") or "").replace("-", "") == today for r in records
        )
        if not today_in_records and _get_analysis_from_db(today):
            records = inject_fallback_if_missing(records, today)
        return v1_success_response(data={"records": records})
    except (IOError, TimeoutError) as e:
        logger.error(f"请求 StockAPI 情绪周期失败: {e}")
        return v1_error_response(message=f"请求 StockAPI 失败: {str(e)}")
    except ValueError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"处理情绪周期数据异常: {e}")
        return v1_error_response(message=f"处理数据异常: {str(e)}")


# ---------- 2. 情绪周期分析 ----------

def _get_analysis_from_db(dt: str) -> dict:
    """从数据库查询该日期的分析结果"""
    from utils.db import execute_query
    sql = "SELECT analysis_result_json FROM emotion_analysis_results WHERE date = %s"
    result = execute_query(sql, (dt,))
    if result:
        try:
            return json.loads(result[0]["analysis_result_json"])
        except (json.JSONDecodeError, IndexError, KeyError):
            return None
    return None


def _is_placeholder_analysis(data: dict) -> bool:
    """判断周期研判是否为占位/未生成（盘中刷新会写入空占位）"""
    if not isinstance(data, dict):
        return True
    if data.get("stage") == "待生成":
        return True
    return not (
        data.get("analysis")
        or data.get("advice")
        or data.get("recommendations")
    )


def _save_analysis_to_db(dt: str, analysis_json: dict) -> bool:
    """保存分析结果到数据库"""
    from utils.db import execute_write
    sql = """
    INSERT INTO emotion_analysis_results (date, analysis_result_json)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE
        analysis_result_json = VALUES(analysis_result_json),
        updated_at = CURRENT_TIMESTAMP
    """
    try:
        execute_write(
            sql,
            (dt, json.dumps(analysis_json, ensure_ascii=False))
        )
        return True
    except Exception as e:
        logger.error(f"保存分析结果失败: {e}")
        return False


def _get_intraday_from_db(dt: str) -> dict:
    """从数据库查询当天分析结果（intraday_result_json）"""
    from utils.db import execute_query
    sql = (
        "SELECT intraday_result_json, intraday_updated_at "
        "FROM emotion_analysis_results WHERE date = %s"
    )
    result = execute_query(sql, (dt,))
    if not result or not result[0].get("intraday_result_json"):
        return None
    try:
        data = json.loads(result[0]["intraday_result_json"])
        updated_at = result[0].get("intraday_updated_at")
        if updated_at and isinstance(data, dict):
            data["updated_at"] = str(updated_at)
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def _save_intraday_to_db(dt: str, intraday_json: dict) -> bool:
    """保存当天分析，不覆盖 analysis_result_json"""
    from utils.db import execute_query, execute_write
    payload = json.dumps(intraday_json, ensure_ascii=False)
    existing = execute_query(
        "SELECT id FROM emotion_analysis_results WHERE date = %s",
        (dt,),
    )
    if existing:
        sql = """
        UPDATE emotion_analysis_results
        SET intraday_result_json = %s, intraday_updated_at = CURRENT_TIMESTAMP
        WHERE date = %s
        """
        try:
            execute_write(sql, (payload, dt))
            return True
        except Exception as e:
            logger.error(f"更新当天分析失败: {e}")
            return False

    placeholder = json.dumps(
        {"stage": "待生成", "analysis": "", "advice": "", "recommendations": []},
        ensure_ascii=False,
    )
    sql = """
    INSERT INTO emotion_analysis_results (date, analysis_result_json, intraday_result_json)
    VALUES (%s, %s, %s)
    """
    try:
        execute_write(sql, (dt, placeholder, payload))
        return True
    except Exception as e:
        logger.error(f"保存当天分析失败: {e}")
        return False


def _json_safe(value):
    """将 DB Decimal 等类型转为 JSON 可序列化值"""
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _summarize_echelon_context(dt: str) -> str:
    """压缩当日涨停梯队，供当天分析 prompt 使用"""
    try:
        from services.theme_service import get_limit_up_stocks_by_date

        stocks = get_limit_up_stocks_by_date(dt.replace("-", "")) or []
        if not stocks:
            return "（当日涨停梯队数据暂无，请结合情绪数据与热门板块推断）"
        compact = []
        for s in stocks[:45]:
            compact.append(_json_safe({
                "name": s.get("name"),
                "code": s.get("code"),
                "boards": s.get("boards"),
                "tag": s.get("tag_name") or s.get("industry"),
                "seal_ratio": s.get("seal_ratio"),
                "turnover_rate": s.get("turnover_rate"),
                "first_time": s.get("first_time"),
                "break_count": s.get("break_count"),
                "is_leader": s.get("is_leader"),
            }))
        return json.dumps(compact, ensure_ascii=False)[:3500]
    except Exception as e:
        logger.warning(f"获取涨停梯队摘要失败 {dt}: {e}")
        return "（涨停梯队数据暂不可用）"


def _fetch_hot_sectors() -> str:
    """获取当日热门板块题材，用于丰富分析"""
    try:
        body = _curl_get_json(
            STOCKAPI_GN_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "token": STOCKAPI_GN_TOKEN,
            },
            timeout=10,
        )
        return json.dumps(body, ensure_ascii=False)[:2000]
    except Exception as e:
        logger.warning(f"获取热门板块失败: {e}")
        return "（热门板块数据暂不可用）"


@emotion_cycle_bp.route('/api/v1/emotion-analysis', methods=['POST'])
def post_emotion_analysis():
    """接收近期情绪周期数据，调用 Claude 进行分析"""
    try:
        body = request.get_json(silent=True) or {}
        records = body.get("records")
        if not records or not isinstance(records, list):
            return v1_error_response(message="请在 body 中提供 records 数组")

        # 获取热门板块辅助信息
        hot_sectors = _fetch_hot_sectors()

        # 构造用户 prompt
        data_text = json.dumps(records, ensure_ascii=False, indent=2)
        user_prompt = (
            f"以下是最近的情绪周期数据（从旧到新）：\n{data_text}\n\n"
            f"当日热门板块题材信息：\n{hot_sectors}\n\n"
            f"{EMOTION_CYCLE_REALTIME_USER_SUFFIX}\n"
        )

        content = call_claude_for_scenario(
            "emotion_cycle_realtime",
            SYSTEM_PROMPT + "\n\n" + user_prompt,
            raise_on_error=True,
        )

        logger.info(f"Claude 原始返回 content (前500字): {content[:500]}")
        # 尝试解析 JSON
        import re
        result = None
        clean = content.strip()
        # 去掉 markdown 代码块包裹
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]
            clean = clean.rsplit("```", 1)[0].strip()
        # 尝试直接解析
        try:
            result = json.loads(clean)
        except json.JSONDecodeError:
            pass
        # 如果失败，用正则提取第一个 { ... } 块
        if result is None:
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        # 最终 fallback
        if result is None:
            logger.warning(f"Claude 返回非 JSON 内容: {content[:500]}")
            result = {
                "stage": "未知",
                "analysis": content,
                "advice": "",
                "recommendations": [],
            }

        return v1_success_response(data=result)

    except Exception as e:
        logger.error(f"情绪分析异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")


# ---------- 3. 查询已有分析结果 ----------

@emotion_cycle_bp.route('/api/v1/emotion-analysis-cache', methods=['GET'])
def get_emotion_analysis_cache():
    """查询数据库中已有的分析结果（不触发新分析）"""
    dt = request.args.get('date')
    if not dt:
        return v1_error_response(message="请提供 date 参数")
    db_result = _get_analysis_from_db(dt)
    if db_result and not _is_placeholder_analysis(db_result):
        return v1_success_response(data=db_result)
    return v1_success_response(data=None, message="还未生成")


def _record_date_key(record: dict) -> str:
    """统一记录日期格式为 YYYYMMDD，方便比较和存库。"""
    return str(record.get("date", "")).replace("-", "")


def _relax_json_text(text: str) -> str:
    """修正常见 JSON 语法问题（尾逗号、智能引号等）"""
    import re

    t = text.replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub(r",\s*}", "}", t)
    t = re.sub(r",\s*]", "]", t)
    return t


def _parse_claude_json_object(content: str) -> dict:
    """解析 Claude 返回的单个 JSON 对象"""
    import re

    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()

    candidates = [clean]
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        candidates.append(match.group())

    result = None
    last_err = None
    for raw in candidates:
        for variant in (raw, _fix_json_quotes(raw), _relax_json_text(raw),
                        _relax_json_text(_fix_json_quotes(raw))):
            try:
                result = json.loads(variant)
                break
            except json.JSONDecodeError as e:
                last_err = e
        if result is not None:
            break

    if result is None:
        logger.warning(f"JSON 解析失败: {last_err}, 片段: {content[:400]}")
        raise Exception("AI 返回格式异常")
    if not isinstance(result, dict):
        raise Exception("AI 返回格式异常")
    return result


def _call_claude_daily_analysis(
    current_record: dict,
    context_records: list,
    cycle_anchor: Optional[dict],
    prev_daily: Optional[dict] = None,
    echelon_text: str = "",
    hot_sectors: str = "",
) -> dict:
    """生成单日当天分析（含买卖点与昨日复盘）"""
    anchor_text = "（暂无周期研判锚点，请仅依据数据判断）"
    if cycle_anchor:
        anchor_text = json.dumps(
            {
                "stage": cycle_anchor.get("stage"),
                "analysis": cycle_anchor.get("analysis"),
                "advice": cycle_anchor.get("advice"),
                "recommendations": cycle_anchor.get("recommendations"),
            },
            ensure_ascii=False,
        )

    prev_text = "（无上一交易日当天分析）"
    if prev_daily:
        prev_text = json.dumps(
            {
                "stage": prev_daily.get("stage"),
                "advice": prev_daily.get("advice"),
                "recommendations": prev_daily.get("recommendations"),
                "trade_plans": prev_daily.get("trade_plans"),
            },
            ensure_ascii=False,
        )

    data_text = json.dumps(
        {"context": context_records, "today": current_record},
        ensure_ascii=False,
        indent=2,
    )
    same_slot_text = _build_same_slot_comparison_text(context_records)
    user_prompt = (
        f"分析日期：{current_record.get('date')}\n\n"
        f"周期研判锚点：\n{anchor_text}\n\n"
        f"上一交易日当天分析（用于 prev_day_review 复盘）：\n{prev_text}\n\n"
    )
    if same_slot_text:
        user_prompt += f"{same_slot_text}\n\n"
    user_prompt += (
        f"情绪周期数据：\n{data_text}\n\n"
        f"当日涨停梯队（按连板高度排序）：\n{echelon_text}\n\n"
        f"热门板块：\n{hot_sectors}\n\n"
        f"{EMOTION_CYCLE_DAILY_USER_SUFFIX}"
    )

    content = call_claude_for_scenario(
        "emotion_cycle_daily",
        DAILY_ANALYSIS_SYSTEM_PROMPT + "\n\n" + user_prompt,
        raise_on_error=True,
    )
    result = _parse_claude_json_object(content)
    result["date"] = current_record.get("date")
    return calibrate_analysis_stage(result, current_record, context_records)


def _call_claude_intraday(
    current_record: dict,
    context_records: list,
    cycle_anchor: Optional[dict],
) -> dict:
    """兼容旧接口：调用当天分析（无昨日复盘上下文时）"""
    dt = _record_date_key(current_record)
    prev_dt = None
    if context_records:
        prev_dt = _record_date_key(context_records[-1])
    prev_daily = _get_intraday_from_db(prev_dt) if prev_dt else None
    echelon_text = _summarize_echelon_context(dt)
    hot_sectors = _fetch_hot_sectors()
    return _call_claude_daily_analysis(
        current_record,
        context_records,
        cycle_anchor,
        prev_daily=prev_daily,
        echelon_text=echelon_text,
        hot_sectors=hot_sectors,
    )


def _is_empty_daily_analysis(data: dict) -> bool:
    if not isinstance(data, dict):
        return True
    return not (
        data.get("analysis")
        or data.get("trade_plans")
        or data.get("recommendations")
    )


def analyze_daily_one_date(
    target_dt: str,
    all_records: list,
    force: bool = False,
) -> str:
    """为单个交易日生成当天分析并存库。返回 skipped | saved | failed"""
    target_dt = str(target_dt).replace("-", "")
    if not force:
        existing = _get_intraday_from_db(target_dt)
        if existing and not _is_empty_daily_analysis(existing):
            logger.info(f"{target_dt} 已有当天分析，跳过")
            return "skipped"

    valid = [r for r in all_records if isinstance(r, dict) and _record_date_key(r)]
    ordered = sorted(valid, key=_record_date_key)
    idx = next(
        (i for i, r in enumerate(ordered) if _record_date_key(r) == target_dt),
        None,
    )
    if idx is None:
        logger.error(f"{target_dt} 不在记录列表中，无法生成当天分析")
        return "failed"

    current_record = ordered[idx]
    ctx_start = max(0, idx - 5)
    context_records = ordered[ctx_start:idx]

    cycle_anchor = _get_analysis_from_db(target_dt)
    if not cycle_anchor and context_records:
        cycle_anchor = _get_analysis_from_db(_record_date_key(context_records[-1]))

    prev_daily = None
    if context_records:
        prev_daily = _get_intraday_from_db(_record_date_key(context_records[-1]))

    echelon_text = _summarize_echelon_context(target_dt)
    hot_sectors = _fetch_hot_sectors()
    save_intraday_snapshot(current_record)

    logger.info(f"生成当天分析 {target_dt}，上下文 {len(context_records)} 条")
    result = None
    last_err = None
    for attempt in range(2):
        try:
            result = _call_claude_daily_analysis(
                current_record,
                context_records,
                cycle_anchor,
                prev_daily=prev_daily,
                echelon_text=echelon_text,
                hot_sectors=hot_sectors,
            )
            break
        except Exception as e:
            last_err = e
            logger.warning(f"{target_dt} 当天分析第 {attempt + 1} 次失败: {e}")
    if result is None:
        logger.error(f"{target_dt} 当天分析 AI 失败: {last_err}")
        return "failed"

    if not _save_intraday_to_db(target_dt, result):
        logger.error(f"{target_dt} 当天分析存库失败")
        return "failed"
    logger.info(f"{target_dt} 当天分析已存库")
    return "saved"


def run_batch_daily_analysis(records: list, force_mode: str = "missing") -> dict:
    """批量离线生成当天分析。force_mode: missing | recent | all"""
    if not records or not isinstance(records, list):
        raise ValueError("records 必须为非空 list")

    all_dates = sorted({_record_date_key(r) for r in records if _record_date_key(r)})
    if force_mode == "all":
        target_dates = all_dates
    elif force_mode == "recent":
        target_dates = all_dates[-3:]
    elif force_mode == "missing":
        target_dates = []
        for dt in all_dates:
            existing = _get_intraday_from_db(dt)
            if not existing or _is_empty_daily_analysis(existing):
                target_dates.append(dt)
    else:
        raise ValueError(f"未知 force_mode: {force_mode}")

    if not target_dates:
        return {
            "analyzed": 0,
            "total": len(records),
            "target_dates": 0,
            "message": "所有目标日期已有当天分析",
        }

    saved = 0
    failed = 0
    skipped = 0
    force = force_mode in ("all", "recent")
    # 从旧到新，保证 prev_day_review 可引用前一日结果
    for dt in sorted(target_dates):
        status = analyze_daily_one_date(dt, records, force=force)
        if status == "saved":
            saved += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1

    msg = f"当天分析完成: 生成 {saved} 天，跳过 {skipped} 天，失败 {failed} 天"
    logger.info(msg)
    return {
        "analyzed": saved,
        "skipped": skipped,
        "failed": failed,
        "total": len(records),
        "target_dates": len(target_dates),
        "message": msg,
    }


@emotion_cycle_bp.route('/api/v1/emotion-intraday-cache', methods=['GET'])
def get_emotion_intraday_cache():
    """查询当天分析缓存（只读，与 emotion-analysis-cache 一致，无需登录）"""
    dt = request.args.get('date')
    if not dt:
        return v1_error_response(message="请提供 date 参数")
    dt = dt.replace("-", "")
    db_result = _get_intraday_from_db(dt)
    if db_result:
        return v1_success_response(data=db_result)
    return v1_success_response(data=None)


@emotion_cycle_bp.route('/api/v1/emotion-intraday-refresh', methods=['POST'])
@login_required
def refresh_emotion_intraday():
    """刷新当天分析：可传 date(YYYYMMDD)，默认最新交易日；force=1 强制重算"""
    try:
        body = request.get_json(silent=True) or {}
        force = str(body.get("force") or request.args.get("force", "0")).lower() in (
            "1", "true", "yes"
        )
        records = _fetch_emotion_records()
        if not records:
            return v1_error_response(message="未获取到情绪周期数据")

        ordered = sorted(records, key=_record_date_key)
        req_date = (body.get("date") or request.args.get("date") or "").replace("-", "")
        if req_date:
            current_record = next(
                (r for r in ordered if _record_date_key(r) == req_date),
                None,
            )
            if not current_record:
                return v1_error_response(message=f"日期 {req_date} 无情绪数据")
            current_dt = req_date
            idx = ordered.index(current_record)
            context_records = ordered[max(0, idx - 5):idx]
        else:
            current_record = ordered[-1]
            current_dt = _record_date_key(current_record)
            context_records = ordered[max(0, len(ordered) - 6):-1]

        if force:
            status = analyze_daily_one_date(current_dt, ordered, force=True)
            if status == "failed":
                return v1_error_response(message="生成当天分析失败")
            result = _get_intraday_from_db(current_dt)
        else:
            status = analyze_daily_one_date(current_dt, ordered, force=False)
            if status == "failed":
                return v1_error_response(message="生成当天分析失败")
            result = _get_intraday_from_db(current_dt)

        if not result:
            return v1_error_response(message="当天分析结果为空")

        return v1_success_response(
            data={
                "intraday": result,
                "daily": result,
                "records": records,
            },
            message=f"已刷新 {current_dt} 当天分析",
        )
    except (IOError, TimeoutError) as e:
        logger.error(f"当天分析拉取行情失败: {e}")
        return v1_error_response(message=f"请求 StockAPI 失败: {str(e)}")
    except ValueError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"当天分析刷新异常: {e}")
        return v1_error_response(message=f"当天分析异常: {str(e)}")


@emotion_cycle_bp.route('/api/v1/emotion-analysis-refresh-current', methods=['POST'])
def refresh_current_emotion_analysis():
    """只刷新最新交易日的情绪分析，适合盘中数据更新后快速重算。"""
    try:
        body = request.get_json(silent=True) or {}
        records = body.get("records")
        if not records or not isinstance(records, list):
            return v1_error_response(message="请在 body 中提供 records 数组")

        valid_records = [r for r in records if isinstance(r, dict) and _record_date_key(r)]
        if not valid_records:
            return v1_error_response(message="records 中缺少有效日期")

        ordered_records = sorted(valid_records, key=_record_date_key)
        current_record = ordered_records[-1]
        current_dt = _record_date_key(current_record)
        current_index = len(ordered_records) - 1
        context_start = max(0, current_index - 5)
        records_to_analyze = ordered_records[context_start:current_index + 1]

        logger.info(
            f"刷新最新交易日情绪分析: {current_dt}, 上下文 {len(records_to_analyze)} 条"
        )
        results = _call_claude_batch(records_to_analyze)
        current_result = next(
            (
                item for item in results
                if isinstance(item, dict) and _record_date_key(item) == current_dt
            ),
            None,
        )
        if current_result is None:
            return v1_error_response(message="AI 未返回最新交易日分析结果")

        current_result = _calibrate_result_for_records(current_result, ordered_records)

        if not _save_analysis_to_db(current_dt, current_result):
            return v1_error_response(message="保存最新交易日分析失败")

        return v1_success_response(
            data=current_result,
            message=f"已刷新 {current_dt} 情绪分析"
        )

    except Exception as e:
        logger.error(f"刷新最新交易日情绪分析异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")


# ---------- 4. 全量情绪周期分析（为每一天生成分析） ----------

def _calibrate_result_for_records(item: dict, all_records: list) -> dict:
    """按记录在完整序列中的位置，对 AI 研判做阶段校准。"""
    if not isinstance(item, dict):
        return item
    dt = _record_date_key(item)
    ordered = sorted(
        [r for r in all_records if isinstance(r, dict) and _record_date_key(r)],
        key=_record_date_key,
    )
    idx = next((i for i, r in enumerate(ordered) if _record_date_key(r) == dt), None)
    if idx is None:
        return item
    return calibrate_analysis_stage(item, ordered[idx], ordered[max(0, idx - 5):idx])


def _fix_json_quotes(text):
    """修复 AI 返回的 JSON 中字符串值内未转义的双引号"""
    import re
    # Strategy: find all string values and escape internal quotes
    # Match pattern: "key": "value with "quotes" inside"
    # We fix by replacing unescaped quotes inside string values
    result = []
    i = 0
    in_string = False
    escape_next = False
    string_start = -1

    while i < len(text):
        ch = text[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if ch == '\\':
            escape_next = True
            i += 1
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                string_start = i
            else:
                # Check if this quote ends the string or is embedded
                # Look ahead: after closing quote should be , ] } : or whitespace
                rest = text[i+1:].lstrip()
                if rest and rest[0] in (',', ']', '}', ':'):
                    in_string = False
                elif not rest:
                    in_string = False
                else:
                    # This is an embedded quote — escape it
                    text = text[:i] + '\u201c' + text[i+1:]  # Replace with left curly quote
                    i += 1
                    continue
        i += 1
    return text


def _call_claude_batch(records_batch):
    """调用 Claude 分析一批记录，返回解析后的 list"""
    import re

    data_text = json.dumps(records_batch, ensure_ascii=False, indent=2)
    user_prompt = f"以下是连续交易日的情绪周期数据（共{len(records_batch)}天）：\n{data_text}"

    content = call_claude_for_scenario(
        "emotion_cycle_batch",
        BATCH_ANALYSIS_PROMPT + "\n\n" + user_prompt,
        raise_on_error=True,
    )
    logger.info(f"批量分析返回 (前300字): {content[:300]}")

    results = None
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        results = json.loads(clean)
    except json.JSONDecodeError:
        # 尝试修复 AI 返回的 JSON 中未转义的双引号
        try:
            fixed = _fix_json_quotes(clean)
            results = json.loads(fixed)
            logger.info("JSON 修复后解析成功")
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', content)
            if match:
                try:
                    results = json.loads(match.group())
                except json.JSONDecodeError:
                    try:
                        results = json.loads(_fix_json_quotes(match.group()))
                    except json.JSONDecodeError:
                        pass

    if not isinstance(results, list):
        raise Exception("AI 返回格式异常")
    return results


def _call_claude_single(context_records: list, target_record: dict) -> dict:
    """用上下文 + 目标日期调用 Claude，只返回目标日期的单条分析结果"""
    import re

    ctx_text = json.dumps(context_records, ensure_ascii=False, indent=2)
    tgt_text = json.dumps(target_record, ensure_ascii=False, indent=2)
    same_slot_text = _build_same_slot_comparison_text(context_records)
    user_prompt = (
        f"【历史上下文（仅供参考趋势，共{len(context_records)}条）】\n{ctx_text}\n\n"
        f"【目标日期（只分析这一天）】\n{tgt_text}"
    )
    if same_slot_text:
        user_prompt += f"\n\n{same_slot_text}"

    # 把字段说明从 BATCH_ANALYSIS_PROMPT 复用
    field_guide = "\n".join(
        BATCH_ANALYSIS_PROMPT.split("## 六大情绪指标")[0].split("## 数据字段说明")[1].strip().splitlines()
    ) if "## 数据字段说明" in BATCH_ANALYSIS_PROMPT else ""

    prompt = SINGLE_DATE_ANALYSIS_PROMPT.replace("{FIELD_GUIDE}", field_guide)

    content = call_claude_for_scenario(
        "emotion_cycle_single",
        prompt + "\n\n" + user_prompt,
        raise_on_error=True,
    )
    logger.info(f"单日分析返回 (前200字): {content[:200]}")

    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()

    # 兼容 AI 误返回数组的情况
    try:
        result = json.loads(clean)
        if isinstance(result, list) and result:
            result = result[-1]
    except json.JSONDecodeError:
        try:
            result = json.loads(_fix_json_quotes(clean))
            if isinstance(result, list) and result:
                result = result[-1]
        except json.JSONDecodeError:
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                result = json.loads(match.group())
            else:
                raise Exception("AI 返回格式异常")

    if not isinstance(result, dict):
        raise Exception("AI 返回格式异常")
    return calibrate_analysis_stage(result, target_record, context_records)


def analyze_one_date(target_dt: str, all_records: list, force: bool = False) -> str:
    """为单个交易日生成周期研判并存库（幂等、不依赖 HTTP）。

    返回 'skipped' | 'saved' | 'failed'。
    - force=False 且 DB 已有该日 → 'skipped'
    - 取 target 当日前 5 个交易日作趋势上下文，只让 Claude 分析 target 当日
    """
    target_dt = str(target_dt).replace("-", "")
    if not force:
        existing = _get_analysis_from_db(target_dt)
        if existing and not _is_placeholder_analysis(existing):
            logger.info(f"{target_dt} 已有周期研判，跳过")
            return "skipped"

    valid = [r for r in all_records if isinstance(r, dict) and _record_date_key(r)]
    ordered = sorted(valid, key=_record_date_key)
    idx = next(
        (i for i, r in enumerate(ordered) if _record_date_key(r) == target_dt),
        None,
    )
    if idx is None:
        logger.error(f"{target_dt} 不在记录列表中，无法分析")
        return "failed"

    ctx_records = ordered[max(0, idx - 5):idx]
    target_record = ordered[idx]
    save_intraday_snapshot(target_record)
    logger.info(f"分析 {target_dt}，上下文 {len(ctx_records)} 条")

    item = _call_claude_single(ctx_records, target_record)
    if _record_date_key(item) != target_dt:
        logger.warning(f"AI 返回日期 {item.get('date')} 与目标 {target_dt} 不符，强制修正")
        item["date"] = f"{target_dt[:4]}-{target_dt[4:6]}-{target_dt[6:8]}"

    if not _save_analysis_to_db(target_dt, item):
        logger.error(f"{target_dt} 存库失败")
        return "failed"
    logger.info(f"{target_dt} 周期研判已存库")
    return "saved"


BATCH_SIZE = 5  # 每批处理的记录数


def run_batch_emotion_analysis(records: list, force_mode: str = "missing") -> dict:
    """离线批量生成周期研判。force_mode: missing | recent | all"""
    if not records or not isinstance(records, list):
        raise ValueError("records 必须为非空 list")

    all_dates = [r["date"].replace("-", "") for r in records]
    need_analysis_dates = set(all_dates)

    if force_mode == "all":
        pass
    elif force_mode == "recent":
        sorted_dates = sorted(all_dates)
        need_analysis_dates = set(sorted_dates[-3:])
    elif force_mode == "missing":
        from utils.db import execute_query
        placeholders = ",".join(["%s"] * len(all_dates))
        existing = execute_query(
            f"SELECT date FROM emotion_analysis_results WHERE date IN ({placeholders})",
            tuple(all_dates),
        )
        existing_dates = {row["date"] for row in existing} if existing else set()
        need_analysis_dates -= existing_dates
    else:
        raise ValueError(f"未知 force_mode: {force_mode}")

    if not need_analysis_dates:
        logger.info("所有目标日期已有分析结果，跳过 AI 调用")
        return {
            "analyzed": 0,
            "total": len(records),
            "total_batches": 0,
            "need_dates": 0,
            "message": "所有日期已有分析缓存",
        }

    records_to_analyze = []
    for i, r in enumerate(records):
        dt = r["date"].replace("-", "")
        if dt in need_analysis_dates:
            ctx_start = max(0, i - 5)
            ctx_records = records[ctx_start:i]
            for cr in ctx_records:
                cdt = cr["date"].replace("-", "")
                if not any(x["date"].replace("-", "") == cdt for x in records_to_analyze):
                    records_to_analyze.append(cr)
            if not any(x["date"].replace("-", "") == dt for x in records_to_analyze):
                records_to_analyze.append(r)

    logger.info(
        f"需分析 {len(need_analysis_dates)} 天, 含上下文共 {len(records_to_analyze)} 条记录"
    )

    total_saved = 0
    total_batches = (len(records_to_analyze) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(records_to_analyze))
        batch = records_to_analyze[start:end]

        logger.info(f"处理第 {batch_idx + 1}/{total_batches} 批 ({len(batch)} 条)")

        try:
            results = _call_claude_batch(batch)
        except Exception as e:
            logger.error(f"第 {batch_idx + 1} 批分析失败: {e}")
            continue

        for item in results:
            if not isinstance(item, dict) or "date" not in item:
                continue
            item = _calibrate_result_for_records(item, records)
            dt = item["date"].replace("-", "")
            if dt in need_analysis_dates:
                _save_analysis_to_db(dt, item)
                total_saved += 1

    logger.info(f"批量分析完成: 共 {total_batches} 批, 存库 {total_saved} 条")
    return {
        "analyzed": total_saved,
        "total": len(records),
        "total_batches": total_batches,
        "need_dates": len(need_analysis_dates),
        "message": f"已分析 {total_saved} 个交易日（分 {total_batches} 批完成）",
    }


@emotion_cycle_bp.route('/api/v1/emotion-analysis-with-storage', methods=['POST'])
@admin_required
def post_emotion_analysis_with_storage():
    """
    全量分析：接收所有交易日数据，分批调用 Claude 为每天生成分析，批量存库
    支持 force=1 刷新最近3天, force=all 强制重新分析所有日期
    """
    try:
        body = request.get_json(silent=True) or {}
        records = body.get("records")
        force_param = request.args.get("force", "0")
        if force_param == "all":
            force_mode = "all"
        elif force_param == "1":
            force_mode = "recent"
        else:
            force_mode = "missing"

        if not records or not isinstance(records, list):
            return v1_error_response(message="请在 body 中提供 records 数组")

        result = run_batch_emotion_analysis(records, force_mode=force_mode)
        return v1_success_response(data=result, message=result["message"])

    except ValueError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"情绪分析存储异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")
