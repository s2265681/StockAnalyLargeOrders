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

from config.ai_config import GENERAL_BROAD_TAGS_ORDERED
from config.ai_prompts import (
    STOCK_THEME_PROMPT,
    build_group_prompt,
    build_regroup_prompt,
    build_split_oversized_prompt,
)
from utils.claude_client import get_claude_api_key, call_claude_for_scenario

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
# 所属概念在文本匹配中的权重（高于行业/标题关键词）
CONCEPT_MATCH_WEIGHT = 4
CONCEPT_TEXT_REPEAT = 3

GENERAL_BROAD_TAG_SET = frozenset(GENERAL_BROAD_TAGS_ORDERED)


def _broad_tags_prompt_list() -> str:
    return "、".join(GENERAL_BROAD_TAGS_ORDERED)


# 细碎/长标签名 → 通用大类（按复盘图口径）
BROAD_TAG_ALIASES = {
    "人形机器人": "机器人", "减速器": "机器人", "汽车零部件": "机器人",
    "工业自动化": "机器人", "智能物流": "机器人", "具身智能": "机器人",
    "伺服电机": "机器人", "智能制造": "机器人",
    "化工": "氟化工", "化工新材料": "氟化工", "化学制品": "氟化工",
    "氢氟酸": "氟化工", "制冷剂": "氟化工",
    "电子特气": "电子特气/化工", "电子化学品": "电子特气/化工",
    "六氟化钨": "电子特气/化工", "硅烷": "电子特气/化工", "环氧丙烷": "电子特气/化工",
    "消费": "大消费", "食品饮料": "大消费", "白酒": "大消费", "家居": "大消费",
    "建材": "大消费", "陶瓷": "大消费", "家电": "大消费", "小家电": "大消费",
    "零售": "大消费", "预制菜": "大消费",
    "半导体": "半导体产业链", "芯片": "半导体产业链", "存储芯片": "半导体产业链",
    "存储": "半导体产业链", "HBM": "半导体产业链", "GPU": "半导体产业链",
    "先进封装": "算力/半导体产业化", "玻璃基板": "算力/半导体产业化",
    "算力租赁": "算力/服务器", "AI服务器": "算力/服务器", "液冷": "算力/服务器",
    "数据中心": "算力/服务器", "东数西算": "算力/服务器",
    "碳化硅": "第三代半导体", "SiC": "第三代半导体", "功率器件": "第三代半导体",
    "绿电": "电力", "火电": "电力", "风电": "电力", "储能": "电力",
    "发电": "电力", "煤电": "电力", "虚拟电厂": "电力", "热电": "电力",
    "TOPCon": "光伏", "HJT": "光伏", "硅片": "光伏", "组件": "光伏", "逆变器": "光伏",
    "CPO": "光通信", "光模块": "光通信", "1.6T": "光通信", "800G": "光通信",
    "覆铜板": "PCB", "铜箔": "PCB", "电子布": "PCB",
    "生猪": "猪肉", "养殖": "猪肉", "屠宰": "猪肉",
    "股权转让": "并购重组", "借壳": "并购重组", "资产注入": "并购重组",
    "资产重组": "并购重组", "要约收购": "并购重组",
    "短剧": "AI应用", "AIGC": "AI应用", "AI电商": "AI应用", "AI营销": "AI应用",
    "游戏": "文化传媒", "影视": "文化传媒", "传媒": "文化传媒",
    "职业教育": "教育", "K12": "教育", "在线教育": "教育",
    "创新药": "医药", "医疗器械": "医药", "生物制药": "医药", "维生素": "合成生物",
    "生物柴油": "合成生物", "酶制剂": "合成生物", "细胞培养": "合成生物",
    "飞行汽车": "低空经济", "eVTOL": "低空经济", "无人机": "低空经济",
    "固态电池": "锂电池", "正极材料": "锂电池", "锂电": "锂电池",
    "房地产": "房地产", "地产": "房地产", "物业": "房地产", "新型城镇化": "房地产",
    "基建": "房地产", "建筑装饰": "房地产",
    "商业航天": "军工", "卫星导航": "军工", "航天": "军工", "军工电子": "军工",
    "页岩气": "油气", "可燃冰": "油气", "天然气": "油气", "石油": "油气",
    "稀土": "稀土永磁", "永磁": "稀土永磁",
    "换电": "充电桩", "超充": "充电桩",
}

