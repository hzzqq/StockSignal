"""modules/ai_skills.py — AI 分析规则库（对标 quantdash 的 Skills 页面）。

把老板自己的复盘口径 / 交易框架 / 禁做事项沉淀成可复用的规则条目，
注入到「AI 当日复盘 / 盘前计划 / 个股观察 / 研报摘要 / 决策解释」等场景，
避免每次都要重新口述一遍口径，也避免不同页面给出互相打架的结论。

红线（照抄 quantdash 的忠告并写进代码，防回退）：
- **不要把数据本身写死在 skill 里**。skill 约束的是模型的**分析方式**，不代替输入数据。
- 规则库是"人定的口径"，不是模型自动生成的；不允许 AI 静默改写后生效。
- 本项目额外红线：任何规则都不得诱导模型用合成数据填补缺失（见内置「诚实口径」）。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

# 生效范围：与 UI 的下拉多选一一对应
SCOPES = [
    ("review", "AI 当日复盘"),
    ("premarket", "盘前计划"),
    ("stock", "个股观察"),
    ("report", "研报摘要"),
    ("decision", "决策解释"),
]
SCOPE_KEYS = [k for k, _ in SCOPES]

DEFAULT_SKILLS: list[dict] = [
    {
        "id": "builtin-honest",
        "name": "诚实口径（内置）",
        "desc": "数据缺失必须说缺，禁止用合成/示例数据填充",
        "instruction": (
            "1) 任何数据缺失就明确写「缺」，禁止用示例或合成数据冒充真实数据。\n"
            "2) 引用任何数值时必须带上它的数据日期（as_of）。\n"
            "3) 结论与数据冲突时以数据为准，并明确指出冲突点。"
        ),
        "scopes": list(SCOPE_KEYS),
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "builtin-emotion",
        "name": "情绪周期口径（内置）",
        "desc": "按牧羊人情绪指标口径描述，不自创情绪阶段",
        "instruction": (
            "描述市场情绪时使用本项目的牧羊人情绪指标口径，不要自创情绪阶段名称。\n"
            "涉及仓位时引用决策模块给出的建议区间，不要自行给出满仓/清仓结论。\n"
            "事件因子若已陈旧（滞后超过 4 天），必须说明它已被降权，而不是照常给建议。"
        ),
        "scopes": ["review", "premarket", "decision"],
        "enabled": True,
        "builtin": True,
    },
]


def _default_path() -> str:
    base = os.environ.get("SS_DATA_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    return os.path.join(base, "ai_skills.json")


def load_skills(path: str | None = None) -> list[dict]:
    """读取规则库；文件缺失/损坏时回落到内置默认规则（不静默返回空）。"""
    p = path or _default_path()
    try:
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        skills = obj.get("skills") if isinstance(obj, dict) else obj
        if isinstance(skills, list):
            return skills
    except Exception:  # noqa: BLE001
        pass
    return [dict(s) for s in DEFAULT_SKILLS]


def save_skills(skills: list[dict], path: str | None = None) -> bool:
    """落盘规则库。返回是否成功（失败不抛，交由调用方提示）。"""
    p = path or _default_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(
                {"skills": skills,
                 "updated_at": datetime.now().isoformat(timespec="seconds")},
                f, ensure_ascii=False, indent=2)
        return True
    except Exception:  # noqa: BLE001
        return False


def upsert_skill(skill: dict, path: str | None = None) -> list[dict]:
    """新增或按 id 更新一条规则，返回更新后的完整列表。"""
    skills = load_skills(path)
    sid = skill.get("id")
    if sid and any(s.get("id") == sid for s in skills):
        skills = [dict(skill) if s.get("id") == sid else s for s in skills]
    else:
        skill = dict(skill)
        skill.setdefault("id", f"skill-{int(time.time() * 1000)}")
        skill.setdefault("enabled", True)
        skill.setdefault("scopes", [])
        skills.append(skill)
    save_skills(skills, path)
    return skills


def delete_skill(sid: str, path: str | None = None) -> list[dict]:
    """删除一条规则（按 id），返回剩余列表。"""
    skills = [s for s in load_skills(path) if s.get("id") != sid]
    save_skills(skills, path)
    return skills


def active_skills(scope: str, path: str | None = None) -> list[dict]:
    """取某个场景下**启用且命中范围**的规则。"""
    return [s for s in load_skills(path)
            if s.get("enabled") and scope in (s.get("scopes") or [])]


def compose_prompt(scope: str, path: str | None = None) -> str:
    """把某场景的生效规则拼成可注入模型的 prompt 片段。

    无命中规则时返回空串（调用方应据此判断"没有额外口径约束"，而不是塞一句空话）。
    """
    hits = active_skills(scope, path)
    if not hits:
        return ""
    parts = ["# 分析规则（用户自定义口径，优先级高于你的默认习惯）"]
    for s in hits:
        parts.append(f"\n## {s.get('name', '未命名规则')}")
        if s.get("desc"):
            parts.append(f"> {s['desc']}")
        parts.append(s.get("instruction", "").strip())
    return "\n".join(parts)


def reset_to_defaults(path: str | None = None) -> list[dict]:
    """恢复内置默认规则（会清掉自定义规则）。"""
    skills = [dict(s) for s in DEFAULT_SKILLS]
    save_skills(skills, path)
    return skills
