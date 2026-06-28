"""
页面2：事件追踪
信号评分、事件时间轴、事件管理
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="事件追踪", page_icon="🔔", layout="wide")
st.title("🔔 事件追踪")

from modules.signal import SignalEngine
from modules.fetcher import StockFetcher
from modules.cleaner import DataCleaner
from modules.visualizer import Visualizer

engine = SignalEngine()
fetcher = StockFetcher()

# ------------------------------------------------------------------
# 信号评分
# ------------------------------------------------------------------
st.subheader("信号评分")

with st.form("signal_form"):
    col1, col2 = st.columns(2)
    with col1:
        sig_ticker = st.text_input("股票代码", value="601088", key="sig_ticker")
    with col2:
        sig_date = st.date_input("评估日期", value=datetime.now(), key="sig_date")

    keywords_input = st.text_input(
        "事件关键词（逗号分隔）",
        value="煤炭,保供,电厂库存",
        key="sig_keywords"
    )

    submitted = st.form_submit_button("开始评分")

if submitted:
    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
    date_str = sig_date.strftime("%Y-%m-%d")

    with st.spinner("正在计算信号得分..."):
        try:
            scores = engine.evaluate(sig_ticker, keywords, date_str)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("价格信号", f"{scores['price_score']}/100")
            with col2:
                st.metric("事件信号", f"{scores['event_score']}/100")
            with col3:
                st.metric("宏观信号", f"{scores['macro_score']}/100")
            with col4:
                total = scores['total']
                delta_text = "买入信号" if total >= 70 else ("卖出信号" if total <= 40 else "观望")
                st.metric("综合评分", f"{total}/100", delta=delta_text)

            col_radar, col_detail = st.columns([1, 1])
            with col_radar:
                fig = Visualizer.signal_radar(scores)
                st.plotly_chart(fig, use_container_width=True)
            with col_detail:
                st.markdown("#### 评分说明")
                st.markdown(f"""
                - **价格信号 ({scores['price_score']})**: 基于均线趋势、动量、量价关系
                - **事件信号 ({scores['event_score']})**: 基于关键词匹配事件库，利好加分/利空减分
                - **宏观信号 ({scores['macro_score']})**: 基于制造业 PMI（>50扩张，<50收缩）
                - **综合评分 ({total})**: 加权 = 价格×0.4 + 事件×0.4 + 宏观×0.2
                - **阈值**: >70 买入 | 40-70 观望 | <40 卖出
                """)
        except Exception as e:
            st.error(f"评分失败: {e}")

# ------------------------------------------------------------------
# 事件时间轴
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("事件时间轴")

with st.form("timeline_form"):
    tl_ticker = st.text_input("股票代码", value="601088", key="tl_ticker")
    tl_days = st.slider("回溯天数", min_value=30, max_value=365, value=180, step=30)
    tl_submitted = st.form_submit_button("生成时间轴")

if tl_submitted:
    end = datetime.now()
    start = end - timedelta(days=tl_days)
    with st.spinner("正在生成..."):
        try:
            df = fetcher.get_daily(tl_ticker, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            events = engine._load_events()
            if not events.empty:
                events = events[events["date"] >= start]
                events = events[events["ticker"].str.contains(tl_ticker, na=False) | events["ticker"].isna()]

            if not df.empty:
                fig = Visualizer.event_timeline(df, events, title=f"{tl_ticker} 事件时间轴")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("未获取到行情数据。")

            if not events.empty:
                st.markdown("#### 事件列表")
                st.dataframe(events[["date", "title", "type"]].sort_values("date", ascending=False),
                             use_container_width=True)
            else:
                st.info("当前事件库为空，请在下方添加事件。")
        except Exception as e:
            st.error(f"生成失败: {e}")

# ------------------------------------------------------------------
# 事件管理
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("事件管理")

with st.form("add_event_form"):
    col1, col2 = st.columns(2)
    with col1:
        evt_date = st.date_input("事件日期", value=datetime.now(), key="evt_date")
        evt_ticker = st.text_input("关联股票代码", value="", key="evt_ticker")
    with col2:
        evt_type = st.selectbox("事件类型", options=["利好", "利空", "中性"])
        evt_title = st.text_input("事件标题", value="", key="evt_title",
                                  placeholder="如：煤炭价格大涨10%")

    add_submitted = st.form_submit_button("添加事件")

if add_submitted and evt_title:
    try:
        engine.add_event(evt_date.strftime("%Y-%m-%d"), evt_ticker, evt_title, evt_type)
        st.success("事件添加成功！")
    except Exception as e:
        st.error(f"添加失败: {e}")

# 显示现有事件
events_all = engine._load_events()
if not events_all.empty:
    st.markdown("#### 现有事件库")
    st.dataframe(events_all[["date", "ticker", "title", "type"]].sort_values("date", ascending=False),
                 use_container_width=True)

# ------------------------------------------------------------------
# 新闻事件自动挖掘（新增）
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("新闻事件自动挖掘")
st.caption("一键抓取最新新闻 → jieba 关键词提取 → 金融情感分析 → 自动入库")

col_mine1, col_mine2 = st.columns(2)
with col_mine1:
    mine_keyword = st.text_input("挖掘关键词（留空抓财经要闻）", value="煤炭", key="mine_keyword")
with col_mine2:
    mine_limit = st.slider("抓取条数", min_value=10, max_value=50, value=20)

if st.button("一键挖掘新闻事件", type="primary"):
    with st.spinner("正在抓取新闻并分析..."):
        try:
            mined = engine.auto_mine_events(
                keyword=mine_keyword or None,
                source="eastmoney",
                limit=mine_limit
            )
            if mined.empty:
                st.warning("未抓取到新闻，请稍后重试。")
            else:
                st.success(f"成功挖掘 {len(mined)} 条事件并入库！")

                # 情感分布
                col_s1, col_s2, col_s3 = st.columns(3)
                pos_count = len(mined[mined["type"] == "正面"])
                neg_count = len(mined[mined["type"] == "负面"])
                neu_count = len(mined[mined["type"] == "中性"])
                with col_s1:
                    st.metric("正面事件", f"{pos_count} 条")
                with col_s2:
                    st.metric("负面事件", f"{neg_count} 条")
                with col_s3:
                    st.metric("中性事件", f"{neu_count} 条")

                # 挖掘结果
                st.markdown("#### 挖掘结果")
                display_cols = [c for c in ["date", "ticker", "title", "type", "keywords", "sentiment_score"] if c in mined.columns]
                st.dataframe(mined[display_cols].sort_values("date", ascending=False),
                             use_container_width=True)
        except Exception as e:
            st.error(f"挖掘失败: {e}")

# ------------------------------------------------------------------
# 情感分析报告（新增）
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("新闻情感分析报告")

report_keyword = st.text_input("分析关键词", value="煤炭", key="report_keyword")
if st.button("生成情感报告"):
    with st.spinner("正在生成情感分析报告..."):
        try:
            report = engine.sentiment_report(keyword=report_keyword or None, limit=50)

            if report["total"] == 0:
                st.warning("未抓取到新闻。")
            else:
                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                with col_r1:
                    st.metric("新闻总数", f"{report['total']} 条")
                with col_r2:
                    st.metric("正面占比", f"{report['positive_pct']}%")
                with col_r3:
                    st.metric("负面占比", f"{report['negative_pct']}%")
                with col_r4:
                    st.metric("中性占比", f"{report['neutral_pct']}%")

                # 情感分布饼图
                import plotly.express as px
                pie_df = pd.DataFrame([
                    {"类型": "正面", "占比": report["positive_pct"]},
                    {"类型": "负面", "占比": report["negative_pct"]},
                    {"类型": "中性", "占比": report["neutral_pct"]},
                ])
                color_map = {"正面": "#e74c3c", "负面": "#2ecc71", "中性": "#95a5a6"}
                fig_pie = px.pie(pie_df, values="占比", names="类型",
                                 color="类型", color_discrete_map=color_map,
                                 title=f"「{report_keyword}」新闻情感分布")
                fig_pie.update_layout(template="plotly_white", height=350)
                st.plotly_chart(fig_pie, use_container_width=True)

                # 热门关键词
                if report["top_keywords"]:
                    st.markdown("#### 热门关键词 TOP15")
                    kw_df = pd.DataFrame(report["top_keywords"], columns=["关键词", "频次"])
                    fig_kw = px.bar(kw_df, x="频次", y="关键词", orientation="h",
                                    title="关键词频次排行",
                                    color="频次", color_continuous_scale="Reds")
                    fig_kw.update_layout(template="plotly_white", height=400,
                                         yaxis=dict(autorange="reversed"))
                    st.plotly_chart(fig_kw, use_container_width=True)

                # 样本新闻
                if report["sample_news"]:
                    st.markdown("#### 正负面新闻样本")
                    for s in report["sample_news"]:
                        color = "#e74c3c" if s["sentiment"] == "正面" else "#2ecc71"
                        st.markdown(
                            f"<span style='color:{color};font-weight:500'>[{s['sentiment']}]</span> "
                            f"{s['title']} <small>(情感分: {s['score']})</small>",
                            unsafe_allow_html=True
                        )
        except Exception as e:
            st.error(f"生成报告失败: {e}")