# 通用大类关键词（先匹配更细的类；电力与光伏分开）
GENERAL_THEME_KEYWORD_RULES = (
    ("合成生物", (
        "合成生物", "生物制造", "酶制剂", "细胞培养", "工业大麻", "维生素",
        "蔚蓝生物", "鲁抗医药", "播恩集团", "圣达生物", "富士莱",
    )),
    ("低空经济", (
        "低空经济", "飞行汽车", "eVTOL", "无人机", "通航", "低空基建",
        "宗申动力", "亿嘉和", "威奥股份", "康达新材",
    )),
    ("锂电池", (
        "锂电池", "固态电池", "正极材料", "锂矿", "碳酸锂", "储能电池",
        "丰元股份", "融捷股份", "江特电机", "领湃科技",
    )),
    ("医药", (
        "医药", "创新药", "医疗器械", "眼科", "CXO", "仿制药",
        "济民医疗", "兴齐眼药", "海思科", "奥锐特",
    )),
    ("房地产", (
        "房地产", "地产", "物业", "新型城镇化", "装修装饰", "基建",
        "荣盛发展", "金科股份", "南国置业", "我爱我家", "特发服务",
    )),
    ("教育", (
        "教育", "职业教育", "K12", "在线教育", "公考",
        "昂立教育", "学大教育", "传智教育", "中公教育",
    )),
    ("文化传媒", (
        "文化传媒", "游戏", "影视", "出版", "IP",
        "巨人网络", "恺英网络", "完美世界", "读客文化",
    )),
    ("军工", (
        "军工", "航天", "商业航天", "卫星导航", "北斗", "航空零部件",
        "航天晨光", "航天科技", "航天电子", "中兵红箭",
    )),
    ("PCB", (
        "PCB", "覆铜板", "铜箔", "电子布", "印制电路",
        "胜宏科技", "崇达技术", "华正新材", "协和电子",
    )),
    ("油气", (
        "油气", "页岩气", "可燃冰", "天然气", "石油", "油服",
        "仁智股份", "准油股份",
    )),
    ("稀土永磁", (
        "稀土永磁", "稀土", "永磁", "磁材",
        "英洛华", "中科三环",
    )),
    ("充电桩", (
        "充电桩", "换电", "超充", "充电设施",
        "超讯通信", "博菲电气",
    )),
    ("算力/服务器", (
        "算力/服务器", "AI服务器", "液冷散热", "液冷", "服务器", "IDC",
        "浪潮信息", "曙光数创", "申菱环境", "朗威股份",
    )),
    ("并购重组", (
        "并购重组", "股权转让", "借壳", "资产注入", "卖壳", "重组", "要约收购",
        "智微智能", "花王", "威龙股份", "宁波中百", "金正大", "豪悦股份",
    )),
    ("第三代半导体", (
        "第三代半导体", "碳化硅", "SiC", "功率器件", "氮化镓", "GaN",
        "普冉股份", "康强电子", "中瓷电子",
    )),
    ("电子特气/化工", (
        "电子特气", "六氟化钨", "硅烷偶联", "环氧丙烷",
        "和远气体", "中船特气", "晨光新材", "红宝丽", "红墙股份", "宁波韵升",
    )),
    ("光通信", (
        "光通信", "CPO", "光模块", "1.6T", "800G", "光芯片", "共封装", "交换机",
        "剑桥科技", "联特科技", "天孚通信", "汇绿生态",
    )),
    ("算力/半导体产业化", (
        "算力/半导体", "算力芯片", "先进封装", "玻璃基板", "OLED", "封测",
        "宏盛华源", "宁夏建材", "盛视科技", "金富科技", "兆易创新",
    )),
    ("光伏", (
        "光伏", "TOPCon", "HJT", "异质结", "硅片", "组件", "TCO玻璃",
        "协鑫集成", "双良节能", "钧达股份", "耀皮玻璃", "联泓新科",
    )),
    ("猪肉", (
        "猪肉", "生猪", "养殖", "屠宰", "猪周期", "天邦食品", "华统股份",
        "神农集团", "天域生态",
    )),
    ("机器人", (
        "机器人", "人形机器人", "减速器", "RV减速", "Optimus", "Figure",
        "谐波", "执行器", "智能物流", "北特科技", "丰立智能", "鸣志电器",
    )),
    ("氟化工", (
        "氟化工", "制冷剂", "PVDF", "多氟多", "金石资源",
    )),
    ("大消费", (
        "大消费", "家居用品", "建筑陶瓷", "蒙娜丽莎", "食品饮料", "白酒",
        "利仁科技", "有友食品", "零售", "家电", "绝味食品", "三只松鼠",
    )),
    ("半导体产业链", (
        "半导体产业链", "半导体设备", "光刻胶", "存储芯片", "中巨芯", "半导体材料",
        "寒武纪", "佰维存储", "江波龙",
    )),
    ("电力", (
        "电力", "绿电", "火电", "煤电", "超临界", "发电", "虚拟电厂", "热电",
        "京能电力", "天富能源", "明星电力", "西昌电力", "大连热电", "算电协同",
    )),
    ("AI应用", (
        "AI应用", "AI营销", "AIGC", "短剧", "漫剧", "AI视频", "知识产权",
        "值得买", "达实智能", "宣亚国际",
    )),
    ("体育产业", (
        "体育", "世界杯", "足球", "赛事", "舒华体育", "共创草坪",
    )),
)

