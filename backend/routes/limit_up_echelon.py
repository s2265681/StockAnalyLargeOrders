"""
涨停板梯队接口模块
- GET  /api/v1/limit-up-echelon              获取当日涨停板梯队数据
  支持 ?analysis=1 触发异步 AI 分组（有缓存直接返回，无缓存后台执行）
- GET  /api/v1/limit-up-echelon/ai-status    轮询 AI 分组结果
- POST /api/v1/limit-up-echelon/themes       Claude 题材/分组（与 GET analysis 共用解析逻辑）
"""
import json
import logging
import os
import subprocess
import tempfile
import time
import threading
from collections import Counter
from datetime import datetime

from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.theme_service import (
    get_recent_tags,
    get_tags_by_date,
    get_limit_up_stocks_by_date,
    save_ai_grouping_result,
    load_echelon_from_db,
)

logger = logging.getLogger(__name__)

limit_up_echelon_bp = Blueprint('limit_up_echelon', __name__)

CLAUDE_API_URL = os.environ.get(
    "CLAUDE_API_URL", "https://token.kalowave.com/v1/chat/completions"
)
CLAUDE_API_KEY = os.environ.get(
    "CLAUDE_API_KEY",
    "sk-9bs6AtWPA7p0vs6Rnz0lxP6VOpufoWSQGV8MAS0i3ncqMGB7",
)
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# (date, codes_tuple) -> (unix_ts, {"labels": code -> group_label, "reasons": label -> reason, "leaders": label -> [leader]})
_echelon_ai_cache = {}
AI_CACHE_TTL_SEC = int(os.environ.get("LIMIT_UP_AI_CACHE_SEC", "600"))
AI_CACHE_VERSION = "leaders-v2"

# 后台 AI 任务状态: cache_key -> {"status": "pending"|"done"|"error", "result": dict}
_ai_task_status = {}
_ai_task_lock = threading.Lock()

# ---------- Claude 分组（相近概念合并为同一 group_label）----------

GROUP_PROMPT = """你是A股超短题材复盘专家。下面是同一交易日涨停股列表，包含同花顺热股的概念、标题和分析。

任务：先归纳当天 6-9 个「最强风口大标签」，再把每只涨停股归入其中一个大标签。

要求：
1. 大标签必须是市场复盘常用的大主线，2-8字左右，例如：机器人、氟化工、大消费、半导体产业链、电力、AI应用、体育产业。
2. 禁止输出过细标签，必须用市场通用的大主线名称。具体合并规则（严格执行）：
   - 「人形机器人/减速器/执行器/PCB/光模块/传感器」→ 合并为「机器人」
   - 「陶瓷材料/先进陶瓷/半导体陶瓷材料/光刻胶/电子化学品/先进封装/芯片/半导体设备」→ 合并为「半导体」
   - 「短剧/传媒/游戏/AI营销/影视/网红经济」→ 合并为「传媒短剧」或「AI应用」
   - 「食品/白酒/家电/零售/旅游」→ 合并为「消费」
   如果某个细分标签在上面有明确归属，绝对不能单独作为大标签输出。
3. **优先使用以下已有标签**（来自近期历史数据库），如果今天的涨停股能匹配这些标签就直接使用，不要创造语义相近的新标签：
{known_tags}
   如果某些已有标签今天没有对应的涨停股，不需要输出。如果出现全新的主线，可以创建新标签。
4. 每只股票必须只属于一个大标签。归类时重点参考同花顺给出的概念标签和涨停标题，找到该票与哪个大标签关联最紧密。
5. **「其他概念」必须控制在 3 只以内**。只有完全无法与任何大标签关联的个股才放「其他概念」。如果某只票的同花顺概念、行业、涨停标题中能找到与任一大标签的关联（哪怕是次要关联），就必须归入那个大标签，而非「其他概念」。宁可放进关联性较弱的大标签，也不要轻易扔进「其他概念」。
6. 每个大标签必须给一句「涨停原因」，像短线复盘语言，概括该主题当天爆发原因，例如"特斯拉Optimus Gen-3启动量产，Figure机器人连续工作30小时"。
7. 每个大标签选出 1-2 个「板块龙头」，优先只选 1 个。按顺序输出：最正宗、最有带动性的先锋龙放第一；如需要，再给一个容量/辨识度最高的中军放第二。优先考虑连板高度、封板强度、同花顺热度、市场辨识度、题材正宗性和带动性。
8. 按成分股数量从高到低输出 groups，「其他概念」放最后。

股票列表（每行：代码 名称 行业 连板 同花顺热度 同花顺标题 同花顺概念 同花顺分析）：
{stock_list}

只输出一个 JSON 对象，不要 markdown，不要解释文字，格式严格为：
{{"groups":[{{"label":"机器人","reason":"涨停原因","leaders":[{{"code":"000000","name":"示例","role":"先锋龙","reason":"龙头理由"}}],"stocks":[{{"code":"000000","name":"示例","why":"归类依据"}}]}}],"stock_groups":{{"000000":"机器人"}}}}
股票代码必须与输入一致（6位数字字符串）。"""

