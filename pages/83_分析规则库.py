"""pages/83_分析规则库.py — AI 分析规则库（对标 quantdash 的 Skills 页面）。

把老板自己的复盘口径 / 交易框架 / 禁做事项沉淀成可复用规则，
注入到「AI 当日复盘 / 盘前计划 / 个股观察 / 研报摘要 / 决策解释」等场景。

红线：
- 规则约束的是 AI 的**分析方式**，不代替输入数据。**不要把行情数字写死在规则里**——
  数据源一变，写死的规则就会让模型持续给出过期结论。
- 规则由人维护，不由模型自动改写后静默生效。
"""
from __future__ import annotations

import streamlit as st

from modules.page_utils import render_standard_page
from modules import ai_skills as sk

_SCOPE_LABEL = dict(sk.SCOPES)


def _scope_labels(keys: list[str]) -> str:
    return "、".join(_SCOPE_LABEL.get(k, k) for k in keys) or "（未选择）"


def main() -> None:
    render_standard_page(title="分析规则库", icon="📜", layout="wide")

    st.caption(
        "规则用于约束 AI 的**分析方式**，不代替输入数据。"
        "请勿把行情数字写死在规则里——数据源一变，写死的规则会让 AI 持续给出过期结论。"
    )

    # ── ① 预览：某场景实际会注入什么 ──
    st.markdown("#### 🎯 规则预览")
    scope_key = st.selectbox(
        "选择场景，查看将注入 AI 的规则",
        options=sk.SCOPE_KEYS,
        format_func=lambda k: _SCOPE_LABEL.get(k, k),
    )
    hits = sk.active_skills(scope_key)
    prompt = sk.compose_prompt(scope_key)
    if prompt:
        with st.expander(f"「{_SCOPE_LABEL.get(scope_key)}」将注入 {len(hits)} 条规则",
                         expanded=False):
            st.code(prompt, language="markdown")
    else:
        st.info("该场景暂无启用规则，AI 将按默认习惯回答。")

    st.divider()

    # ── ② 规则列表 ──
    st.markdown("#### 📜 规则列表")
    skills = sk.load_skills()
    if not skills:
        st.warning("还没有任何规则，可在下方新增。")
    for s in skills:
        sid = str(s.get("id", ""))
        tag = "（内置）" if s.get("builtin") else ""
        with st.container(border=True):
            c1, c2 = st.columns([6, 1])
            with c1:
                st.markdown(f"**{s.get('name', '未命名')}** {tag}")
                if s.get("desc"):
                    st.caption(s["desc"])
                st.caption("生效范围：" + _scope_labels(s.get("scopes") or []))
            with c2:
                enabled = st.checkbox("启用", value=bool(s.get("enabled")),
                                      key=f"en_{sid}")
                if enabled != bool(s.get("enabled")):
                    s["enabled"] = enabled
                    sk.save_skills(skills)
                    st.rerun()
            with st.expander("查看规则内容"):
                st.code(s.get("instruction", ""), language="markdown")
            if st.button("删除", key=f"del_{sid}"):
                sk.delete_skill(sid)
                st.rerun()

    st.divider()

    # ── ③ 新增规则 ──
    st.markdown("#### ➕ 新增规则")
    with st.form("new_skill", clear_on_submit=True):
        name = st.text_input("规则名称")
        desc = st.text_input("一句话描述")
        instruction = st.text_area("规则指令（将直接注入模型）", height=140)
        scopes = st.multiselect("生效范围", options=sk.SCOPE_KEYS,
                                format_func=lambda k: _SCOPE_LABEL.get(k, k))
        submitted = st.form_submit_button("保存")
        if submitted:
            if not name.strip():
                st.error("规则名称不能为空")
            elif not instruction.strip():
                st.error("请填写规则指令")
            elif not scopes:
                st.error("请至少选择一个生效范围")
            else:
                sk.upsert_skill({
                    "name": name.strip(),
                    "desc": desc.strip(),
                    "instruction": instruction.strip(),
                    "scopes": scopes,
                    "enabled": True,
                })
                st.success(f"已保存规则「{name.strip()}」")
                st.rerun()

    if st.button("恢复内置默认规则"):
        sk.reset_to_defaults()
        st.rerun()


main()