# 兼容旧引用
THEME_KEYWORD_RULES = GENERAL_THEME_KEYWORD_RULES
CANONICAL_BROAD_TAGS = tuple(t for t, _ in GENERAL_THEME_KEYWORD_RULES)

DEFAULT_THEME_REASONS = {
    "合成生物": "生物制造与新质生产力赛道景气",
    "机器人": "人形机器人量产与零部件订单放量",
    "低空经济": "低空基建与飞行汽车政策催化",
    "算力/服务器": "AI服务器、液冷与数据中心需求",
    "算力/半导体产业化": "国产算力芯片、先进封装等产业化",
    "半导体产业链": "半导体材料、存储与设备景气",
    "第三代半导体": "AI数据中心带动碳化硅等需求",
    "光通信": "AI基建带动光模块/CPO需求",
    "PCB": "AI服务器带动PCB与覆铜板景气",
    "电力": "绿电直供、算电协同及电力改革预期",
    "光伏": "光伏去产能与行业预期修复",
    "锂电池": "碳酸锂反弹与储能需求",
    "医药": "创新药与医疗器械政策催化",
    "房地产": "地产政策放松与产业链修复",
    "大消费": "家居建材、食品饮料等消费复苏",
    "教育": "职业教育与AI+教育预期",
    "文化传媒": "游戏影视与IP内容催化",
    "AI应用": "AI营销、短剧等应用落地",
    "军工": "商业航天与军工装备景气",
    "油气": "国际油价波动与油气板块",
    "稀土永磁": "稀土供给与磁材需求",
    "充电桩": "充电基建与换电政策",
    "电子特气/化工": "电子特气涨价与氟化工景气",
    "氟化工": "氢氟酸及制冷剂产业链景气",
    "猪肉": "产能去化与猪价见底预期",
    "并购重组": "股权转让、借壳等事件活跃",
    "体育产业": "体育赛事相关催化",
    "其他概念": "未能归入当日主线",
}

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


def _code_to_em_symbol(code: str) -> str:
    """6 位代码 → 东财 F10 代码 SZ/SH"""
    c = str(code or "").strip().zfill(6)
    if c.startswith(("5", "6", "9")):
        return f"SH{c}"
    return f"SZ{c}"


def _fetch_em_stock_concepts(code: str) -> list:
    """拉取个股所属概念/板块（东方财富 CoreConception）"""
    import requests

    try:
        resp = requests.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax",
            params={"code": _code_to_em_symbol(code)},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == -1:
            return []
        items = data.get("ssbk") or []
        ranked = sorted(
            items,
            key=lambda x: int(x.get("BOARD_RANK") or 999),
        )
        names = []
        for item in ranked:
            name = (item.get("BOARD_NAME") or "").strip()
            if name and name not in names:
                names.append(name)
        return names[:20]
    except Exception as e:
        logger.debug("东财所属概念 %s 获取失败: %s", code, e)
        return []


def _merge_stock_concept_tags(stock: dict, ths_info: Optional[dict] = None) -> list:
    """合并东财所属概念 + 同花顺概念，去重保序"""
    ths_info = ths_info if ths_info is not None else {}
    ths_tags = ths_info.get("concept_tags") if isinstance(ths_info, dict) else []
    if not ths_tags:
        ths_tags = stock.get("ths_concept_tags") or []
    em_tags = stock.get("em_concept_tags") or []
    seen = set()
    merged = []
    for tag in list(em_tags) + list(ths_tags):
        t = str(tag).strip()
        if t and t not in seen:
            seen.add(t)
            merged.append(t)
    return merged


