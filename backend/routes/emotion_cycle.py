"""
情绪周期接口模块
- GET  /api/v1/emotion-cycle     代理 StockAPI 情绪周期数据
- POST /api/v1/emotion-analysis  调用 Claude 分析情绪周期阶段
"""
import json
import logging
import requests
import urllib3
from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response

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


# 模块加载时初始化
_init_emotion_analysis_table()


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
CLAUDE_API_URL = "https://token.kalowave.com/v1/chat/completions"
CLAUDE_API_KEY = "sk-9bs6AtWPA7p0vs6Rnz0lxP6VOpufoWSQGV8MAS0i3ncqMGB7"
CLAUDE_MODEL = "claude-opus-4-7"

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

@emotion_cycle_bp.route('/api/v1/emotion-cycle', methods=['GET'])
def get_emotion_cycle():
    """代理 StockAPI 情绪周期数据并转换格式"""
    try:
        resp = requests.get(
            STOCKAPI_EMOTION_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            verify=False,
            timeout=15,
        )
        resp.raise_for_status()
        body = resp.json()

        if body.get("code") != 20000:
            return v1_error_response(
                message=f"StockAPI 返回异常: code={body.get('code')}"
            )

        data = body["data"]
        col_names = data["colNameList"]
        records = [_transform_row(col_names, row) for row in data["contentList"]]

        return v1_success_response(data={"records": records})

    except requests.RequestException as e:
        logger.error(f"请求 StockAPI 情绪周期失败: {e}")
        return v1_error_response(message=f"请求 StockAPI 失败: {str(e)}")
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

        # 调用 Claude API（OpenAI 兼容格式）— 用 subprocess curl 避免 eventlet 干扰
        import subprocess, tempfile
        payload = json.dumps({
            "model": CLAUDE_MODEL,
            "messages": [
                {"role": "user", "content": SYSTEM_PROMPT + "\n\n" + user_prompt},
            ],
            "max_tokens": 2048,
        })
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(payload)
            payload_file = f.name
        try:
            proc = subprocess.run(
                [
                    "curl", "-s", "--max-time", "60",
                    CLAUDE_API_URL,
                    "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
                    "-H", "Content-Type: application/json",
                    "-d", f"@{payload_file}",
                ],
                capture_output=True, text=True, timeout=65,
            )
            import os
            os.unlink(payload_file)
            if proc.returncode != 0:
                raise Exception(f"curl 失败 (exit {proc.returncode}): {proc.stderr[:500]}")
            claude_body = json.loads(proc.stdout)
            if "error" in claude_body:
                raise Exception(f"Claude API 错误: {claude_body['error']}")
        except subprocess.TimeoutExpired:
            raise Exception("Claude API 调用超时(60s)")

        # 提取回复文本
        content = (
            claude_body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
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
    if db_result:
        return v1_success_response(data=db_result)
    return v1_success_response(data=None)


# ---------- 4. 情绪周期分析 + 数据库存储 ----------

@emotion_cycle_bp.route('/api/v1/emotion-analysis-with-storage', methods=['POST'])
def post_emotion_analysis_with_storage():
    """
    接收情绪周期数据，查库或调用 Claude 分析，结果存入数据库
    支持 force=1 参数强制重新分析
    """
    try:
        body = request.get_json(silent=True) or {}
        records = body.get("records")
        dt = body.get("date")  # 用户选中的分析日期，格式 YYYYMMDD
        force = request.args.get("force", "0") == "1"

        if not records or not isinstance(records, list):
            return v1_error_response(message="请在 body 中提供 records 数组")
        if not dt:
            from datetime import datetime
            dt = datetime.now().strftime("%Y%m%d")

        # 1. 尝试从数据库查询
        if not force:
            db_result = _get_analysis_from_db(dt)
            if db_result:
                logger.info(f"从数据库返回已有分析结果 (date={dt})")
                return v1_success_response(data=db_result, message="(来自数据库缓存)")

        # 2. 调用 Claude API 进行分析
        hot_sectors = _fetch_hot_sectors()
        data_text = json.dumps(records, ensure_ascii=False, indent=2)
        user_prompt = (
            f"以下是最近的情绪周期数据（从旧到新），截止日期 {dt}：\n{data_text}\n\n"
            f"当日热门板块题材信息：\n{hot_sectors}\n\n"
            "请分析：\n"
            "1. 当前情绪阶段（冰点/修复/升温/高潮/退潮）\n"
            "2. 判断依据\n"
            "3. 操作建议\n"
            "4. 推荐1-2只强势连板股及仓位建议\n"
        )

        import subprocess, tempfile
        payload = json.dumps({
            "model": CLAUDE_MODEL,
            "messages": [
                {"role": "user", "content": SYSTEM_PROMPT + "\n\n" + user_prompt},
            ],
            "max_tokens": 2048,
        })
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(payload)
            payload_file = f.name
        try:
            proc = subprocess.run(
                [
                    "curl", "-s", "--max-time", "60",
                    CLAUDE_API_URL,
                    "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
                    "-H", "Content-Type: application/json",
                    "-d", f"@{payload_file}",
                ],
                capture_output=True, text=True, timeout=65,
            )
            import os
            os.unlink(payload_file)
            if proc.returncode != 0:
                raise Exception(f"curl 失败 (exit {proc.returncode}): {proc.stderr[:500]}")
            claude_body = json.loads(proc.stdout)
            if "error" in claude_body:
                raise Exception(f"Claude API 错误: {claude_body['error']}")
        except subprocess.TimeoutExpired:
            raise Exception("Claude API 调用超时(60s)")

        # 3. 解析 Claude 返回
        content = (
            claude_body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
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

        # 4. 保存到数据库
        _save_analysis_to_db(dt, result)

        return v1_success_response(data=result, message="(新分析结果)")

    except requests.Timeout:
        logger.error("调用 Claude API 超时")
        return v1_error_response(message="AI 分析超时，请稍后重试")
    except requests.RequestException as e:
        logger.error(f"调用 Claude API 失败: {e}")
        return v1_error_response(message=f"AI 分析请求失败: {str(e)}")
    except Exception as e:
        logger.error(f"情绪分析存储异常: {e}")
        return v1_error_response(message=f"情绪分析异常: {str(e)}")
