"""
涨停板梯队接口模块
- GET  /api/v1/limit-up-echelon              只读库返回涨停梯队（分组由离线任务写入）
- GET  /api/v1/limit-up-echelon/ai-status    兼容：返回库内分组是否就绪
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
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, request

from utils.response import v1_success_response, v1_error_response
from services.theme_service import (
    get_recent_tags,
    get_tags_by_date,
    get_limit_up_stocks_by_date,
    save_ai_grouping_result,
    load_echelon_from_db,
    date_has_manual_tags,
    clear_echelon_date,
)

logger = logging.getLogger(__name__)

limit_up_echelon_bp = Blueprint('limit_up_echelon', __name__)


def _default_echelon_dt() -> str:
    """无 dt 参数时默认最近交易日（周末退到周五），与前端 getLastTradingDayStr 一致"""
    d = datetime.now()
    dow = d.weekday()
    if dow == 5:
        d -= timedelta(days=1)
    elif dow == 6:
        d -= timedelta(days=2)
    return d.strftime('%Y%m%d')

from utils.claude_client import CLAUDE_API_KEY, call_claude as _call_claude

# (date, codes_tuple) -> (unix_ts, {"labels": code -> group_label, "reasons": label -> reason, "leaders": label -> [leader]})
_echelon_ai_cache = {}
AI_CACHE_TTL_SEC = int(os.environ.get("LIMIT_UP_AI_CACHE_SEC", "600"))
AI_CACHE_VERSION = "leaders-v2"

# 后台 AI 任务状态: cache_key -> {"status": "pending"|"done"|"error", "result": dict}
_ai_task_status = {}
_ai_task_lock = threading.Lock()

MAX_DAY_TAGS = 10
MAX_OTHER_STOCKS = 5
MIN_TAG_STOCKS = 2
OTHER_LABEL_SET = frozenset({"其他概念", "其他", "其他行业"})

# 复盘常用大主线（对齐复盘图：约 7 主线 + 其他概念≤5）
CANONICAL_BROAD_TAGS = (
    "机器人", "氟化工", "大消费", "半导体产业链", "电力", "AI应用", "体育产业",
)

# 细碎标签强制并入大主线（名称与复盘图一致，勿再缩写）
BROAD_TAG_ALIASES = {
    "人形机器人": "机器人", "减速器": "机器人", "汽车零部件": "机器人",
    "工业自动化": "机器人", "电机及驱动": "机器人", "自动化设备": "机器人",
    "专用设备": "机器人", "智能制造": "机器人",
    "化工新材料": "氟化工", "化学制品": "氟化工", "塑料制品": "氟化工",
    "电子化学品": "氟化工", "氢氟酸": "氟化工",
    "消费": "大消费", "消费食品": "大消费", "家居建材": "大消费", "建筑陶瓷": "大消费",
    "家居用品": "大消费", "食品饮料": "大消费", "白酒": "大消费", "零售": "大消费",
    "绿电": "电力", "绿色电力": "电力", "新能源产业链": "电力", "储能": "电力",
    "风电": "电力", "光伏": "电力", "火电": "电力",
    "半导体": "半导体产业链", "芯片": "半导体产业链", "存储芯片": "半导体产业链",
    "先进封装": "半导体产业链", "光刻胶": "半导体产业链", "其他电子": "半导体产业链",
    "传媒短剧": "AI应用", "传媒广告": "AI应用", "传媒": "AI应用", "短剧": "AI应用",
    "游戏": "AI应用", "影视": "AI应用",
    "AI营销": "AI应用", "人工智能": "AI应用", "AIGC": "AI应用", "算力": "AI应用",
    "体育": "体育产业", "足球": "体育产业", "世界杯": "体育产业",
}

# ---------- Claude 分组（相近概念合并为同一 group_label）----------

GROUP_PROMPT = """你是A股超短题材复盘专家。下面是同一交易日涨停股列表，包含同花顺热股的概念、标题和分析。

任务：把涨停股归入当天 **6-8 个**最强风口大主线（另可加「其他概念」≤5 只），**总共不超过 10 个标签名**。

