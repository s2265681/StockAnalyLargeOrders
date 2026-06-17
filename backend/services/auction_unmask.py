"""
stockapi 额度用尽时返回 00**** / 冰轮**** 等脱敏字段，通过名称前缀 + 板块 + 竞价涨幅反查真实代码。
"""
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


def _is_valid_stock_code(code: str) -> bool:
    c = str(code or "").strip().zfill(6)
    return len(c) == 6 and c.isdigit()


def is_valid_stock_code(code: str) -> bool:
    return _is_valid_stock_code(code)


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


def _decode_smartbox_name(raw: str) -> str:
    """smartbox 返回 \\uXXXX 字面量，需解码为中文"""
    if not raw:
        return ''
    if '\\u' in raw:
        try:
            return raw.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
    return raw


@lru_cache(maxsize=256)
def _lookup_by_name(name_prefix: str) -> tuple[tuple[str, str, str], ...]:
    """腾讯 smartbox：返回 ((market, code, name), ...)"""
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
        if not name.startswith(name_prefix):
            continue
        out.append((market, code, name))
    return tuple(out)


@lru_cache(maxsize=512)
def _get_change_pct(code: str) -> float | None:
    prefix = 'sz' if code.startswith(('0', '3')) else 'sh'
    text = _curl(f'https://qt.gtimg.cn/q={prefix}{code}')
    if '~' not in text:
        return None
    try:
        fields = text.split('"')[1].split('~')
        return float(fields[32]) if fields[32] else None
    except Exception:
        return None


def resolve_masked_row(row: dict) -> dict | None:
    """单条 stockapi 脱敏记录 → 补全 code/name；失败返回 None"""
    code_raw = str(row.get('code', '')).zfill(6)
    if _is_valid_stock_code(code_raw):
        return row

    name_prefix = _name_prefix(row.get('name', ''))
    board_key = _board_key(code_raw)
    target_zf = float(row.get('qczf') or 0)

    candidates = [
        {'code': code, 'name': name, 'market': market}
        for market, code, name in _lookup_by_name(name_prefix)
        if _code_matches_board(code, board_key)
    ]
    if not candidates:
        logger.debug(f"去脱敏失败: name={name_prefix} board={board_key}")
        return None

    if len(candidates) == 1:
        hit = candidates[0]
    else:
        scored = []
        for c in candidates:
            chg = _get_change_pct(c['code'])
            if chg is None:
                continue
            scored.append((abs(chg - target_zf), c))
        if not scored:
            hit = candidates[0]
        else:
            scored.sort(key=lambda x: x[0])
            if scored[0][0] > 2.5:
                logger.debug(
                    f"去脱敏涨幅不匹配: {name_prefix} best_dz={scored[0][0]:.2f} zf={target_zf}"
                )
                return None
            hit = scored[0][1]

    resolved = dict(row)
    resolved['code'] = hit['code']
    resolved['name'] = hit['name']
    return resolved


def unmask_stockapi_rows(rows: list[dict]) -> list[dict]:
    """批量去脱敏，保留原有竞价字段"""
    if not rows:
        return []
    if all(_is_valid_stock_code(str(r.get('code', '')).zfill(6)) for r in rows):
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
        logger.info(f"stockapi 去脱敏: {ok}/{len(rows)} 条")
    else:
        logger.warning(f"stockapi 去脱敏全部失败: {len(rows)} 条")
    return out
