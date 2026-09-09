# 第 6 章 系统总体设计

本章将前 5 章的方法论落到工程实现，给出 StockSignal 平台的总体架构与"决策闭环 + 刻度校准"关键模块的设计。设计目标是：**可解释、可复现、可演进**——所有仓位逻辑收敛为单一实现，所有数值由可复现脚本实算，所有校准建议人工确认落地而非自动改写规则。

## 6.1 总体架构

StockSignal 采用前后端分离的多页结构（见图 6-1）：

- **前端**：基于 Streamlit 的多页应用（入口 `app.py` + `pages/` 下 41 个页面），覆盖行情看板、事件追踪、板块详情、个股与多股对比、策略回测、持仓管理、连板梯队、决策面板等。前端只负责展示与交互，不直接持有业务规则。
- **后端**：Flask 微服务（端口 5050，SQLAlchemy + PyJWT 鉴权），提供行情、事件、账户等 REST 接口；与前端通过 JSON 规范响应（`utils/response.ok/fail`）通信。
- **数据层**：SQLite 落地于 `data/` 目录，承载每日决策快照、历史归档、广度历史、回测打分等；取数优先本地缓存，多源 fallback，断网优雅降级。

```
                  ┌───────────────────────────┐
   浏览器 ───────► │  Streamlit 多页前端(41页)  │
                  └─────────────┬─────────────┘
                                │ 调用 / 读取
                  ┌─────────────▼─────────────┐
                  │   Flask 后端 (5050, JWT)    │
                  └─────────────┬─────────────┘
                                │ 取数 / 落盘
                  ┌─────────────▼─────────────┐
                  │   SQLite 数据层 (data/)      │
                  │  daily_snapshot / snapshots  │
                  │  shepherd_history / 回测打分  │
                  └───────────────────────────┘

        决策闭环独立模块（纯 Python，不依赖 streamlit/flask）：
   shepherd_reconstruct ─► shepherd_forecast.locate_cycle
        │                        │
        ▼                        ▼
   data/shepherd_history   cycle_name(六阶段)
                                │
                                ▼
                  decision.derive_position ──► {pct, band, color, reasons}
                                │
                                ▼
          decision_track.record_prediction / score_predictions
                                │
                                ▼
                  calibration.suggestions / verdict / as_patch
        图 6-1 系统总体架构与决策闭环数据流
```

## 6.2 数据层设计

### 6.2.1 广度历史重建（`shepherd_reconstruct`）

广度历史的重建路径为：`build_shepherd_history → reconstruct_breadth → _enrich_zt_from_cache → save_history`。

- **数据源**：新浪日线（`stock_zh_a_daily`）主源 + 牧羊人涨停池（`get_zt_ladder`）反推连板高度、炸板率、晋级率；akshare 在离线环境下走确定性静态样本兜底。
- **指标族**：`red_ratio`（红盘率，天然 0–100 温度）、`limit_up` / `limit_down`（涨停/跌停家数）、`connect_hl`（最高板）、`zt_fail_ratio`（炸板率）、`median_chg`（中位数涨跌幅）、连板梯队晋级率等。
- **写入护栏**：`save_history` 默认**拒绝覆盖**已有历史表，必须显式 `--force` 且先自动备份双份，防止重跑把已验证的真实历史冲掉（见第 3 章）。

重建结果 `data/shepherd_history.csv` 含 **4094 个真实交易日**（2009–2026），是本文全部实证与回测的唯一只读数据源，并在 Git 中以双备份 + `.gitignore` 隔离，保证"任何人 clone 后重跑脚本得到逐字节一致结果"。

### 6.2.2 每日决策快照

`decision` 模块将当日决策落盘为 `data/daily_snapshot.json`（首页 banner 直读）+ `data/snapshots/YYYY-MM-DD.json`（历史归档，复盘回测源）。快照与归档共用同一 `derive_position` 实现，杜绝"三套互相矛盾的仓位建议"。

## 6.3 决策闭环模块设计

### 6.3.1 情绪周期定位器（`shepherd_forecast.locate_cycle`）

`locate_cycle(today: dict, prev: dict = None) -> dict` 是一个**纯函数**六阶段分类器，把当日广度指标映射为六阶段之一：

> 冰点 → 修复试探 → 修复确认 → 主升高潮 → 高潮分化 → 退潮

其设计要点（与第 2、3 章理论一致）：