THEME_PROMPT = GROUP_PROMPT


def _fetch_ths_hot_stocks() -> tuple:
    """获取同花顺最强风口热股数据，返回 (list, dict_by_code)"""
    try:
        urls = [
            "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock?stock_type=a&type=hour&list_type=normal",
            "https://eq.10jqka.com.cn/open/api/hot_list/v1/hot_stock/a/hour/data.txt",
        ]
        proc = subprocess.run(
            [
                "curl", "-s", "--max-time", "10",
                urls[0],
                "-H", "User-Agent: Mozilla/5.0",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return [], {}
        data = json.loads(proc.stdout)
        if data.get("status_code") != 0:
            proc = subprocess.run(
                [
                    "curl", "-s", "--max-time", "10",
                    urls[1],
                    "-H", "User-Agent: Mozilla/5.0",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                return [], {}
            data = json.loads(proc.stdout)
        if data.get("status_code") == 0:
            stock_list = data.get("data", {}).get("stock_list", [])
            hot_map = {}
            for item in stock_list:
                code = item.get("code", "")
                tags = item.get("tag", {})
                concept_tags = tags.get("concept_tag", []) if isinstance(tags, dict) else []
                hot_map[code] = {
                    "rank": item.get("order", 0),
                    "name": item.get("name", ""),
                    "analyse": item.get("analyse", ""),
                    "analyse_title": item.get("analyse_title", ""),
                    "concept_tags": concept_tags,
                    "popularity_tag": tags.get("popularity_tag", "") if isinstance(tags, dict) else "",
                }
            return stock_list, hot_map
        return [], {}
    except Exception as e:
        logger.warning(f"获取同花顺热股失败: {e}")
        return [], {}


def _format_amount(val):
    """格式化金额为亿/万"""
    if not val:
        return "--"
    v = float(val)
    if v >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if v >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.0f}"


def _build_ths_hot_tag(ths_info: dict) -> str:
    """同花顺热股第二标签：优先风口人气标签，否则取概念标签首项"""
    if not ths_info:
        return ""
    pop = (ths_info.get("popularity_tag") or "").strip()
    if pop:
        return pop
    tags = ths_info.get("concept_tags") or []
    if isinstance(tags, list) and tags:
        t0 = tags[0]
        return str(t0).strip() if t0 else ""
    return ""


def _parse_grouping_json(content: str) -> dict:
    """
    解析 Claude 返回：支持
    {"groups": [{"label": "机器人", "reason": "...", "leaders": [{...}], "stocks": [{"code": "000001"}]}]}
    {"groups": {"000001": {"group_label": "机器人"}, ...}}
    或旧版 {"themes": {"000001": "机器人", ...}}
    返回 {"labels": code -> group_label, "reasons": group_label -> reason, "leaders": group_label -> [leader]}
    """
    import re
    if not content or not content.strip():
        return {}
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        clean = clean.rsplit("```", 1)[0].strip()
    result = None
    try:
        result = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                return {}
    if not result or not isinstance(result, dict):
        return {}

    labels = {}
    reasons = {}
    leaders = {}
    groups = result.get("groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            label = str(group.get("label") or group.get("theme") or "").strip()
            if not label:
                continue
            reason = str(group.get("reason") or "").strip()
            if reason:
                reasons[label] = reason
            raw_leaders = group.get("leaders")
            if raw_leaders is None:
                raw_leaders = [group.get("leader")] if group.get("leader") else []
            elif not isinstance(raw_leaders, list):
                raw_leaders = [raw_leaders]
            parsed_leaders = []
            for leader in raw_leaders[:2]:
                if isinstance(leader, dict):
                    leader_code = str(leader.get("code", "")).strip()
                    if leader_code:
                        parsed_leaders.append({
                            "code": leader_code,
                            "name": str(leader.get("name") or "").strip(),
                            "role": str(leader.get("role") or "").strip(),
                            "reason": str(leader.get("reason") or "").strip(),
                        })
                elif isinstance(leader, str) and leader.strip():
                    parsed_leaders.append({
                        "code": leader.strip(),
                        "name": "",
                        "role": "",
                        "reason": "",
                    })
            if parsed_leaders:
                leaders[label] = parsed_leaders
            for item in group.get("stocks") or []:
                if isinstance(item, dict):
                    code = str(item.get("code", "")).strip()
                else:
                    code = str(item).strip()
                if code:
                    labels[code] = label
    elif isinstance(groups, dict):
        for code, v in groups.items():
            code = str(code).strip()
            if not code:
                continue
            if isinstance(v, dict):
                label = (v.get("group_label") or v.get("theme") or "").strip()
                reason = (v.get("reason") or "").strip()
            else:
                label = str(v).strip()
                reason = ""
            if label:
                labels[code] = label
                if reason:
                    reasons[label] = reason
    elif "themes" in result and isinstance(result["themes"], dict):
        for code, v in result["themes"].items():
            code = str(code).strip()
            if not code:
                continue
            label = str(v).strip() if not isinstance(v, dict) else (
                (v.get("group_label") or v.get("theme") or "")).strip()
            if label:
                labels[code] = label

    stock_groups = result.get("stock_groups")
    if isinstance(stock_groups, dict):
        for code, label in stock_groups.items():
            code = str(code).strip()
            label = str(label).strip()
            if code and label:
                labels.setdefault(code, label)

    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def _claude_group_labels_for_stocks(stocks: list) -> dict:
    """对涨停列表调用 Claude，返回 labels/reasons 结构
    优先从数据库获取近期已有标签，注入 prompt 让 AI 复用
    """
    if not stocks or not CLAUDE_API_KEY:
        return {}

    # 获取最近 1-2 天的已知标签
    known_tags_text = "   （暂无历史标签）"
    try:
        recent_tags = get_recent_tags(days=2)
        if recent_tags:
            tag_names = [t["tag_name"] for t in recent_tags if t.get("tag_name")]
            if tag_names:
                known_tags_text = "   " + "、".join(tag_names)
    except Exception as e:
        logger.warning(f"获取历史标签失败，跳过: {e}")

    lines = []
    for s in stocks:
        ths_tags = s.get("ths_concept_tags") or []
        tag_str = ",".join(str(t) for t in ths_tags if t) if ths_tags else ""
        lines.append(
            f"{s['code']} {s['name']} 行业:{s.get('industry', '')} "
            f"连板:{s.get('boards', 1)} 同花顺热度:{s.get('ths_rank') or '-'} "
            f"同花顺标题:{s.get('ths_analyse_title') or ''} "
            f"同花顺概念:[{tag_str}] 同花顺分析:{(s.get('ths_analyse') or '')[:260]}"
        )
    prompt = GROUP_PROMPT.replace("{stock_list}", "\n".join(lines)).replace("{known_tags}", known_tags_text)
    content = _call_claude(prompt, max_tokens=8192)
    parsed = _parse_grouping_json(content)
    if not parsed.get("labels"):
        logger.warning("Claude 分组解析为空，原始长度=%s", len(content or ""))
    return parsed


def _apply_group_labels(stocks: list, group_result: dict) -> tuple:
    """
    将分组写入 stock：group_label / theme / theme_count / group_count
    返回 theme_ranking 列表
    """
    label_by_code = (group_result or {}).get("labels") or {}
    reason_by_label = (group_result or {}).get("reasons") or {}
    leader_by_label = (group_result or {}).get("leaders") or {}
    if not label_by_code:
        return []
    counter = Counter(label_by_code.values())
    for s in stocks:
        code = s.get("code", "")
        label = (label_by_code.get(code) or "").strip() or (s.get("industry") or "其他")
        s["group_label"] = label
        s["theme"] = label
        cnt = counter.get(label, 1)
        s["theme_count"] = cnt
        s["group_count"] = cnt
        s["theme_reason"] = reason_by_label.get(label, "")
        leaders = leader_by_label.get(label) or []
        primary_leader = leaders[0] if leaders else {}
        s["theme_leaders"] = leaders
        s["theme_leader_code"] = primary_leader.get("code", "")
        s["theme_leader_name"] = primary_leader.get("name", "")
        s["theme_leader_reason"] = primary_leader.get("reason", "")
        s["is_theme_leader"] = any(item.get("code") == code for item in leaders)
    return [
        {
            "theme": t,
            "count": c,
            "reason": reason_by_label.get(t, ""),
            "leader": (leader_by_label.get(t, []) or [{}])[0],
            "leaders": leader_by_label.get(t, []),
        }
        for t, c in counter.most_common()
    ]


def _call_claude(prompt: str, max_tokens: int = 4096) -> str:
    """调用Claude API（通过subprocess curl避免eventlet干扰）"""
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    })
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(payload)
        payload_file = f.name
    try:
        proc = subprocess.run(
            [
                "curl", "-s", "--max-time", "90",
                CLAUDE_API_URL,
                "-H", f"Authorization: Bearer {CLAUDE_API_KEY}",
                "-H", "Content-Type: application/json",
                "-d", f"@{payload_file}",
            ],
            capture_output=True, text=True, timeout=95,
        )
        os.unlink(payload_file)
        if proc.returncode != 0:
            return ""
        body = json.loads(proc.stdout)
        if "error" in body:
            logger.error(f"Claude API 错误: {body['error']}")
            return ""
        return (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
    except Exception as e:
        logger.error(f"Claude API调用失败: {e}")
        return ""


def _smart_group_stocks(stocks: list, dt: str) -> dict:
    """智能分组：先用库里已有标签（含手动改动）匹配，剩余的才调 AI
    返回与 _claude_group_labels_for_stocks 相同的 group_result 结构
    """
    # 1. 从库里读取当天已有的 stock -> tag 映射（含手动修改）
    db_stocks = get_limit_up_stocks_by_date(dt)
    db_code_to_tag = {s["code"]: s["tag_name"] for s in db_stocks if s.get("tag_name")}

    # 从库里读取当天标签和原因
    db_tags = get_tags_by_date(dt)
    db_reasons = {t["tag_name"]: t.get("reason", "") for t in db_tags}

    # 1.5 检测标签重命名：如果 limit_up_stocks 里的 tag 不在 theme_tags 里，
    # 说明用户改了 theme_tags 的名字，需要同步 limit_up_stocks
    valid_tag_names = set(t["tag_name"] for t in db_tags)
    if db_code_to_tag and valid_tag_names:
        old_tags_in_stocks = set(db_code_to_tag.values()) - valid_tag_names - {"", "其他概念"}
        if old_tags_in_stocks:
            from utils.db import execute_write as _db_write
            for old_tag in old_tags_in_stocks:
                # 尝试通过 reason 匹配找到新标签名
                old_reason = ""
                for s in db_stocks:
                    if s.get("tag_name") == old_tag:
                        # 在 theme_tags 里找 reason 相近的新标签
                        break
                # 找不到对应的新标签，把这些股票的标签清空让 AI 重新分类
                logger.info(f"检测到失效标签 '{old_tag}'，同步清空 limit_up_stocks 对应记录")
                _db_write(
                    "UPDATE limit_up_stocks SET tag_name='' WHERE date=%s AND tag_name=%s",
                    (dt, old_tag),
                )
            # 刷新 db_code_to_tag
            for code, tag in list(db_code_to_tag.items()):
                if tag in old_tags_in_stocks:
                    db_code_to_tag[code] = ""

    # 2. 用库里标签给当前股票分类
    labels = {}
    unmatched = []
    for s in stocks:
        code = s.get("code", "")
        if code in db_code_to_tag and db_code_to_tag[code]:
            labels[code] = db_code_to_tag[code]
        else:
            unmatched.append(s)

    logger.info(f"智能分组: 库里匹配 {len(labels)} 只, 未匹配 {len(unmatched)} 只")

    # 3. 未匹配的调 AI（传入已知标签作为参考）
    ai_result = {}
    if unmatched:
        ai_result = _claude_group_labels_for_stocks(unmatched)
        if ai_result.get("labels"):
            labels.update(ai_result["labels"])

    # 4. 合并 reasons 和 leaders
    reasons = dict(db_reasons)
    if ai_result.get("reasons"):
        reasons.update(ai_result["reasons"])

    # 从 limit_up_stocks 读龙头（is_leader=1 的记录）
    leaders = {}
    for s in db_stocks:
        if s.get("is_leader") and s.get("tag_name"):
            tag = s["tag_name"]
            if tag not in leaders:
                leaders[tag] = []
            leaders[tag].append({
                "code": s["code"], "name": s["name"],
                "role": s.get("leader_role", ""), "reason": s.get("leader_reason", ""),
            })
    if ai_result.get("leaders"):
        for tag, ai_leaders in ai_result["leaders"].items():
            if tag not in leaders:
                leaders[tag] = ai_leaders

    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def _bg_ai_grouping(stocks: list, cache_key: tuple):
    """后台线程：执行智能分组（优先库里标签）并写入缓存 + 数据库"""
    try:
        dt = cache_key[1] if len(cache_key) >= 2 else datetime.now().strftime("%Y%m%d")
        group_result = _smart_group_stocks(stocks, dt)
        if group_result.get("labels"):
            # 先应用分组到 stocks 上（补充 group_label 等字段）
            _apply_group_labels(stocks, group_result)

            _echelon_ai_cache[cache_key] = (time.time(), dict(group_result))
            with _ai_task_lock:
                _ai_task_status[cache_key] = {"status": "done", "result": group_result}

            # 写入数据库
            try:
                save_ai_grouping_result(dt, stocks, group_result)
                logger.info(f"智能分组结果已写入数据库 (date={dt})")
            except Exception as db_err:
                logger.error(f"分组写入数据库失败: {db_err}", exc_info=True)
        else:
            with _ai_task_lock:
                _ai_task_status[cache_key] = {"status": "error", "result": {}}
    except Exception as e:
        logger.error(f"后台分组失败: {e}", exc_info=True)
        with _ai_task_lock:
            _ai_task_status[cache_key] = {"status": "error", "result": {}}


def _build_stocks_from_df(df, ths_hot_map: dict) -> list:
    """从 DataFrame 构建股票列表"""
    stocks = []
    for _, row in df.iterrows():
        code = str(row.get('代码', ''))
        turnover = float(row.get('成交额', 0))
        seal_amount = float(row.get('封板资金', 0))
        seal_ratio = round(seal_amount / turnover, 2) if turnover > 0 else 0
        ths_info = ths_hot_map.get(code, {})
        stocks.append({
            "code": code,
            "name": str(row.get('名称', '')),
            "boards": int(row.get('连板数', 1)),
            "price": float(row.get('最新价', 0)),
            "change_pct": round(float(row.get('涨跌幅', 0)), 2),
            "seal_amount": seal_amount,
            "seal_amount_text": _format_amount(seal_amount),
            "seal_ratio": seal_ratio,
            "turnover": turnover,
            "turnover_text": _format_amount(turnover),
            "float_mv": float(row.get('流通市值', 0)),
            "float_mv_text": _format_amount(row.get('流通市值', 0)),
            "turnover_rate": round(float(row.get('换手率', 0)), 2),
            "first_time": str(row.get('首次封板时间', '')),
            "last_time": str(row.get('最后封板时间', '')),
            "break_count": int(row.get('炸板次数', 0)),
            "industry": str(row.get('所属行业', '')),
            "zt_stat": str(row.get('涨停统计', '')),
            "ths_rank": ths_info.get("rank", 0),
            "ths_analyse": ths_info.get("analyse", ""),
            "ths_analyse_title": ths_info.get("analyse_title", ""),
            "ths_concept_tags": ths_info.get("concept_tags", []),
            "ths_popularity": ths_info.get("popularity_tag", ""),
            "ths_hot_tag": _build_ths_hot_tag(ths_info),
            "group_label": "",
            "group_count": 0,
            "theme": "",
            "theme_count": 0,
            "theme_reason": "",
            "theme_leader_code": "",
            "theme_leader_name": "",
            "theme_leader_reason": "",
            "theme_leaders": [],
            "is_theme_leader": False,
        })
    return stocks


def _build_echelon_response(stocks, ths_hot_list, dt, theme_ranking, ai_meta):
    """构建最终响应数据"""
    echelon_map = {}
    for s in stocks:
        echelon_map.setdefault(s["boards"], []).append(s)
    echelon_list = [
        {
            "boards": boards,
            "count": len(group),
            "stocks": sorted(group, key=lambda x: x["seal_amount"], reverse=True),
        }
        for boards in sorted(echelon_map.keys(), reverse=True)
        for group in [echelon_map[boards]]
    ]
    total = len(stocks)
    first_board_count = sum(1 for s in stocks if s["boards"] == 1)
    return {
        "echelons": echelon_list,
        "ths_hot": ths_hot_list[:20],
        "date": dt,
        "theme_ranking": theme_ranking,
        "ai": ai_meta,
        "summary": {
            "total": total,
            "first_board_count": first_board_count,
            "consec_count": total - first_board_count,
            "max_boards": max((s["boards"] for s in stocks), default=0),
        },
    }


@limit_up_echelon_bp.route('/api/v1/limit-up-echelon', methods=['GET'])
def get_limit_up_echelon():
    """获取当日涨停板梯队数据"""
    dt = request.args.get('dt', datetime.now().strftime('%Y%m%d'))
    dt_clean = dt.replace('-', '')

    try:
        import akshare as ak
        from concurrent.futures import ThreadPoolExecutor

        # 1. 并行获取涨停池 + 同花顺热股
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_zt = pool.submit(ak.stock_zt_pool_em, date=dt_clean)
            fut_ths = pool.submit(_fetch_ths_hot_stocks)
            df = fut_zt.result()
            ths_hot_list, ths_hot_map = fut_ths.result()

        if df is None or df.empty:
            return v1_success_response(data={
                "echelons": [],
                "ths_hot": [],
                "date": dt,
                "theme_ranking": [],
                "ai": {"enabled": False, "cached": False, "ok": False},
            })

        # 2. 构建股票数据
        stocks = _build_stocks_from_df(df, ths_hot_map)

        # 3. AI 分组：有缓存直接用，无缓存异步触发
        theme_ranking = []
        ai_meta = {"enabled": False, "cached": False, "ok": False, "status": "none"}
        want_analysis = request.args.get("analysis", "0") == "1"
        force_ai = request.args.get("force", "0") == "1"

        if want_analysis and stocks:
            ai_meta["enabled"] = True
            codes_key = tuple(sorted(s["code"] for s in stocks))
            cache_key = (AI_CACHE_VERSION, dt_clean, codes_key)
            now_ts = time.time()

            # force 时清除旧缓存和任务状态
            if force_ai:
                _echelon_ai_cache.pop(cache_key, None)
                with _ai_task_lock:
                    _ai_task_status.pop(cache_key, None)

            # 检查内存缓存
            group_result = {}
            if not force_ai and cache_key in _echelon_ai_cache:
                ts0, cached = _echelon_ai_cache[cache_key]
                if now_ts - ts0 < AI_CACHE_TTL_SEC:
                    group_result = dict(cached)
                    ai_meta["cached"] = True

            # 内存无缓存时，尝试从数据库加载
            if not group_result.get("labels") and not force_ai:
                try:
                    db_data = load_echelon_from_db(dt_clean)
                    if db_data and db_data.get("stocks"):
                        # 从库里重建 group_result
                        db_labels = {}
                        db_reasons = {}
                        db_leaders = {}
                        for s in db_data["stocks"]:
                            if s.get("tag_name"):
                                db_labels[s["code"]] = s["tag_name"]
                        for t in db_data.get("tags") or []:
                            if t.get("reason"):
                                db_reasons[t["tag_name"]] = t["reason"]
                        for tr in db_data.get("theme_ranking") or []:
                            if tr.get("leaders"):
                                db_leaders[tr["theme"]] = tr["leaders"]
                        if db_labels:
                            group_result = {"labels": db_labels, "reasons": db_reasons, "leaders": db_leaders}
                            _echelon_ai_cache[cache_key] = (now_ts, dict(group_result))
                            ai_meta["cached"] = True
                            logger.info(f"从数据库加载 AI 分组缓存 (date={dt_clean})")
                except Exception as e:
                    logger.warning(f"从数据库加载分组失败: {e}")

            if group_result.get("labels"):
                # 命中缓存（内存或数据库），直接返回完整数据
                theme_ranking = _apply_group_labels(stocks, group_result)
                ai_meta["ok"] = True
                ai_meta["status"] = "done"
            else:
                # 检查是否已有后台任务
                with _ai_task_lock:
                    task = _ai_task_status.get(cache_key)
                    if task and task["status"] == "done" and task["result"].get("labels"):
                        # 后台任务已完成
                        group_result = task["result"]
                        _echelon_ai_cache[cache_key] = (now_ts, dict(group_result))
                        theme_ranking = _apply_group_labels(stocks, group_result)
                        ai_meta["ok"] = True
                        ai_meta["status"] = "done"
                    elif task and task["status"] == "pending":
                        # 正在执行中
                        ai_meta["status"] = "pending"
                    else:
                        # 启动后台AI任务
                        _ai_task_status[cache_key] = {"status": "pending", "result": {}}
                        t = threading.Thread(
                            target=_bg_ai_grouping,
                            args=(list(stocks), cache_key),
                            daemon=True,
                        )
                        t.start()
                        ai_meta["status"] = "pending"

        return v1_success_response(data=_build_echelon_response(
            stocks, ths_hot_list, dt, theme_ranking, ai_meta
        ))

    except Exception as e:
        logger.error(f"获取涨停板梯队失败: {e}", exc_info=True)
        return v1_error_response(message=f"获取涨停板梯队失败: {str(e)}")


@limit_up_echelon_bp.route('/api/v1/limit-up-echelon/ai-status', methods=['GET'])
def get_ai_status():
    """轮询 AI 分组状态，完成后返回带分组的完整数据"""
    dt = request.args.get('dt', datetime.now().strftime('%Y%m%d'))
    dt_clean = dt.replace('-', '')

    # 找到匹配的 cache_key
    with _ai_task_lock:
        matched_key = None
        for key, task in _ai_task_status.items():
            if len(key) >= 3 and key[1] == dt_clean:
                matched_key = key
                break

        if not matched_key:
            return v1_success_response(data={"status": "none"})

        task = _ai_task_status[matched_key]
        if task["status"] == "pending":
            return v1_success_response(data={"status": "pending"})
        if task["status"] == "error":
            return v1_success_response(data={"status": "error"})

    # done - 返回分组结果供前端合并
    group_result = task["result"]
    label_by_code = group_result.get("labels") or {}
    reason_by_label = group_result.get("reasons") or {}
    leader_by_label = group_result.get("leaders") or {}
    counter = Counter(label_by_code.values())

    themed_stocks = {}
    for code, label in label_by_code.items():
        leaders = leader_by_label.get(label, [])
        primary_leader = leaders[0] if leaders else {}
        themed_stocks[code] = {
            "group_label": label,
            "theme": label,
            "theme_count": counter.get(label, 1),
            "group_count": counter.get(label, 1),
            "theme_reason": reason_by_label.get(label, ""),
            "theme_leaders": leaders,
            "theme_leader_code": primary_leader.get("code", ""),
            "theme_leader_name": primary_leader.get("name", ""),
            "theme_leader_reason": primary_leader.get("reason", ""),
            "is_theme_leader": any(item.get("code") == code for item in leaders),
        }

    theme_ranking = [
        {
            "theme": theme,
            "count": count,
            "reason": reason_by_label.get(theme, ""),
            "leader": (leader_by_label.get(theme, []) or [{}])[0],
            "leaders": leader_by_label.get(theme, []),
        }
        for theme, count in counter.most_common()
    ]

    return v1_success_response(data={
        "status": "done",
        "themed_stocks": themed_stocks,
        "theme_ranking": theme_ranking,
    })


@limit_up_echelon_bp.route('/api/v1/limit-up-echelon/themes', methods=['POST'])
def analyze_themes():
    """调用 Claude 做涨停分组（与 GET ?analysis=1 相同逻辑）"""
    try:
        body = request.get_json(silent=True) or {}
        stocks = body.get("stocks", [])
        if not stocks:
            return v1_error_response(message="请提供stocks数组")

        group_result = _claude_group_labels_for_stocks(stocks)
        label_by_code = group_result.get("labels") or {}
        reason_by_label = group_result.get("reasons") or {}
        leader_by_label = group_result.get("leaders") or {}
        if not label_by_code:
            return v1_error_response(message="AI分析结果解析失败")

        counter = Counter(label_by_code.values())
        themed_stocks = {}
        for code, label in label_by_code.items():
            themed_stocks[str(code)] = {
                "theme": label,
                "group_label": label,
                "theme_count": counter.get(label, 0),
                "group_count": counter.get(label, 0),
                "theme_reason": reason_by_label.get(label, ""),
                "theme_leaders": leader_by_label.get(label, []),
                "theme_leader_code": ((leader_by_label.get(label, []) or [{}])[0]).get("code", ""),
                "theme_leader_name": ((leader_by_label.get(label, []) or [{}])[0]).get("name", ""),
                "theme_leader_reason": ((leader_by_label.get(label, []) or [{}])[0]).get("reason", ""),
            }
        theme_ranking = [
            {
                "theme": theme,
                "count": count,
                "reason": reason_by_label.get(theme, ""),
                "leader": (leader_by_label.get(theme, []) or [{}])[0],
                "leaders": leader_by_label.get(theme, []),
            }
            for theme, count in counter.most_common()
        ]

        return v1_success_response(data={
            "themed_stocks": themed_stocks,
            "theme_ranking": theme_ranking,
        })

    except Exception as e:
        logger.error(f"题材分析失败: {e}", exc_info=True)
        return v1_error_response(message=f"题材分析失败: {str(e)}")
