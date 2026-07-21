"""
modules/fundamental_helpers.py
──────────────────────────────
从 pages/E_基本面分析.py 抽出的纯函数簇与常量（#408 拆分超大文件）。
仅依赖 pandas / numpy，不依赖 streamlit / fetcher / session_state，便于复用与单测。
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def _to_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("%", "").strip()
        if s in ("", "-", "--", "nan", "None"):
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None

def _find_col(df, exact, suffixes):
    for c in df.columns:
        if str(c) in exact:
            return c
    for c in df.columns:
        for s in suffixes:
            if str(c).endswith(s):
                return c
    return None

def _find_period_col(df: pd.DataFrame):
    if "报告期" in df.columns:
        return "报告期"
    for c in df.columns:
        cs = str(c)
        if any(k in cs for k in ("报告期", "报告日", "报告年度", "会计期间")):
            return c
    return None

def _extract_metric_series(df: pd.DataFrame | None, candidates: list) -> pd.Series | None:
    """从财务 DataFrame（行=报告期，列=科目）中提取指标时间序列。"""
    if df is None or df.empty:
        return None
    pcol = _find_period_col(df)
    if pcol is None:
        return None
    mcol = None
    for cand in candidates:
        for c in df.columns:
            if str(c) == cand or str(c).replace(" ", "") == cand:
                mcol = c
                break
        if mcol:
            break
    if mcol is None:
        for cand in candidates:
            for c in df.columns:
                if cand in str(c):
                    mcol = c
                    break
            if mcol:
                break
    if mcol is None:
        return None
    tmp = df[[pcol, mcol]].copy()
    tmp[pcol] = tmp[pcol].astype(str).str.strip()
    tmp[mcol] = pd.to_numeric(tmp[mcol], errors="coerce")
    tmp = tmp.dropna()
    if tmp.empty:
        return None
    tmp[pcol] = pd.to_datetime(tmp[pcol], errors="coerce")
    tmp = tmp.dropna(subset=[pcol])
    return tmp.set_index(pcol)[mcol].sort_index()

def _period_label(dt: pd.Timestamp, mode: str) -> str:
    if mode == "年度":
        return f"{dt.year}年报"
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}Q{q}"

def _compute_yoy(s: pd.Series) -> pd.Series:
    """计算同比：与一年前最近报告期比较。"""
    if s is None or s.empty:
        return pd.Series(dtype=float)
    s = s.sort_index()
    yoy = {}
    for idx, val in s.items():
        prev_idx = idx - pd.DateOffset(years=1)
        mask = (s.index >= prev_idx - pd.Timedelta(days=10)) & (s.index <= prev_idx + pd.Timedelta(days=10))
        if mask.any():
            pv = s.loc[mask].iloc[0]
            if pv and pv != 0:
                yoy[idx] = round((val - pv) / abs(pv) * 100, 2)
    return pd.Series(yoy)

def _compute_qoq(s: pd.Series) -> pd.Series:
    """计算环比：与上一个报告期比较。"""
    if s is None or s.empty:
        return pd.Series(dtype=float)
    s = s.sort_index()
    qoq = {}
    prev = None
    for idx, val in s.items():
        if prev is not None and prev != 0:
            qoq[idx] = round((val - prev) / abs(prev) * 100, 2)
        prev = val
    return pd.Series(qoq)

_FINANCIAL_METRICS = {
    "归母净利润": {"unit": "亿元", "fmt": "{:.2f}亿", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "营业总收入": {"unit": "亿元", "fmt": "{:.2f}亿", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "扣非净利润": {"unit": "亿元", "fmt": "{:.2f}亿", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "净资产收益率": {"unit": "%", "fmt": "{:.2f}%", "yoy_fmt": "{:+.2f}pct", "qoq_fmt": "{:+.2f}pct"},
    "销售净利率": {"unit": "%", "fmt": "{:.2f}%", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "销售毛利率": {"unit": "%", "fmt": "{:.2f}%", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "每股经营现金流": {"unit": "元", "fmt": "{:.2f}元", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
    "每股收益": {"unit": "元", "fmt": "{:.2f}元", "yoy_fmt": "{:+.2f}%", "qoq_fmt": "{:+.2f}%"},
}

def _fmt_fin_value(v, metric: str) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    cfg = _FINANCIAL_METRICS.get(metric, {})
    try:
        return cfg.get("fmt", "{:.2f}").format(float(v))
    except Exception:
        return str(v)

def _fmt_fin_yoy(v, metric: str) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    cfg = _FINANCIAL_METRICS.get(metric, {})
    try:
        return cfg.get("yoy_fmt", "{:+.2f}%").format(float(v))
    except Exception:
        return str(v)

def _fmt_fin_qoq(v, metric: str) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    cfg = _FINANCIAL_METRICS.get(metric, {})
    try:
        return cfg.get("qoq_fmt", "{:+.2f}%").format(float(v))
    except Exception:
        return str(v)

def _to_float(x):
    try:
        return float(x) if x not in (None, "", "—") else None
    except Exception:
        return None

def _percentile(series: pd.Series, value: float) -> float | None:
    """计算 value 在 series 中的百分位（0-100）。"""
    if series is None or series.empty or value is None:
        return None
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return float(np.clip((s <= value).mean() * 100, 0, 100))

def _pe_status(pe: float | None) -> str:
    if pe is None or pe <= 0:
        return "—"
    if pe < 15:
        return "低估区间"
    if pe < 30:
        return "合理区间"
    if pe < 50:
        return "偏高区间"
    return "高估区间"

def _tag(text: str, level: str) -> str:
    """语义化彩色标签：good/warn/bad/neu（仅用于基本面「好/坏」语义，非价格涨跌色）。"""
    colors = {"good": "#16a34a", "warn": "#d97706", "bad": "#dc2626", "neu": "#6b7280"}
    c = colors.get(level, "#6b7280")
    return (f'<span style="display:inline-block;font-size:12px;font-weight:600;'
            f'padding:2px 9px;border-radius:12px;background:{c}1a;color:{c};'
            f'border:1px solid {c}55;">{text}</span>')

_INDUSTRY_SECTOR_MAP = {
    # 申万/东财行业名 -> 同花顺/东财板块名（sector_list 中实际出现的）
    "白酒": "酿酒概念",
    "白酒Ⅱ": "酿酒概念",
    "白酒II": "酿酒概念",
    "啤酒": "酿酒概念",
    "葡萄酒": "酿酒概念",
    "其他酒类": "酿酒概念",
    "非白酒": "酿酒概念",
    "饮料乳品": "乳业",
    "乳品": "乳业",
    "食品综合": "食品",
    "食品加工": "食品",
    "休闲食品": "食品",
    "调味发酵品": "调味品概念",
    "调味发酵品Ⅱ": "调味品概念",
    "生物制品": "生物疫苗",
    "生物制品Ⅱ": "生物疫苗",
    "中药": "中药概念",
    "中药Ⅱ": "中药概念",
    "化学制药": "化学制药",
    "医疗器械": "医疗器械",
    "医疗服务": "医疗服务",
    "医药商业": "医药商业",
    "酒店餐饮": "旅游酒店",
    "旅游及景区": "旅游酒店",
    "旅游零售": "商业百货",
    "一般零售": "商业百货",
    "专业连锁": "商业百货",
    "贸易": "商业百货",
    "证券": "券商概念",
    "证券Ⅱ": "券商概念",
    "保险": "保险",
    "保险Ⅱ": "保险",
    "银行": "银行",
    "多元金融": "多元金融",
    "房地产开发": "房地产开发",
    "住宅开发": "房地产开发",
    "商业地产": "房地产开发",
    "房地产": "房地产开发",
    "电力": "电力行业",
    "燃气": "燃气",
    "水务": "水务",
    "煤炭开采": "煤炭行业",
    "焦炭": "煤炭行业",
    "动力煤": "煤炭行业",
    "石油开采": "石油行业",
    "炼化及贸易": "石油行业",
    "油服工程": "油气设服",
    "钢铁": "钢铁行业",
    "普钢": "钢铁行业",
    "特钢": "钢铁行业",
    "冶钢原料": "钢铁行业",
    "水泥": "水泥建材",
    "装修建材": "装修建材",
    "化工": "化工原料",
    "化学原料": "化工原料",
    "化学制品": "化工原料",
    "农化制品": "农药兽药",
    "化肥": "农药兽药",
    "造纸": "造纸印刷",
    "包装印刷": "包装印刷",
    "塑料": "塑料制品",
    "橡胶": "橡胶制品",
    "工业金属": "基本金属",
    "贵金属": "贵金属",
    "小金属": "小金属",
    "能源金属": "能源金属",
    "金属新材料": "新材料",
    "非金属材料": "非金属材料",
    "半导体": "半导体",
    "元件": "电子元件",
    "电子元件": "电子元件",
    "光学光电子": "光学光电子",
    "消费电子": "消费电子",
    "其他电子": "电子元件",
    "计算机设备": "计算机设备",
    "软件开发": "国产软件",
    "IT服务": "互联网服务",
    "互联网服务": "互联网服务",
    "互联网电商": "互联网服务",
    "通信设备": "通信设备",
    "通信服务": "通信服务",
    "军工电子": "军工",
    "航空装备": "航天航空",
    "航天装备": "航天航空",
    "航天航空": "航天航空",
    "汽车零部件": "汽车零部件",
    "汽车整车": "汽车整车",
    "商用车": "汽车整车",
    "乘用车": "汽车整车",
    "摩托车及其他": "汽车整车",
    "电机": "电机",
    "电网设备": "电网设备",
    "光伏设备": "光伏设备",
    "风电设备": "风电设备",
    "电池": "电池",
    "电源设备": "电源设备",
    "其他电源设备": "电源设备",
    "家电零部件": "家电行业",
    "黑色家电": "家电行业",
    "白色家电": "家电行业",
    "小家电": "家电行业",
    "厨卫电器": "家电行业",
    "照明设备": "家电行业",
    "其他家电": "家电行业",
    "纺织制造": "纺织服装",
    "服装家纺": "纺织服装",
    "化学纤维": "化纤行业",
    "种植业": "农业种植",
    "农产品加工": "农业种植",
    "饲料": "农牧饲渔",
    "养殖": "农牧饲渔",
    "渔业": "农牧饲渔",
    "林业": "农业种植",
    "环保": "节能环保",
    "工程建设": "工程建设",
    "房屋建设": "工程建设",
    "专业工程": "工程建设",
    "工程咨询服务": "工程咨询服务",
    "装修装饰": "装修装饰",
    "建筑装修": "装修装饰",
    "物流": "物流行业",
    "公路铁路": "铁路公路",
    "铁路": "铁路公路",
    "公路": "铁路公路",
    "公交": "公交",
    "航运": "航运港口",
    "港口": "航运港口",
    "机场": "航空机场",
    "航空运输": "航空机场",
    "交运设备": "交运设备",
    "传媒": "文化传媒",
    "广告营销": "文化传媒",
    "影视院线": "影视概念",
    "游戏": "网络游戏",
    "游戏Ⅱ": "网络游戏",
    "体育": "体育概念",
    "教育": "教育",
    "美容护理": "美容护理",
    "社会服务": "社会服务",
}

def _normalize_industry(industry: str) -> str:
    """把申万/东财行业名（如 白酒Ⅱ）清洗为便于映射的键。"""
    if not industry:
        return ""
    s = industry.strip()
    # 去除罗马数字、阿拉伯数字后缀、空格
    s = s.replace("Ⅲ", "").replace("Ⅱ", "").replace("III", "").replace("II", "").strip()
    return s

def _find_sector_name(sector_df: pd.DataFrame, industry: str) -> str | None:
    """把个股行业名映射到 sector_list 中的板块名；支持映射表 + 模糊匹配。"""
    if not industry or sector_df is None or sector_df.empty:
        return None
    sectors = sector_df["sector"].astype(str).tolist()
    # 1) 精确映射
    mapped = _INDUSTRY_SECTOR_MAP.get(industry) or _INDUSTRY_SECTOR_MAP.get(_normalize_industry(industry))
    if mapped and mapped in sectors:
        return mapped
    # 2) 子串匹配（优先原串，再清洗后）
    for cand in (industry, _normalize_industry(industry)):
        if not cand:
            continue
        for sec in sectors:
            if cand in sec or sec in cand:
                return sec
    # 3) 关键词匹配（取行业名中核心 2-4 字尝试命中板块）
    keywords = [industry[i:j] for i in range(len(industry)) for j in range(i + 2, min(i + 5, len(industry) + 1))]
    for kw in keywords:
        for sec in sectors:
            if kw in sec:
                return sec
    return None

def _sector_rank(sector_df: pd.DataFrame, industry: str) -> int | None:
    if sector_df is None or sector_df.empty or not industry:
        return None
    df = sector_df.copy()
    df["change_pct"] = pd.to_numeric(df.get("change_pct", 0), errors="coerce").fillna(0)
    df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    sector_name = _find_sector_name(df, industry)
    if sector_name:
        hits = df[df["sector"].astype(str) == sector_name]
        if not hits.empty:
            return int(hits.iloc[0]["rank"])
    return None

def _composite_score(
    price, pe, hist_pct_5y, sector_rank, sector_total, market_cap, perf
) -> tuple[int, str]:
    """返回 0-100 的综合评分与解读文本（Batch8 #277：新增盈利成长 + 偿债安全维度）。"""
    reasons = []
    perf = perf or {}
    # 1) 估值合理性(PE) 20 分
    pe_score = 10.0
    if pe is not None and pe > 0:
        if pe < 15:
            pe_score = 18.0
            reasons.append(f"✅ PE(TTM) {pe:.1f} 处于低估区间，安全边际较高")
        elif pe < 30:
            pe_score = 15.0
            reasons.append(f"✅ PE(TTM) {pe:.1f} 估值合理")
        elif pe < 50:
            pe_score = 8.0
            reasons.append(f"⚠️ PE(TTM) {pe:.1f} 估值偏高，需业绩支撑")
        else:
            pe_score = 3.0
            reasons.append(f"❌ PE(TTM) {pe:.1f} 估值偏高，注意回撤风险")
    else:
        reasons.append("ℹ️ 暂无有效 PE 数据")

    # 2) 历史位置 15 分
    hist_score = 7.5
    if hist_pct_5y is not None:
        if 40 <= hist_pct_5y <= 75:
            hist_score = 13.0
            reasons.append(f"✅ 5年价格分位 {hist_pct_5y:.1f}%，处于健康区间")
        elif hist_pct_5y < 20:
            hist_score = 9.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，处于历史低位（偏弱或超跌）")
        elif hist_pct_5y > 90:
            hist_score = 5.0
            reasons.append(f"⚠️ 5年价格分位 {hist_pct_5y:.1f}%，接近历史高位")
        else:
            hist_score = 10.0
            reasons.append(f"ℹ️ 5年价格分位 {hist_pct_5y:.1f}%")
    else:
        reasons.append("ℹ️ 暂无历史位置数据")

    # 3) 行业动能 20 分
    theme_score = 10.0
    if sector_rank is not None and sector_total > 0:
        if sector_rank <= 5:
            theme_score = 18.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，位于主线前列")
        elif sector_rank <= 20:
            theme_score = 14.0
            reasons.append(f"✅ 行业排名 #{sector_rank} / {sector_total}，动能较好")
        elif sector_rank <= sector_total * 0.5:
            theme_score = 10.0
            reasons.append(f"ℹ️ 行业排名 #{sector_rank} / {sector_total}，中等水平")
        else:
            theme_score = 5.0
            reasons.append(f"⚠️ 行业排名 #{sector_rank} / {sector_total}，相对落后")
    else:
        reasons.append("ℹ️ 暂无行业排名数据")

    # 4) 市值规模 15 分
    cap_score = 7.5
    if market_cap is not None and market_cap > 0:
        if market_cap >= 1000:
            cap_score = 13.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，大盘蓝筹，抗风险强")
        elif market_cap >= 300:
            cap_score = 11.0
            reasons.append(f"✅ 总市值 {market_cap:.1f} 亿，中大盘")
        elif market_cap >= 50:
            cap_score = 8.0
            reasons.append(f"ℹ️ 总市值 {market_cap:.1f} 亿，中小盘")
        else:
            cap_score = 5.0
            reasons.append(f"⚠️ 总市值 {market_cap:.1f} 亿，小盘股波动大")
    else:
        reasons.append("ℹ️ 暂无市值数据")

    # 5) 盈利成长 20 分（结合营收/净利润同比）
    growth_score = 10.0
    rev_yoy = perf.get("revenue_yoy")
    pr_yoy = perf.get("profit_yoy")
    if rev_yoy is not None and pr_yoy is not None:
        if rev_yoy > 0 and pr_yoy > 0:
            growth_score = 18.0
            reasons.append(f"✅ 营收同比 +{rev_yoy:.1f}%、净利润同比 +{pr_yoy:.1f}%，业绩双增")
        elif rev_yoy > 0:
            growth_score = 13.0
            reasons.append(f"ℹ️ 营收同比 +{rev_yoy:.1f}%，但净利润同比 {pr_yoy:.1f}%")
        elif pr_yoy > 0:
            growth_score = 12.0
            reasons.append(f"⚠️ 营收同比 {rev_yoy:.1f}%，净利润同比 +{pr_yoy:.1f}%")
        else:
            growth_score = 5.0
            reasons.append(f"❌ 营收同比 {rev_yoy:.1f}%、净利润同比 {pr_yoy:.1f}%，业绩承压")
    elif rev_yoy is not None:
        growth_score = 12.0 if rev_yoy > 0 else 7.0
        reasons.append(f"ℹ️ 营收同比 {rev_yoy:+.1f}%（净利润同比暂无）")
    else:
        reasons.append("ℹ️ 暂无业绩同比数据")

    # 6) 偿债安全 10 分（资产负债率 + 流动比率）
    safe_score = 5.0
    alr = perf.get("alr")
    cr = perf.get("current_ratio")
    if alr is not None:
        if alr < 40:
            safe_score += 3.0
            reasons.append(f"✅ 资产负债率 {alr:.1f}%，偿债压力低")
        elif alr < 60:
            safe_score += 2.0
            reasons.append(f"ℹ️ 资产负债率 {alr:.1f}%，处于适中水平")
        else:
            safe_score += 0.0
            reasons.append(f"⚠️ 资产负债率 {alr:.1f}%，偏高，关注杠杆风险")
    if cr is not None:
        if cr >= 1.5:
            safe_score += 2.0
            reasons.append(f"✅ 流动比率 {cr:.2f}，短期偿债能力较强")
        elif cr >= 1:
            safe_score += 1.0
            reasons.append(f"ℹ️ 流动比率 {cr:.2f}，处于临界水平")
        else:
            safe_score += 0.0
            reasons.append(f"⚠️ 流动比率 {cr:.2f}，短期偿债偏紧")

    score = pe_score + hist_score + theme_score + cap_score + growth_score + safe_score
    score = int(round(np.clip(score, 0, 100)))
    return score, "<br>".join(reasons)


