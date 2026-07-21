"""
pages/8_系统配置.py
------------------
管理员系统配置页面：股票数据统计 / 股票列表管理 / 系统配置键值表 / 自选股管理。
"""
import streamlit as st
import json
from modules.session import init_session_state, require_admin, render_user_badge, api_get, api_post
from modules.admin_api import (
    get_stock_stats, get_stock_list, get_config, update_config,
    create_config, delete_config, get_watchlist, add_watchlist, remove_watchlist,
    search_stocks,
)
from modules.page_widgets import _empty_info, _toast

# 系统配置项：key → 中文可读名称
CONFIG_LABELS = {
    "cache_days": "行情缓存天数",
    "cache_hours_today": "当日数据缓存小时数",
    "default_page_size": "默认分页大小",
    "jwt_expires_seconds": "JWT 过期时间（秒）",
    "search_limit": "股票搜索最大返回数",
}

init_session_state()
require_admin()

from modules.ui_theme import apply_page_config
apply_page_config(page_title="系统配置", page_icon="⚙️", layout="wide")
st.session_state["_active_page"] = __file__
st.title("⚙️ 系统配置")
render_user_badge()

# ================================================================ Tab 布局
tab_overview, tab_stocks, tab_config, tab_watch, tab_alert = st.tabs([
    "📊 数据概览", "📈 股票管理", "🔧 系统配置", "⭐ 自选股", "🔔 异动扫描"
])

# ----------------------------------------------------------------- 数据概览
with tab_overview:
    col1, col2, col3 = st.columns(3)
    code, resp = get_stock_stats()
    if code == 200 and resp.get("status") == "ok":
        stats = resp["data"]
        col1.metric("股票总数", stats["total"])
        col2.metric("沪市 (SH)", stats["sh"])
        col3.metric("深市 (SZ)", stats["sz"])
    else:
        st.error(f"获取统计数据失败：{resp.get('message', '服务异常')}。请确认后端 Flask 已启动（:5050），稍后点右上角刷新重试。")

    st.markdown("---")
    st.subheader("系统信息")
    col_a, col_b = st.columns(2)
    with col_a:
        st.info("""
        **后端服务**
        - Flask API: `http://127.0.0.1:5050`
        - 数据库: SQLite (`backend/data/app.db`)
        - 鉴权: JWT (HS256)
        """)
    with col_b:
        st.info("""
        **前端服务**
        - Streamlit: `http://127.0.0.1:8501`
        - 行情缓存: `data/cache.db`
        - 新闻库: `data/news.db`
        """)

# ----------------------------------------------------------------- 股票管理
with tab_stocks:
    if "stock_page" not in st.session_state:
        st.session_state["stock_page"] = 1
    if "stock_keyword" not in st.session_state:
        st.session_state["stock_keyword"] = ""

    col_search, col_refresh = st.columns([3, 1])
    with col_search:
        keyword = st.text_input("搜索股票", value=st.session_state["stock_keyword"],
                                key="stock_search_mgmt", placeholder="代码/名称/拼音",
                                help="按代码、名称或拼音首字母搜索全部股票。")
    with col_refresh:
        if st.button("🔄 刷新", width="stretch"):
            st.session_state["stock_keyword"] = keyword
            st.rerun()

    st.session_state["stock_keyword"] = keyword
    page = st.session_state["stock_page"]

    code, resp = get_stock_list(page=page, per_page=30, keyword=keyword)
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取股票列表失败: {resp.get('message', '未知错误')}")
    else:
        data = resp["data"]
        items = data["items"]
        total = data["total"]
        pages = data["pages"]

        st.caption(f"共 {total} 只股票 · 第 {page}/{pages} 页")

        if items:
            import pandas as pd
            df = pd.DataFrame(items)
            df = df[["code", "name", "market", "pinyin_initials", "pinyin_full"]]
            df.columns = ["代码", "名称", "市场", "拼音首字母", "全拼"]
            st.dataframe(df, width="stretch", hide_index=True)

            col_prev, col_info, col_next = st.columns([1, 2, 1])
            with col_prev:
                if st.button("⬅️ 上一页", disabled=(page <= 1), key="stock_prev"):
                    st.session_state["stock_page"] = page - 1
                    st.rerun()
            with col_info:
                st.caption(f"第 {page} / {pages} 页")
            with col_next:
                if st.button("➡️ 下一页", disabled=(page >= pages), key="stock_next"):
                    st.session_state["stock_page"] = page + 1
                    st.rerun()

