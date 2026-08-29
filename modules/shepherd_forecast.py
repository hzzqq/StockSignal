"""
modules/shepherd_forecast.py — 牧羊人指标「次日走势预判」引擎

把当日 17 项牧羊人指标映射为「次日大概率走向」，并标注指标之间的联动关系。

═══════════════════════════════════════════════════════════════
理论依据（杨哥视频方法论 + A股短线情绪周期实战复盘框架）
═══════════════════════════════════════════════════════════════

一、情绪周期六阶段（决定次日走向的「位置」）
    冰点 → 修复试探 → 修复确认 → 主升高潮 → 高潮分化 → 退潮

    · 冰点：跌停>100家、涨停<40家、最高板≤3板、上涨家数枯竭
            → 恐慌彻底出清，往往是新一轮修复的起点
    · 修复试探：跌停收敛、涨停回升，但缩量 + 高炸板率 + 梯队断层 + 晋级率低迷
            → 「看着热闹实则虚弱」，是中继反抽而非新周期，警惕二次探底
    · 修复确认：最高板晋级成功 + 炸板率回落<25% + 跌停个位数 + 量能放大
            → 新周期启动信号
    · 主升高潮：最高板连续打开(6板+) + 涨停家数高位 + 炸板率<15% + 主线清晰
    · 高潮分化：炸板率飙升至40%+ + 指数与情绪背离 + 轮动加速 + 高度断崖
    · 退潮：高度递减 + 跌停回升 + 炸板率高企 + 晋级率低迷

二、反向修复规律（V反）—— 当日越惨，次日越容易修复
    · 炸板率 ≥50%        → 抛压当日已释放，次日易低开高走 V反（杨哥核心规律）
    · 回头波>10% ≥30~50家 → 追高者当日被套，次日易有抄底盘 V反（杨哥核心规律）
    · 跌停 >100家        → 情绪冰点，恐慌出清后次日修复概率高

三、正向延续规律 —— 当日越强，次日越容易接力
    · 昨日涨停溢价 >3%   → 赚钱效应炸裂，次日接力意愿强
    · 连板高度打开(6板+) → 空间打开，进入主升
    · 连板梯队厚(≥15家)  → 赚钱效应扩散，不是「一只独苗」
    · 炸板率 <15%       → 主升浪健康区间，封板资金信心足

四、弱修复识别（量价背离）
    · 缩量 + 普涨        → 场外资金未入场，是存量博弈自救，修复质量差
    · 缩量 + 高炸板率    → 抛压重且无增量，二次探底风险高

五、中期顶背离
    · 两融余额增 + 指数不创新高 → 杠杆资金进场但未推动指数，警惕见顶

六、指标联动（组合信号比单指标更可靠）
    · 炸板率↑ + 回头波↑        → V反概率叠加（双重确认）
    · 炸板率↑ + 涨停家数↓      → 退潮确认（分歧大且无赚钱效应）
    · 炸板率↓ + 连板高度↑      → 主升确认（封板稳 + 空间打开）
    · 跌停↑ + 中位数大跌       → 恐慌见底，次日修复
    · 缩量 + 普涨              → 弱修复（存量博弈）
    · 昨板表现↑ + 梯队厚        → 接力强
    · 两融↑ + 指数不新高        → 顶背离

七、外部资料交叉验证（2026-08-29 检索，多来源口径一致）
    实盘复盘圈「盯四个数」的口径与本引擎高度吻合，可作为外部佐证：
      · 涨停÷跌停比值：比值连续 2~3 天抬升+跌停收敛=回暖；
                        比值<1 且跌停>15 家=退潮 → 已实现为派生指标 zt_ld_ratio
      · 昨日涨停今日平均涨幅：连续两天<2%=打板亏钱（容错率极低）；
                              稳定>4%=情绪高潮 → 即 zt_prev_ret，权重最高的正向指标
      · 市场空间板高度：7板→3板=冰点；3板→5板以上=风险偏好回升 → 即 connect_hl
      · 连板梯队完整性：「仅一只高位独苗+中位断层」=虚假回暖；
                        「首板/二板/高位梯队完整」=健康 → 即 connect_2b + get_zt_ladder 断层检测
      · 量能：缩量普涨=存量自救（弱修复），放量上涨=增量入场（真修复）→ 即 turnover_amt 环比

    ⚠️ 已知缺口：分档「晋级率」（首板进二板 / 2进3 / 高位晋级率）在实盘复盘中
       比「连板家数」更精细，但历史数据未保存分档明细，当前无法回溯计算。
       若要补，需要在 shepherd 历史重跑时落盘各档家数（zt_pool 的连板数字段已可得）。

设计原则：
    ✅ 纯函数为主（forecast_next_day / locate_cycle / score_next_day），可离线单测
    ✅ 单源缺失优雅降级：某项指标缺失则该规则不参与打分，不抛异常
    ✅ 只做统计规律映射，不构成投资建议
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  一、次日预测指标表（哪些指标最能反映第二天走势）
#     dir: +1 当日值越高→次日越强（正向延续）
#          -1 当日值越高→次日越容易修复/V反（反向修复）
#           0 观察项，不直接预测
# ═══════════════════════════════════════════════════════════════
FORECAST_INDICATORS = [
    # ── A 类：反向修复指标（当日越差 → 次日越容易 V反修复）──
    dict(
        key="zt_fail_ratio", name="炸板率", unit="%", dir=-1, weight=20,
        why="炸板率=炸板/(涨停+炸板)。封不住板说明当日抛压已经释放，"
             "次日低开后容易有抄底盘拉起 V 反。杨哥：≥50% 次日易 V反。",
        bands=[
            (0, 15, "健康一致", "封板稳，主升浪区间，次日多延续", "#ee2a2a"),
            (15, 25, "温和分歧", "接力有分歧但可控，次日震荡偏强", "#f59e0b"),
            (25, 40, "明显分歧", "抛压重、封板资金信心不足，次日分歧延续", "#3b82f6"),
            (40, 50, "高位分歧", "高潮末端/退潮特征，警惕高度断崖", "#7c5cff"),
            (50, 999, "抛压释放", "★ 杨哥规律：≥50% 次日易 V 型反弹", "#00d486"),
        ],
    ),
    dict(
        key="hb_wave10", name="回头波>10%家数", unit="家", dir=-1, weight=15,
        why="日内从最高点回撤超10%的家数 = 当日追高者被套的程度。"
             "套得越狠，次日越容易有抄底盘做 V 反。杨哥：≥30~50 家次日易 V反。",
        bands=[
            (0, 20, "追高安全", "高位回撤少，持股体验好", "#ee2a2a"),
            (20, 50, "开始分歧", "部分高位股跳水，谨慎追高", "#f59e0b"),
            (50, 999, "抛压释放", "★ 杨哥规律：≥30~50 家次日易 V 型反弹", "#00d486"),
        ],
    ),
    dict(
        key="limit_down", name="跌停家数", unit="家", dir=-1, weight=12,
        why="亏钱效应的直接度量。跌停越多说明恐慌越彻底，"
             "出清之后次日修复概率越高；反之跌停回升是二次探底信号。",
        bands=[
            (0, 10, "亏钱效应收敛", "恐慌盘基本出清，健康", "#ee2a2a"),
            (10, 30, "有亏钱效应", "部分个股杀跌，控制仓位", "#f59e0b"),
            (30, 100, "恐慌蔓延", "亏钱效应明显，等待出清", "#3b82f6"),
            (100, 99999, "情绪冰点", "★ 恐慌彻底出清，次日修复概率高", "#00d486"),
        ],
    ),
    # ── B 类：正向延续指标（当日越好 → 次日越容易接力）──
    dict(
        key="zt_prev_ret", name="昨日涨停表现", unit="%", dir=1, weight=20,
        why="昨日涨停股今天平均赚多少 = 最直接的赚钱效应。"
             "有溢价才有人愿意次日接力；吃面则接力意愿崩塌。",
        bands=[
            (-999, -2, "吃面", "昨板亏钱，次日接力意愿弱", "#00d486"),
            (-2, 0, "溢价弱", "打板不赚钱，谨慎", "#3b82f6"),
            (0, 3, "正常溢价", "有赚钱效应，可参与", "#f59e0b"),
            (3, 999, "炸裂", "★ 赚钱效应强，次日接力意愿高", "#ee2a2a"),
        ],
    ),
    dict(
        key="connect_hl", name="连板高度", unit="板", dir=1, weight=15,
        why="市场最高板 = 情绪的空间高度。高度递增=上升期，"
             "断崖式下降=退潮开启，6板以上=主升空间打开。",
        bands=[
            (0, 3, "冰点高度", "空间被压缩到极致，等待修复", "#00d486"),
            (3, 5, "修复中", "高度温和上移，但未打开", "#3b82f6"),
            (5, 7, "高度打开", "★ 空间打开，进入主升", "#f59e0b"),
            (7, 999, "高位", "高潮区，注意分歧与断板风险", "#ee2a2a"),
        ],
    ),
    dict(
        key="connect_2b", name="连板家数(≥2板)", unit="家", dir=1, weight=13,
        why="梯队厚度。≥15家说明赚钱效应在扩散（线状）；"
             "少于5家是「一只独苗」，主线缺乏补涨梯队，持续性差。",
        bands=[
            (0, 5, "梯队断层", "只有独苗，主线缺乏补涨", "#00d486"),
            (5, 15, "梯队正常", "有一定接力，但不够厚", "#3b82f6"),
            (15, 30, "梯队厚", "★ 赚钱效应扩散，接力顺畅", "#f59e0b"),
            (30, 99999, "梯队极厚", "高潮特征，注意盛极而衰", "#ee2a2a"),
        ],
    ),
    dict(
        key="fc_ratio", name="平均封成比", unit="", dir=1, weight=8,
        why="封板资金/成交额。封成比高说明封单扎实、抛压小，"
             "次日溢价概率高；封成比低则是虚板，容易炸。",
        bands=[
            (0, 0.4, "封板弱", "封单薄，次日溢价难", "#00d486"),
            (0.4, 1.0, "封板正常", "封单一般", "#f59e0b"),
            (1.0, 999, "封板强", "★ 封单扎实，次日溢价概率高", "#ee2a2a"),
        ],
    ),
    # ── C 类：观察/确认项 ──
    dict(
        key="turnover_amt", name="全A成交额", unit="亿", dir=0, weight=0,
        why="量能是「确认项」而非预测项：缩量普涨=存量自救（弱修复），"
             "放量上涨=增量入场（真修复）。需与前一日对比才有效。",
        bands=[],
    ),
    dict(
        key="median_chg", name="中位数涨跌幅", unit="%", dir=0, weight=0,
        why="当日「人均赚亏」。与跌停家数联动：跌停多 + 中位数大跌 = 恐慌见底。",
        bands=[],
    ),
    # ── D 类：派生指标（由现有指标现算，不需要新数据源）──
    dict(
        key="zt_ld_ratio", name="涨停/跌停比", unit="倍", dir=1, weight=10, derived=True,
        why="涨停家数 ÷ 跌停家数 = 多空力量对比（实盘复盘「四个数」之首）。"
             "比值连续 2~3 天抬升、跌停收敛 = 亏钱效应消退、情绪回暖；"
             "比值跌破 1 且跌停>15 家 = 空头占优，大概率进入退潮期。"
             "（注意：单日突发消息会干扰，看连续趋势更可靠）",
        bands=[
            (0, 1, "空头占优", "跌停多于涨停，亏钱效应扩散，退潮期", "#00d486"),
            (1, 3, "弱势平衡", "多空拉锯，控制仓位为主", "#3b82f6"),
            (3, 10, "多头占优", "赚钱效应正常，可参与", "#f59e0b"),
            (10, 40, "情绪健康", "★ 亏钱效应收敛，情绪回暖", "#ee2a2a"),
            (40, 99999, "极度健康", "跌停近乎清零（也可能是高潮末端）", "#ee2a2a"),
        ],
    ),
]

# 便于按 key 快速取配置
_FC_BY_KEY = {c["key"]: c for c in FORECAST_INDICATORS}


def _band_of(key, value):
    """返回 (档位名, 解读, 颜色)；指标缺失或无档位返回 None。"""
    cfg = _FC_BY_KEY.get(key)
    if not cfg or value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    for lo, hi, name, desc, color in cfg.get("bands", []):
        if lo <= v < hi:
            return name, desc, color
    return None


# ═══════════════════════════════════════════════════════════════
#  二、指标联动规则（组合信号比单指标更可靠）
#     cond: (指标key, 比较符, 阈值)  或 (key, "delta", 阈值) 表示与昨日的变化
# ═══════════════════════════════════════════════════════════════
LINKAGE_RULES = [
    dict(
        id="v_reversal_double",
        name="V反双确认",
        conds=[("zt_fail_ratio", ">=", 50), ("hb_wave10", ">=", 30)],
        logic="炸板率≥50% 且 回头波≥30家",
        effect="次日 V 型反弹概率显著提升（当日抛压已充分释放）",
        color="#00d486",
        tags=["看多次日", "V反"],
    ),
    dict(
        id="weak_repair",
        name="弱修复（量价背离）",
        conds=[("turnover_amt", "drop", 0), ("zt_fail_ratio", ">=", 25)],
        logic="成交额较昨日萎缩 且 炸板率≥25%",
        effect="缩量 + 高炸板 = 存量博弈自救，是中继反抽而非新周期，警惕二次探底",
        color="#3b82f6",
        tags=["谨慎", "弱修复"],
    ),
    dict(
        id="retreat_confirm",
        name="退潮确认",
        conds=[("zt_fail_ratio", ">=", 40), ("connect_2b", "<", 8)],
        logic="炸板率≥40% 且 连板梯队<8家",
        effect="分歧大且赚钱效应无法扩散，退潮概率高",
        color="#00d486",
        tags=["看空次日", "退潮"],
    ),
    dict(
        id="main_rise_confirm",
        name="主升确认",
        conds=[("zt_fail_ratio", "<", 20), ("connect_hl", ">=", 5), ("zt_prev_ret", ">", 1.0)],
        logic="炸板率<20% 且 最高板≥5板 且 昨板溢价>1%",
        effect="封板稳 + 空间打开 + 有溢价，赚钱效应可持续，次日偏强",
        color="#ee2a2a",
        tags=["看多次日", "主升"],
    ),
    dict(
        id="panic_bottom",
        name="恐慌见底",
        conds=[("limit_down", ">=", 60), ("median_chg", "<", -3)],
        logic="跌停≥60家 且 中位数跌幅>3%",
        effect="恐慌集中释放，接近冰点，次日技术性修复概率高",
        color="#00d486",
        tags=["看多次日", "冰点修复"],
    ),
    dict(
        id="relay_strong",
        name="接力环境好",
        conds=[("zt_prev_ret", ">=", 3), ("connect_2b", ">=", 12)],
        logic="昨板溢价≥3% 且 连板梯队≥12家",
        effect="赚钱效应 + 梯队扩散，打板接力环境健康",
        color="#ee2a2a",
        tags=["看多次日", "接力"],
    ),
    dict(
        id="euphoria_top",
        name="高潮过热（盛极而衰）",
        conds=[("limit_up", ">=", 100), ("zt_fail_ratio", ">=", 30)],
        logic="涨停≥100家 且 炸板率≥30%",
        effect="涨停家数高位但封板质量下降，高潮分化特征，注意见顶",
        color="#f59e0b",
        tags=["风险", "高潮"],
    ),
    dict(
        id="retreat_by_ratio",
        name="退潮（多空比失衡）",
        conds=[("zt_ld_ratio", "<", 3), ("limit_down", ">", 15)],
        logic="涨停/跌停比<3 且 跌停>15家",
        effect="☆ 实盘复盘口径：空头力量占优，亏钱效应扩散，大概率进入情绪退潮期，首要任务是控制仓位",
        color="#00d486",
        tags=["看空次日", "退潮"],
    ),
    dict(
        id="repair_by_ratio",
        name="回暖（多空比修复）",
        conds=[("zt_ld_ratio", ">=", 10), ("zt_fail_ratio", "<", 30)],
        logic="涨停/跌停比≥10 且 炸板率<30%",
        effect="☆ 实盘复盘口径：亏钱效应收敛且封板尚可，情绪回暖，可以提高关注度",
        color="#ee2a2a",
        tags=["看多次日", "回暖"],
    ),
]

_CMP = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


def _eval_cond(today, prev, key, op, thr):
    """评估单条联动条件。返回 True/False；数据缺失返回 False（不触发）。"""
    try:
        if op == "drop":
            # 需要 prev 做环比：今日值 < 昨日值 才算萎缩
            if prev is None:
                return False
            tv, pv = today.get(key), prev.get(key)
            if tv is None or pv is None:
                return False  # 任一侧缺失则不触发（避免误判为缩量）
            try:
                v, p = float(tv), float(pv)
            except (TypeError, ValueError):
                return False
            if v != v or p != p:  # NaN
                return False
            return v < p
        if key not in today or today.get(key) is None:
            return False
        v = float(today[key])
        if v != v:
            return False
        return _CMP[op](v, float(thr))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[shepherd_forecast] 联动条件评估异常 {key}{op}{thr}: {e}")
        return False


def eval_linkages(today: dict, prev: dict = None) -> list:
    """评估所有联动规则，返回命中的规则列表（含 name/logic/effect/color/tags）。

    派生指标（如涨停/跌停比 zt_ld_ratio）在此统一补齐，调用方直接喂原始指标即可。
    """
    today = with_derived(today)
    prev = with_derived(prev) if prev else None
    hits = []
    for rule in LINKAGE_RULES:
        try:
            if all(_eval_cond(today, prev, k, op, thr) for k, op, thr in rule["conds"]):
                hits.append(rule)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[shepherd_forecast] 联动规则 {rule.get('id')} 评估异常: {e}")
    return hits


# ═══════════════════════════════════════════════════════════════
#  三、情绪周期六阶段定位
# ═══════════════════════════════════════════════════════════════
CYCLES = [
    dict(id="ice", name="冰点", emoji="🥶", color="#00d486",
         desc="恐慌彻底出清，跌停遍地、高度压缩。往往是新一轮修复的起点。",
         bias="次日修复概率高（超跌反弹）"),
    dict(id="probe", name="修复试探", emoji="🌱", color="#3b82f6",
         desc="跌停收敛、涨停回升，但缩量 + 高炸板 + 梯队断层，"
              "是「看着热闹实则虚弱」的中继反抽，警惕二次探底。",
         bias="次日震荡分化，需量能与高度确认"),
    dict(id="confirm", name="修复确认", emoji="✅", color="#f59e0b",
         desc="最高板晋级成功 + 炸板率回落 + 跌停个位数，新周期启动信号。",
         bias="次日偏强，可适度参与"),
    dict(id="main", name="主升高潮", emoji="🔥", color="#ee2a2a",
         desc="最高板连续打开、涨停家数高位、炸板率低、主线清晰。",
         bias="次日多延续，但注意盛极而衰"),
    dict(id="diverge", name="高潮分化", emoji="⚠️", color="#7c5cff",
         desc="炸板率飙升至40%+、指数与情绪背离、轮动加速、高度断崖。",
         bias="次日分歧加大，降低仓位"),
    dict(id="retreat", name="退潮", emoji="📉", color="#00d486",
         desc="高度递减、跌停回升、炸板率高企、晋级率低迷。",
         bias="次日偏弱，等待出清"),
]


def _num(d, k):
    """安全取数：缺失/NaN 返回 None。"""
    if not d or k not in d:
        return None
    try:
        v = float(d[k])
        return None if v != v else v
    except Exception:
        return None


def with_derived(d: dict) -> dict:
    """补齐派生指标（不修改入参，返回新 dict；幂等）。

    目前派生：
      zt_ld_ratio = 涨停家数 / 跌停家数（多空力量对比，实盘复盘「四个数」之首）
        · 跌停为 0 时用 0.5 做分母（避免除零），并 clamp 到 999 倍，避免失真极值
        · 缺涨停家数时不派生（保持缺失语义，后续规则不会误触发）
    """
    if not d:
        return d
    out = dict(d)
    if "zt_ld_ratio" in out:
        return out
    lu, ld = _num(d, "limit_up"), _num(d, "limit_down")
    if lu is None:
        return out
    denom = ld if (ld is not None and ld > 0) else 0.5
    try:
        out["zt_ld_ratio"] = round(min(lu / denom, 999.0), 2)
    except Exception:  # noqa: BLE001
        pass
    return out


def locate_cycle(today: dict, prev: dict = None) -> dict:
    """情绪周期定位（纯函数）。返回命中的周期 dict + 判定依据列表。

    判定优先级（从最极端到最温和）：
      冰点 → 退潮 → 高潮分化 → 主升高潮 → 修复确认 → 修复试探

    ⚠️ 鲁棒性设计：历史长周期数据往往只有涨停池系列
       （limit_up / connect_hl / connect_2b / zt_fail_ratio / zt_prev_ret / fc_ratio），
       缺 limit_down / median_chg / turnover_amt 等。
       因此本函数**只用核心指标做主判定**，缺失指标仅作「加强证据」，
       绝不能因为某项缺失就直接落兜底（否则历史回测会全判成「修复试探」）。
    """
    reasons = []
    lu = _num(today, "limit_up")          # 涨停家数
    ld = _num(today, "limit_down")        # 跌停家数（历史常缺，仅加强）
    hl = _num(today, "connect_hl")        # 最高板
    zb = _num(today, "zt_fail_ratio")     # 炸板率
    c2 = _num(today, "connect_2b")        # 连板家数
    pr = _num(today, "zt_prev_ret")       # 昨板表现
    tu = _num(today, "turnover_amt")      # 成交额（历史常缺，仅加强）
    tu_p = _num(prev, "turnover_amt") if prev else None
    hl_p = _num(prev, "connect_hl") if prev else None

    # 1) 冰点：跌停遍地（有数据）+ 高度压缩；无跌停数据时用「涨停枯竭 + 高度极低」兜底
    if ld is not None and ld >= 80 and (hl is None or hl <= 4):
        reasons.append(f"跌停 {ld:.0f} 家（恐慌出清）")
        if hl is not None:
            reasons.append(f"最高板仅 {hl:.0f} 板（空间压缩）")
        if lu is not None:
            reasons.append(f"涨停仅 {lu:.0f} 家")
        return dict(CYCLES[0], reasons=reasons)
    if ld is None and lu is not None and lu < 30 and hl is not None and hl <= 3:
        reasons.append(f"涨停仅 {lu:.0f} 家 + 最高板 {hl:.0f} 板（无跌停数据，按枯竭判定冰点）")
        return dict(CYCLES[0], reasons=reasons)

    # 2) 退潮：高度断崖（核心），或 梯队极薄 + 封板差
    if hl is not None and hl_p is not None and hl_p - hl >= 2:
        reasons.append(f"最高板从 {hl_p:.0f} 板断崖至 {hl:.0f} 板")
        if ld is not None and ld >= 10:
            reasons.append(f"跌停 {ld:.0f} 家（亏钱效应回升）")
        return dict(CYCLES[5], reasons=reasons)
    if ld is not None and ld >= 30 and (zb is None or zb >= 30):
        reasons.append(f"跌停 {ld:.0f} 家且炸板率 {zb:.0f}%（亏钱效应 + 封板差）")
        return dict(CYCLES[5], reasons=reasons)
    if c2 is not None and c2 <= 2 and zb is not None and zb >= 45:
        reasons.append(f"连板梯队仅 {c2:.0f} 家 + 炸板率 {zb:.0f}%（接力资金缺席 + 封板崩）")
        return dict(CYCLES[5], reasons=reasons)

    # 3) 高潮分化：炸板率飙升 + 涨停仍多（核心：只看炸板率与涨停）
    if zb is not None and zb >= 40 and (lu is None or lu >= 50):
        reasons.append(f"炸板率 {zb:.0f}%（≥40%，分歧剧烈）")
        if lu is not None:
            reasons.append(f"涨停仍有 {lu:.0f} 家（高度未崩但质量下降）")
        return dict(CYCLES[4], reasons=reasons)

    # 4) 主升高潮：高度打开 + 封板稳 + 有溢价（三项核心齐全即可，不再强制要求 pr > 0）
    if (hl is not None and hl >= 6 and zb is not None and zb < 20):
        reasons.append(f"最高板 {hl:.0f} 板（空间打开）")
        reasons.append(f"炸板率 {zb:.0f}%（<20%，封板稳）")
        if pr is not None:
            reasons.append(f"昨板溢价 {pr:+.2f}%")
        return dict(CYCLES[3], reasons=reasons)

    # 5) 修复确认：封板质量改善 + 高度晋级/达标 + 溢价不差
    hl_up = (hl is not None and hl_p is not None and hl >= hl_p)
    if (zb is not None and zb < 25
            and (hl_up or (hl is not None and hl >= 4))
            and (pr is None or pr > -1.0)):
        reasons.append(f"炸板率 {zb:.0f}%（<25%，封板质量改善）")
        if hl_up:
            reasons.append(f"最高板 {hl_p:.0f}→{hl:.0f} 板（高度晋级/维持）")
        elif hl is not None:
            reasons.append(f"最高板 {hl:.0f} 板")
        if ld is not None:
            reasons.append(f"跌停 {ld:.0f} 家")
        if pr is not None:
            reasons.append(f"昨板溢价 {pr:+.2f}%")
        if tu is not None and tu_p is not None and tu >= tu_p:
            reasons.append(f"成交额 {tu:,.0f} 亿（较昨日 {tu_p:,.0f} 亿放量）")
        return dict(CYCLES[2], reasons=reasons)

    # 6) 兜底：修复试探（附「为什么没进更乐观档位」的解释）
    if zb is not None and zb >= 25:
        reasons.append(f"炸板率 {zb:.0f}%（≥25%，封板质量未达标，故未判修复确认）")
    if hl is not None:
        reasons.append(f"最高板 {hl:.0f} 板")
    if hl is not None and hl_p is not None and hl < hl_p:
        reasons.append(f"最高板 {hl_p:.0f}→{hl:.0f} 板（高度回落）")
    if pr is not None:
        reasons.append(f"昨板溢价 {pr:+.2f}%")
    if c2 is not None and c2 < 8:
        reasons.append(f"连板梯队仅 {c2:.0f} 家（梯队偏薄）")
    if ld is not None:
        reasons.append(f"跌停 {ld:.0f} 家")
    if tu is not None and tu_p is not None and tu < tu_p:
        reasons.append(f"成交额 {tu:,.0f} 亿（较昨日 {tu_p:,.0f} 亿缩量，存量博弈）")
    if not reasons:
        reasons.append("关键指标不足，按修复试探处理")
    return dict(CYCLES[1], reasons=reasons)


# ═══════════════════════════════════════════════════════════════
#  四、次日情绪评分（0-100，越高代表次日环境越友好）
# ═══════════════════════════════════════════════════════════════
def _score_dim(key, value, vmax):
    """把单指标归一到 0~1（考虑 dir 方向）。缺失返回 None。"""
    cfg = _FC_BY_KEY.get(key)
    if not cfg or value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    d = cfg["dir"]
    if d == 0:
        return None
    try:
        r = v / float(vmax)
    except Exception:
        return None
    r = max(0.0, min(1.0, r))
    # dir=-1 的反向指标：值适中最好（太低=一致健康但可能过热，太高=抛压释放后修复）
    # 这里采用「U 型」处理：极低(<15%炸板)与极高(≥50%)都偏正面，25-40% 最差
    if d == -1 and key in ("zt_fail_ratio",):
        if v >= 50:
            return 0.85          # 抛压释放 → 次日 V反
        if v < 15:
            return 0.80          # 封板稳 → 延续
        if v < 25:
            return 0.55
        if v < 40:
            return 0.30
        return 0.45              # 40-50% 开始有修复预期
    return r if d > 0 else (1.0 - r)


def score_next_day(today: dict, prev: dict = None) -> dict:
    """次日情绪评分（0-100）。返回 {total, dims:[{name, score, max, value, tip}]}。

    维度与权重（参考实战复盘「次日情绪评分系统」改造为牧羊人可得指标）：
      昨日涨停溢价 25 / 连板高度 20 / 梯队厚度 20 / 封板质量(炸板率) 20 / 亏钱效应(跌停) 15
    """
    dims = []

    # 1) 赚钱效应：昨日涨停表现（-5%~+5% 映射到 0~25）
    pr = _num(today, "zt_prev_ret")
    if pr is not None:
        r = max(0.0, min(1.0, (pr + 5.0) / 10.0))
        dims.append(dict(name="赚钱效应(昨板溢价)", score=round(r * 25, 1), max=25,
                         value=f"{pr:+.2f}%",
                         tip="昨板有溢价才有人接力" if pr > 0 else "打板亏钱，接力意愿弱"))

    # 2) 空间高度：最高板（0~10 板映射到 0~20）
    hl = _num(today, "connect_hl")
    if hl is not None:
        r = max(0.0, min(1.0, hl / 10.0))
        dims.append(dict(name="空间高度(最高板)", score=round(r * 20, 1), max=20,
                         value=f"{hl:.0f}板",
                         tip="高度决定情绪天花板" if hl >= 5 else "空间未打开"))

    # 3) 梯队厚度：连板家数（0~30 家映射到 0~20）
    c2 = _num(today, "connect_2b")
    if c2 is not None:
        r = max(0.0, min(1.0, c2 / 30.0))
        dims.append(dict(name="梯队厚度(连板家数)", score=round(r * 20, 1), max=20,
                         value=f"{c2:.0f}家",
                         tip="梯队厚=赚钱效应扩散" if c2 >= 15 else "梯队偏薄，独苗难持续"))

    # 4) 封板质量：炸板率（U 型）
    zb = _num(today, "zt_fail_ratio")
    if zb is not None:
        r = _score_dim("zt_fail_ratio", zb, 100)
        if r is not None:
            dims.append(dict(name="封板质量(炸板率)", score=round(r * 20, 1), max=20,
                             value=f"{zb:.1f}%",
                             tip="低=封板稳，≥50%=抛压释放后易V反"))

    # 5) 亏钱效应：跌停家数（0~80 家反向映射 0~15）
    ld = _num(today, "limit_down")
    if ld is not None:
        r = max(0.0, min(1.0, 1.0 - ld / 80.0))
        dims.append(dict(name="亏钱效应(跌停家数)", score=round(r * 15, 1), max=15,
                         value=f"{ld:.0f}家",
                         tip="跌停少=恐慌出清" if ld < 15 else "亏钱效应仍明显"))

    got = sum(d["max"] for d in dims)
    total = sum(d["score"] for d in dims)
    # 归一化到满分 100（缺失维度不计入分母）
    total = round(total / got * 100, 1) if got else 50.0
    return dict(total=total, dims=dims, covered=got)


# ═══════════════════════════════════════════════════════════════
#  五、次日走向主入口
# ═══════════════════════════════════════════════════════════════
def _scenario_emoji(bias):
    return {"偏多": "🔴", "偏空": "🟢", "中性": "⚪"}.get(bias, "⚪")


def forecast_next_day(today: dict, prev: dict = None) -> dict:
    """综合判定次日走向（纯函数，可离线单测）。

    Args:
        today: 今日牧羊人指标 dict（键同 shepherd.THRESHOLDS）
        prev:  昨日同结构 dict（用于高度变化 / 量能环比；可为 None）

    Returns:
        dict:
          cycle     情绪周期定位（含 name/emoji/color/desc/bias/reasons）
          score     次日情绪评分（0-100）
          bias      '偏多' / '中性' / '偏空'
          confidence  置信度 0-100
          scenario  情景推演列表 [{name, prob, desc, trigger}]
          signals   命中的联动规则
          drivers   各预测指标的档位解读 [{key,name,value,band,desc,color,why}]
          summary   一句话总结
    """
    if not today:
        return dict(cycle=None, score=50.0, bias="中性", confidence=0,
                    scenario=[], signals=[], drivers=[], summary="暂无数据")

    # 派生指标（涨停/跌停比等）在内层统一补齐，外部调用方无需关心
    today = with_derived(today)
    prev = with_derived(prev) if prev else None

    cyc = locate_cycle(today, prev)
    sc = score_next_day(today, prev)
    hits = eval_linkages(today, prev)

    # ── 方向投票：周期基准 + 联动规则加减 ──
    cycle_bias = {
        "ice": 1,       # 冰点 → 次日修复（偏多）
        "probe": 0,     # 修复试探 → 中性
        "confirm": 1,   # 修复确认 → 偏多
        "main": 1,      # 主升 → 偏多
        "diverge": -1,  # 高潮分化 → 偏空
        "retreat": -1,  # 退潮 → 偏空
    }.get(cyc["id"], 0)

    vote = cycle_bias * 2  # 周期权重 2
    for h in hits:
        if "看多次日" in h["tags"]:
            vote += 1
        elif "看空次日" in h["tags"]:
            vote -= 1
        elif "风险" in h["tags"]:
            vote -= 1
        elif "谨慎" in h["tags"]:
            vote -= 0  # 谨慎不改方向，只降置信度

    # 评分也参与：>60 偏多，<40 偏空
    if sc["total"] >= 60:
        vote += 1
    elif sc["total"] <= 40:
        vote -= 1

    if vote >= 2:
        bias = "偏多"
    elif vote <= -2:
        bias = "偏空"
    else:
        bias = "中性"

    # ── 置信度：命中规则数 + 数据覆盖度 + 方向一致性 ──
    conf = 40.0
    conf += min(len(hits) * 12, 30)                    # 每命中一条联动 +12（上限30）
    conf += min(sc["covered"] / 100.0 * 20, 20)        # 数据覆盖度最多 +20
    conf += 10 if abs(vote) >= 3 else 0                # 方向明确 +10
    if len(hits) == 0:
        conf -= 10                                     # 无联动命中，降置信
    confidence = int(max(10.0, min(95.0, conf)))

    # ── 三情景推演（概率按方向分配）──
    if bias == "偏多":
        main_p, mid_p, low_p = 50, 32, 18
    elif bias == "偏空":
        main_p, mid_p, low_p = 18, 32, 50
    else:
        main_p, mid_p, low_p = 27, 46, 27

    zh = _num(today, "connect_hl")
    scenario = [
        dict(name="修复升级 / 情绪转强", prob=main_p, color="#ee2a2a",
             desc="赚钱效应延续，最高板晋级打开空间，指数与情绪共振向上。",
             trigger=f"观察：最高板{'从 ' + str(int(zh)) + ' 板晋级' if zh else '晋级'} + 量能放大 + 炸板率回落"),
        dict(name="震荡分化 / 高位分歧", prob=mid_p, color="#f59e0b",
             desc="指数与情绪背离，题材轮动加速，赚钱效应收缩到少数高辨识度标的。",
             trigger="观察：最高板反复炸板或维持不变，量能无法有效放大"),
        dict(name="退潮 / 二次探底", prob=low_p, color="#00d486",
             desc="高度断崖、跌停回升、晋级率低迷，修复半途而废。",
             trigger="观察：最高板断板 + 跌停家数回升 + 缩量"),
    ]

    # ── 各预测指标档位解读 ──
    drivers = []
    for c in FORECAST_INDICATORS:
        v = _num(today, c["key"])
        if v is None:
            continue
        b = _band_of(c["key"], v)
        drivers.append(dict(
            key=c["key"], name=c["name"], value=v, unit=c["unit"],
            dir=c["dir"], weight=c["weight"], why=c["why"],
            band=(b[0] if b else "—"), desc=(b[1] if b else ""), color=(b[2] if b else "#888"),
        ))
    drivers.sort(key=lambda x: -x["weight"])

    summary = (
        f"{cyc['emoji']} 情绪周期：{cyc['name']} ｜ 次日情绪评分 {sc['total']:.0f}/100 ｜ "
        f"方向判断：{bias}（置信度 {confidence}%）"
    )

    return dict(
        cycle=cyc, score=sc["total"], score_dims=sc["dims"],
        bias=bias, confidence=confidence, scenario=scenario,
        signals=hits, drivers=drivers, summary=summary,
    )