def _enrich_stocks_concepts(stocks: list, ths_hot_map: dict) -> None:
    """批量补充个股所属概念（东财），写入 stock_concept_tags"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not stocks:
        return
    codes = [s.get("code") for s in stocks if s.get("code")]
    em_map: dict = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_em_stock_concepts, code): code for code in codes
        }
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                em_map[code] = fut.result()
            except Exception:
                em_map[code] = []

    filled = 0
    for s in stocks:
        code = s.get("code", "")
        s["em_concept_tags"] = em_map.get(code, [])
        s["stock_concept_tags"] = _merge_stock_concept_tags(
            s, ths_hot_map.get(code, {})
        )
        if s["stock_concept_tags"]:
            filled += 1
    logger.info(
        "所属概念 enrichment: %s/%s 只股票有概念标签",
        filled,
        len(stocks),
    )


def _stock_concept_text(stock: dict, *, weighted: bool = False) -> str:
    """所属概念文本；weighted=True 时重复以提高规则/匹配权重"""
    tags = (
        stock.get("stock_concept_tags")
        or stock.get("em_concept_tags")
        or stock.get("ths_concept_tags")
        or []
    )
    blob = " ".join(str(t) for t in tags if t)
    if weighted and blob:
        return (blob + " ") * CONCEPT_TEXT_REPEAT
    return blob


def _format_stock_prompt_line(stock: dict) -> str:
    """统一 prompt 行：所属概念置顶标注"""
    ths_tags = stock.get("ths_concept_tags") or []
    ths_tag_str = ",".join(str(t) for t in ths_tags if t) if ths_tags else ""
    stock_concepts = stock.get("stock_concept_tags") or []
    concept_str = ",".join(stock_concepts) if stock_concepts else "无"
    rule_hint = _hint_label_from_stock(stock) or "无"
    return (
        f"{stock['code']} {stock['name']} 行业:{stock.get('industry', '')} "
        f"连板:{stock.get('boards', 1)} 涨停统计:{stock.get('zt_stat') or ''} "
        f"所属概念【重点】:[{concept_str}] "
        f"规则参考:{rule_hint} "
        f"同花顺热度:{stock.get('ths_rank') or '-'} "
        f"同花顺标题:{stock.get('ths_analyse_title') or ''} "
        f"同花顺概念:[{ths_tag_str}] "
        f"同花顺分析:{(stock.get('ths_analyse') or '')[:260]}"
    )


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


def _stock_rule_text(stock: dict) -> str:
    parts = [
        _stock_concept_text(stock, weighted=True),
        stock.get("name") or "",
        stock.get("industry") or "",
        stock.get("ths_analyse_title") or "",
        " ".join(str(t) for t in (stock.get("ths_concept_tags") or []) if t),
        (stock.get("ths_analyse") or "")[:240],
    ]
    return " ".join(p for p in parts if p)


def _rule_scores_from_stock(stock: dict) -> dict:
    text = _stock_rule_text(stock)
    concepts = " ".join(
        str(t) for t in (stock.get("stock_concept_tags") or []) if t
    )
    if not text.strip():
        return {}
    scores = {}
    for tag, keywords in GENERAL_THEME_KEYWORD_RULES:
        score = 0
        for kw in keywords:
            if not kw or kw not in text:
                continue
            if kw in concepts:
                score += CONCEPT_MATCH_WEIGHT
            else:
                score += 1
        if score:
            scores[tag] = score
    return scores


def _hint_label_from_stock(stock: dict) -> str:
    """规则引擎：通用大类建议"""
    return _assign_broad_tag_from_stock(stock)


def _assign_broad_tag_from_stock(stock: dict) -> str:
    """按所属概念+涨停文本打分，返回通用大类"""
    scores = _rule_scores_from_stock(stock)
    if not scores:
        return ""
    best_tag, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 2:
        return ""
    return best_tag


def _coerce_general_broad_label(label: str, stock: Optional[dict] = None) -> str:
    """将任意标签名规范为通用大类"""
    name = (label or "").strip()
    if _is_other_label(name):
        return "其他概念"
    if name in GENERAL_BROAD_TAG_SET:
        return name
    if name in BROAD_TAG_ALIASES:
        return BROAD_TAG_ALIASES[name]
    for broad in GENERAL_BROAD_TAG_SET:
        if broad != "其他概念" and (broad in name or name in broad):
            return broad
    if stock:
        assigned = _assign_broad_tag_from_stock(stock)
        if assigned:
            return assigned
    return ""


def _prefill_labels_from_rules(stocks: list) -> dict:
    return {
        s["code"]: hint
        for s in stocks
        if (hint := _hint_label_from_stock(s))
    }


def _normalize_label_name(label: str, stock: Optional[dict] = None) -> str:
    """规范为通用大类名称"""
    name = (label or "").strip()
    if name.startswith("其他") and name != "其他概念":
        return ""
    return _coerce_general_broad_label(name, stock)


def _reassign_invalid_labels(labels: dict, stocks: list) -> dict:
    """将空标签/伪「其他XXX」股票并入文本最相近的合法主线"""
    counter = Counter(
        lbl for lbl in labels.values()
        if lbl and lbl != "其他概念" and not lbl.startswith("其他")
    )
    if not counter:
        return labels
    for code, lbl in list(labels.items()):
        norm = _normalize_label_name(lbl)
        if norm:
            labels[code] = norm
            continue
        labels[code] = _best_tag_for_stock(code, labels, stocks, counter)
    return labels


def _label_text_overlap(label: str, stock: dict) -> int:
    """标签名与个股文本重合度；所属概念匹配权重更高"""
    if not label:
        return 0
    score = 0
    concepts = (
        stock.get("stock_concept_tags")
        or stock.get("em_concept_tags")
        or stock.get("ths_concept_tags")
        or []
    )
    for concept in concepts:
        c = str(concept).strip()
        if len(c) < 2:
            continue
        if c in label or label in c:
            score += CONCEPT_MATCH_WEIGHT
        else:
            for part in label.replace("/", " ").replace("+", " ").split():
                part = part.strip()
                if len(part) >= 2 and (part in c or c in part):
                    score += CONCEPT_MATCH_WEIGHT - 1
                    break

    text = _stock_rule_text(stock)
    if not text:
        return score
    for part in label.replace("/", " ").replace("+", " ").split():
        part = part.strip()
        if len(part) >= 2 and part in text:
            score += 2
    if label in text:
        score += 2
    return score


def _best_tag_for_stock(code: str, labels: dict, stocks: list, counter: Counter) -> str:
    """为单只股票找当日最合适的大标签（按文本重合 + 板块规模）"""
    stock_by_code = {s.get("code"): s for s in stocks if s.get("code")}
    st = stock_by_code.get(code) or {}
    candidates = [
        t for t in counter if not _is_other_label(t)
    ]
    if not candidates:
        return "其他概念"
    scored = []
    for tag in candidates:
        overlap = _label_text_overlap(tag, st)
        scored.append((overlap + counter[tag] * 0.01, tag))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else counter.most_common(1)[0][0]


def _merge_synonym_labels(labels: dict, reasons: dict, leaders: dict) -> tuple:
    """合并高度同义的标签名（子串包含且合计≥2只）"""
    counter = Counter(labels.values())
    tag_list = [t for t in counter if not _is_other_label(t)]
    merge_map = {}
    for i, a in enumerate(tag_list):
        for b in tag_list[i + 1:]:
            if a == b:
                continue
            if a in b or b in a:
                keep, drop = (a, b) if counter[a] >= counter[b] else (b, a)
                merge_map[drop] = keep
    for code, lbl in list(labels.items()):
        if lbl in merge_map:
            labels[code] = merge_map[lbl]
    for drop, keep in merge_map.items():
        if drop in reasons and keep not in reasons:
            reasons[keep] = reasons.pop(drop)
        if drop in leaders and keep not in leaders:
            leaders[keep] = leaders.pop(drop)
    return labels, reasons, leaders


def _split_oversized_in_result(
    group_result: dict,
    stocks: list,
    max_ratio: float = 0.30,
) -> dict:
    """对结果中占比过高的标签做二次拆分（限额合并后再执行）"""
    labels = dict((group_result or {}).get("labels") or {})
    reasons = dict((group_result or {}).get("reasons") or {})
    leaders = dict((group_result or {}).get("leaders") or {})
    if not labels:
        return group_result or {}
    n = len(labels)
    threshold = max(8, int(n * max_ratio))
    counter = Counter(labels.values())
    for tag, cnt in list(counter.most_common()):
        if _is_other_label(tag) or cnt <= threshold:
            continue
        codes = [c for c, l in labels.items() if l == tag]
        _split_oversized_tag(tag, codes, stocks, labels, reasons, leaders)
    labels = _reassign_invalid_labels(labels, stocks)
    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def _split_oversized_tag(
    tag_name: str,
    codes: list,
    stocks: list,
    labels: dict,
    reasons: dict,
    leaders: dict,
) -> None:
    """单标签占比过高时，对该批股票二次 AI 拆分"""
    if len(codes) < 8:
        return
    stock_map = {s["code"]: s for s in stocks}
    subset = [stock_map[c] for c in codes if c in stock_map]
    if not subset:
        return
    existing = "、".join(
        t for t in set(labels.values()) if t != tag_name and not _is_other_label(t)
    ) or "（无）"
    lines = [_format_stock_prompt_line(s) for s in subset]
    prompt = build_split_oversized_prompt(tag_name, existing, "\n".join(lines))
    try:
        content = call_claude_for_scenario("limit_up_split", prompt)
        parsed = _parse_grouping_json(content)
        if not parsed.get("labels"):
            return
        for code in codes:
            new_lbl = _normalize_label_name(parsed["labels"].get(code, ""))
            if new_lbl and new_lbl != tag_name:
                labels[code] = new_lbl
        if parsed.get("reasons"):
            reasons.update(parsed["reasons"])
        if parsed.get("leaders"):
            for t, ldr in parsed["leaders"].items():
                if t not in leaders:
                    leaders[t] = ldr
        logger.info(
            "过大标签「%s」已拆分为 %s 个子类",
            tag_name,
            len({labels[c] for c in codes}),
        )
    except Exception as e:
        logger.warning("拆分过大标签「%s」失败: %s", tag_name, e)


def _finalize_group_labels(group_result: dict, stocks: list) -> dict:
    """后处理：规范名称、合并同义/过小标签，不强制七大主线"""
    labels = dict((group_result or {}).get("labels") or {})
    reasons = dict((group_result or {}).get("reasons") or {})
    leaders = dict((group_result or {}).get("leaders") or {})
    if not labels:
        return group_result or {}

    stock_by_code = {s.get("code"): s for s in stocks if s.get("code")}
    for code, lbl in list(labels.items()):
        labels[code] = _normalize_label_name(lbl, stock_by_code.get(code))
    labels = _reassign_invalid_labels(labels, stocks)

    labels, reasons, leaders = _merge_synonym_labels(labels, reasons, leaders)
    counter = Counter(labels.values())

    # 不足 MIN_TAG_STOCKS 的标签并入文本最相近的大标签
    for lbl, cnt in list(counter.items()):
        if _is_other_label(lbl) or cnt >= MIN_TAG_STOCKS:
            continue
        for code, l in list(labels.items()):
            if l != lbl:
                continue
            labels[code] = _best_tag_for_stock(code, labels, stocks, counter)

    active = set(labels.values())
    reasons = {k: v for k, v in reasons.items() if k in active}
    leaders = {k: v for k, v in leaders.items() if k in active}
    result = {"labels": labels, "reasons": reasons, "leaders": leaders}
    return _split_oversized_in_result(result, stocks, max_ratio=0.28)


# 兼容旧调用
_normalize_to_broad_tags = _finalize_group_labels


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

    stock_by_code = {s.get("code"): s for s in stocks if s.get("code")}

    def _fallback_main_for_code(code: str) -> str:
        c = _counter()
        ranked = [t for t, cnt in c.most_common() if not _is_other_label(t)]
        if len(ranked) >= 2 and c[ranked[0]] > len(labels) * 0.25:
            # 避免「其他概念」溢出时全部塞进最大标签
            for tag in ranked[1:]:
                if _label_text_overlap(tag, stock_by_code.get(code) or {}) >= 2:
                    return tag
            return ranked[1]
        return _best_tag_for_stock(code, labels, stocks, c)

    counter = _counter()
    other_codes = [c for c, l in labels.items() if l == "其他概念"]
    if len(other_codes) > MAX_OTHER_STOCKS:
        for code in other_codes[MAX_OTHER_STOCKS:]:
            labels[code] = _fallback_main_for_code(code)
        logger.info(
            "「其他概念」超过 %s 只，已按规则分散并入各主线",
            MAX_OTHER_STOCKS,
        )

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
        reasons["其他概念"] = DEFAULT_THEME_REASONS.get(
            "其他概念", "未能归入当日主线"
        )

    logger.info(
        "分组限额: 标签数=%s, 其他概念=%s只",
        len(active_tags),
        sum(1 for l in labels.values() if l == "其他概念"),
    )
    result = {"labels": labels, "reasons": reasons, "leaders": leaders}
    return _split_oversized_in_result(result, stocks, max_ratio=0.25)


def _claude_group_labels_for_stocks(stocks: list) -> dict:
    """对涨停列表调用 Claude，返回 labels/reasons 结构
    优先从数据库获取近期已有标签，注入 prompt 让 AI 复用
    """
    if not stocks or not get_claude_api_key():
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

    lines = [_format_stock_prompt_line(s) for s in stocks]
    prompt = build_group_prompt(known_tags_text, "\n".join(lines))
    parsed = {}
    for attempt in range(2):
        content = call_claude_for_scenario("limit_up_group", prompt)
        try:
            parsed = _parse_grouping_json(content)
        except Exception as e:
            logger.warning("Claude 分组解析异常 attempt=%s: %s", attempt + 1, e)
            parsed = {}
        if parsed.get("labels"):
            return parsed
        logger.warning(
            "Claude 分组解析为空 attempt=%s，原始长度=%s",
            attempt + 1,
            len(content or ""),
        )
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


def _cap_other_bucket(group_result: dict, stocks: list) -> dict:
    """最终兜底：「其他概念」不得超过 MAX_OTHER_STOCKS"""
    labels = dict((group_result or {}).get("labels") or {})
    reasons = dict((group_result or {}).get("reasons") or {})
    leaders = dict((group_result or {}).get("leaders") or {})
    other_codes = [c for c, l in labels.items() if l == "其他概念"]
    if len(other_codes) <= MAX_OTHER_STOCKS:
        return group_result
    counter = Counter(labels.values())
    stock_by_code = {s.get("code"): s for s in stocks if s.get("code")}
    ranked = [t for t, _ in counter.most_common() if not _is_other_label(t)]
    overflow = other_codes[MAX_OTHER_STOCKS:]
    for i, code in enumerate(overflow):
        st = stock_by_code.get(code) or {}
        scored = sorted(
            (( _label_text_overlap(tag, st), tag) for tag in ranked),
            reverse=True,
        )
        if scored and scored[0][0] > 0:
            labels[code] = scored[0][1]
        elif ranked:
            labels[code] = ranked[i % len(ranked)]
        else:
            labels[code] = "其他概念"
    logger.info(
        "「其他概念」从 %s 只压至 %s 只",
        len(other_codes),
        sum(1 for l in labels.values() if l == "其他概念"),
    )
    return {"labels": labels, "reasons": reasons, "leaders": leaders}


def _group_stocks_fresh(stocks: list) -> dict:
    """全新归纳：规则通用大类 + AI 补充 reason/leader，标签强制落通用大类"""
    rule_labels = {
        s["code"]: _assign_broad_tag_from_stock(s)
        for s in stocks
        if s.get("code")
    }
    ai_result = _claude_group_labels_for_stocks(stocks)
    if not (ai_result or {}).get("labels"):
        raise ValueError("AI 分组未返回有效标签")
    labels = {}
    for s in stocks:
        code = s.get("code", "")
        if not code:
            continue
        ai_lbl = _coerce_general_broad_label(
            (ai_result.get("labels") or {}).get(code, ""), s
        )
        rule_lbl = rule_labels.get(code) or ""
        if rule_lbl:
            labels[code] = rule_lbl
        else:
            labels[code] = ai_lbl
    reasons = dict((ai_result or {}).get("reasons") or {})
    leaders = dict((ai_result or {}).get("leaders") or {})
    group_result = {"labels": labels, "reasons": reasons, "leaders": leaders}
    group_result = _finalize_group_labels(group_result, stocks)
    group_result = _enforce_group_limits(group_result, stocks)
    group_result = _cap_other_bucket(group_result, stocks)
    group_result = _split_oversized_in_result(group_result, stocks, max_ratio=0.20)
    return _cap_other_bucket(group_result, stocks)


def _smart_group_stocks(stocks: list, dt: str, *, fresh: bool = False) -> dict:
    """智能分组：fresh=True 时忽略库内旧标签，按复盘模板全量重算"""
    if fresh or not get_limit_up_stocks_by_date(dt):
        logger.info("全量 AI 归纳（按当日涨停因果动态合并标签）")
        return _group_stocks_fresh(stocks)

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

    # 3. 未匹配的调 AI（以 AI 结果为准）
    ai_result = {}
    if unmatched:
        ai_result = _claude_group_labels_for_stocks(unmatched)
        for s in unmatched:
            code = s.get("code", "")
            ai_lbl = _coerce_general_broad_label(
                ((ai_result or {}).get("labels") or {}).get(code, ""), s
            )
            labels[code] = ai_lbl or "其他概念"

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

        lines = [_format_stock_prompt_line(s) for s in other_stocks]
        regroup_prompt = build_regroup_prompt(
            existing_labels_text or "（无）", "\n".join(lines)
        )
        try:
            content = call_claude_for_scenario("limit_up_regroup", regroup_prompt)
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
    group_result = _finalize_group_labels(group_result, stocks)
    group_result = _enforce_group_limits(group_result, stocks)
    return _cap_other_bucket(group_result, stocks)


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
            "em_concept_tags": [],
            "stock_concept_tags": [],
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


def _prev_trading_date(dt_clean: str) -> Optional[str]:
    """上一交易日 YYYYMMDD"""
    d = datetime.strptime(dt_clean, "%Y%m%d")
    for _ in range(10):
        d -= timedelta(days=1)
        if d.weekday() < 5:
            return d.strftime("%Y%m%d")
    return None


_emotion_records_cache = {"ts": 0.0, "records": []}
EMOTION_CACHE_TTL_SEC = 300


def _get_emotion_record(dt_clean: str) -> Optional[dict]:
    """按日期取情绪周期记录（带短时缓存）"""
    global _emotion_records_cache
    now = time.time()
    if now - _emotion_records_cache.get("ts", 0) > EMOTION_CACHE_TTL_SEC:
        try:
            from routes.emotion_cycle import _fetch_emotion_records
            _emotion_records_cache = {
                "ts": now,
                "records": _fetch_emotion_records(),
            }
        except Exception as e:
            logger.warning("拉取情绪周期数据失败: %s", e)
            if not _emotion_records_cache.get("records"):
                return None
    dt_display = f"{dt_clean[:4]}-{dt_clean[4:6]}-{dt_clean[6:8]}"
    for record in _emotion_records_cache.get("records") or []:
        if record.get("date") == dt_display:
            return record
    return None


def _safe_mean_pct(values) -> Optional[float]:
    nums = []
    for v in values:
        try:
            if v is None or v != v:  # NaN
                continue
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _compute_premium_rates(dt_clean: str) -> dict:
    """昨日涨停股在当日的平均涨跌幅（首板/连板分组）"""
    empty = {
        "limit_up_premium_pct": None,
        "first_board_premium_pct": None,
        "consec_board_premium_pct": None,
    }
    try:
        import akshare as ak
        df = ak.stock_zt_pool_previous_em(date=dt_clean)
    except Exception as e:
        logger.debug("stock_zt_pool_previous_em 不可用 date=%s: %s", dt_clean, e)
        return empty
    if df is None or df.empty:
        return empty

    change_col = next((c for c in df.columns if "涨跌幅" in str(c)), None)
    boards_col = next(
        (c for c in df.columns if "昨日连板" in str(c)),
        None,
    )
    if not change_col:
        return empty

    changes = df[change_col]
    result = {"limit_up_premium_pct": _safe_mean_pct(changes)}
    if boards_col:
        try:
            boards = df[boards_col].fillna(1).astype(int)
        except (TypeError, ValueError):
            boards = None
        if boards is not None:
            result["first_board_premium_pct"] = _safe_mean_pct(changes[boards <= 1])
            result["consec_board_premium_pct"] = _safe_mean_pct(changes[boards > 1])
    return result


def _akshare_sentiment_counts(dt_clean: str) -> dict:
    """akshare 跌停池/炸板池家数（情绪 API 不可用时的兜底）"""
    out = {"limit_down_count": None, "broken_board_count": None}
    try:
        import akshare as ak
        if out["limit_down_count"] is None:
            dt_df = ak.stock_zt_pool_dtgc_em(date=dt_clean)
            out["limit_down_count"] = len(dt_df) if dt_df is not None else None
        if out["broken_board_count"] is None:
            zb_df = ak.stock_zt_pool_zbgc_em(date=dt_clean)
            out["broken_board_count"] = len(zb_df) if zb_df is not None else None
    except Exception as e:
        logger.debug("akshare 涨跌停池兜底失败 date=%s: %s", dt_clean, e)
    return out


def _build_market_stats(dt_clean: str, echelon_total: int = 0) -> dict:
    """市场情绪指标：上涨家数、打板成功率、跌停、炸板、炸板率、昨日涨停/连板溢价"""
    stats = {
        "rise_count": None,
        "board_hit_rate": None,
        "limit_down_count": None,
        "broken_board_count": None,
        "broken_board_rate": None,
        "limit_up_premium_pct": None,
        "first_board_premium_pct": None,
        "consec_board_premium_pct": None,
    }
    record = _get_emotion_record(dt_clean)
    limit_up_for_rate = echelon_total
    if record:
        for key, src in (
            ("limit_down_count", "limit_down_count"),
            ("broken_board_count", "broken_board_count"),
        ):
            val = record.get(src)
            if val is not None:
                stats[key] = int(val)
        rise = record.get("rise_count")
        if rise is not None:
            try:
                stats["rise_count"] = int(rise)
            except (TypeError, ValueError):
                pass
        hit = record.get("board_hit_rate")
        if hit is not None:
            try:
                stats["board_hit_rate"] = round(float(hit), 2)
            except (TypeError, ValueError):
                pass
        lu = record.get("limit_up_count")
        if lu is not None:
            limit_up_for_rate = int(lu)

    ak_fallback = _akshare_sentiment_counts(dt_clean)
    if stats["limit_down_count"] is None and ak_fallback["limit_down_count"] is not None:
        stats["limit_down_count"] = ak_fallback["limit_down_count"]
    if stats["broken_board_count"] is None and ak_fallback["broken_board_count"] is not None:
        stats["broken_board_count"] = ak_fallback["broken_board_count"]

    broken = stats.get("broken_board_count")
    if broken is not None and limit_up_for_rate is not None:
        denom = int(limit_up_for_rate) + int(broken)
        if denom > 0:
            stats["broken_board_rate"] = round(int(broken) / denom * 100, 1)

    stats.update(_compute_premium_rates(dt_clean))
    return stats


def _build_summary(stocks: list, dt_clean: str) -> dict:
    total = len(stocks)
    first_board_count = sum(1 for s in stocks if s.get("boards") == 1)
    summary = {
        "total": total,
        "first_board_count": first_board_count,
        "consec_count": total - first_board_count,
        "max_boards": max((s.get("boards") or 0 for s in stocks), default=0),
    }
    summary.update(_build_market_stats(dt_clean, echelon_total=total))
    return summary


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
        "summary": _build_summary(stocks, dt_clean),
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

        _enrich_stocks_concepts(stocks, ths_hot_map)
        group_result = _smart_group_stocks(stocks, dt_clean, fresh=force)

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
    dt_clean = dt.replace("-", "") if dt else _default_echelon_dt()
    return {
        "echelons": echelon_list,
        "ths_hot": ths_hot_list[:20],
        "date": dt,
        "theme_ranking": theme_ranking,
        "ai": ai_meta,
        "summary": _build_summary(stocks, dt_clean),
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
        "summary": _build_summary([], dt_clean),
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
            if get_claude_api_key():
                try:
                    info = ths_info or {}
                    existing_text = '、'.join(db_tag_names[:20]) if db_tag_names else '（今日暂无题材标签）'
                    prompt = (
                        STOCK_THEME_PROMPT
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
                    content = call_claude_for_scenario("limit_up_stock_theme", prompt)
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