1. **规则化、可解释**：每个阶段的判定由"跌停家数 + 涨停家数 + 最高板 + 炸板率 + 梯队晋级率"的显式阈值组合构成，输出附带 `reasons` 与 `bias`（偏多/偏空/中性），而非黑箱概率。
2. **单源缺失优雅降级**：某项指标缺失时该规则不参与判定，不抛异常、不静默兜底误判——缺失指标只作加强证据，绝不触发"无数据就给中性"的伪判定（第 3 章现代段不坍缩的诚实披露即源于此）。
3. **可离线单测**：纯函数不依赖网络与 UI，回测脚本与单元测试均可直接调用。

### 6.3.2 仓位推导（`decision.derive_position`）

`derive_position(temp, bias, cycle_name, overall_promo, event_adj, freshness_status)` 是闭环的**单一真理源**，透明规则如下：

```
base  = 市场温度(0-100) 作为基准仓位%
+ 方向调节：偏多 +8 / 偏空 -8
+ 周期调节（CYCLE_ADJ）：
      主升高潮 +5 / 修复确认 +3 / 修复试探 0
      高潮分化 -5 / 退潮 -10 / 冰点 +5（超卖左侧试探）
+ 梯队晋级率调节（≥60% +5 / 40-60% 0 / 20-40% -3 / <20% -6）
+ 事件驱动调节（真实 P1 EV 事件因子多头池广度；取不到则为 None，不臆造催化）
最终 clamp 到 [5, 95]%，并按档位（激进/偏多/中性/偏空/防御）绑定红涨绿跌配色
```

- `CYCLE_ADJ` 是六阶段 → 仓位调节的单一字典，初始为经验常数，第 5 章用回测反推其合理性。
- `freshness_status`（ok/warn/stale）：陈旧数据必须让位——`stale` 时封顶 40%、`warn` 时封顶 60%，杜绝"半个月前的情绪仍算出激进仓位只是附句'仅供参考'"的伪诚实。
- 所有调节逐条留痕进 `reasons`，前端直接展示，使建议可解释。

### 6.3.3 预测记录与回测打分（`decision_track`）

为使闭环"可演进"，系统每日落盘一条预测并在次日回填真实涨跌：

- `record_prediction(date, temp, cycle_name, bias, pct)`：挂钩在每日快照落盘后，记录系统当日给出的周期与仓位建议。
- `score_predictions()`：联网拉取次日上证 000001 涨跌判方向命中；断网时优雅降级（纯本地、不报错）。
- `by_cycle()` / `by_group()`：把样本按六阶段 / 四大战术分组（进攻/分化/修复/防守）聚合，输出方向命中率与"平均建议仓位 vs 次日平均实际涨跌"，供校准模块消费。
- `verdict()`：综合各分组样本量与调节量，给出"是否达到可采纳阈值"的结论（语义为**至少一个战术分组达标**，而非全局样本阈值，避免无单组达标却误报"可校准"）。

## 6.4 刻度校准模块设计（`calibration`）

校准模块把"经验常数"推向"数据驱动演进"，其核心是三条铁律（详见第 5 章）：

1. **只出建议、不自动改规则**：`as_patch()` 仅返回 `{周期: 建议调节量}` 字典，**绝不写** `decision.py` 的 `CYCLE_ADJ`。原因：自动拟合历史 = 过拟合，把噪音当信号；落地须人工确认且样本 ≥ `strong_samples`。
2. **调节量有界**：`sug_delta = clamp(round(GAIN × avg_realized), ±MAX_DELTA)`，`GAIN=2.0`、`MAX_DELTA=5`，单次最多微调 5 点，剩余交由下一轮。
3. **小样本不表态**：`actionable` 要求 `n_call ≥ strong_samples(20)` 且 `|sug_delta| ≥ NOISE_DELTA(2)`；1 条样本算出的"100% 命中"是噪音，页面必须显式展示"样本不足"。

校准建议在 54_今日决策面板与历史页面均有"⚖️ 仓位刻度校准"版块呈现，由人工对照 `as_patch()` 建议决定是否落地，全程留痕。

## 6.5 设计小结

本章把"决策闭环 + 刻度校准"落为四个可独立测试、可独立演进的纯 Python 模块（数据重建 / 周期定位 / 仓位推导 / 校准），并以 SQLite 时序快照串起"预测—回填—校准"的演进闭环。模块间通过显式字典与纯函数解耦，既满足论文方法论的可解释要求，也满足生产系统的可维护要求——这正是第 4、5 章能在真实 4092 天数据上复现的根本工程前提。
