import { z } from 'zod'

/**
 * 只读端点响应 schema（W1 后端 /api/v2/read/*）。
 *
 * 字段以本仓真实数据文件（`data/daily_snapshot.json` / `snapshots/*.json` /
 * `p1_signals/signal_*.json` / `paper_*.json` 等）2026-11-06 真扫得到的结构为准，
 * 不臆造字段名。深度嵌套且前端不逐一渲染的容器用 `z.record` / `z.unknown()` 兜底，
 * 但凡渲染到的字段都显式声明类型。缺失文件 → 信封返回 status=error，前端判空渲染「无数据」。
 *
 * 红线（PLAN.md §4.3 / §5）：解析失败即抛错，禁止 `?? 0` / 默认值兜底。
 */

// ───────── 决策快照（daily_snapshot / snapshots/<date>）─────────
export const PositionSchema = z.object({
  pct: z.number(),
  band: z.string(),
  color: z.string(),
  reasons: z.array(z.string()).default([]),
})
export type Position = z.infer<typeof PositionSchema>

export const EventFactorSchema = z.object({
  available: z.boolean().optional(),
  long_count: z.number().optional(),
  adj: z.number().optional(),
  as_of: z.string().optional(),
})
export type EventFactor = z.infer<typeof EventFactorSchema>

export const DataFreshnessSourceSchema = z.object({
  as_of: z.string().optional(),
  lag_days: z.number().optional(),
  status: z.string().optional(),
})
export type DataFreshnessSource = z.infer<typeof DataFreshnessSourceSchema>

export const DataFreshnessSchema = z.object({
  status: z.string().optional(),
  max_lag_days: z.number().optional(),
  sources: z.record(z.string(), DataFreshnessSourceSchema).optional(),
})
export type DataFreshness = z.infer<typeof DataFreshnessSchema>

export const ScenarioSchema = z.object({
  name: z.string().optional(),
  prob: z.number().optional(),
  color: z.string().optional(),
  desc: z.string().optional(),
  trigger: z.string().optional(),
})
export type Scenario = z.infer<typeof ScenarioSchema>

export const LadderSchema = z.object({
  distribution: z.array(z.array(z.unknown())).optional(),
  max_boards: z.number().optional(),
  total_connect: z.number().optional(),
})
export type Ladder = z.infer<typeof LadderSchema>

/** 指标字典：键为指标名，值为数值（含 null，缺失即 null 不补零）。 */
export const IndicatorsSchema = z.record(z.string(), z.unknown()).optional()
export type Indicators = z.infer<typeof IndicatorsSchema>

export const DailySnapshotSchema = z.object({
  date: z.string(),
  as_of: z.string().optional(),
  data_age_days: z.number().optional(),
  generated_at: z.string().optional(),
  temperature: z.number().optional(),
  cycle: z.string().optional(),
  score: z.number().optional(),
  bias: z.string().optional(),
  confidence: z.number().optional(),
  promo_overall: z.number().optional(),
  ladder: LadderSchema.optional(),
  position: PositionSchema.optional(),
  event_factor: EventFactorSchema.optional(),
  data_freshness: DataFreshnessSchema.optional(),
  indicators: IndicatorsSchema,
  signals: z.array(z.unknown()).optional(),
  scenario: z.array(ScenarioSchema).optional(),
})
export type DailySnapshot = z.infer<typeof DailySnapshotSchema>

// ───────── P1 量化信号（p1_signals/signal_*.json）─────────
export const P1TopItemSchema = z.object({
  symbol: z.string(),
  pred: z.number().optional(),
  rank: z.number().optional(),
})
export type P1TopItem = z.infer<typeof P1TopItemSchema>

export const P1SignalSchema = z.object({
  generated_at: z.string().optional(),
  latest_date: z.string().optional(),
  top_long: z.array(P1TopItemSchema).optional(),
  top_short: z.array(P1TopItemSchema).optional(),
  daily: z.unknown().optional(),
  model: z.unknown().optional(),
  horizon: z.unknown().optional(),
})
export type P1Signal = z.infer<typeof P1SignalSchema>

// ───────── 每日荐股（daily_recommendation.json，可能 unavailable）─────────
export const DailyRecommendationSchema = z
  .object({
    status: z.string().optional(),
    reason: z.string().optional(),
    generated_at: z.string().optional(),
    disclaimer: z.string().optional(),
  })
  .catchall(z.unknown())
export type DailyRecommendation = z.infer<typeof DailyRecommendationSchema>

// ───────── 虚拟用户模拟（reports/virtual_users_sim.json）─────────
export const VirtualUsersSimSchema = z
  .object({
    meta: z.record(z.string(), z.unknown()).optional(),
    aggregate: z.unknown().optional(),
    profiles: z.unknown().optional(),
  })
  .catchall(z.unknown())
export type VirtualUsersSim = z.infer<typeof VirtualUsersSimSchema>

// ───────── 模拟交易账本（paper_<user>.json）─────────
export const PaperPositionSchema = z.object({
  name: z.string().optional(),
  qty: z.number().optional(),
  avg_cost: z.number().optional(),
})
export type PaperPosition = z.infer<typeof PaperPositionSchema>