**标准复盘结构（20260515 参考，按当日实际涨停池调整数量）：**
机器人、氟化工、大消费、半导体产业链、电力、AI应用、体育产业，其余≤5只放「其他概念」。

要求：
1. 大标签优先且尽量只使用以下名称（不要自创近义词）：
   机器人、氟化工、大消费、半导体产业链、电力、AI应用、体育产业。
2. 禁止细碎标签单独成类。必须合并（示例）：
   - 汽车零部件/工业自动化/电机及驱动/减速器/人形机器人 → **机器人**
   - 绿电/储能/风电/光伏 → **电力**
   - 消费食品/家居建材/建筑陶瓷/白酒 → **大消费**
   - 化工新材料/塑料制品/电子化学品 → **氟化工**
   - 传媒短剧/短剧/游戏/AI营销 → **AI应用**（传媒类）或 **体育产业**（体育赛事项）
   - 芯片/存储/先进封装/光刻胶/电子化学品 → **半导体产业链**（不要用「半导体」简称）
   不满 2 只涨停的细分方向不得单独成标签，并入最接近的大主线。
3. **优先使用以下已有标签**（来自近期历史数据库），如果今天的涨停股能匹配这些标签就直接使用，不要创造语义相近的新标签：
{known_tags}
   如果某些已有标签今天没有对应的涨停股，不需要输出。如果出现全新的主线，可以创建新标签。
4. 每只股票必须只属于一个大标签。归类时重点参考同花顺给出的概念标签和涨停标题，找到该票与哪个大标签关联最紧密。
5. **「其他概念」必须控制在 5 只以内**。只有完全无法与任何大标签关联的个股才放「其他概念」。如果某只票的同花顺概念、行业、涨停标题中能找到与任一大标签的关联（哪怕是次要关联），就必须归入那个大标签，而非「其他概念」。宁可放进关联性较弱的大标签，也不要轻易扔进「其他概念」。
6. **大标签总数（含其他概念）不得超过 10 个**，禁止细碎小题材单独成类。
7. 每个大标签必须给一句「涨停原因」，像短线复盘语言，概括该主题当天爆发原因，例如"特斯拉Optimus Gen-3启动量产，Figure机器人连续工作30小时"。
8. 每个大标签选出 1-2 个「板块龙头」，优先只选 1 个。按顺序输出：最正宗、最有带动性的先锋龙放第一；如需要，再给一个容量/辨识度最高的中军放第二。优先考虑连板高度、封板强度、同花顺热度、市场辨识度、题材正宗性和带动性。
9. 按成分股数量从高到低输出 groups，「其他概念」放最后。
股票列表（每行：代码 名称 行业 连板 同花顺热度 同花顺标题 同花顺概念 同花顺分析）：
{stock_list}

只输出一个 JSON 对象，不要 markdown，不要解释文字，格式严格为：
{{"groups":[{{"label":"机器人","reason":"涨停原因","leaders":[{{"code":"000000","name":"示例","role":"先锋龙","reason":"龙头理由"}}],"stocks":[{{"code":"000000","name":"示例","why":"归类依据"}}]}}],"stock_groups":{{"000000":"机器人"}}}}
股票代码必须与输入一致（6位数字字符串）。"""

THEME_PROMPT = GROUP_PROMPT

# 当「其他概念」超过 5 只时，用此 prompt 二次归纳新标签
REGROUP_PROMPT = """你是A股超短题材复盘专家。下面这些涨停股被初步归为「其他概念」，请尽量并入已有大主线，不要新建细碎标签。

要求：
1. **只能**使用以下已有大标签之一（禁止新建「低空经济」「医疗器械」等细碎名）：
{existing_labels}
   若实在无法归入，可保留在「其他概念」（全市场其他概念合计不得超过 5 只）。
2. 每个大标签至少 2 只股票才单独成类，否则并入最接近的大主线。
3. 不要创造与机器人/氟化工/消费/电力/传媒短剧/半导体/AI应用 语义重复的新名字。
4. 每个被使用的大标签写一句涨停原因，选出 1 个龙头。
5. 已有主流大标签：
{existing_labels}

