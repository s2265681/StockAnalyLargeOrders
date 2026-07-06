"""
stockapi 额度用尽时返回 00**** / 冰轮**** 等脱敏字段，通过名称前缀 + 板块 + 涨幅/价格反查真实代码。
"""
import json
import logging
import re
import subprocess
from functools import lru_cache
from urllib.parse import quote

logger = logging.getLogger(__name__)

_BOARD_PREFIXES = {
    '00': ('000', '001', '002', '003'),
    '60': ('600', '601', '603', '605', '606'),
    '30': ('300', '301', '302'),
    '68': ('688', '689'),
}

_ZF_TOLERANCE = 2.5
_PRICE_TOLERANCE_PCT = 1.2


_BOARD_EM_FS = {
    '60': 'm:1+t:2',
    '68': 'm:1+t:23',
    '00': 'm:0+t:6',
    '30': 'm:0+t:80',
}


def _is_valid_stock_code(code: str) -> bool:
    c = str(code or "").strip().zfill(6)
    return len(c) == 6 and c.isdigit()


def is_valid_stock_code(code: str) -> bool:
    return _is_valid_stock_code(code)


def _is_masked_code(code: str) -> bool:
    raw = str(code or "")
    return '*' in raw or not _is_valid_stock_code(raw.zfill(6))