export const PaperTradeRowSchema = z.object({
  time: z.string().optional(),
  code: z.string().optional(),
  name: z.string().optional(),
  side: z.string().optional(),
  price: z.number().optional(),
  qty: z.number().optional(),
  amount: z.number().optional(),
})
export type PaperTradeRow = z.infer<typeof PaperTradeRowSchema>

export const PaperTradeSchema = z.object({
  init_cash: z.number().optional(),
  cash: z.number().optional(),
  positions: z.record(z.string(), PaperPositionSchema).optional(),
  trades: z.array(PaperTradeRowSchema).optional(),
  equity: z.array(z.array(z.unknown())).optional(),
})
export type PaperTrade = z.infer<typeof PaperTradeSchema>

// ───────── 复盘笔记（review_notes_<date>.md 包装）─────────
export const ReviewNotesSchema = z.object({
  date: z.string(),
  content: z.string(),
})
export type ReviewNotes = z.infer<typeof ReviewNotesSchema>

// ───────── 网页作品集（webapps/*/meta.json）─────────
export const WebAppSchema = z.object({
  dir: z.string(),
  title: z.string(),
  desc: z.string().optional(),
  entry: z.string(),
  version: z.string().optional(),
  added: z.string().optional(),
})
export type WebApp = z.infer<typeof WebAppSchema>

// ───────── 归档日期清单 ─────────
export const SnapshotDateListSchema = z.array(z.string())
export type SnapshotDateList = z.infer<typeof SnapshotDateListSchema>

