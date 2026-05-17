"""将 DB / 数值库类型转为 JSON 可序列化结构。"""
import json
from datetime import date, datetime
from decimal import Decimal


def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def dumps_json(obj, **kwargs):
    return json.dumps(json_safe(obj), **kwargs)