股票列表（每行：代码 名称 行业 连板 同花顺标题 同花顺概念 同花顺分析）：
{stock_list}

只输出一个 JSON 对象，格式同前：
{{"groups":[{{"label":"低空经济","reason":"涨停原因","leaders":[{{"code":"000000","name":"示例","role":"先锋龙","reason":"龙头理由"}}],"stocks":[{{"code":"000000","name":"示例","why":"归类依据"}}]}}],"stock_groups":{{"000000":"低空经济"}}}}
不属于任何新标签的股票放入「其他概念」组。"""


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


def _is_other_label(label: str) -> bool:
    name = (label or "").strip()
    return not name or name in OTHER_LABEL_SET


def _resolve_broad_label(label: str) -> str:
    """将细碎标签映射到复盘大主线"""
    name = (label or "").strip()
    if _is_other_label(name):
        return "其他概念"
    if name in BROAD_TAG_ALIASES:
        return BROAD_TAG_ALIASES[name]
    if name in CANONICAL_BROAD_TAGS:
        return name
    for broad in CANONICAL_BROAD_TAGS:
        if broad in name or name in broad:
            return broad
    return name


def _normalize_to_broad_tags(group_result: dict, stocks: list) -> dict:
    """合并到复盘大主线，避免汽车零部件/绿电等细碎标签"""
    labels = dict((group_result or {}).get("labels") or {})
    reasons = dict((group_result or {}).get("reasons") or {})
    leaders = dict((group_result or {}).get("leaders") or {})
    if not labels:
        return group_result or {}

    for code, lbl in list(labels.items()):
        labels[code] = _resolve_broad_label(lbl)

    counter = Counter(labels.values())
    if not counter:
        return group_result or {}

    dominant = counter.most_common(1)[0][0]
    for lbl, cnt in list(counter.items()):
        if _is_other_label(lbl) or cnt >= MIN_TAG_STOCKS or lbl in CANONICAL_BROAD_TAGS:
            continue
        target = dominant if not _is_other_label(dominant) else "其他概念"
        for code, l in list(labels.items()):
            if l == lbl:
                labels[code] = target

    # 非标准主线名：并入当日股数最多的标准主线
    counter = Counter(labels.values())
    for lbl in list(counter.keys()):
        if _is_other_label(lbl) or lbl in CANONICAL_BROAD_TAGS:
            continue
        target = next(
            (t for t, _ in counter.most_common() if t in CANONICAL_BROAD_TAGS),
            dominant,
        )
        for code, l in list(labels.items()):
            if l == lbl:
                labels[code] = target if not _is_other_label(target) else "其他概念"

    active = set(labels.values())
    reasons = {k: v for k, v in reasons.items() if k in active}
    leaders = {k: v for k, v in leaders.items() if k in active}
    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def _enforce_group_limits(group_result: dict, stocks: list) -> dict:
    """硬性限制：当天大标签 ≤10，「其他概念」个股 ≤5"""
    labels = dict((group_result or {}).get("labels") or {})
    reasons = dict((group_result or {}).get("reasons") or {})
    leaders = dict((group_result or {}).get("leaders") or {})
    if not labels:
        return group_result or {}

    for code, lbl in list(labels.items()):
        if _is_other_label(lbl):
            labels[code] = "其他概念"

    def _counter():
        return Counter(labels.values())

    counter = _counter()
    non_other = sorted(
        (t for t in counter if not _is_other_label(t)),
        key=lambda t: counter[t],
        reverse=True,
    )
    max_main_tags = MAX_DAY_TAGS - 1
    if len(non_other) > max_main_tags:
        keep = set(non_other[:max_main_tags])
        fallback = non_other[0]
        for code, lbl in list(labels.items()):
            if not _is_other_label(lbl) and lbl not in keep:
                labels[code] = fallback
        logger.info("大标签超过 %s 个，已合并细碎题材", MAX_DAY_TAGS)

    counter = _counter()
    other_codes = [c for c, l in labels.items() if l == "其他概念"]
    if len(other_codes) > MAX_OTHER_STOCKS:
        # 优先并入当日第二大主线，避免全部塞进机器人
        ranked = [t for t, _ in counter.most_common() if not _is_other_label(t)]
        main_fallback = ranked[1] if len(ranked) > 1 else (ranked[0] if ranked else "大消费")
        for code in other_codes[MAX_OTHER_STOCKS:]:
            labels[code] = main_fallback
        logger.info("「其他概念」超过 %s 只，已并入 %s", MAX_OTHER_STOCKS, main_fallback)

    counter = _counter()
    while len(counter) > MAX_DAY_TAGS:
        candidates = [t for t in counter if not _is_other_label(t)]
        if not candidates:
            break
        smallest = min(candidates, key=lambda t: counter[t])
        largest = max(candidates, key=lambda t: counter[t])
        for code, lbl in list(labels.items()):
            if lbl == smallest:
                labels[code] = largest
        counter = _counter()

    active_tags = set(labels.values())
    reasons = {k: v for k, v in reasons.items() if k in active_tags}
    leaders = {k: v for k, v in leaders.items() if k in active_tags}
    if "其他概念" in active_tags and not reasons.get("其他概念"):
        reasons["其他概念"] = "未能归入当日主线"

    logger.info(
        "分组限额: 标签数=%s, 其他概念=%s只",
        len(active_tags),
        sum(1 for l in labels.values() if l == "其他概念"),
    )
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

    group_result = {"labels": labels, "reasons": reasons, "leaders": leaders}

    # 5. 仅当本次有 AI 新分组时，才对「其他概念」二次归纳（避免覆盖人工校准）
    other_codes = [code for code, lbl in labels.items() if _is_other_label(lbl)]
    if unmatched and len(other_codes) > MAX_OTHER_STOCKS and not date_has_manual_tags(dt):
        logger.info(f"「其他概念」共 {len(other_codes)} 只，触发二次归纳...")
        stock_map = {s["code"]: s for s in stocks}
        other_stocks = [stock_map[c] for c in other_codes if c in stock_map]
        existing_labels_text = "、".join(
            lbl for lbl in set(labels.values()) if not _is_other_label(lbl)
        )

        lines = []
        for s in other_stocks:
            ths_tags = s.get("ths_concept_tags") or []
            tag_str = ",".join(str(t) for t in ths_tags if t) if ths_tags else ""
            lines.append(
                f"{s['code']} {s['name']} 行业:{s.get('industry', '')} "
                f"连板:{s.get('boards', 1)} "
                f"同花顺标题:{s.get('ths_analyse_title') or ''} "
                f"同花顺概念:[{tag_str}] 同花顺分析:{(s.get('ths_analyse') or '')[:200]}"
            )
        regroup_prompt = (
            REGROUP_PROMPT
            .replace("{existing_labels}", existing_labels_text or "（无）")
            .replace("{stock_list}", "\n".join(lines))
        )
        try:
            content = _call_claude(regroup_prompt, max_tokens=4096)
            regroup = _parse_grouping_json(content)
            if regroup.get("labels"):
                for code, new_label in regroup["labels"].items():
                    labels[code] = new_label  # 覆盖「其他概念」
                if regroup.get("reasons"):
                    reasons.update(regroup["reasons"])
                if regroup.get("leaders"):
                    for tag, ldr in regroup["leaders"].items():
                        if tag not in leaders:
                            leaders[tag] = ldr
                remaining = sum(1 for lbl in labels.values() if _is_other_label(lbl))
                logger.info(f"二次归纳完成，「其他概念」从 {len(other_codes)} 只降至 {remaining} 只")
        except Exception as e:
            logger.error(f"二次归纳失败: {e}", exc_info=True)

    group_result = {"labels": labels, "reasons": reasons, "leaders": leaders}
    group_result = _normalize_to_broad_tags(group_result, stocks)
    return _enforce_group_limits(group_result, stocks)


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


def _echelon_response_from_db(dt_clean: str, dt: str):
    """从数据库构建涨停梯队响应（akshare 不可用或返回空时的回退）"""
    db_data = load_echelon_from_db(dt_clean)
    if not db_data or not db_data.get("stocks"):
        return None

    stocks = db_data["stocks"]
    theme_ranking = db_data["theme_ranking"]
    echelon_map = {}
    for s in stocks:
        echelon_map.setdefault(s["boards"], []).append(s)
    echelon_list = [
        {
            "boards": boards,
            "count": len(group),
            "stocks": sorted(group, key=lambda x: float(x.get("seal_amount") or 0), reverse=True),
        }
        for boards in sorted(echelon_map.keys(), reverse=True)
        for group in [echelon_map[boards]]
    ]
    total = len(stocks)
    first_board_count = sum(1 for s in stocks if s["boards"] == 1)
    return {
        "echelons": echelon_list,
        "ths_hot": [],
        "date": dt,
        "theme_ranking": theme_ranking,
        "ai": {
            "enabled": True,
            "cached": True,
            "ok": True,
            "status": "done",
            "source": "database",
        },
        "summary": {
            "total": total,
            "first_board_count": first_board_count,
            "consec_count": total - first_board_count,
            "max_boards": max((s["boards"] for s in stocks), default=0),
        },
    }


def _normalize_echelon_dt(dt: Optional[str] = None) -> tuple:
    """返回 (dt_clean YYYYMMDD, dt_display YYYY-MM-DD 或原样)"""
    raw = dt or _default_echelon_dt()
    dt_clean = raw.replace("-", "")
    if len(dt_clean) == 8 and "-" not in raw:
        dt_display = f"{dt_clean[:4]}-{dt_clean[4:6]}-{dt_clean[6:8]}"
    else:
        dt_display = raw
    return dt_clean, dt_display


def _echelon_grouping_complete(dt_clean: str) -> bool:
    """判断该日是否已有离线分组结果（可跳过任务）"""
    db_data = load_echelon_from_db(dt_clean)
    stocks = (db_data or {}).get("stocks") or []
    if not stocks:
        return False
    tagged = sum(1 for s in stocks if s.get("tag_name"))
    return tagged >= max(1, len(stocks) // 2)


def _fetch_zt_pool_and_ths(dt_clean: str):
    """拉取涨停池 + 同花顺热股（离线任务用，非 eventlet 环境）"""
    import akshare as ak
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_zt = pool.submit(ak.stock_zt_pool_em, date=dt_clean)
        fut_ths = pool.submit(_fetch_ths_hot_stocks)
        df = fut_zt.result()
        ths_hot_list, ths_hot_map = fut_ths.result()
    return df, ths_hot_list, ths_hot_map


def _preserve_tags_refresh_pool(dt_clean: str, stocks: list) -> dict:
    """保留库内人工/已校准分组，仅刷新涨停池行情字段"""
    db_data = load_echelon_from_db(dt_clean)
    if not db_data or not db_data.get("stocks"):
        return {}
    db_by_code = {s["code"]: s for s in db_data["stocks"]}
    labels = {}
    reasons = {t["tag_name"]: t.get("reason", "") for t in db_data.get("tags") or []}
    leaders = {}
    for s in db_data.get("theme_ranking") or []:
        if s.get("leaders"):
            leaders[s["theme"]] = s["leaders"]
    for stock in stocks:
        code = stock.get("code")
        prev = db_by_code.get(code)
        if prev and prev.get("tag_name"):
            labels[code] = prev["tag_name"]
            stock["tag_name"] = prev["tag_name"]
            for field in (
                "is_leader", "leader_role", "leader_reason",
                "is_theme_leader", "theme_leaders",
            ):
                if field in prev:
                    stock[field] = prev[field]
    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def build_echelon_one_date(dt: str, force: bool = False) -> str:
    """离线生成单日涨停梯队：涨停池 + AI 分组 + 写库。

    返回: 'skipped' | 'saved' | 'failed' | 'empty'
    """
    dt_clean = dt.replace("-", "")
    if not force and _echelon_grouping_complete(dt_clean):
        logger.info("涨停梯队已有离线分组，跳过 date=%s", dt_clean)
        return "skipped"

    if force:
        clear_echelon_date(dt_clean)
        logger.info("force: 已清除 %s 旧分组，将重新拉池并 AI 归纳", dt_clean)

    try:
        df, ths_hot_list, ths_hot_map = _fetch_zt_pool_and_ths(dt_clean)
        if df is None or df.empty:
            logger.warning("涨停池为空 date=%s", dt_clean)
            return "empty"

        stocks = _build_stocks_from_df(df, ths_hot_map)
        if not stocks:
            return "empty"

        group_result = _smart_group_stocks(stocks, dt_clean)

        if not group_result.get("labels"):
            logger.error("分组无结果 date=%s", dt_clean)
            return "failed"

        _apply_group_labels(stocks, group_result)
        save_ai_grouping_result(dt_clean, stocks, group_result)
        logger.info(
            "涨停梯队已写库 date=%s stocks=%s tags=%s",
            dt_clean,
            len(stocks),
            len(set(group_result["labels"].values())),
        )
        return "saved"
    except Exception as e:
        logger.error("离线生成涨停梯队失败 date=%s: %s", dt_clean, e, exc_info=True)
        return "failed"


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
    """获取涨停板梯队（只读库，分组由收盘后离线任务写入）"""
    dt_clean, dt_display = _normalize_echelon_dt(request.args.get('dt'))

    payload = _echelon_response_from_db(dt_clean, dt_display)
    if payload:
        return v1_success_response(data=payload)

    return v1_success_response(data={
        "echelons": [],
        "ths_hot": [],
        "date": dt_display,
        "theme_ranking": [],
        "ai": {"enabled": False, "cached": False, "ok": False, "status": "none"},
        "summary": {
            "total": 0,
            "first_board_count": 0,
            "consec_count": 0,
            "max_boards": 0,
        },
    })


@limit_up_echelon_bp.route('/api/v1/limit-up-echelon/ai-status', methods=['GET'])
def get_ai_status():
    """兼容旧前端轮询：分组已离线化，仅反映库内是否已有数据"""
    dt_clean, _ = _normalize_echelon_dt(request.args.get('dt'))
    if _echelon_grouping_complete(dt_clean):
        return v1_success_response(data={"status": "done", "source": "database"})
    return v1_success_response(data={"status": "none"})


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


# ──────────────────────────────────────────────────────────────────────────────
# 智能题材标签接口（不存库，实时分析单只股票的涨停题材归属）
# GET /api/v1/stock-theme-tags?code=000001&dt=20260515
# ──────────────────────────────────────────────────────────────────────────────

_STOCK_THEME_PROMPT = """你是A股超短题材复盘专家。根据以下这只股票的信息，判断它属于哪个涨停题材大标签（2-8字，市场常用语言）。