// ───────── 广度时序（breadth-timeseries 聚合 snapshots）─────────
// 字段以真实 data/snapshots/*.json 的 indicators + 顶层 temperature 为准。
// 数值可能为 null（快照缺失该字段），严禁 `?? 0` 兜底。
export const BreadthPointSchema = z
  .object({
    date: z.string(),
    temperature: z.number().nullable().optional(),
    up_count: z.number().nullable().optional(),
    down_count: z.number().nullable().optional(),
    limit_up: z.number().nullable().optional(),
    limit_down: z.number().nullable().optional(),
    red_ratio: z.number().nullable().optional(),
    median_chg: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type BreadthPoint = z.infer<typeof BreadthPointSchema>

export const BreadthSeriesSchema = z.array(BreadthPointSchema)
export type BreadthSeries = z.infer<typeof BreadthSeriesSchema>

// ───────── 连板梯队明细（ladder-detail / shepherd_ladder_history）─────────
// 结构 {date, distribution{连板数:家数}, max_boards, total_connect, updated_at, suspect?}
export const LadderDaySchema = z
  .object({
    date: z.string(),
    distribution: z.record(z.string(), z.number()).optional(),
    max_boards: z.number().nullable().optional(),
    total_connect: z.number().nullable().optional(),
    updated_at: z.string().optional(),
    suspect: z.boolean().optional(),
  })
  .catchall(z.unknown())
export type LadderDay = z.infer<typeof LadderDaySchema>

export const LadderHistorySchema = z.array(LadderDaySchema)
export type LadderHistory = z.infer<typeof LadderHistorySchema>

// ───────── 长周期广度历史（breadth-history / shepherd_history）─────────
// 字段以真实 data/shepherd_history.json 的逐日行准（2007→2026，个别字段为 NaN）。
// 数值可空（NaN 后端已清洗为 null），严禁 `?? 0` 兜底。
export const BreadthHistoryPointSchema = z
  .object({
    date: z.string(),
    up_count: z.number().nullable().optional(),
    down_count: z.number().nullable().optional(),
    flat_count: z.number().nullable().optional(),
    limit_up: z.number().nullable().optional(),
    limit_down: z.number().nullable().optional(),
    red_ratio: z.number().nullable().optional(),
    connect_hl: z.number().nullable().optional(),
    zt_fail_ratio: z.number().nullable().optional(),
    zt_prev_ret: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type BreadthHistoryPoint = z.infer<typeof BreadthHistoryPointSchema>

export const BreadthHistorySeriesSchema = z.array(BreadthHistoryPointSchema)
export type BreadthHistorySeries = z.infer<typeof BreadthHistorySeriesSchema>

// ───────── W3 后续簇：事件因子池（event-pool / data/event_pool_brief.json）─────────
// 2026-11-07 真扫：顶层 DICT {date, model, source, note, count, pool}；
// pool 元素 {rank, symbol, score, raw_rank, raw_pred, signal, source}。
// ⚠️ note 原文是「统计意义上的超额收益概率排序，非买卖指令」，页面必须原样带出，
// 不得把本页包装成荐股/买卖信号（诚实红线）。
export const EventPoolItemSchema = z
  .object({
    rank: z.number(),
    symbol: z.string(),
    score: z.number().nullable().optional(),
    raw_rank: z.number().nullable().optional(),
    raw_pred: z.number().nullable().optional(),
    signal: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type EventPoolItem = z.infer<typeof EventPoolItemSchema>

export const EventPoolSchema = z
  .object({
    date: z.string(),
    model: z.string().optional(),
    source: z.string().optional(),
    note: z.string().optional(),
    count: z.number().nullable().optional(),
    pool: z.array(EventPoolItemSchema).optional(),
  })
  .catchall(z.unknown())
export type EventPool = z.infer<typeof EventPoolSchema>

// ───────── 预测校准日志（prediction-log / data/prediction_log.json）─────────
// 真扫：LIST 32 行；并集 keys = date/temp/cycle/bias/pct/event_adj/event_available/realized/hit。
// hit 为 boolean|null、realized 为 number|null：尚未兑现的预测**没有**结果，禁止补 0 或补 false。
export const PredictionLogRowSchema = z
  .object({
    date: z.string(),
    temp: z.number().nullable().optional(),
    cycle: z.string().nullable().optional(),
    bias: z.string().nullable().optional(),
    pct: z.number().nullable().optional(),
    event_adj: z.number().nullable().optional(),
    event_available: z.boolean().nullable().optional(),
    realized: z.number().nullable().optional(),
    hit: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type PredictionLogRow = z.infer<typeof PredictionLogRowSchema>

export const PredictionLogSchema = z.array(PredictionLogRowSchema)
export type PredictionLog = z.infer<typeof PredictionLogSchema>

// ───────── P1 同步状态（p1-sync-status / data/p1_sync_status.json）─────────
// 真扫：health{status,message,latest,age_days,models,rows[]}、counts{copy,unchanged,target_newer,skip}。
// ⚠️ 真实文件含 target_dir 绝对路径（本机盘符），后端 /p1-sync-status 已递归剔除该 key。
// schema 刻意**不声明** target_dir；catchall 收下额外键但页面绝不渲染任何路径类信息。
export const P1SyncHealthRowSchema = z
  .object({
    file: z.string().optional(),
    model_key: z.string().optional(),
    latest_date: z.string().optional(),
    age_days: z.number().nullable().optional(),
    structural_ok: z.boolean().optional(),
    freshness_ok: z.boolean().optional(),
    errors: z.array(z.string()).optional(),
  })
  .catchall(z.unknown())

export const P1SyncHealthSchema = z
  .object({
    status: z.string().optional(),
    message: z.string().optional(),
    latest: z.string().optional(),
    age_days: z.number().nullable().optional(),
    models: z.array(z.string()).optional(),
    rows: z.array(P1SyncHealthRowSchema).optional(),
  })
  .catchall(z.unknown())

export const P1SyncStatusSchema = z
  .object({
    run_at: z.string().optional(),
    mode: z.string().optional(),
    interval_minutes: z.number().nullable().optional(),
    dry_run: z.boolean().optional(),
    ok: z.boolean().optional(),
    written: z.array(z.string()).optional(),
    skipped: z.array(z.string()).optional(),
    errors: z.array(z.string()).optional(),
    all_invalid: z.boolean().optional(),
    counts: z.record(z.string(), z.number()).optional(),
    health: P1SyncHealthSchema.optional(),
    prev_run_at: z.string().optional(),
  })
  .catchall(z.unknown())
export type P1SyncStatus = z.infer<typeof P1SyncStatusSchema>

// ───────── 回测运行记录（backtest-runs / data/backtest_runs.json）─────────
// 真扫：DICT {runs: 4}，元素 {run_id, created_at, status, params{...}, summary{...}}。
// ⚠️ 诚实红线：total_return_pct / sharpe_ratio 可以为负，不得取绝对值、
// 不得把负向结果包装成「策略领先」；缺失字段一律 undefined，不补零。
export const BacktestRunSummarySchema = z
  .object({
    ticker: z.string().optional(),
    strategy: z.string().optional(),
    initial_capital: z.number().nullable().optional(),
    final_value: z.number().nullable().optional(),
    total_return_pct: z.number().nullable().optional(),
    max_drawdown_pct: z.number().nullable().optional(),
    sharpe_ratio: z.number().nullable().optional(),
    win_rate_pct: z.number().nullable().optional(),
    profit_factor: z.number().nullable().optional(),
    avg_trade_return_pct: z.number().nullable().optional(),
    trade_count: z.number().nullable().optional(),
    start_date: z.string().optional(),
    end_date: z.string().optional(),
  })
  .catchall(z.unknown())

export const BacktestRunSchema = z
  .object({
    run_id: z.string(),
    created_at: z.string().optional(),
    status: z.string().optional(),
    params: z.record(z.string(), z.unknown()).optional(),
    summary: BacktestRunSummarySchema.optional(),
  })
  .catchall(z.unknown())
export type BacktestRun = z.infer<typeof BacktestRunSchema>

export const BacktestRunsSchema = z
  .object({ runs: z.array(BacktestRunSchema) })
  .catchall(z.unknown())
export type BacktestRuns = z.infer<typeof BacktestRunsSchema>

// ───────── 数据刷新状态（data-refresh-state / data/data_refresh_state.json）─────────
// 真扫：DICT {attempts_today, last_run_date, last_result, finished_at, last_csv_date, detail}。
export const DataRefreshStateSchema = z
  .object({
    attempts_today: z.number().nullable().optional(),
    last_run_date: z.string().optional(),
    last_result: z.string().optional(),
    finished_at: z.string().optional(),
    last_csv_date: z.string().optional(),
    detail: z.string().optional(),
  })
  .catchall(z.unknown())
export type DataRefreshState = z.infer<typeof DataRefreshStateSchema>

// ───────── 因子分析（factor-analysis / modules.factor_analysis 纯函数）─────────
// 字段名严格对齐 backend/api/read_routes.py:1497 factor_analysis() 的 data 字典：
// codes/days/factor/forward/n_layers 为请求回显；ic_series[{date,ic}] 为逐期 IC；
// ic_summary 为 IC 汇总（n/ic_mean/ic_std/ir/positive_ratio/t_stat，数值可 NaN→null）；
// layered_cum[{date,"0"..层}] 为分层累计收益（列名为层号字符串，含 date 键）；
// long_short_cum[{date,ic}] 为多空累计净值（(1+ls).cumprod()-1）；
// errs 为取数错误清单 [[code,reason]]；date 为 IC 序列末根权威数据日（null 表示无）。
// ⚠️ 诚实红线：NaN/Inf 后端已清洗为 null，严禁 `?? 0` 兜底；有效标的<3 时后端返回
// status=error（前端判空渲染「数据不足」），本 schema 只覆盖 200+status=ok 的成功态。
export const FactorIcPointSchema = z.object({
  date: z.string(),
  ic: z.number().nullable().optional(),
})
export type FactorIcPoint = z.infer<typeof FactorIcPointSchema>

export const FactorAnalysisSchema = z
  .object({
    codes: z.array(z.string()),
    days: z.number(),
    factor: z.string(),
    forward: z.number(),
    n_layers: z.number(),
    ic_series: z.array(FactorIcPointSchema),
    ic_summary: z
      .object({
        n: z.number().nullable().optional(),
        ic_mean: z.number().nullable().optional(),
        ic_std: z.number().nullable().optional(),
        ir: z.number().nullable().optional(),
        positive_ratio: z.number().nullable().optional(),
        t_stat: z.number().nullable().optional(),
      })
      .catchall(z.unknown()),
    layered_cum: z.array(z.record(z.string(), z.unknown())),
    long_short_cum: z.array(FactorIcPointSchema),
    errs: z.array(z.array(z.unknown())),
    date: z.string().nullable().optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type FactorAnalysis = z.infer<typeof FactorAnalysisSchema>

// ───────── 策略回测（backtest）─────────
export const BacktestTradeSchema = z.object({
  entry_date: z.string().nullable().optional(),
  exit_date: z.string().nullable().optional(),
  entry_price: z.number().nullable().optional(),
  exit_price: z.number().nullable().optional(),
  profit_pct: z.number().nullable().optional(),
  exit_reason: z.string().nullable().optional(),
  bars_held: z.number().nullable().optional(),
})
export type BacktestTrade = z.infer<typeof BacktestTradeSchema>

export const BacktestEquityPointSchema = z.object({
  date: z.string(),
  cumulative_return: z.number().nullable().optional(),
  total_asset: z.number().nullable().optional(),
  drawdown: z.number().nullable().optional(),
})
export type BacktestEquityPoint = z.infer<typeof BacktestEquityPointSchema>

export const BacktestSchema = z
  .object({
    ticker: z.string(),
    strategy: z.string(),
    start: z.string(),
    end: z.string(),
    initial_capital: z.number().nullable().optional(),
    final_value: z.number().nullable().optional(),
    total_return_pct: z.number().nullable().optional(),
    annualized_return_pct: z.number().nullable().optional(),
    max_drawdown_pct: z.number().nullable().optional(),
    sharpe_ratio: z.number().nullable().optional(),
    win_rate_pct: z.number().nullable().optional(),
    profit_factor: z.number().nullable().optional(),
    avg_trade_return_pct: z.number().nullable().optional(),
    trade_count: z.number().nullable().optional(),
    exposure_pct: z.number().nullable().optional(),
    start_date: z.string().nullable().optional(),
    end_date: z.string().nullable().optional(),
    equity_curve: z.array(BacktestEquityPointSchema),
    trades: z.array(BacktestTradeSchema),
    date: z.string().nullable().optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type Backtest = z.infer<typeof BacktestSchema>

// ───────── 市场全景 / 状态机（market-panorama：regime_report + shepherd 广度）─────────
export const RegimeAnalogSchema = z.object({
  date: z.string(),
  distance: z.number().nullable().optional(),
  metrics: z
    .object({
      red_ratio: z.number().nullable().optional(),
      limit_up: z.number().nullable().optional(),
      limit_down: z.number().nullable().optional(),
    })
    .catchall(z.unknown()),
  state: z.string().optional(),
  forward: z.record(z.string(), z.unknown()).optional(),
})
export type RegimeAnalog = z.infer<typeof RegimeAnalogSchema>

export const RegimeReportSchema = z
  .object({
    available: z.boolean().optional(),
    reason: z.string().optional(),
    data: z
      .object({
        rows: z.number().optional(),
        start: z.string().optional(),
        end: z.string().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    latest: z
      .object({
        date: z.string().optional(),
        state: z.string().optional(),
        confidence: z.number().nullable().optional(),
        metrics: z.record(z.string(), z.unknown()).optional(),
      })
      .catchall(z.unknown())
      .optional(),
    state_distribution: z.record(z.string(), z.number()).optional(),
    transition_matrix: z.record(z.string(), z.record(z.string(), z.number())).optional(),
    analogs: z.array(RegimeAnalogSchema).optional(),
  })
  .catchall(z.unknown())
export type RegimeReport = z.infer<typeof RegimeReportSchema>

export const MarketPanoramaSchema = z
  .object({
    k: z.number().optional(),
    regime: RegimeReportSchema,
    shepherd_latest: z.record(z.string(), z.unknown()).optional(),
    shepherd_series: z.array(z.record(z.string(), z.unknown())).optional(),
    shepherd_unavailable: z.array(z.array(z.string())).optional(),
    date: z.string().nullable().optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type MarketPanorama = z.infer<typeof MarketPanoramaSchema>

// 持仓中心（45）：本地模拟持仓 + FIFO 盈亏 + 收益归因 + 尽力而为净值曲线。
export const PortfolioPositionSchema = z.object({
  ticker: z.string(),
  name: z.string().optional(),
  buy_date: z.string().optional(),
  buy_price: z.number().nullable().optional(),
  shares: z.number().nullable().optional(),
  remaining_shares: z.number().nullable().optional(),
  cost: z.number().nullable().optional(),
  current_price: z.number().nullable().optional(),
  market_value: z.number().nullable().optional(),
  realized_pnl: z.number().nullable().optional(),
  pnl: z.number().nullable().optional(),
  pnl_pct: z.number().nullable().optional(),
})
export type PortfolioPosition = z.infer<typeof PortfolioPositionSchema>

export const PortfolioAttributionSchema = z.object({
  ticker: z.string(),
  name: z.string().optional(),
  pnl: z.number().nullable().optional(),
  pnl_pct: z.number().nullable().optional(),
  contribution: z.number().nullable().optional(),
})
export type PortfolioAttribution = z.infer<typeof PortfolioAttributionSchema>

export const PortfolioWeightSchema = z.object({
  ticker: z.string(),
  name: z.string().optional(),
  weight_pct: z.number().nullable().optional(),
})
export type PortfolioWeight = z.infer<typeof PortfolioWeightSchema>

export const PortfolioCurvePointSchema = z.object({
  date: z.string(),
  portfolio: z.number().nullable().optional(),
  benchmark: z.number().nullable().optional(),
})
export type PortfolioCurvePoint = z.infer<typeof PortfolioCurvePointSchema>

export const PortfolioSchema = z
  .object({
    summary: z
      .object({
        total_cost: z.number().nullable().optional(),
        total_market_value: z.number().nullable().optional(),
        total_pnl: z.number().nullable().optional(),
        total_pnl_pct: z.number().nullable().optional(),
        position_count: z.number().nullable().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    positions: z.array(PortfolioPositionSchema).optional(),
    attribution: z.array(PortfolioAttributionSchema).optional(),
    weights: z.array(PortfolioWeightSchema).optional(),
    curve: z.array(PortfolioCurvePointSchema).optional(),
    curve_available: z.boolean().optional(),
    date: z.string().nullable().optional(),
    note: z.string().optional(),
    unavailable: z.array(z.unknown()).optional(),
  })
  .catchall(z.unknown())
export type Portfolio = z.infer<typeof PortfolioSchema>

// ───────── 资金流向（fund-flow / 35 页 V2 化）─────────
// 四块各自独立 available；金额为「亿元」（后端已折算），百分比为原始百分数。
// 缺值后端已清洗为 null，前端显示「—」，绝不补 0。
export const FundFlowNorthboundBoardSchema = z.object({
  board: z.string().nullable().optional(),
  direction: z.string().nullable().optional(),
  trade_net: z.number().nullable().optional(),
  net_inflow: z.number().nullable().optional(),
  up_count: z.number().nullable().optional(),
  down_count: z.number().nullable().optional(),
  index_chg_pct: z.number().nullable().optional(),
})
export type FundFlowNorthboundBoard = z.infer<typeof FundFlowNorthboundBoardSchema>

export const FundFlowNorthboundSchema = z.object({
  available: z.boolean(),
  trade_date: z.string().nullable().optional(),
  total_inflow: z.number().nullable().optional(),
  sh_inflow: z.number().nullable().optional(),
  sz_inflow: z.number().nullable().optional(),
  northbound_net_available: z.boolean().optional(),
  boards: z.array(FundFlowNorthboundBoardSchema).optional(),
  last_net_buy: z.number().nullable().optional(),
  last_net_buy_date: z.string().nullable().optional(),
  cumulative: z.number().nullable().optional(),
  cumulative_date: z.string().nullable().optional(),
})
export type FundFlowNorthbound = z.infer<typeof FundFlowNorthboundSchema>

export const FundFlowIndustryRowSchema = z.object({
  industry: z.string().nullable().optional(),
  chg_pct: z.number().nullable().optional(),
  inflow: z.number().nullable().optional(),
  outflow: z.number().nullable().optional(),
  net: z.number().nullable().optional(),
  leader: z.string().nullable().optional(),
  leader_chg_pct: z.number().nullable().optional(),
})
export type FundFlowIndustryRow = z.infer<typeof FundFlowIndustryRowSchema>

export const FundFlowMarketRowSchema = z.object({
  date: z.string().nullable().optional(),
  index_chg_pct: z.number().nullable().optional(),
  main_net: z.number().nullable().optional(),
  main_net_pct: z.number().nullable().optional(),
  super_net: z.number().nullable().optional(),
  big_net: z.number().nullable().optional(),
  mid_net: z.number().nullable().optional(),
})
export type FundFlowMarketRow = z.infer<typeof FundFlowMarketRowSchema>

export const FundFlowMarginRowSchema = z.object({
  date: z.string().nullable().optional(),
  sh_rzmr_yi: z.number().nullable().optional(),
  sz_rzmr_yi: z.number().nullable().optional(),
  total_rzmr_yi: z.number().nullable().optional(),
  sh_rzye_yi: z.number().nullable().optional(),
  sz_rzye_yi: z.number().nullable().optional(),
  total_rzye_yi: z.number().nullable().optional(),
  sh000001: z.number().nullable().optional(),
  sz399001: z.number().nullable().optional(),
  sz399006: z.number().nullable().optional(),
})
export type FundFlowMarginRow = z.infer<typeof FundFlowMarginRowSchema>

export const FundFlowMarginLatestSchema = z.object({
  date: z.string().nullable().optional(),
  total_rzmr_yi: z.number().nullable().optional(),
  total_rzye_yi: z.number().nullable().optional(),
  sh_rzmr_yi: z.number().nullable().optional(),
  sz_rzmr_yi: z.number().nullable().optional(),
  rzmr_change_yi: z.number().nullable().optional(),
  rzye_change_yi: z.number().nullable().optional(),
  rzmr_change_pct: z.number().nullable().optional(),
  rzye_change_pct: z.number().nullable().optional(),
})
export type FundFlowMarginLatest = z.infer<typeof FundFlowMarginLatestSchema>

export const FundFlowSchema = z
  .object({
    northbound: FundFlowNorthboundSchema,
    industry: z.object({
      available: z.boolean(),
      rows: z.array(FundFlowIndustryRowSchema),
    }),
    market: z.object({
      available: z.boolean(),
      rows: z.array(FundFlowMarketRowSchema),
    }),
    margin: z.object({
      available: z.boolean(),
      rows: z.array(FundFlowMarginRowSchema),
      latest: FundFlowMarginLatestSchema.nullable().optional(),
    }),
    note: z.string().optional(),
    unavailable: z.array(z.unknown()).optional(),
  })
  .catchall(z.unknown())
export type FundFlow = z.infer<typeof FundFlowSchema>

// ───────── 实盘交易只读概览（trading-account / 43 页 V2 化）─────────
// V2 此处只读：聚合本地模拟账本（后端读 data/paper_<user>.json）。不暴露任何写接口；
// 金额单位为「元」（本地账本原始值），前端按需以 ¥ 千分位展示；缺值后端已清洗为 null → 「—」。
export const TradingAccountPositionSchema = z.object({
  code: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  qty: z.number().nullable().optional(),
  avg_cost: z.number().nullable().optional(),
  cost_basis: z.number().nullable().optional(),
})
export type TradingAccountPosition = z.infer<typeof TradingAccountPositionSchema>

export const TradingAccountOrderSchema = z.object({
  time: z.string().nullable().optional(),
  code: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  side: z.string().nullable().optional(), // 买 / 卖
  price: z.number().nullable().optional(),
  qty: z.number().nullable().optional(),
  amount: z.number().nullable().optional(),
})
export type TradingAccountOrder = z.infer<typeof TradingAccountOrderSchema>

export const TradingAccountSchema = z
  .object({
    account: z
      .object({
        broker_type: z.string().nullable().optional(),
        mode: z.string().nullable().optional(),
        init_cash: z.number().nullable().optional(),
        cash: z.number().nullable().optional(),
        position_cost: z.number().nullable().optional(),
        total_assets: z.number().nullable().optional(),
        available: z.boolean().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    positions: z.array(TradingAccountPositionSchema).optional(),
    orders: z.array(TradingAccountOrderSchema).optional(),
    note: z.string().optional(),
    unavailable: z.array(z.unknown()).optional(),
  })
  .catchall(z.unknown())
export type TradingAccount = z.infer<typeof TradingAccountSchema>

// ───────── 宏观数据（macro-data / 84 页 V2 化）─────────
// 复用 modules.macro_data.fetch_all + global_regime_score。各指标**独立降级**：
// 取不到的指标后端返回 null（而非 0 或兜底串），前端显示「—」。
// 数值字段均为 nullable（后端已把 NaN/Inf 清洗为 null）；regime 评分取不到为 null。
export const MacroIndicatorSchema = z
  .object({
    key: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    unit: z.string().nullable().optional(),
    freq: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    region: z.string().nullable().optional(),
    desc: z.string().nullable().optional(),
    value: z.number().nullable().optional(),
    prev: z.number().nullable().optional(),
    change: z.number().nullable().optional(),
    date: z.string().nullable().optional(),
    stale: z.boolean().nullable().optional(),
    from_cache: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type MacroIndicator = z.infer<typeof MacroIndicatorSchema>

export const MacroRegimeSchema = z
  .object({
    score: z.number().nullable().optional(),
    sub: z.record(z.string(), z.number()).nullable().optional(),
    parts: z.record(z.string(), z.number().nullable()).nullable().optional(),
    yield_curve: z.number().nullable().optional(),
    cn_us_spread: z.number().nullable().optional(),
    dates: z.record(z.string(), z.string().nullable()).nullable().optional(),
  })
  .catchall(z.unknown())
export type MacroRegime = z.infer<typeof MacroRegimeSchema>

export const MacroDataSchema = z
  .object({
    indicators: z.record(z.string(), MacroIndicatorSchema.nullable()).optional(),
    regime: MacroRegimeSchema.nullable().optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type MacroData = z.infer<typeof MacroDataSchema>

// ───────── 龙虎榜（85 页 V2 化）─────────
export const DragonTigerRowSchema = z
  .object({
    code: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    net_yi: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type DragonTigerRow = z.infer<typeof DragonTigerRowSchema>

export const DragonTigerSchema = z
  .object({
    date: z.string().nullable().optional(),
    count: z.number().nullable().optional(),
    net_col: z.string().nullable().optional(),
    net_sum_yi: z.number().nullable().optional(),
    buy_top: z.array(DragonTigerRowSchema).nullable().optional(),
    sell_top: z.array(DragonTigerRowSchema).nullable().optional(),
    detail: z.array(z.record(z.string(), z.unknown())).nullable().optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type DragonTiger = z.infer<typeof DragonTigerSchema>

// ───────── 题材热点（75 页 V2 化）─────────
export const ThemeConceptSchema = z
  .object({
    name: z.string().nullable().optional(),
    chg: z.number().nullable().optional(),
    turnover_p: z.number().nullable().optional(),
    lifecycle: z.string().nullable().optional(),
    mv: z.number().nullable().optional(),
    turnover: z.number().nullable().optional(),
    up: z.number().nullable().optional(),
    down: z.number().nullable().optional(),
    leader: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type ThemeConcept = z.infer<typeof ThemeConceptSchema>

export const ThemeSummarySchema = z
  .object({
    count: z.number().nullable().optional(),
    n_up: z.number().nullable().optional(),
    n_down: z.number().nullable().optional(),
    top_name: z.string().nullable().optional(),
    top_chg: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type ThemeSummary = z.infer<typeof ThemeSummarySchema>

export const ThemeSchema = z
  .object({
    concepts: z.array(ThemeConceptSchema).optional(),
    summary: ThemeSummarySchema.nullable().optional(),
    lifecycle_counts: z.record(z.string(), z.number()).optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type Theme = z.infer<typeof ThemeSchema>

// 事件传导图谱（75 ④，按需触发）
export const ThemeTransmissionEntrySchema = z
  .object({
    name: z.string().optional(),
    code: z.string().optional(),
    score: z.number().optional(),
    direction: z.string().optional(),
    dir_color: z.string().optional(),
    concepts: z.string().optional(),
    evidence: z.string().optional(),
    direct: z.boolean().optional(),
  })
  .catchall(z.unknown())
export type ThemeTransmissionEntry = z.infer<typeof ThemeTransmissionEntrySchema>

export const ThemeTransmissionSchema = z
  .object({
    status: z.string().optional(),
    basis: z.string().nullable().optional(),
    disclaimer: z.string().nullable().optional(),
    entries: z.array(ThemeTransmissionEntrySchema).optional(),
    concepts_hit: z.array(z.unknown()).optional(),
    members_unavailable: z.array(z.unknown()).optional(),
    n_titles: z.number().nullable().optional(),
    n_concepts: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type ThemeTransmission = z.infer<typeof ThemeTransmissionSchema>

// ───────── 实时强势榜（76 页 V2 化）─────────
export const StrongItemSchema = z
  .object({
    rank: z.number().nullable().optional(),
    code: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    price: z.number().nullable().optional(),
    chg: z.number().nullable().optional(),
    amount: z.number().nullable().optional(),
    turnover: z.number().nullable().optional(),
    vol_ratio: z.number().nullable().optional(),
    score: z.number().nullable().optional(),
    s_chg: z.number().nullable().optional(),
    s_vr: z.number().nullable().optional(),
    s_to: z.number().nullable().optional(),
    s_amt: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type StrongItem = z.infer<typeof StrongItemSchema>

export const StrongSchema = z
  .object({
    items: z.array(StrongItemSchema).optional(),
    src_label: z.string().nullable().optional(),
    kicked: z.array(z.unknown()).optional(),
    unavailable: z.array(z.unknown()).optional(),
    date: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type Strong = z.infer<typeof StrongSchema>

// ───────── 板块轮动（sector-rotation / 12 页 V2 化）─────────
// 复用 modules.fundflow.get_industry_fund_flow：行业级 涨跌幅 + 资金净额(亿) + 领涨股。
// 字段以真实接口返回为准；净额缺失（仅涨跌幅降级源）为 null，前端显示「—」，绝不补 0。
export const SectorItemSchema = z
  .object({
    name: z.string().nullable().optional(),
    chg_pct: z.number().nullable().optional(),
    net: z.number().nullable().optional(),
    leader: z.string().nullable().optional(),
    leader_chg_pct: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type SectorItem = z.infer<typeof SectorItemSchema>

export const SectorRotationSchema = z
  .object({
    items: z.array(SectorItemSchema).optional(),
    src_label: z.string().nullable().optional(),
    unavailable: z.array(z.unknown()).optional(),
    date: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type SectorRotation = z.infer<typeof SectorRotationSchema>

// ───────── 智能盯盘（watch / 14 页 V2 化）─────────
// 只读聚合：自选股 + 逐只主力资金流 + 板块资金异动 + 资金流阈值预警。
// 金额单位为亿元（后端已 _ff_yi 折算），缺失/未披露为 null，前端显示「—」，绝不补 0。
// 实时现价/涨跌幅未在此端点聚合（Flask 只读上下文不可用 Streamlit 实时行情单例），前端如实标注。
export const WatchFundSchema = z
  .object({
    source: z.string().nullable().optional(),
    main_net: z.number().nullable().optional(),
    main_net_pct: z.number().nullable().optional(),
    big_net: z.number().nullable().optional(),
    super_net: z.number().nullable().optional(),
    latest_date: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type WatchFund = z.infer<typeof WatchFundSchema>

export const WatchlistItemSchema = z
  .object({
    code: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    note: z.string().nullable().optional(),
    fund: WatchFundSchema.optional(),
  })
  .catchall(z.unknown())
export type WatchlistItem = z.infer<typeof WatchlistItemSchema>

export const WatchAlertSchema = z
  .object({
    code: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    level: z.string().nullable().optional(),
    reason: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type WatchAlert = z.infer<typeof WatchAlertSchema>

export const WatchSummarySchema = z
  .object({
    watch_count: z.number().nullable().optional(),
    with_fund: z.number().nullable().optional(),
    strong_count: z.number().nullable().optional(),
    weak_count: z.number().nullable().optional(),
    sector_available: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type WatchSummary = z.infer<typeof WatchSummarySchema>

export const WatchSchema = z
  .object({
    watchlist: z.array(WatchlistItemSchema).optional(),
    sector_items: z.array(SectorItemSchema).optional(),
    alerts: z.array(WatchAlertSchema).optional(),
    summary: WatchSummarySchema.optional(),
    src_labels: z
      .object({
        watchlist_fund: z.string().nullable().optional(),
        sector: z.string().nullable().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type Watch = z.infer<typeof WatchSchema>

// ───────── 行情看板（quote-board / 10 页 V2 化）─────────
// 只读聚合：主要指数报价（akshare 日线，离线为确定性静态样例）+ 行业板块涨跌榜
// （行业资金流，net 单位亿元）+ 市场状态（服务器北京时间真实计算，非伪造数据日）。
// 指数取不到 → current/change/change_pct=null（诚实降级，前端显示「—」，绝不补 0）；
// 板块取不到 → sectors=[] + unavailable 标注；市场状态是真实「当前时段」计算，不是数据日。
export const QuoteBoardIndexSchema = z
  .object({
    code: z.string().nullable().optional(),
    name: z.string().nullable().optional(),
    current: z.number().nullable().optional(),
    prev_close: z.number().nullable().optional(),
    change: z.number().nullable().optional(),
    change_pct: z.number().nullable().optional(),
    date: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type QuoteBoardIndex = z.infer<typeof QuoteBoardIndexSchema>

export const QuoteBoardMarketStatusSchema = z
  .object({
    is_open: z.boolean().nullable().optional(),
    text: z.string().nullable().optional(),
    refresh_ms: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type QuoteBoardMarketStatus = z.infer<typeof QuoteBoardMarketStatusSchema>

export const QuoteBoardSummarySchema = z
  .object({
    index_count: z.number().nullable().optional(),
    index_available: z.number().nullable().optional(),
    sector_count: z.number().nullable().optional(),
    sector_available: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type QuoteBoardSummary = z.infer<typeof QuoteBoardSummarySchema>

export const QuoteBoardSchema = z
  .object({
    indices: z.array(QuoteBoardIndexSchema).optional(),
    sectors: z.array(SectorItemSchema).optional(),
    market_status: QuoteBoardMarketStatusSchema.optional(),
    summary: QuoteBoardSummarySchema.optional(),
    src_labels: z
      .object({
        indices: z.string().nullable().optional(),
        sectors: z.string().nullable().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type QuoteBoard = z.infer<typeof QuoteBoardSchema>

