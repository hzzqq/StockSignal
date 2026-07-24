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
    # 加法式健壮性：api_get 返回 (code, body)，body 可能为 None。先兜底空字典，
    # 否则下方 resp.get 抛 AttributeError 会让整个数据概览 Tab 崩溃。
    code, resp = get_stock_stats()
    resp = resp or {}
    if code == 200 and resp.get("status") == "ok":
        stats = resp.get("data") or {}
        col1.metric("股票总数", stats.get("total", 0))
        col2.metric("沪市 (SH)", stats.get("sh", 0))
        col3.metric("深市 (SZ)", stats.get("sz", 0))
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
        # 加法式健壮性：status==ok 但 data / 内层字段可能因后端异常缺失，
        # 直接下标访问会抛 KeyError 让整个「股票管理」Tab 崩溃。统一 .get 兜底降级。
        data = resp.get("data") or {}
        items = data.get("items") or []
        total = data.get("total") or 0
        pages = data.get("pages") or 1

        st.caption(f"共 {total} 只股票 · 第 {page}/{pages} 页")

        if items:
            import pandas as pd
            df = pd.DataFrame(items)
            _cols = [c for c in ["code", "name", "market", "pinyin_initials", "pinyin_full"] if c in df.columns]
            df = df[_cols] if _cols else df
            df.columns = ["代码", "名称", "市场", "拼音首字母", "全拼"][: len(_cols)]
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
        else:
            # 加法式空态引导：搜索无匹配或全部为空时，给出可操作的排查提示，
            # 而非仅显示「共 0 只股票」一行，降低用户困惑。
            _empty_info("未找到匹配的股票。请检查搜索关键词（支持代码 / 名称 / 拼音首字母），"
                        "或点击上方「🔄 刷新」重置搜索条件后重试。")

# ----------------------------------------------------------------- 系统配置
with tab_config:
    st.subheader("系统配置项")

    code, resp = get_config()
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取配置失败: {resp.get('message', '未知错误')}")
    else:
        configs = resp.get("data") or []
        if not configs:
            _empty_info("暂无配置项。可在下方「➕ 新增配置」中添加自定义配置键与默认值。")
        else:
            for cfg in configs:
                with st.container(border=True):
                    # 加法式健壮性：后端配置项可能缺 "key" 字段，直接 cfg['key'] 会抛 KeyError
                    # 让整个「系统配置」Tab 崩溃。先安全取值，缺键时降级为空串。
                    cfg_key = cfg.get("key", "")
                    col_key, col_val, col_desc, col_action = st.columns([2, 2, 2, 1])
                    with col_key:
                        label = CONFIG_LABELS.get(cfg_key, cfg_key)
                        st.markdown(f"**{label}**")
                        st.caption(f"更新: {cfg.get('updated_at', 'N/A')[:10] if cfg.get('updated_at') else 'N/A'}")
                    with col_val:
                        new_val = st.text_input("值", value=cfg.get("value", ""),
                                                key=f"cfg_val_{cfg.get('key')}", label_visibility="collapsed")
                    with col_desc:
                        st.caption(cfg.get("description", ""))
                    with col_action:
                        if st.button("💾", key=f"cfg_save_{cfg.get('key')}", help="保存"):
                            if new_val != cfg.get("value", ""):
                                c, r = update_config(cfg.get("key"), new_val)
                                if c == 200 and r.get("status") == "ok":
                                    st.success("已保存")
                                    st.rerun()
                                else:
                                    st.error(r.get("message", "保存失败"))
                            else:
                                st.caption("无变化")
                        if cfg.get("key") not in ("cache_days", "cache_hours_today", "jwt_expires_seconds",
                                               "default_page_size", "search_limit"):
                            _ck = f"cfg_del_{cfg_key}"
                            if st.session_state.get(_ck):
                                if st.button("确认删除", key=f"cfg_del_cfm_{cfg_key}", type="primary"):
                                    c, r = delete_config(cfg_key)
                                    if c == 200 and r.get("status") == "ok":
                                        st.success("已删除")
                                        st.session_state.pop(_ck, None)
                                        st.rerun()
                                    else:
                                        st.error(r.get("message", "删除失败"))
                                        st.session_state.pop(_ck, None)
                                if st.button("取消", key=f"cfg_del_cancel_{cfg_key}"):
                                    st.session_state.pop(_ck, None)
                            else:
                                if st.button("🗑️", key=f"cfg_del_{cfg_key}", help="删除"):
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
                        st.text(f"{s.get('code','')}  {s.get('name','')}  ({s.get('market','')})")
                    with col_btn:
                        if st.button("➕", key=f"watch_add_{s.get('code')}"):
                            c2, r2 = add_watchlist(s.get("code"))
                            if c2 == 200:
                                st.success(f"已添加 {s.get('name', s.get('code', '该股票'))}")
                                st.rerun()

    st.markdown("---")
    code, resp = get_watchlist()
    if code != 200 or resp.get("status") != "ok":
        st.error(f"获取自选股失败: {resp.get('message', '未知错误')}")
    else:
        # 加法式健壮性：status==ok 但 data 缺失/非列表时，直接 resp["data"] 会抛 KeyError，
        # 或 DataFrame 因非 list 异常。统一 .get 兜底为空列表降级为空态提示。
        items = resp.get("data") or []
        if not items:
            _empty_info("暂无自选股。在上方输入框填入代码（如 600519）后点「➕ 添加自选」即可跟踪。")
        else:
            for item in items:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{item.get('stock_code','')}** {item.get('stock_name','')}")
                with col2:
                    _ca = str(item.get("created_at") or "")
                    st.caption(f"添加: {_ca[:10]}")
                    if item.get("note"):
                        st.caption(f"备注: {item['note']}")
                with col3:
                    _wid = item.get("id")
                    if st.button("🗑️", key=f"watch_del_{_wid}"):
                        c, r = remove_watchlist(_wid)
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
        cfg = (resp.get("data") or {}).get("config", {})
        col1, col2, col3 = st.columns(3)
        with col1:
            try:
                _iv = int(cfg.get("scan_interval_minutes", 15))
            except (TypeError, ValueError):
                _iv = 15
            interval = st.number_input("扫描间隔（分钟）", min_value=1, max_value=120,
                                      value=_iv,
                                      key="alert_interval",
                                      help="市场扫描的触发间隔（分钟），过小会增加请求压力。")
        with col2:
            try:
                _cd = int(cfg.get("cooldown_hours", 6))
            except (TypeError, ValueError):
                _cd = 6
            cooldown = st.number_input("冷却时长（小时）", min_value=1, max_value=48,
                                       value=_cd,
                                       key="alert_cooldown",
                                       help="同一标的两次预警之间的最小间隔（小时），避免重复打扰。")
        with col3:
            try:
                _dl = int(cfg.get("initial_delay_seconds", 10))
            except (TypeError, ValueError):
                _dl = 10
            delay = st.number_input("首次延迟（秒）", min_value=0, max_value=600,
                                    value=_dl,
                                    key="alert_delay",
                                    help="系统启动后首次扫描的延迟（秒），用于错峰。")

        try:
            _thr_json = json.dumps(cfg.get("thresholds", {}), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            _thr_json = "{}"
        thr_txt = st.text_area(
            "阈值覆盖（JSON，可选）",
            value=_thr_json,
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
