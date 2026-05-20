"""盘前资讯服务：拉取海外指数、生成 AI 摘要、读写 market_brief 表"""
import json
import logging
import re
import subprocess
from datetime import date

from utils.db import execute_query, execute_write

logger = logging.getLogger(__name__)

_NAME_MAP = {
    'b_INDEXDOW':    '道指',
    'b_INDEXNASDAQ': '纳指',
    'b_INDEXSP':     '标普',
    'b_INDEXHK':     '恒指',
    'b_INDEXNK225':  '日经',
}


def _parse_sina_response(text: str) -> list[dict]:
    """解析新浪财经海外指数响应文本，返回指数列表。"""
    indices = []
    pattern = re.compile(r'var hq_str_(b_INDEX\w+)="([^"]+)"')
    for m in pattern.finditer(text):
        sym = m.group(1)
        fields = m.group(2).split(',')
        if len(fields) < 5:
            continue
        try:
            close = float(fields[1])
            change_pct = float(fields[4])
        except (ValueError, IndexError):
            continue
        indices.append({
            'symbol': sym,
            'name': _NAME_MAP.get(sym, sym),
            'close': close,
            'change_pct': round(change_pct, 2),
        })
    if not indices:
        raise RuntimeError('未从新浪财经解析到任何指数数据')
    return indices


def fetch_overseas_indices() -> list[dict]:
    """用 curl 子进程拉取新浪财经海外指数（eventlet 安全）。"""
    symbols = 'b_INDEXDOW,b_INDEXNASDAQ,b_INDEXSP,b_INDEXHK,b_INDEXNK225'
    url = f'https://hq.sinajs.cn/list={symbols}'
    result = subprocess.run(
        ['curl', '-s', '--max-time', '15',
         '-H', 'Referer: https://finance.sina.com.cn', url],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        raise RuntimeError(f'curl 拉取指数失败: {result.stderr.strip()}')
    return _parse_sina_response(result.stdout)


def generate_ai_summary(overseas: list[dict]) -> str:
    """调用 Claude 生成摘要文本。"""
    lines = []
    for idx in overseas:
        sign = '+' if idx['change_pct'] >= 0 else ''
        lines.append(f"- {idx['name']}：{sign}{idx['change_pct']}%")

    prompt = (
        '今日盘前海外市场数据（昨夜收盘）：\n'
        + '\n'.join(lines)
        + '\n\n请生成一份简洁的今日A股盘前参考摘要，包含：'
        '\n1. 海外市场简评（1-2句）'
        '\n2. 今日A股值得关注的板块方向（2-3个，结合海外表现推断）'
        '\n3. 风险提示（1句）'
        '\n\n要求：纯中文，总字数不超过200字，不需要任何标题，直接正文。'
    )

    from utils.claude_client import call_claude_for_scenario
    text = call_claude_for_scenario('market_brief', prompt)
    if not text:
        raise RuntimeError('Claude 返回空摘要')
    return text


def save_brief(brief_date: str, overseas: list[dict], ai_summary: str) -> None:
    """upsert 当日盘前资讯到 market_brief 表。"""
    overseas_json = json.dumps(overseas, ensure_ascii=False)
    execute_write(
        'INSERT INTO market_brief (brief_date, overseas_json, ai_summary, generated_at) '
        'VALUES (%s, %s, %s, NOW()) '
        'ON DUPLICATE KEY UPDATE overseas_json=%s, ai_summary=%s, generated_at=NOW()',
        (brief_date, overseas_json, ai_summary, overseas_json, ai_summary),
    )
    logger.info('已保存 market_brief date=%s', brief_date)


def get_today_brief() -> dict | None:
    """读取今日盘前资讯，无数据时返回 None。"""
    today = date.today().isoformat()
    rows = execute_query(
        'SELECT brief_date, overseas_json, ai_summary, generated_at '
        'FROM market_brief WHERE brief_date = %s',
        (today,),
    )
    if not rows:
        return None
    r = rows[0]
    return {
        'brief_date': str(r['brief_date']),
        'overseas': json.loads(r['overseas_json']),
        'ai_summary': r['ai_summary'],
        'generated_at': str(r['generated_at']),
    }
