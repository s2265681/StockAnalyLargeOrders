"""股票代码校验（无外部依赖）"""


def is_valid_stock_code(code: str) -> bool:
    """6 位纯数字代码；stockapi 额度用尽时会返回 00**** 等脱敏值"""
    c = str(code or "").strip().zfill(6)
    return len(c) == 6 and c.isdigit()
