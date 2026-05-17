"""
情绪周期接口模块
- GET  /api/v1/emotion-cycle     代理 StockAPI 情绪周期数据
- POST /api/v1/emotion-analysis-with-storage  管理员全量分析
- POST /api/v1/emotion-intraday-refresh       盘中刷新当日研判
"""
import json
import logging
import requests
import urllib3
from typing import Optional
from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from utils.auth_middleware import login_required, admin_required

# 抑制 StockAPI 的 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    """为已有表补充盘中研判字段"""
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
from utils.claude_client import call_claude

# 列名 → 英文 key 的映射
COL_KEY_MAP = {
    "date1": "date",
    "szbl": "rise_pct",
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
    """从 StockAPI 拉取情绪周期原始记录列表"""
    resp = requests.get(
        STOCKAPI_EMOTION_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        verify=False,
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 20000:
        raise ValueError(f"StockAPI 返回异常: code={body.get('code')}")
    data = body["data"]
    col_names = data["colNameList"]
    return [_transform_row(col_names, row) for row in data["contentList"]]


@emotion_cycle_bp.route('/api/v1/emotion-cycle', methods=['GET'])
def get_emotion_cycle():
    """代理 StockAPI 情绪周期数据并转换格式"""
    try:
        records = _fetch_emotion_records()
        return v1_success_response(data={"records": records})
    except requests.RequestException as e:
        logger.error(f"请求 StockAPI 情绪周期失败: {e}")
        return v1_error_response(message=f"请求 StockAPI 失败: {str(e)}")
    except ValueError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"处理情绪周期数据异常: {e}")
        return v1_error_response(message=f"处理数据异常: {str(e)}")


# ---------- 2. 情绪周期分析 ----------

SYSTEM_PROMPT = """你是短线情绪博弈的高手，能通过多维数据综合研判A股市场情绪周期。

## 数据字段说明
- rise_pct: 上涨比例(%)
- consec_limit: 连板家数（当日有多少只连板股）
- pressure_height: 压力高度(历史最高连板高度)
- latest_height: 最新高度(当前市场最高连板)
- big_loss_mood: 大面情绪(越高=亏钱效应越强，即跌幅>7%的前期强势股数量)
- big_profit_mood: 大肉情绪(越高=赚钱效应越强，即涨幅>7%的股票数量)
- limit_up_count: 涨停家数
- board_hit_rate: 打板成功率(%)
- limit_down_count: 跌停家数
- monster_stock: 妖股名称(当日最高连板股)
- broken_board_count: 炸板家数（封板后打开的股票数）

## 六大情绪指标交叉验证

1. **涨停/跌停数量** — 情绪基本温度计。涨停数反映赚钱效应广度，跌停数反映亏钱效应烈度。
2. **连板高度(latest_height)** — 情绪天花板。高标断板往往是情绪转折的关键信号。
3. **大面情绪(big_loss_mood)** — 亏钱效应烈度。>20=极端恐慌，10-20=较强亏钱，5-10=温和，<5=健康。
4. **大肉情绪(big_profit_mood)** — 赚钱效应强度。>80=极强（高潮），>60=强（升温），<40=弱。
5. **打板成功率(board_hit_rate)** — 打板资金盈亏。>65%=强，50-65%=温和，<40%=亏钱。
6. **炸板家数(broken_board_count)** — 市场分歧度。炸板/涨停比>0.5=分歧极大。

## 情绪周期五阶段

### 1. 冰点期
- 核心条件：涨停<30只，跌停>50只，无3板以上连板
- 辅助确认：大面情绪>20，打板成功率<40%，大肉情绪<20
- 策略：空仓。若出现板块集体抵抗可极轻仓试错龙头
- 转折信号：跌停连续2日减少 + 某方向出现2连板

### 2. 修复期
- 核心条件：涨停30-50只，跌停明显减少，出现3板股
- 辅助确认：大面情绪降至10以下，打板成功率40-50%，大肉情绪回升
- 策略：小仓位试错(2-3成)，锁定率先打出连板的方向龙头
- 转折信号：大肉情绪>50 + 出现4板股 + 连续2日涨停递增

### 3. 升温期
- 核心条件：涨停50-80只，有5板以上龙头，连板家数明显增多
- 辅助确认：大肉情绪>60，大面情绪<5，打板成功率50-65%
- 策略：加仓至5-7成，做龙头确认买点和强势板块补涨龙
- 警惕信号：打板成功率开始下降但仍>50% = 可能进入高潮末期

### 4. 高潮期
- 核心条件：涨停>100只，多只高位连板(7板+)，连板家数>15
- 辅助确认：大肉情绪>80，大面情绪极低(<3)，打板成功率>65%
- 策略：持股为主不加仓，逐步提高止盈标准，享受利润但开始警惕
- 退潮预警：打板成功率持续下降 + 高标股出现大幅分歧 + 跟风股开始掉队

### 5. 退潮期
- 核心条件：涨停骤降(较前日减少30%以上)，大面情绪急升(>15)
- 辅助确认：炸板家数远超涨停家数，打板成功率骤降，龙头断板或天地板
- 策略：减仓至1-2成或空仓，绝不追高，不抄底补跌股
- 底部信号：跌停开始缩减 + 新方向出现涨停板块效应

## 趋势判断要点
- 不要只看单日数据，要看近5-10日的趋势变化方向
- 关注"拐点"：连续上升后的首次回落，或连续下降后的首次回升
- 炸板/涨停比例是分歧度的关键指标
- 情绪周期不一定按顺序走，可能从高潮直接跳到冰点

## 推荐标的时必须结合以下三大战法筛选

### 战法一：龙头首阴低吸
适用：龙头股连续上涨后首次收阴线（首阴），是强势调整的低吸机会。
条件：①公认龙头（连板最高/辨识度最强）②第一根阴线（第二根不算）③跌幅-3%~-7%，量不超前日2倍 ④情绪非极端退潮 ⑤板块未崩。
买点：首阴日尾盘缩量企稳，或次日低开不破首阴最低价。
情绪适配：升温期/高潮期标准仓位3-4成，修复期2成，退潮期极轻仓试错。
注意：放巨量阴线(量比>3)是出货不是首阴；高位8板+首阴需更严格止损。

### 战法二：龙头爆量涨停 & 次日竞价弱转强
适用：龙头在关键位置放巨量封涨停，次日通过竞价高开+弱转强确认买入。
第一日选股条件：①龙头地位 ②成交额创10日新高，换手>10%(中小盘)或>5%(大盘) ③封死涨停(开板<3次) ④14:00前封板 ⑤板块3只+涨停。
第二日确认：竞价高开+2%~5%最佳，9:20后价格持续上移为强；开盘弱转强确认买入。
情绪适配：升温期积极参与4-5成，修复期只做龙头2成，退潮期不做。

### 战法三：首板一进二
适用：从当日涨停板中筛选次日最可能连板（一进二）的标的，次日竞价确认后买入。
首板筛选硬性条件：①属于当日主线热点板块(板块3只+涨停) ②10:30前封板为强，封板过程流畅(3波内到板，开板不超3次) ③换手率5%-15% ④流通市值50-200亿 ⑤排除一字板/T字板/尾盘偷袭板。
加分条件：封成比(封单额/成交额)>3为强(>10超强，次日高开率>70%)；低位突破平台首板；有政策/事件催化；板块内最早封板。
次日竞价确认：竞价额>前日成交额3%为强竞价；高开+3%~5%最佳；9:20后价格上移。
买入方式：竞价抢筹(激进)、开盘弱转强确认(稳健)、盘中二次封板(保守)。
仓位：单票1-2成，同时关注2-3只分散操作，单票不超3成。
情绪适配：升温期一进二成功率最高(40%+)积极参与，修复期只做主线龙头1成，退潮期不做。

推荐标的筛选逻辑：
1. 首阴机会：前几日的monster_stock如果断板了（不再是最新monster_stock），大概率是龙头首阴，这是"龙头首阴低吸"的核心标的。即使在退潮期，前期总龙头的首阴也值得关注（轻仓试错），因为龙头有资金记忆和惯性。
2. 爆量涨停机会：当日monster_stock或热门板块龙头中放巨量封板的标的，适用"爆量涨停&弱转强"战法。
3. 首板一进二机会：结合热门板块题材信息，筛选当日符合首板条件的强势股作为备选池，说明封板质量和次日竞价观察要点。
4. 每个推荐要说明适用哪个战法、为什么符合条件。
5. 即使退潮期也要给出可观察/可轻仓试错的标的，不要只推荐"空仓观望"。

请严格按以下JSON格式返回（不要返回其他内容）：
{
  "stage": "冰点期/修复期/升温期/高潮期/退潮期",
  "analysis": "详细分析：包含数据趋势解读、关键拐点、与前几日对比（300字以内）",
  "advice": "操作建议：包含仓位、方向、风控（150字以内）",
  "recommendations": [
    {"stock": "股票名称", "reason": "推荐理由（说明符合哪个战法及原因）", "position": "建议仓位如2成"}
  ]
}"""


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
    """从数据库查询盘中研判结果"""
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
    """保存盘中研判，不覆盖 analysis_result_json"""
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
            logger.error(f"更新盘中研判失败: {e}")
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
        logger.error(f"保存盘中研判失败: {e}")
        return False


def _fetch_hot_sectors() -> str:
    """获取当日热门板块题材，用于丰富分析"""
    try:
        resp = requests.get(
            STOCKAPI_GN_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "token": STOCKAPI_GN_TOKEN,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)[:2000]
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
            "请分析：\n"
            "1. 当前情绪阶段（冰点/修复/升温/高潮/退潮）\n"
            "2. 判断依据\n"
            "3. 操作建议\n"
            "4. 推荐1-2只强势连板股及仓位建议\n"
        )

        content = call_claude(
            SYSTEM_PROMPT + "\n\n" + user_prompt,
            max_tokens=2048,
            curl_timeout=60,
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

    except requests.Timeout:
        logger.error("调用 Claude API 超时")
        return v1_error_response(message="AI 分析超时，请稍后重试")
    except requests.RequestException as e:
        logger.error(f"调用 Claude API 失败: {e}")
        return v1_error_response(message=f"AI 分析请求失败: {str(e)}")
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


INTRADAY_SYSTEM_PROMPT = """你是短线情绪博弈高手。请基于【最新盘中情绪数据】输出当日盘中研判。
已给出的「周期研判」来自管理员离线全量分析，作为阶段锚点；你需结合实时数据判断盘中变化、分歧与操作节奏。

请严格按以下 JSON 返回（不要返回其他内容）：
{
  "stage": "冰点期/修复期/升温期/高潮期/退潮期",
  "analysis": "盘中变化解读：与锚定阶段的异同、关键指标、拐点信号（200字以内）",
  "advice": "盘中操作建议：仓位、节奏、风控（120字以内）",
  "recommendations": [
    {"stock": "股票名称", "reason": "理由", "position": "建议仓位"}
  ]
}
JSON 字符串值内不得包含未转义的英文双引号。"""


def _call_claude_intraday(
    current_record: dict,
    context_records: list,
    cycle_anchor: Optional[dict],
) -> dict:
    """轻量单日盘中研判"""
    import os
    import re
    import subprocess
    import tempfile

    anchor_text = "（暂无周期研判锚点，请仅依据数据判断）"
    if cycle_anchor:
        anchor_text = json.dumps(
            {
                "stage": cycle_anchor.get("stage"),
                "analysis": cycle_anchor.get("analysis"),
                "advice": cycle_anchor.get("advice"),
            },
            ensure_ascii=False,
        )

    data_text = json.dumps(
        {"context": context_records, "today": current_record},
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = (
        f"周期研判锚点：\n{anchor_text}\n\n"
        f"情绪周期数据（context 为前几日，today 为当日最新）：\n{data_text}\n\n"
        "请输出【当日】盘中研判 JSON。"
    )

    content = call_claude(
        INTRADAY_SYSTEM_PROMPT + "\n\n" + user_prompt,
        max_tokens=2048,
        curl_timeout=90,
        raise_on_error=True,
    )
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()
    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            result = json.loads(match.group())
        else:
            raise Exception("AI 返回格式异常")
    if not isinstance(result, dict):
        raise Exception("AI 返回格式异常")
    result["date"] = current_record.get("date")
    return result


@emotion_cycle_bp.route('/api/v1/emotion-intraday-cache', methods=['GET'])
@login_required
def get_emotion_intraday_cache():
    """查询盘中研判缓存"""
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
    """盘中刷新：拉最新行情 + 引用周期研判锚点 + 生成当日研判"""
    try:
        records = _fetch_emotion_records()
        if not records:
            return v1_error_response(message="未获取到情绪周期数据")

        ordered = sorted(records, key=_record_date_key)
        current_record = ordered[-1]
        current_dt = _record_date_key(current_record)
        context_start = max(0, len(ordered) - 6)
        context_records = ordered[context_start:-1]

        cycle_anchor = _get_analysis_from_db(current_dt)
        if not cycle_anchor and context_records:
            prev_dt = _record_date_key(context_records[-1])
            cycle_anchor = _get_analysis_from_db(prev_dt)

        logger.info(f"盘中刷新: {current_dt}, 上下文 {len(context_records)} 条")
        result = _call_claude_intraday(current_record, context_records, cycle_anchor)

        if not _save_intraday_to_db(current_dt, result):
            return v1_error_response(message="保存盘中研判失败")

        return v1_success_response(
            data={"intraday": result, "records": records},
            message=f"已刷新 {current_dt} 盘中研判",
        )
    except requests.RequestException as e:
        logger.error(f"盘中刷新拉取行情失败: {e}")
        return v1_error_response(message=f"请求 StockAPI 失败: {str(e)}")
    except ValueError as e:
        return v1_error_response(message=str(e))
    except Exception as e:
        logger.error(f"盘中刷新异常: {e}")
        return v1_error_response(message=f"盘中研判异常: {str(e)}")


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

        if not _save_analysis_to_db(current_dt, current_result):
            return v1_error_response(message="保存最新交易日分析失败")

        return v1_success_response(
            data=current_result,
            message=f"已刷新 {current_dt} 情绪分析"
        )

    except requests.Timeout:
        logger.error("调用 Claude API 超时")
        return v1_error_response(message="AI 分析超时，请稍后重试")
    except requests.RequestException as e:
        logger.error(f"调用 Claude API 失败: {e}")
        return v1_error_response(message=f"AI 分析请求失败: {str(e)}")
    except Exception as e:
        logger.error(f"刷新最新交易日情绪分析异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")


# ---------- 4. 全量情绪周期分析（为每一天生成分析） ----------

BATCH_ANALYSIS_PROMPT = """你是短线情绪博弈的高手，能通过多维数据综合研判A股市场情绪周期。
下面是连续多个交易日的情绪周期数据。请为【每一个交易日】都做出独立、详细的情绪分析判断。
分析时要结合该日之前的趋势（而非只看单日数据）。

## 数据字段说明
- date: 日期
- rise_pct: 上涨比例(%)
- consec_limit: 连板家数（当日有多少只连板股）
- pressure_height: 压力高度(历史最高连板高度)
- latest_height: 最新高度(当前市场最高连板)
- big_loss_mood: 大面情绪(越高=亏钱效应越强，即跌幅>7%的前期强势股数量)
- big_profit_mood: 大肉情绪(越高=赚钱效应越强，即涨幅>7%的股票数量)
- limit_up_count: 涨停家数
- board_hit_rate: 打板成功率(%)
- limit_down_count: 跌停家数
- monster_stock: 妖股名称(当日最高连板股)
- broken_board_count: 炸板家数（封板后打开的股票数）

## 六大情绪指标交叉验证
1. **涨停/跌停数量** — 情绪基本温度计。涨停数反映赚钱效应广度，跌停数反映亏钱效应烈度。
2. **连板高度(latest_height)** — 情绪天花板。高标断板往往是情绪转折的关键信号。
3. **大面情绪(big_loss_mood)** — 亏钱效应烈度。>20=极端恐慌，10-20=较强亏钱，5-10=温和，<5=健康。
4. **大肉情绪(big_profit_mood)** — 赚钱效应强度。>80=极强（高潮），>60=强（升温），<40=弱。
5. **打板成功率(board_hit_rate)** — 打板资金盈亏。>65%=强，50-65%=温和，<40%=亏钱。
6. **炸板家数(broken_board_count)** — 市场分歧度。炸板/涨停比>0.5=分歧极大。

## 情绪周期五阶段（含仓位策略）

### 1. 冰点期
- 核心条件：涨停<30只，跌停>50只，无3板以上连板
- 辅助确认：大面情绪>20，打板成功率<40%，大肉情绪<20
- 仓位策略：空仓或极轻仓(0-1成)。若出现板块集体抵抗可极轻仓试错龙头
- 转折信号：跌停连续2日减少 + 某方向出现2连板

### 2. 修复期
- 核心条件：涨停30-50只，跌停明显减少，出现3板股
- 辅助确认：大面情绪降至10以下，打板成功率40-50%，大肉情绪回升
- 仓位策略：小仓位试错(2-3成)，锁定率先打出连板的方向龙头
- 转折信号：大肉情绪>50 + 出现4板股 + 连续2日涨停递增

### 3. 升温期
- 核心条件：涨停50-80只，有5板以上龙头，连板家数明显增多
- 辅助确认：大肉情绪>60，大面情绪<5，打板成功率50-65%
- 仓位策略：加仓至5-7成，做龙头确认买点和强势板块补涨龙
- 警惕信号：打板成功率开始下降但仍>50% = 可能进入高潮末期

### 4. 高潮期
- 核心条件：涨停>100只，多只高位连板(7板+)，连板家数>15
- 辅助确认：大肉情绪>80，大面情绪极低(<3)，打板成功率>65%
- 仓位策略：持股为主不加仓(维持5-7成)，逐步提高止盈标准，享受利润但开始警惕
- 退潮预警：打板成功率持续下降 + 高标股出现大幅分歧 + 跟风股开始掉队

### 5. 退潮期
- 核心条件：涨停骤降(较前日减少30%以上)，大面情绪急升(>15)
- 辅助确认：炸板家数远超涨停家数，打板成功率骤降，龙头断板或天地板
- 仓位策略：减仓至1-2成或空仓，绝不追高，不抄底补跌股
- 底部信号：跌停开始缩减 + 新方向出现涨停板块效应

## 趋势判断要点
- 不要只看单日数据，要看近5-10日的趋势变化方向
- 关注"拐点"：连续上升后的首次回落，或连续下降后的首次回升
- 炸板/涨停比例是分歧度的关键指标
- 情绪周期不一定按顺序走，可能从高潮直接跳到冰点

## 推荐标的时必须结合以下三大战法筛选

### 战法一：龙头首阴低吸
适用：龙头股连续上涨后首次收阴线（首阴），是强势调整的低吸机会。
条件：①公认龙头②第一根阴线③跌幅-3%~-7%④情绪非极端退潮⑤板块未崩。
情绪适配：升温/高潮期3-4成，修复期2成，退潮期极轻仓试错。

### 战法二：龙头爆量涨停 & 次日竞价弱转强
适用：龙头在关键位置放巨量封涨停，次日通过竞价高开+弱转强确认买入。
情绪适配：升温期4-5成，修复期只做龙头2成，退潮期不做。

### 战法三：首板一进二
适用：从当日涨停板中筛选次日最可能连板的标的。
情绪适配：升温期积极参与(成功率40%+)，修复期只做主线龙头1成，退潮期不做。

推荐标的筛选逻辑：
1. 首阴机会：前几日的monster_stock断板了，大概率是龙头首阴。即使退潮期前期总龙头的首阴也值得关注（轻仓试错）。
2. 爆量涨停机会：当日monster_stock或热门板块龙头中放巨量封板的标的。
3. 首板一进二机会：结合热门板块，筛选当日符合首板条件的强势股。
4. 每个推荐要说明适用哪个战法、为什么符合条件。
5. 即使退潮/冰点期也要给出可观察/可轻仓试错的标的，不要只推荐"空仓观望"。

请严格按以下JSON格式返回（不要返回其他内容）：
[
  {
    "date": "2026-03-17",
    "stage": "冰点期/修复期/升温期/高潮期/退潮期",
    "analysis": "详细分析：包含数据趋势解读、关键拐点、与前几日对比、六大指标交叉验证（300字以内）",
    "advice": "操作建议：包含仓位比例、方向、风控、注意事项（150字以内）",
    "recommendations": [
      {"stock": "股票名称", "reason": "推荐理由（说明符合哪个战法及原因）", "position": "建议仓位如2成"}
    ]
  },
  ...
]
每个交易日一条，按日期从旧到新排列。每天的分析都要详细、有独立见解，不要用模板化的泛泛之词。
重要：所有JSON字符串值中不得包含英文双引号(")，请用中文引号（""）或书名号（《》）代替。"""


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

    content = call_claude(
        BATCH_ANALYSIS_PROMPT + "\n\n" + user_prompt,
        max_tokens=16000,
        curl_timeout=180,
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


def analyze_one_date(target_dt: str, all_records: list, force: bool = False) -> str:
    """为单个交易日生成周期研判并存库（幂等、不依赖 HTTP）。

    返回 'skipped' | 'saved' | 'failed'。
    - force=False 且 DB 已有该日 → 'skipped'
    - 取 target 当日 + 之前 5 个交易日作趋势上下文
    - 调 _call_claude_batch，从返回中取 target 当日结果并存库
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

    ctx_start = max(0, idx - 5)
    batch = ordered[ctx_start:idx + 1]
    logger.info(f"分析 {target_dt}，上下文 {len(batch)} 条")

    results = _call_claude_batch(batch)
    item = next(
        (
            x for x in results
            if isinstance(x, dict) and _record_date_key(x) == target_dt
        ),
        None,
    )
    if item is None:
        logger.error(f"AI 返回未包含 {target_dt}")
        return "failed"

    if not _save_analysis_to_db(target_dt, item):
        logger.error(f"{target_dt} 存库失败")
        return "failed"
    logger.info(f"{target_dt} 周期研判已存库")
    return "saved"


BATCH_SIZE = 10  # 每批处理的记录数


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
        force_recent = force_param == "1"    # 刷新最近3天
        force_all = force_param == "all"     # 全部重刷

        if not records or not isinstance(records, list):
            return v1_error_response(message="请在 body 中提供 records 数组")

        # 1. 确定哪些日期需要分析
        all_dates = [r["date"].replace("-", "") for r in records]
        need_analysis_dates = set(all_dates)

        if force_all:
            # 全部重刷
            pass
        elif force_recent:
            # 只刷新最近3天
            sorted_dates = sorted(all_dates)
            recent_dates = set(sorted_dates[-3:])
            need_analysis_dates = recent_dates
        else:
            # 默认模式：只分析尚无缓存的日期
            from utils.db import execute_query
            placeholders = ",".join(["%s"] * len(all_dates))
            existing = execute_query(
                f"SELECT date FROM emotion_analysis_results WHERE date IN ({placeholders})",
                tuple(all_dates),
            )
            existing_dates = {row["date"] for row in existing} if existing else set()
            need_analysis_dates -= existing_dates

            if not need_analysis_dates:
                logger.info("所有日期已有分析结果，跳过 AI 调用")
                return v1_success_response(data={"analyzed": 0, "total": len(all_dates)},
                                           message="所有日期已有分析缓存")

        # 2. 筛选需要分析的记录（但始终带上前几天作为趋势上下文）
        records_to_analyze = []
        for i, r in enumerate(records):
            dt = r["date"].replace("-", "")
            if dt in need_analysis_dates:
                # 向前带最多5天作为上下文
                ctx_start = max(0, i - 5)
                ctx_records = records[ctx_start:i]
                # 加入上下文（去重）
                for cr in ctx_records:
                    cdt = cr["date"].replace("-", "")
                    if not any(x["date"].replace("-", "") == cdt for x in records_to_analyze):
                        records_to_analyze.append(cr)
                if not any(x["date"].replace("-", "") == dt for x in records_to_analyze):
                    records_to_analyze.append(r)

        logger.info(f"需分析 {len(need_analysis_dates)} 天, 含上下文共 {len(records_to_analyze)} 条记录")

        # 3. 分批调用 Claude
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

            # 存库（只存需要分析的日期，跳过上下文日期）
            for item in results:
                if not isinstance(item, dict) or "date" not in item:
                    continue
                dt = item["date"].replace("-", "")
                if dt in need_analysis_dates:
                    _save_analysis_to_db(dt, item)
                    total_saved += 1

        logger.info(f"全量分析完成: 共 {total_batches} 批, 存库 {total_saved} 条")
        return v1_success_response(
            data={"analyzed": total_saved, "total": len(records)},
            message=f"已分析 {total_saved} 个交易日（分 {total_batches} 批完成）"
        )

    except requests.Timeout:
        logger.error("调用 Claude API 超时")
        return v1_error_response(message="AI 分析超时，请稍后重试")
    except requests.RequestException as e:
        logger.error(f"调用 Claude API 失败: {e}")
        return v1_error_response(message=f"AI 分析请求失败: {str(e)}")
    except Exception as e:
        logger.error(f"情绪分析存储异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")
