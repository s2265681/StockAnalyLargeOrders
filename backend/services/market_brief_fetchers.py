"""盘前资讯多源抓取（curl 子进程，eventlet 安全）"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)

_CURL_ENV = {**os.environ, 'no_proxy': '*', 'NO_PROXY': '*'}


def _curl_get(url: str, *, headers: list[str] | None = None, timeout: int = 20) -> str:
    cmd = ['curl', '-s', '--max-time', str(min(timeout, 15)), '-H', 'User-Agent: Mozilla/5.0']
    for h in headers or []:
        cmd.extend(['-H', h])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, timeout=timeout, env=_CURL_ENV)
    if result.returncode != 0:
        err = result.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'curl 失败: {err or result.returncode}')
    raw = result.stdout
    try:
        return raw.decode('gbk')
    except UnicodeDecodeError:
        return raw.decode('utf-8', errors='replace')


# ---------- 海外指数 ----------

_OVERSEAS_NAME = {
    'gb_dji': '道指',
    'gb_ixic': '纳指',
    'gb_inx': '标普',
    'rt_hkHSI': '恒指',
    'gb_nikkei': '日经',
    'N225': '日经',
}

_SINA_SYMBOLS = 'gb_dji,gb_ixic,gb_inx,rt_hkHSI,gb_nikkei'


def _parse_sina_overseas(text: str) -> list[dict]:
    """解析新浪 gb_* / rt_hk* 指数（旧 b_INDEX* 已返回空串）。"""
    indices: list[dict] = []
    pattern = re.compile(r'var hq_str_([\w$]+)="([^"]*)"')
    for sym, body in pattern.findall(text):
        if not body.strip():
            continue
        fields = body.split(',')
        try:
            if sym == 'rt_hkHSI' and len(fields) >= 9:
                close = float(fields[5])
                change_pct = float(fields[8])
            elif sym.startswith('gb_') and len(fields) >= 3:
                close = float(fields[1])
                change_pct = float(fields[2])
            else:
                continue
        except (ValueError, IndexError):
            continue
        indices.append({
            'symbol': sym,
            'name': _OVERSEAS_NAME.get(sym, sym),
            'close': close,
            'change_pct': round(change_pct, 2),
        })
    return indices


def _fetch_overseas_eastmoney() -> list[dict]:
    url = (
        'https://push2.eastmoney.com/api/qt/ulist.np/get'
        '?fltt=2&fields=f2,f3,f12,f14&secids=100.DJIA,100.NDX,100.SPX,100.HSI,100.N225'
    )
    text = _curl_get(url)
    data = json.loads(text)
    diff = data.get('data', {}).get('diff') or []
    sym_map = {'DJIA': 'gb_dji', 'NDX': 'gb_ixic', 'SPX': 'gb_inx', 'HSI': 'rt_hkHSI', 'N225': 'N225'}
    out = []
    for row in diff:
        code = row.get('f12', '')
        sym = sym_map.get(code, code)
        out.append({
            'symbol': sym,
            'name': _OVERSEAS_NAME.get(sym, row.get('f14', code)),
            'close': float(row.get('f2') or 0),
            'change_pct': round(float(row.get('f3') or 0), 2),
        })
    return out


def fetch_overseas_indices() -> list[dict]:
    """新浪主源 + 东财补缺（日经等）。"""
    url = f'https://hq.sinajs.cn/list={_SINA_SYMBOLS}'
    text = _curl_get(url, headers=['Referer: https://finance.sina.com.cn'])
    indices = _parse_sina_overseas(text)

    have = {i['name'] for i in indices}
    need_names = {'道指', '纳指', '标普', '恒指', '日经'}
    if need_names - have:
        logger.warning('新浪指数不完整(%s)，尝试东财补缺', [i['name'] for i in indices])
        try:
            em = _fetch_overseas_eastmoney()
            by_name = {i['name']: i for i in indices}
            for row in em:
                by_name.setdefault(row['name'], row)
            indices = [by_name[k] for k in ('道指', '纳指', '标普', '恒指', '日经') if k in by_name]
        except Exception as e:
            logger.warning('东财指数兜底失败: %s', e)

    if len(indices) < 3:
        raise RuntimeError('未能解析海外指数（新浪 b_INDEX* 已下线，请检查网络或东财接口）')
    return indices


# ---------- 资讯条目 ----------

def _news_item(source: str, title: str, snippet: str = '', time_str: str = '') -> dict:
    title = (title or '').strip()
    snippet = (snippet or title)[:200]
    if not title:
        return None
    return {'source': source, 'title': title, 'snippet': snippet, 'time': time_str}


def fetch_eastmoney_flash(limit: int = 8) -> list[dict]:
    url = (
        'https://np-listapi.eastmoney.com/comm/web/getFastNewsList'
        f'?client=web&biz=web_724&fastColumn=102&pageSize={limit}&req_trace=1'
    )
    try:
        data = json.loads(_curl_get(url))
        items = []
        payload = data.get('data') if isinstance(data, dict) else None
        for row in (payload or {}).get('fastNewsList') or []:
            if not isinstance(row, dict):
                continue
            title = (row.get('title') or row.get('summary') or '').strip()
            summary = (row.get('summary') or title or '')[:200]
            it = _news_item('东方财富', title[:80], summary, row.get('showTime', '') or '')
            if it:
                items.append(it)
        return items[:limit]
    except Exception as e:
        logger.warning('东方财富快讯失败: %s', e)
        return []


def fetch_ths_news(limit: int = 8) -> list[dict]:
    """同花顺财经推送"""
    url = f'https://news.10jqka.com.cn/tapp/news/push/stock/?page=1&pagesize={limit}&tag=&track=website'
    try:
        data = json.loads(_curl_get(url))
        items = []
        for row in data.get('data', {}).get('list') or []:
            digest = (row.get('short') or row.get('digest') or '')[:200]
            it = _news_item('同花顺', row.get('title', ''), digest, '')
            if it:
                items.append(it)
        return items[:limit]
    except Exception as e:
        logger.warning('同花顺资讯失败: %s', e)
        return []


def fetch_jin10_flash(limit: int = 6) -> list[dict]:
    """金十数据快讯（财联社 API 需签名，用公开电报源补充）"""
    import time
    url = f'https://www.jin10.com/flash_newest.js?t={int(time.time())}'
    try:
        text = _curl_get(url, headers=['Referer: https://www.jin10.com/'])
        m = re.search(r'var newest\s*=\s*(\[.*?\]);', text, re.DOTALL)
        if not m:
            return []
        rows = json.loads(m.group(1))
        items = []
        for row in rows[:limit * 2]:
            data = row.get('data') or {}
            content = (data.get('content') or data.get('vip_title') or '').strip()
            content = re.sub(r'<br\s*/?>', ' ', content)
            content = re.sub(r'<[^>]+>', '', content)
            if not content or data.get('lock'):
                continue
            it = _news_item('金十快讯', content[:80], content[:200], row.get('time', ''))
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        return items
    except Exception as e:
        logger.warning('金十快讯失败: %s', e)
        return []


def fetch_ths_hot_topics(limit: int = 5) -> list[dict]:
    """同花顺热股（盘面关注度）"""
    urls = [
        'https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock?stock_type=a&type=hour&list_type=normal',
    ]
    for url in urls:
        try:
            data = json.loads(_curl_get(url, headers=['Referer: https://www.10jqka.com.cn/']))
            if data.get('status_code') != 0:
                continue
            items = []
            for row in data.get('data', {}).get('stock_list') or []:
                name = row.get('name', '')
                code = str(row.get('code', '')).zfill(6)
                raw_reason = row.get('reason') or row.get('tag') or ''
                if isinstance(raw_reason, dict):
                    raw_reason = raw_reason.get('name') or raw_reason.get('title') or ''
                reason = str(raw_reason).strip()
                title = f'{name}({code})' + (f' {reason}' if reason else '')
                it = _news_item('同花顺热股', title, reason, '')
                if it:
                    items.append(it)
                if len(items) >= limit:
                    return items
        except Exception as e:
            logger.warning('同花顺热股失败: %s', e)
    return []


def fetch_cls_telegraph(limit: int = 6) -> list[dict]:
    """财联社：公开 API 需签名，尝试备用；失败则返回空"""
    url = 'https://api3.cls.cn/v1/roll/get_roll_list?app=CailianpressWeb&os=web&sv=8.4.6&rn=20'
    try:
        data = json.loads(_curl_get(url, headers=['Referer: https://www.cls.cn/telegraph']))
        if str(data.get('errno')) not in ('0', '200'):
            return []
        roll = data.get('data') or []
        if isinstance(roll, dict):
            roll = roll.get('roll_data') or roll.get('list') or []
        items = []
        for row in roll[:limit * 2]:
            title = (row.get('title') or row.get('content') or '').strip()
            it = _news_item('财联社', title[:80], title[:200], row.get('ctime', ''))
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        return items
    except Exception as e:
        logger.warning('财联社失败: %s', e)
        return []


def fetch_xueqiu_hot(limit: int = 5) -> list[dict]:
    """雪球热股（需登录时常失败，尽力抓取）"""
    url = f'https://xueqiu.com/statuses/hot/listV2.json?since_id=-1&max_id=-1&size={limit}'
    try:
        data = json.loads(_curl_get(url, headers=['Referer: https://xueqiu.com/']))
        items = []
        for row in data.get('data', {}).get('items') or data.get('items') or []:
            orig = row.get('original') or row
            title = (orig.get('title') or orig.get('description') or '')[:80]
            it = _news_item('雪球', title, title[:200], '')
            if it:
                items.append(it)
            if len(items) >= limit:
                break
        return items
    except Exception as e:
        logger.warning('雪球热榜失败: %s', e)
        return []


def fetch_kaipanla_placeholder(limit: int = 5) -> list[dict]:
    """开盘啦：暂无稳定公开 API，返回空列表"""
    return []


_NEWS_FETCHERS: list[tuple[str, Callable[[int], list[dict]]]] = [
    ('cls', fetch_cls_telegraph),
    ('eastmoney', fetch_eastmoney_flash),
    ('ths', fetch_ths_news),
    ('jin10', fetch_jin10_flash),
    ('ths_hot', fetch_ths_hot_topics),
    ('xueqiu', fetch_xueqiu_hot),
    ('kaipanla', fetch_kaipanla_placeholder),
]


def fetch_all_news(limit_per_source: int = 6) -> list[dict]:
    """聚合多源资讯，按来源去重标题。"""
    seen: set[str] = set()
    all_items: list[dict] = []
    for _name, fn in _NEWS_FETCHERS:
        try:
            batch = fn(limit_per_source)
            logger.info('资讯源 %s: %d 条', _name, len(batch))
            for it in batch:
                key = (it['source'], it['title'][:40])
                if key in seen:
                    continue
                seen.add(key)
                all_items.append(it)
        except Exception as e:
            logger.warning('资讯源 %s 异常: %s', _name, e)
    return all_items[:40]


def format_news_for_prompt(news: list[dict]) -> str:
    if not news:
        return '（暂无额外资讯）'
    lines = []
    for it in news:
        t = f" [{it['time']}]" if it.get('time') else ''
        lines.append(f"- [{it['source']}]{t} {it['title']}")
    return '\n'.join(lines)