股票信息：
- 代码：{code}
- 名称：{name}
- 所属行业：{industry}
- 同花顺热度：{ths_rank}
- 同花顺标题：{ths_title}
- 同花顺概念：{ths_tags}
- 同花顺分析：{ths_analyse}
- 今日涨停原因：{reason}

当天已有涨停大标签（优先归入已有标签）：
{existing_labels}

只输出一个 JSON 对象，格式为：
{{"label": "机器人", "reason": "归类依据一句话"}}
如果无法确定，输出 {{"label": "", "reason": ""}}"""


@limit_up_echelon_bp.route('/api/v1/stock-theme-tags', methods=['GET'])
def get_stock_theme_tags():
    """智能分析单只股票的题材归属，返回最多2个标签+各自涨停家数（不存库）"""
    code = request.args.get('code', '').strip().zfill(6)
    dt = request.args.get('dt', datetime.now().strftime('%Y%m%d')).replace('-', '')
    if not code:
        return v1_error_response(message='缺少 code 参数')

    try:
        import akshare as ak

        # 1. 获取当日涨停池（用于统计同行业/同题材涨停数）
        try:
            df = ak.stock_zt_pool_em(date=dt)
        except Exception:
            df = None
        all_stocks = []
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                all_stocks.append({
                    'code': str(row.get('代码', '')).zfill(6),
                    'name': str(row.get('名称', '')),
                    'industry': str(row.get('所属行业', '')),
                })
        total_limit_up = len(all_stocks)

        # 2. 读取当天 DB 题材分组
        db_stocks = get_limit_up_stocks_by_date(dt)
        db_code_to_tag = {s['code']: s['tag_name'] for s in db_stocks if s.get('tag_name')}
        db_tags = get_tags_by_date(dt)
        db_tag_names = [t['tag_name'] for t in db_tags if t.get('tag_name')]
        db_tag_reasons = {t['tag_name']: t.get('reason', '') for t in db_tags}

        # 3. 获取股票行业（优先涨停池 → THS热股 → 前端传参）
        target_industry = next((s['industry'] for s in all_stocks if s['code'] == code), '')
        ths_info = {}
        if not target_industry:
            try:
                _, ths_map = _fetch_ths_hot_stocks()
                ths_info = ths_map.get(code, {})
                target_industry = ths_info.get('industry', '')
            except Exception:
                pass

        # 4. 获取股票名称
        stock_name = next((s['name'] for s in all_stocks if s['code'] == code), '')
        if not stock_name:
            try:
                from utils.stock_utils import get_stock_name_by_code as _get_name
                stock_name = _get_name(code) or code
            except Exception:
                stock_name = code

        # 5. 确定题材标签（DB有则直接用，否则用AI分析）
        db_theme = db_code_to_tag.get(code, '')
        if db_theme and db_theme not in ('其他概念', '其他', '其他行业'):
            theme_label = db_theme
            theme_reason = db_tag_reasons.get(db_theme, '')
        else:
            # 用 Claude 分析：给出已有 theme_tags，让 AI 判断归属或建议新标签
            theme_label = ''
            theme_reason = ''
            if CLAUDE_API_KEY:
                try:
                    info = ths_info or {}
                    existing_text = '、'.join(db_tag_names[:20]) if db_tag_names else '（今日暂无题材标签）'
                    prompt = (
                        _STOCK_THEME_PROMPT
                        .replace('{code}', code)
                        .replace('{name}', stock_name)
                        .replace('{industry}', target_industry or '未知')
                        .replace('{ths_rank}', str(info.get('ths_rank') or '-'))
                        .replace('{ths_title}', str(info.get('ths_analyse_title') or ''))
                        .replace('{ths_tags}', ','.join(info.get('ths_concept_tags') or []))
                        .replace('{ths_analyse}', str(info.get('ths_analyse') or '')[:300])
                        .replace('{reason}', str(info.get('ths_analyse_title') or target_industry or ''))
                        .replace('{existing_labels}', existing_text)
                    )
                    content = _call_claude(prompt, max_tokens=256)
                    import json as _json
                    # 容错：提取 JSON 部分
                    content = content.strip()
                    if '{' in content:
                        content = content[content.index('{'):content.rindex('}')+1]
                    parsed = _json.loads(content)
                    theme_label = (parsed.get('label') or '').strip()
                    theme_reason = (parsed.get('reason') or '').strip()
                except Exception as e:
                    logger.warning(f'AI题材分析失败: {e}')

        # 6. 统计涨停数
        industry_count = sum(1 for s in all_stocks if s['industry'] == target_industry) if target_industry else 0
        theme_count = sum(1 for lbl in db_code_to_tag.values() if lbl == theme_label) if theme_label else 0

        # 7. 构建最多2个标签，按涨停数降序
        tags = []
        if theme_label and theme_label not in ('其他概念', '其他', '其他行业'):
            tags.append({'label': theme_label, 'count': theme_count, 'type': 'theme', 'reason': theme_reason})
        if target_industry:
            # 若行业名与题材名不同才加
            if not any(t['label'] == target_industry for t in tags):
                tags.append({'label': target_industry, 'count': industry_count, 'type': 'industry',
                             'reason': f'{target_industry}行业今日涨停 {industry_count} 只'})

        tags.sort(key=lambda x: x['count'], reverse=True)
        result_tags = tags[:2]

        return v1_success_response(data={
            'code': code,
            'date': dt,
            'total_limit_up': total_limit_up,
            'industry': target_industry,
            'tags': result_tags,
        })

    except Exception as e:
        logger.error(f'stock-theme-tags 失败: {e}', exc_info=True)
        return v1_error_response(message=str(e))