# ----------------------------------------------------------------- 系统配置
with tab_config:
    st.subheader("系统配置项")

    code, resp = get_config()
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取配置失败: {resp.get('message', '未知错误')}")
    else:
        configs = resp["data"]
        if not configs:
            _empty_info("暂无配置项。可在下方「➕ 新增配置」中添加自定义配置键与默认值。")
        else:
            for cfg in configs:
                with st.container(border=True):
                    col_key, col_val, col_desc, col_action = st.columns([2, 2, 2, 1])
                    with col_key:
                        label = CONFIG_LABELS.get(cfg['key'], cfg['key'])
                        st.markdown(f"**{label}**")
                        st.caption(f"更新: {cfg.get('updated_at', 'N/A')[:10] if cfg.get('updated_at') else 'N/A'}")
                    with col_val:
                        new_val = st.text_input("值", value=cfg["value"],
                                                key=f"cfg_val_{cfg['key']}", label_visibility="collapsed")
                    with col_desc:
                        st.caption(cfg.get("description", ""))
                    with col_action:
                        if st.button("💾", key=f"cfg_save_{cfg['key']}", help="保存"):
                            if new_val != cfg["value"]:
                                c, r = update_config(cfg["key"], new_val)
                                if c == 200 and r.get("status") == "ok":
                                    st.success("已保存")
                                    st.rerun()
                                else:
                                    st.error(r.get("message", "保存失败"))
                            else:
                                st.caption("无变化")
                        if cfg["key"] not in ("cache_days", "cache_hours_today", "jwt_expires_seconds",
                                               "default_page_size", "search_limit"):
                            _ck = f"cfg_del_{cfg['key']}"
                            if st.session_state.get(_ck):
                                if st.button("确认删除", key=f"cfg_del_cfm_{cfg['key']}", type="primary"):
                                    c, r = delete_config(cfg["key"])
                                    if c == 200 and r.get("status") == "ok":
                                        st.success("已删除")
                                        st.session_state.pop(_ck, None)
                                        st.rerun()
                                    else:
                                        st.error(r.get("message", "删除失败"))
                                        st.session_state.pop(_ck, None)
                                if st.button("取消", key=f"cfg_del_cancel_{cfg['key']}"):
                                    st.session_state.pop(_ck, None)
                            else:
                                if st.button("🗑️", key=f"cfg_del_{cfg['key']}", help="删除"):
                                    st.session_state[_ck] = True

    # 新增配置
    st.markdown("---")
    st.subheader("➕ 新增配置")
    with st.form("add_config_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_key = st.text_input("配置键", placeholder="如: max_search_results",
                                    help="配置的唯一标识键，建议使用小写英文与下划线，如 max_search_results。")
        with col2:
            new_value = st.text_input("配置值",
                                      help="该配置项的值，保存后即时生效（视具体配置而定）。")
        with col3:
            new_desc = st.text_input("描述",
                                     help="对该配置用途的简短说明，便于后续维护。")

        if st.form_submit_button("✅ 添加", type="primary"):
            if not new_key:
                st.error("配置键不能为空")
            else:
                c, r = create_config(new_key, new_value, new_desc)
                if c == 200 and r.get("status") == "ok":
                    st.success("添加成功！")
                    st.rerun()
                else:
                    st.error(r.get("message", "添加失败"))

