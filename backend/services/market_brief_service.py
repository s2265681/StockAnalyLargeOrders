"""盘前资讯服务：拉取海外指数、多源资讯、生成 AI 摘要、读写 market_brief 表"""
import json
import logging
from datetime import date

from services.market_brief_fetchers import (
    fetch_all_news,
    fetch_overseas_indices,
    format_news_for_prompt,
)
from utils.claude_client import call_claude_for_scenario
from utils.db import execute_query, execute_write
from utils.job_notify import send_plain_email

logger = logging.getLogger(__name__)

# 兼容测试：旧版解析函数入口
def _parse_sina_response(text: str) -> list[dict]:
    from services.market_brief_fetchers import _parse_sina_overseas
    indices = _parse_sina_overseas(text)
    if not indices:
        raise RuntimeError('未从新浪财经解析到任何指数数据')
    return indices


def generate_ai_summary(overseas: list[dict], news: list[dict] | None = None) -> str:
    """调用 Claude 生成简洁盘前摘要。"""
    if not overseas:
        raise ValueError('overseas 列表为空，无法生成摘要')

    idx_lines = []
    for idx in overseas:
        sign = '+' if idx['change_pct'] >= 0 else ''
        idx_lines.append(f"- {idx['name']}：{sign}{idx['change_pct']}%")

    news = news or []
    prompt = (
        '你是 A 股盘前助手。根据以下数据写一份**简洁明了**的今日盘前参考（纯中文正文，不要 markdown）：\n\n'
        '## 海外指数（昨夜）\n'
        + '\n'.join(idx_lines)
        + '\n\n## 市场资讯摘录\n'
        + format_news_for_prompt(news)
        + '\n\n## 输出要求\n'
        '1. 海外市场：1-2 句总评\n'
        '2. 重要资讯：提炼 2-4 条与 A 股相关的要点（合并重复，忽略无关八卦）\n'
        '3. 今日关注：2-3 个可能的方向或板块（结合海外与资讯推断）\n'
        '4. 风险：1 句\n'
        '总字数 180-280 字，分四段，每段前加【海外】【资讯】【关注】【风险】作为小标题（仅此四字标签）。'
    )

    text = call_claude_for_scenario('market_brief', prompt)
    if not text:
        raise RuntimeError('Claude 返回空摘要')
    return text.strip()


def save_brief(
    brief_date: str,
    overseas: list[dict],
    ai_summary: str,
    news: list[dict] | None = None,
) -> None:
    """upsert 当日盘前资讯到 market_brief 表。"""
    overseas_json = json.dumps(overseas, ensure_ascii=False)
    news_json = json.dumps(news or [], ensure_ascii=False)
    try:
        execute_write(
            'INSERT INTO market_brief (brief_date, overseas_json, news_json, ai_summary, generated_at) '
            'VALUES (%s, %s, %s, %s, NOW()) '
            'ON DUPLICATE KEY UPDATE overseas_json=%s, news_json=%s, ai_summary=%s, generated_at=NOW()',
            (brief_date, overseas_json, news_json, ai_summary, overseas_json, news_json, ai_summary),
        )
    except Exception as e:
        if 'news_json' not in str(e):
            raise
        logger.warning('news_json 列不存在，回退旧表结构: %s', e)
        execute_write(
            'INSERT INTO market_brief (brief_date, overseas_json, ai_summary, generated_at) '
            'VALUES (%s, %s, %s, NOW()) '
            'ON DUPLICATE KEY UPDATE overseas_json=%s, ai_summary=%s, generated_at=NOW()',
            (brief_date, overseas_json, ai_summary, overseas_json, ai_summary),
        )
    logger.info('已保存 market_brief date=%s', brief_date)


def build_market_brief_email_body(
    brief_date: str,
    overseas: list[dict],
    news: list[dict],
    ai_summary: str,
) -> str:
    """组装盘前资讯邮件正文（纯文本）。"""
    lines = [f'【NiuNIuNiu 盘前资讯】{brief_date}', '']

    lines.append('【海外指数（昨夜）】')
    for idx in overseas:
        sign = '+' if idx['change_pct'] >= 0 else ''
        lines.append(f"  {idx['name']} {sign}{idx['change_pct']}%")

    lines.append('')
    lines.append(f'【资讯摘录】共 {len(news)} 条')
    for it in news[:15]:
        t = f" [{it['time']}]" if it.get('time') else ''
        lines.append(f"  · [{it['source']}]{t} {it['title']}")
    if len(news) > 15:
        lines.append(f'  … 另有 {len(news) - 15} 条未列出')

    lines.append('')
    lines.append('【AI 盘前摘要】')
    lines.append(ai_summary.strip())
    lines.append('')
    lines.append('— 自动生成于每日 8:30 · 网页「情绪周期」顶部可查看')
    return '\n'.join(lines)


def send_market_brief_email(
    brief_date: str,
    overseas: list[dict],
    news: list[dict],
    ai_summary: str,
) -> bool:
    """任务成功后把盘前资讯发到配置的邮箱。"""
    subject = f'[盘前资讯] {brief_date} A股开盘参考'
    body = build_market_brief_email_body(brief_date, overseas, news, ai_summary)
    ok = send_plain_email(subject, body, tag='盘前资讯')
    if ok:
        logger.info('盘前资讯邮件已发送 date=%s', brief_date)
    else:
        logger.warning('盘前资讯邮件未发送（请检查 SMTP 与 JOB_ALERT_EMAIL）')
    return ok


def generate_today_brief(*, force: bool = False, send_email: bool = True) -> dict:
    """生成并保存今日盘前资讯，返回完整 brief 数据。"""
    today = date.today().isoformat()
    if not force and get_today_brief() is not None:
        logger.info('今日 %s 已有盘前资讯，跳过生成', today)
        return get_today_brief()

    logger.info('生成盘前资讯 date=%s force=%s', today, force)
    overseas = fetch_overseas_indices()
    news = fetch_all_news(limit_per_source=6)
    summary = generate_ai_summary(overseas, news)
    save_brief(today, overseas, summary, news)
    if send_email:
        send_market_brief_email(today, overseas, news, summary)
    return get_today_brief()


def get_today_brief() -> dict | None:
    """读取今日盘前资讯，无数据时返回 None。"""
    today = date.today().isoformat()
    try:
        rows = execute_query(
            'SELECT brief_date, overseas_json, news_json, ai_summary, generated_at '
            'FROM market_brief WHERE brief_date = %s',
            (today,),
        )
    except Exception:
        rows = execute_query(
            'SELECT brief_date, overseas_json, ai_summary, generated_at '
            'FROM market_brief WHERE brief_date = %s',
            (today,),
        )
    if not rows:
        return None
    r = rows[0]
    news_raw = r.get('news_json')
    return {
        'brief_date': str(r['brief_date']),
        'overseas': json.loads(r['overseas_json']),
        'news': json.loads(news_raw) if news_raw else [],
        'ai_summary': r['ai_summary'],
        'generated_at': str(r['generated_at']),
    }