def calc_alr(code: str, fetcher) -> float | None:
    """从资产负债表解析资产负债率(%) = 负债合计 / 资产总计 × 100；失败返回 None。

    纯函数（fetcher 以参数注入，模块不依赖 fetcher）。兼容 akshare 新浪资产负债表
    两种结构：列=科目(最新报告期在第 0 行) 或 行=科目(首列=科目名)。
    """
    try:
        df = fetcher.get_financial(code, "balance")
        if df is None or len(df) == 0:
            return None

        def _find_col(exact, suffix):
            for c in df.columns:
                if str(c) in exact:
                    return c
            for c in df.columns:
                if str(c).endswith(suffix):
                    return c
            return None

        asset_c = _find_col({"资产总计", "资产合计"}, ("资产总计", "资产合计"))
        liab_c = _find_col({"负债合计", "负债总计"}, ("负债合计", "负债总计"))

        if asset_c is not None and liab_c is not None:
            av = _to_num(df.iloc[0][asset_c])
            lv = _to_num(df.iloc[0][liab_c])
            if av and lv:
                return round(lv / av * 100, 2)

        item_col = df.columns[0]
        av = lv = None
        for _, row in df.iterrows():
            it = str(row[item_col])
            if av is None and any(k in it for k in ("资产总计", "资产合计")):
                vals = [x for x in (_to_num(v) for v in row[1:]) if x is not None]
                if vals:
                    av = vals[-1]
            if lv is None and any(k in it for k in ("负债合计", "负债总计")):
                vals = [x for x in (_to_num(v) for v in row[1:]) if x is not None]
                if vals:
                    lv = vals[-1]
        if av and lv:
            return round(lv / av * 100, 2)
    except Exception:
        return None
    return None


def fund_one(code: str, fetcher) -> tuple:
    """线程内并行取 (市盈率TTM, 资产负债率%)；任一项失败返回 None。"""
    pe = alr = None
    try:
        f = fetcher.get_fundamentals(code)
        if isinstance(f, dict):
            pe = f.get("pe_ttm")
    except Exception:
        pe = None
    try:
        alr = calc_alr(code, fetcher)
    except Exception:
        alr = None
    return code, pe, alr