# ----------------------------------------------------------------- 自选股
with tab_watch:
    st.subheader("⭐ 我的自选股")

    col_add, col_search = st.columns([3, 1])
    with col_add:
        add_code = st.text_input("添加股票代码", placeholder="如: 600519", key="watch_add_code",
                                 help="输入股票代码（如 600519）或名称，加入自选便于统一监控。")
        with col_search:
            st.caption("代码如 600519 / 000001")
            if st.button("➕ 添加自选", width="stretch"):
                if add_code:
                    c, r = add_watchlist(add_code)
                    if c == 200 and r.get("status") == "ok":
                        st.success("添加成功！")
                        st.rerun()
                    else:
                        st.error(r.get("message", "添加失败"))

    # 搜索辅助
    st.caption("💡 搜索辅助：")
    search_q = st.text_input("搜索股票", placeholder="输入代码/名称/拼音首字母", key="watch_search")
    if search_q and len(search_q) >= 1:
        c, r = search_stocks(search_q, limit=8)
        if c == 200 and r.get("status") == "ok":
            results = r["data"]
            if results:
                for s in results:
                    col_s, col_btn = st.columns([4, 1])
                    with col_s:
                        st.text(f"{s['code']}  {s['name']}  ({s['market']})")
                    with col_btn:
                        if st.button("➕", key=f"watch_add_{s['code']}"):
                            c2, r2 = add_watchlist(s["code"])
                            if c2 == 200:
                                st.success(f"已添加 {s['name']}")
                                st.rerun()

    st.markdown("---")
    code, resp = get_watchlist()
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取自选股失败: {resp.get('message', '未知错误')}")
    else:
        items = resp["data"]
        if not items:
            _empty_info("暂无自选股。在上方输入框填入代码（如 600519）后点「➕ 添加自选」即可跟踪。")
        else:
            for item in items:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{item['stock_code']}** {item['stock_name']}")
                with col2:
                    st.caption(f"添加: {item['created_at'][:10]}")
                    if item.get("note"):
                        st.caption(f"备注: {item['note']}")
                with col3:
                    if st.button("🗑️", key=f"watch_del_{item['id']}"):
                        c, r = remove_watchlist(item["id"])
                        if c == 200 and r.get("status") == "ok":
                            st.success("已移除")
                            st.rerun()
                        else:
                            st.error(r.get("message", "移除失败"))

# ----------------------------------------------------------------- 异动扫描策略
with tab_alert:
    st.subheader("🔔 市场异动扫描策略")
    st.caption("后台调度器在交易时段自动扫描广度/情绪/估值指标越界并写库。"
               "以下参数为运行时生效；重启服务后恢复环境变量默认值。")

    code, resp = api_get("/api/market-alerts/config")
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取扫描策略失败: {resp.get('message', '未知错误')}")
    else:
        cfg = resp["data"]["config"]
        col1, col2, col3 = st.columns(3)
        with col1:
            interval = st.number_input("扫描间隔（分钟）", min_value=1, max_value=120,
                                      value=int(cfg.get("scan_interval_minutes", 15)),
                                      key="alert_interval",
                                      help="市场扫描的触发间隔（分钟），过小会增加请求压力。")
        with col2:
            cooldown = st.number_input("冷却时长（小时）", min_value=1, max_value=48,
                                       value=int(cfg.get("cooldown_hours", 6)),
                                       key="alert_cooldown",
                                       help="同一标的两次预警之间的最小间隔（小时），避免重复打扰。")
        with col3:
            delay = st.number_input("首次延迟（秒）", min_value=0, max_value=600,
                                    value=int(cfg.get("initial_delay_seconds", 10)),
                                    key="alert_delay",
                                    help="系统启动后首次扫描的延迟（秒），用于错峰。")

        thr_txt = st.text_area(
            "阈值覆盖（JSON，可选）",
            value=json.dumps(cfg.get("thresholds", {}), ensure_ascii=False, indent=2),
            height=160, key="alert_thr",
            help='覆盖某指标阈值，如 {"vix": {"warn_hi": 18, "danger_hi": 28}}',
        )

        if st.button("💾 保存扫描策略", type="primary", key="alert_save"):
            try:
                thr = json.loads(thr_txt) if thr_txt.strip() else {}
                if not isinstance(thr, dict):
                    raise ValueError("必须是 JSON 对象")
            except Exception as e:
                st.error(f"阈值 JSON 解析失败：{e}")
                thr = None
            if thr is not None:
                body = {
                    "scan_interval_minutes": int(interval),
                    "cooldown_hours": int(cooldown),
                    "initial_delay_seconds": int(delay),
                    "thresholds": thr,
                }
                c, r = api_post("/api/market-alerts/config", json=body)
                if c == 200 and r.get("status") == "ok":
                    st.success("已保存（运行时生效，重启后失效）")
                    _toast("市场异动扫描策略已更新")
                    st.rerun()
                else:
                    st.error(r.get("message", "保存失败"))
