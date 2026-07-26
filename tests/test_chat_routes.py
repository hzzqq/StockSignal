"""
tests/test_chat_routes.py
--------------------------
离线（无 Flask / 无网络）单元测试，验证 chat_routes 中的
_ensure_json_safe 能递归净化消息中的不可序列化对象，
保证 json.dumps 保存历史时永不崩溃。

运行：
    python -m pytest tests/test_chat_routes.py -q
"""
from __future__ import annotations

import datetime
import decimal
import json

from backend.api.chat_routes import _ensure_json_safe


def test_normal_list_unchanged_and_serializable():
    """普通 dict 列表保持原样，且 json.dumps 成功。"""
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮您？"},
    ]
    safe = _ensure_json_safe(messages)
    assert safe == messages
    # 严格相等且类型一致
    assert isinstance(safe, list)
    assert safe[0]["role"] == "user"
    # 序列化不抛异常
    payload = json.dumps(safe, ensure_ascii=False)
    assert "你好" in payload


def test_datetime_converted_to_str():
    """含 datetime 的消息被转换为字符串，json.dumps 成功。"""
    dt = datetime.datetime(2026, 7, 26, 10, 30, 0)
    messages = [{"role": "user", "content": "时间", "ts": dt}]

    safe = _ensure_json_safe(messages)
    assert isinstance(safe[0]["ts"], str)
    assert safe[0]["ts"] == dt.isoformat()

    # 序列化不抛异常
    json.dumps(safe)


def test_date_converted_to_str():
    """date 同样被转换为字符串。"""
    d = datetime.date(2026, 7, 26)
    messages = [{"role": "system", "day": d}]

    safe = _ensure_json_safe(messages)
    assert safe[0]["day"] == d.isoformat()
    json.dumps(safe)


def test_decimal_converted():
    """含 Decimal 的消息被转换（转为 float），json.dumps 成功。"""
    dec = decimal.Decimal("123.45")
    messages = [{"role": "assistant", "price": dec}]

    safe = _ensure_json_safe(messages)
    assert isinstance(safe[0]["price"], float)
    assert safe[0]["price"] == 123.45
    json.dumps(safe)


def test_bytes_and_set_converted():
    """bytes 被解码，set 被转为 list。"""
    messages = [
        {"role": "user", "raw": b"hello", "tags": {"a", "b"}},
    ]
    safe = _ensure_json_safe(messages)
    assert isinstance(safe[0]["raw"], str)
    assert isinstance(safe[0]["tags"], list)
    json.dumps(safe)


def test_nested_structures():
    """嵌套 dict/list/set 内部对象也会被递归净化。"""
    dt = datetime.datetime(2026, 1, 1)
    messages = [
        {
            "role": "user",
            "meta": {"when": dt, "nums": [decimal.Decimal("1.1"), decimal.Decimal("2.2")]},
            "history": [{"t": dt}],
        }
    ]
    safe = _ensure_json_safe(messages)
    assert safe[0]["meta"]["when"] == dt.isoformat()
    assert safe[0]["meta"]["nums"] == [1.1, 2.2]
    assert safe[0]["history"][0]["t"] == dt.isoformat()
    json.dumps(safe)


def test_json_dumps_never_raises_for_all_cases():
    """核心断言：对所有已知非序列化类型，json.dumps(_ensure_json_safe(x)) 不抛异常。"""
    cases = [
        [{"role": "user", "content": "x"}],
        [{"role": "user", "ts": datetime.datetime.now()}],
        [{"role": "user", "d": datetime.date.today()}],
        [{"role": "user", "v": decimal.Decimal("9.9")}],
        [{"role": "user", "b": b"bin"}],
        [{"role": "user", "s": {1, 2, 3}}],
        [{"role": "user", "n": None, "f": 1.0, "i": 1, "b": True}],
    ]
    for x in cases:
        # 若是原始 x 直接 dumps 会抛异常，但净化后一定不抛
        safe = _ensure_json_safe(x)
        json.dumps(safe)
