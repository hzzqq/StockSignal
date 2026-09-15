"""tests/test_ai_skills.py — AI 分析规则库守卫（对标 quantdash Skills）。

重点锁三条：
  ① 落盘/读取往返一致（规则库是"人定的口径"，丢了就得重新口述）
  ② 生效范围 + 启用开关过滤正确（不该注入的场景不能串味）
  ③ 无命中规则时 compose_prompt 返回空串 —— 调用方据此判断"没有额外口径约束"，
     而不是塞一句空话（这也防住"规则库空了却假装注入成功"的静默失败）
"""
import os

import pytest

from modules import ai_skills as sk


@pytest.fixture()
def _tmp_store(tmp_path):
    """把规则库指向临时文件，避免污染真实 data/ai_skills.json。"""
    p = str(tmp_path / "ai_skills.json")
    yield p
    if os.path.exists(p):
        os.remove(p)


def test_defaults_returned_when_no_file(_tmp_store):
    """文件不存在时回落到内置默认规则，而不是返回空列表（静默丢口径）。"""
    skills = sk.load_skills(_tmp_store)
    assert skills, "无文件时应回落到内置规则"
    assert any(s.get("builtin") for s in skills)


def test_upsert_and_reload_roundtrip(_tmp_store):
    sk.upsert_skill({
        "id": "my-rule",
        "name": "只做主线龙头",
        "desc": "非主线不做",
        "instruction": "只讨论当日主线板块的前三只龙头，其余标的直接跳过。",
        "scopes": ["review", "premarket"],
        "enabled": True,
    }, _tmp_store)
    loaded = sk.load_skills(_tmp_store)
    mine = [s for s in loaded if s["id"] == "my-rule"]
    assert len(mine) == 1
    assert mine[0]["name"] == "只做主线龙头"
    assert mine[0]["scopes"] == ["review", "premarket"]


def test_upsert_updates_existing_by_id(_tmp_store):
    sk.upsert_skill({"id": "x", "name": "旧名", "instruction": "旧内容",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    sk.upsert_skill({"id": "x", "name": "新名", "instruction": "新内容",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    mine = [s for s in sk.load_skills(_tmp_store) if s["id"] == "x"]
    assert len(mine) == 1, "按 id 更新不应产生重复条目"
    assert mine[0]["name"] == "新名"
    assert mine[0]["instruction"] == "新内容"


def test_delete_removes_skill(_tmp_store):
    sk.upsert_skill({"id": "gone", "name": "待删除", "instruction": "x",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    sk.delete_skill("gone", _tmp_store)
    assert [s for s in sk.load_skills(_tmp_store) if s["id"] == "gone"] == []


def test_active_skills_filters_scope_and_enabled(_tmp_store):
    sk.upsert_skill({"id": "a", "name": "仅复盘", "instruction": "AAA",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    sk.upsert_skill({"id": "b", "name": "被禁用", "instruction": "BBB",
                     "scopes": ["review"], "enabled": False}, _tmp_store)
    sk.upsert_skill({"id": "c", "name": "仅盘前", "instruction": "CCC",
                     "scopes": ["premarket"], "enabled": True}, _tmp_store)

    review_ids = {s["id"] for s in sk.active_skills("review", _tmp_store)}
    assert "a" in review_ids
    assert "b" not in review_ids, "已禁用的规则不应注入"
    assert "c" not in review_ids, "范围不命中的规则不应串味"

    pre_ids = {s["id"] for s in sk.active_skills("premarket", _tmp_store)}
    assert "c" in pre_ids


def test_compose_prompt_includes_instruction_and_header(_tmp_store):
    sk.upsert_skill({"id": "p", "name": "测试规则", "instruction": "这是关键指令内容",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    prompt = sk.compose_prompt("review", _tmp_store)
    assert "测试规则" in prompt
    assert "这是关键指令内容" in prompt


def test_compose_prompt_empty_when_no_match(_tmp_store):
    """无命中规则 → 空串，让调用方如实判断，不编一句占位话术。"""
    sk.reset_to_defaults(_tmp_store)
    # 注意：必须显式保存"改过之后"的那份列表，重新 load 会拿到未修改的副本
    skills = sk.load_skills(_tmp_store)
    for s in skills:
        s["enabled"] = False
    sk.save_skills(skills, _tmp_store)
    assert sk.compose_prompt("review", _tmp_store) == ""


def test_reset_to_defaults_clears_custom(_tmp_store):
    sk.upsert_skill({"id": "custom", "name": "自定义", "instruction": "x",
                     "scopes": ["review"], "enabled": True}, _tmp_store)
    sk.reset_to_defaults(_tmp_store)
    assert [s for s in sk.load_skills(_tmp_store) if s["id"] == "custom"] == []
