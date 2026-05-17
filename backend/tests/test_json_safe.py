import json
from decimal import Decimal

from utils.json_safe import dumps_json, json_safe


def test_json_safe_decimal():
    data = {"price": Decimal("12.34"), "nested": [{"net": Decimal("100.5")}]}
    out = json_safe(data)
    assert out["price"] == 12.34
    assert out["nested"][0]["net"] == 100.5
    json.loads(dumps_json(data))