def _curl(url: str, ref: str = 'https://gu.qq.com/') -> str:
    try:
        r = subprocess.run(
            ['curl', '-s', '--max-time', '12', '-H', f'Referer: {ref}',
             '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, timeout=15,
        )
        return r.stdout.decode('utf-8', errors='replace')
    except Exception:
        return ''


def _name_prefix(name: str) -> str:
    return re.sub(r'\*+', '', str(name or '')).strip()


def _board_key(code_mask: str) -> str:
    c = str(code_mask or '').replace('*', '').strip()
    return c[:2] if len(c) >= 2 else ''


def _code_matches_board(code: str, board_key: str) -> bool:
    prefixes = _BOARD_PREFIXES.get(board_key)
    if not prefixes:
        return True
    return code.startswith(prefixes)


def _bk_keywords(bk: str) -> list[str]:
    parts = re.split(r'[、,，/|]', str(bk or ''))
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            out.append(p)
        for i in range(len(p) - 1):
            sub = p[i:i + 2]
            if len(sub) == 2 and sub not in out:
                out.append(sub)
    return out[:8]


def _decode_smartbox_name(raw: str) -> str:
    if not raw:
        return ''
    if '\\u' in raw:
        try:
            return raw.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
    return raw


@lru_cache(maxsize=256)
def _lookup_smartbox(name_prefix: str) -> tuple[tuple[str, str, str], ...]:
    if not name_prefix:
        return ()
    text = _curl(
        f'https://smartbox.gtimg.cn/s3/?v=2&q={quote(name_prefix)}&t=all&c=1'
    )
    m = re.search(r'v_hint="([^"]+)"', text)
    if not m:
        return ()
    out = []
    for part in m.group(1).split('^'):
        fields = part.split('~')
        if len(fields) < 3:
            continue
        market, code = fields[0], fields[1].zfill(6)
        name = _decode_smartbox_name(fields[2])
        if not _is_valid_stock_code(code):
            continue
        if len(name_prefix) >= 2 and not name.startswith(name_prefix):
            continue
        out.append((market, code, name))
    return tuple(out)


@lru_cache(maxsize=256)
def _lookup_eastmoney(query: str) -> tuple[tuple[str, str], ...]:
    if not query:
        return ()
    count = 100 if len(query) <= 1 else (50 if len(query) == 2 else 20)
    text = _curl(
        f'https://searchapi.eastmoney.com/api/suggest/get'
        f'?input={quote(query)}&type=14&count={count}',
        ref='https://quote.eastmoney.com/',
    )
    try:
        data = json.loads(text).get('QuotationCodeTable', {}).get('Data') or []
    except Exception:
        return ()
    out = []
    for item in data:
        code = str(item.get('Code') or '').zfill(6)
        name = str(item.get('Name') or '').strip()
        if _is_valid_stock_code(code) and name:
            out.append((code, name))
    return tuple(out)


@lru_cache(maxsize=512)
def _get_quote_snapshot(code: str) -> tuple[float | None, float | None]:
    prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
    text = _curl(f'https://qt.gtimg.cn/q={prefix}{code}')
    if '~' not in text:
        return None, None
    try:
        fields = text.split('"')[1].split('~')
        price = float(fields[3]) if fields[3] else None
        chg = float(fields[32]) if fields[32] else None
        return price, chg
    except Exception:
        return None, None


def _get_change_pct(code: str) -> float | None:
    return _get_quote_snapshot(code)[1]


def _collect_candidates(name_prefix: str, board_key: str, bk: str) -> list[dict]:
    seen: set[str] = set()
    candidates: list[dict] = []

    def add(code: str, name: str, market: str = '') -> None:
        if not _is_valid_stock_code(code) or code in seen:
            return
        if not _code_matches_board(code, board_key):
            return
        seen.add(code)
        candidates.append({'code': code, 'name': name, 'market': market})

    queries: list[str] = []
    if len(name_prefix) >= 2:
        queries.append(name_prefix)
    elif len(name_prefix) == 1:
        queries.append(name_prefix)
    for kw in _bk_keywords(bk):
        if kw not in queries:
            queries.append(kw)

    for q in queries:
        for market, code, name in _lookup_smartbox(q):
            add(code, name, market)
        for code, name in _lookup_eastmoney(q):
            if len(name_prefix) <= 1:
                if not name.startswith(name_prefix):
                    continue
            elif not name.startswith(name_prefix):
                continue
            add(code, name)

    return candidates


def _candidate_score(code: str, target_zf: float, target_price: float) -> float | None:
    price, chg = _get_quote_snapshot(code)
    if chg is None:
        return None

    zf_diff = abs(chg - target_zf)
    if target_price and target_price > 0 and price:
        price_diff_pct = abs(price - target_price) / target_price * 100
        if zf_diff > _ZF_TOLERANCE and price_diff_pct > _PRICE_TOLERANCE_PCT:
            return None
        if price_diff_pct > _PRICE_TOLERANCE_PCT * 2:
            return None
        return zf_diff + price_diff_pct * 0.35

    if zf_diff > _ZF_TOLERANCE:
        return None
    return zf_diff


def _pick_best_candidate(
    candidates: list[dict],
    target_zf: float,
    target_price: float,
    name_prefix: str = '',
) -> dict | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        c = candidates[0]
        if len(name_prefix) >= 2 and c['name'].startswith(name_prefix):
            return c
        score = _candidate_score(c['code'], target_zf, target_price)
        return c if score is not None else None

    scored: list[tuple[float, dict]] = []
    for c in candidates:
        score = _candidate_score(c['code'], target_zf, target_price)
        if score is not None:
            scored.append((score, c))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


@lru_cache(maxsize=256)
def _scan_by_price_board(
    board_key: str,
    target_price: float,
    target_zf: float,
) -> tuple[tuple[str, str], ...]:
    """价格+涨幅在板块内扫描（单字名称等弱线索时的兜底）"""
    fs = _BOARD_EM_FS.get(board_key)
    if not fs or not target_price or target_price <= 0:
        return ()

    fid = 'f3'
    text = _curl(
        'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1'
        f'&fltt=2&invt=2&fid={fid}&fs={fs}'
        '&fields=f2,f3,f12,f14&ut=fa5fd1943c7b033f859fcf9c8751841',
        ref='https://quote.eastmoney.com/',
    )
    try:
        rows = json.loads(text).get('data', {}).get('diff') or []
    except Exception:
        return ()

    hits: list[tuple[float, str, str]] = []
    prefixes = _BOARD_PREFIXES.get(board_key, ())
    for row in rows:
        code = str(row.get('f12') or '').zfill(6)
        name = str(row.get('f14') or '').strip()
        if not _is_valid_stock_code(code) or not name:
            continue
        if prefixes and not code.startswith(prefixes):
            continue
        try:
            price = float(row.get('f2'))
            chg = float(row.get('f3'))
        except (TypeError, ValueError):
            continue
        price_diff_pct = abs(price - target_price) / target_price * 100
        zf_diff = abs(chg - target_zf)
        if price_diff_pct > _PRICE_TOLERANCE_PCT:
            continue
        if zf_diff > _ZF_TOLERANCE and price_diff_pct > 0.3:
            continue
        hits.append((zf_diff + price_diff_pct * 0.35, code, name))

    hits.sort(key=lambda x: x[0])
    return tuple((code, name) for _, code, name in hits[:5])


def resolve_masked_row(row: dict) -> dict | None:
    """单条 stockapi 脱敏记录 → 补全 code/name；失败返回 None"""
    code_raw = str(row.get('code', '')).zfill(6)
    if _is_valid_stock_code(code_raw):
        return row

    name_prefix = _name_prefix(row.get('name', ''))
    board_key = _board_key(code_raw)
    target_zf = float(row.get('qczf') or row.get('zf') or 0)
    target_price = float(row.get('price') or 0)
    bk = str(row.get('bk') or '')

    candidates = _collect_candidates(name_prefix, board_key, bk)
    hit = _pick_best_candidate(candidates, target_zf, target_price, name_prefix)

    if not hit and target_price > 0:
        for code, name in _scan_by_price_board(board_key, target_price, target_zf):
            hit = {'code': code, 'name': name}
            break

    if not hit:
        logger.debug(
            "去脱敏失败: name=%s board=%s zf=%s price=%s bk=%s candidates=%s",
            name_prefix, board_key, target_zf, target_price, bk, len(candidates),
        )
        return None

    resolved = dict(row)
    resolved['code'] = hit['code']
    resolved['name'] = hit['name']
    return resolved


def unmask_stockapi_rows(rows: list[dict]) -> list[dict]:
    """批量去脱敏，保留原有竞价字段"""
    if not rows:
        return []
    if not any(_is_masked_code(str(r.get('code', ''))) for r in rows):
        return rows

    out: list[dict] = []
    seen: set[str] = set()
    ok = 0
    for row in rows:
        fixed = resolve_masked_row(row)
        if not fixed:
            continue
        code = str(fixed.get('code', '')).zfill(6)
        if code in seen:
            continue
        seen.add(code)
        out.append(fixed)
        ok += 1

    if ok:
        logger.info("stockapi 去脱敏: %s/%s 条", ok, len(rows))
    else:
        logger.warning("stockapi 去脱敏全部失败: %s 条", len(rows))
    return out
