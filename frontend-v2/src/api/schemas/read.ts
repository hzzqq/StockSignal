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
  policy: z.unknown().optional(),
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

/**
 * 登录页公开摘要（GET /api/v2/read/public-overview，无鉴权）—— 2026-11-17 修复
 * 登录页「资金温度/今日市场/AI 信号」全空：旧实现调 daily-snapshot（需鉴权），
 * 未登录永远拿不到。本端点只透传展示必需的脱敏字段；数据缺失字段为 null，
 * 页面诚实显示「—」，不编造。Zod 宽松 nullable/optional 是设计内（缺失=降级路径）。
 */
export const PublicOverviewSchema = z.object({
  date: z.string().nullish(),
  as_of: z.string().nullish(),
  cycle: z.string().nullish(),
  temperature: z.number().nullish(),
  indicators: z
    .object({
      up_count: z.number().nullish(),
      down_count: z.number().nullish(),
      limit_up: z.number().nullish(),
      limit_down: z.number().nullish(),
      red_ratio: z.number().nullish(),
      median_chg: z.number().nullish(),
    })
    .optional(),
  event_factor: z
    .object({
      long_count: z.number().nullish(),
      adj: z.number().nullish(),
      as_of: z.string().nullish(),
    })
    .optional(),
})
export type PublicOverview = z.infer<typeof PublicOverviewSchema>

/**
 * 登录页上证指数当日分时（GET /api/v2/read/public-index-intraday，无鉴权，脱敏只读）。
 * 2026-11-21 老板需求：分时图。rows 只含 time/close 两个脱敏字段；prev_close 为
 * 上一交易日收盘 bar 的 close（真实历史数据）；取不到 -> date=null、rows=[]（诚实空态）。
 */
export const PublicIndexIntradaySchema = z.object({
  code: z.string(),
  name: z.string().nullish(),
  date: z.string().nullish(),
  prev_close: z.number().nullish(),
  rows: z.array(z.object({ time: z.string(), close: z.number() })),
})
export type PublicIndexIntraday = z.infer<typeof PublicIndexIntradaySchema>

/**
 * 登录页「今日推荐」公开摘要（GET /api/v2/read/public-picks，无鉴权，脱敏只读）。
 * stocks = P1 量化信号 top_long 前 5（名称水合未命中 -> null，显示「—」）；
 * sectors = 行业资金流净额前 3；都带 disclaimer，不构成投资建议。
 */
export const PublicPicksSchema = z.object({
  stocks: z.array(
    z.object({
      code: z.string(),
      name: z.string().nullable(),
      pred: z.number().nullable(),
    }),
  ),
  stocks_as_of: z.string().nullish(),
  sectors: z.array(
    z.object({
      industry: z.string(),
      chg_pct: z.number().nullish(),
      net: z.string().nullish(),
    }),
  ),
  disclaimer: z.string().nullish(),
})
export type PublicPicks = z.infer<typeof PublicPicksSchema>

// ───────── P1 量化信号（p1_signals/signal_*.json）─────────
export const P1TopItemSchema = z.object({
  symbol: z.string(),
  name: z.string().nullable().optional(),
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
    data_staleness: z
      .object({
        latest: z.string().nullable().optional(),
        lag_days: z.number().nullable().optional(),
        stale: z.boolean().optional(),
        freshness: z.enum(['ok', 'warn', 'stale', 'unknown']).optional(),
        note: z.string().optional(),
      })
      .optional(),
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
  // parity C：新写入的模拟成交带服务端 id；历史账本记录无 id，故为可选（不伪造）。
  id: z.number().int().optional(),
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

// ───────── 我的（user_dashboard.json 包装）─────────
export const UserDashboardSchema = z.object({
  default_widgets: z.array(z.string()),
  note: z.string().optional(),
  updated_at: z.string().optional(),
})
export type UserDashboard = z.infer<typeof UserDashboardSchema>

// ───────── 财报披露日历（akshare 披露日历；字段随数据源变化，rows 宽松记录）─────────
export const EarningsCalendarSchema = z.object({
  market: z.string(),
  period: z.string(),
  rows: z.array(z.record(z.string(), z.unknown())),
  date: z.string().nullable(),
  unavailable: z.boolean(),
  note: z.string(),
})
export type EarningsCalendar = z.infer<typeof EarningsCalendarSchema>

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
    // 后端对历史日返回 null（未判定），近期被标记日返回 true/false；与 max_boards/
    // total_connect 一致用 nullable 接受「未知」空态，绝不把 null 当 false 兜底。
    suspect: z.boolean().nullable().optional(),
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

// ───────── 事件因子回测（event-backtest / modules.event_backtest 离线 walk-forward）─────────
// 严格对齐 backend/api/read_routes.py event_backtest() 的 data 字典：
// available 恒有；n_event/n_base 整数；base_rate/event_rate/edge_pp/z 为数值或 null
// （小样本/退化序列时 z=null，缺失诚实空态，前端严禁 `?? 0` 兜底）；distribution 为分箱计数；
// example_dates 为触发示例；available=false 时可能仅含 reason（无 distribution）。
export const EventBacktestBinSchema = z.object({
  bucket: z.string(),
  event_count: z.number(),
  base_count: z.number(),
})
export type EventBacktestBin = z.infer<typeof EventBacktestBinSchema>

export const EventBacktestExampleSchema = z.object({
  date: z.string(),
  metric_value: z.number().nullable().optional(),
  forward_red_day_frac: z.number().nullable().optional(),
})
export type EventBacktestExample = z.infer<typeof EventBacktestExampleSchema>

export const EventBacktestSchema = z
  .object({
    available: z.boolean(),
    metric: z.string().optional(),
    tail: z.number().nullable().optional(),
    direction: z.string().optional(),
    horizon: z.number().nullable().optional(),
    n_event: z.number().nullable().optional(),
    n_base: z.number().nullable().optional(),
    base_rate: z.number().nullable().optional(),
    event_rate: z.number().nullable().optional(),
    edge_pp: z.number().nullable().optional(),
    z: z.number().nullable().optional(),
    distribution: z.array(EventBacktestBinSchema).optional(),
    example_dates: z.array(EventBacktestExampleSchema).optional(),
    method: z.string().optional(),
    honesty_notes: z.array(z.string()).optional(),
    reason: z.string().optional(),
  })
  .catchall(z.unknown())
export type EventBacktest = z.infer<typeof EventBacktestSchema>

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

// ───────── 仓位落地（position-allocation / 98 页 V2 化）─────────
// 复用 modules.position_allocator.build_allocation：市场仓位×评分源→个股目标权重（纯建议层）。
// 诚实红线：status=unavailable 时前端判空；meta 内 market/source 溯源；score 可空（缺失剔除）；
// 所有数值可空，严禁 ?? 0 兜底。
export const PositionAllocationMetaSchema = z
  .object({
    mode: z.string().nullable().optional(),
    degraded: z.boolean().nullable().optional(),
    cap_pct: z.number().nullable().optional(),
    target_pct: z.number().nullable().optional(),
    sum_pct: z.number().nullable().optional(),
    n_alloc: z.number().nullable().optional(),
    n_excluded: z.number().nullable().optional(),
    capped: z.array(z.string()).optional(),
    overflow_pct: z.number().nullable().optional(),
    market: z.record(z.string(), z.unknown()).nullable().optional(),
    source: z.record(z.string(), z.unknown()).nullable().optional(),
  })
  .catchall(z.unknown())
export type PositionAllocationMeta = z.infer<typeof PositionAllocationMetaSchema>

export const PositionAllocationItemSchema = z.object({
  code: z.string(),
  name: z.string().optional(),
  score: z.number().nullable().optional(),
  weight: z.number().nullable().optional(),
  pct: z.number().nullable().optional(),
})
export type PositionAllocationItem = z.infer<typeof PositionAllocationItemSchema>

export const PositionAllocationSchema = z
  .object({
    status: z.string().optional(),
    source: z.string().optional(),
    meta: PositionAllocationMetaSchema.nullable().optional(),
    allocations: z.array(PositionAllocationItemSchema).optional(),
    excluded: z
      .array(
        z.object({
          code: z.string(),
          name: z.string().optional(),
          reason: z.string().optional(),
        }),
      )
      .optional(),
    note: z.string().optional(),
    unavailable: z.array(z.unknown()).optional(),
  })
  .catchall(z.unknown())
export type PositionAllocation = z.infer<typeof PositionAllocationSchema>

// ───────── 自然语言选股 · 语义解析（nl-screen / 81 页解析层 V2 化）─────────
// 复用 modules.nl_screen.parse_query（纯函数、确定性、不触网）。
// ⚠️ 诚实红线：只返回结构化 QuerySpec，绝不返回候选标的；未识别的词进 unparsed，
//    解析不出的字段为 null（前端显示「—」），严禁补默认值假装听懂。
export const NlFilterSchema = z
  .object({
    field: z.string(),
    op: z.string(),
    value: z.unknown().optional(),
    unit: z.string().nullable().optional(),
    raw: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type NlFilter = z.infer<typeof NlFilterSchema>

export const NlSpecSchema = z
  .object({
    boards: z.array(z.string()).optional(),
    filters: z.array(NlFilterSchema).optional(),
    sort: z.string().nullable().optional(),
    sort_dir: z.string().nullable().optional(),
    limit: z.number().nullable().optional(),
    concepts: z.array(z.string()).optional(),
    exclude_boards: z.array(z.string()).optional(),
    exclude_concepts: z.array(z.string()).optional(),
    unparsed: z.array(z.string()).optional(),
    errors: z.array(z.string()).optional(),
  })
  .catchall(z.unknown())
export type NlSpec = z.infer<typeof NlSpecSchema>

export const NlScreenSchema = z
  .object({
    status: z.string().optional(),
    query: z.string().optional(),
    spec: NlSpecSchema.nullable().optional(),
    note: z.string().optional(),
    unavailable: z.array(z.unknown()).optional(),
  })
  .catchall(z.unknown())
export type NlScreen = z.infer<typeof NlScreenSchema>

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
    /** date 是否为明细里的真实数据日；false = 数据日不可得（date 为 null）。 */
    data_date_available: z.boolean().optional(),
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
    /** 同花顺 fallback 的概念资金净额（亿元）；东财源为 null。 */
    net_yi: z.number().nullable().optional(),
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
    source: z.string().nullable().optional(),
    note: z.string().nullable().optional(),
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

// ───────── 政策事件传导工作台（policy-documents / policy-transmission / sector-map）─────────
// 所有业务字段 nullable().optional()，不给默认值：缺失由页面显式显示「—」，绝不补 0 / now()。
export const PolicyDocumentSchema = z
  .object({
    policy_id: z.string().nullable().optional(),
    title: z.string().nullable().optional(),
    issuing_body: z.string().nullable().optional(),
    doc_number: z.string().nullable().optional(),
    publish_date: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    source_url: z.string().nullable().optional(),
    body_source: z.string().nullable().optional(),
    content_hash: z.string().nullable().optional(),
    crawled_at: z.string().nullable().optional(),
    body_excerpt: z.string().nullable().optional(),
    body_text: z.string().nullable().optional(),
    is_fresh: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type PolicyDocument = z.infer<typeof PolicyDocumentSchema>

export const PolicyDocumentsSchema = z
  .object({
    items: z.array(PolicyDocumentSchema).optional(),
    stats: z.record(z.string(), z.unknown()).nullable().optional(),
    unavailable: z.array(z.unknown()).optional(),
    note: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type PolicyDocuments = z.infer<typeof PolicyDocumentsSchema>

export const PolicyTransmissionSectorSchema = z
  .object({
    name: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    member_count: z.number().nullable().optional(),
    stock_codes_count: z.number().nullable().optional(),
    derived: z.boolean().nullable().optional(),
    matched_by: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type PolicyTransmissionSector = z.infer<typeof PolicyTransmissionSectorSchema>

export const PolicyTransmissionEntrySchema = z
  .object({
    name: z.string().nullable().optional(),
    code: z.string().nullable().optional(),
    score: z.number().nullable().optional(),
    direction: z.string().nullable().optional(),
    dir_color: z.string().nullable().optional(),
    concepts: z.string().nullable().optional(),
    evidence: z.string().nullable().optional(),
    direct: z.boolean().nullable().optional(),
  })
  .catchall(z.unknown())
export type PolicyTransmissionEntry = z.infer<typeof PolicyTransmissionEntrySchema>

export const PolicyTransmissionSchema = z
  .object({
    status: z.string().optional(),
    policy: PolicyDocumentSchema.nullable().optional(),
    sectors: z.array(PolicyTransmissionSectorSchema).optional(),
    entries: z.array(PolicyTransmissionEntrySchema).optional(),
    concepts_hit: z.array(z.unknown()).optional(),
    members_unavailable: z.array(z.unknown()).optional(),
    basis: z.string().nullable().optional(),
    disclaimer: z.string().nullable().optional(),
    derived_note: z.string().nullable().optional(),
    unavailable: z.array(z.unknown()).optional(),
    reason: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type PolicyTransmission = z.infer<typeof PolicyTransmissionSchema>

export const SectorMapItemSchema = z
  .object({
    board_name: z.string().nullable().optional(),
    board_code: z.string().nullable().optional(),
    board_type: z.string().nullable().optional(),
    keywords: z.string().nullable().optional(),
    stock_codes: z.string().nullable().optional(),
    member_count: z.number().nullable().optional(),
    source: z.string().nullable().optional(),
    fetch_status: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type SectorMapItem = z.infer<typeof SectorMapItemSchema>

export const SectorMapSchema = z
  .object({
    items: z.array(SectorMapItemSchema).optional(),
    stats: z.record(z.string(), z.unknown()).nullable().optional(),
    note: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type SectorMap = z.infer<typeof SectorMapSchema>

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


// ───────── 离线广度统计分析（65/67/68/69 页 v2 等价数据源）─────────
// 后端逐段独立降级：任一模块异常/数据不足只让该段 available=false + reason，
// 其余段照常返回。前端按段显「暂无」，绝不整包吞成空数据。
const NumOrNull = z.number().nullable()
const AnalyticsSectionBase = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
}).catchall(z.unknown())

/** 65 投机情绪相位时钟：当前相位 + 归一化时序 */
export const SentimentPhaseSchema = AnalyticsSectionBase.extend({
  date: z.string().nullable().optional(),
  phase: z.string().nullable().optional(),
  red_ratio: NumOrNull.optional(),
  red_ratio_pct: NumOrNull.optional(),
  limit_up: NumOrNull.optional(),
  limit_up_pct: NumOrNull.optional(),
  limit_down: NumOrNull.optional(),
})
export type SentimentPhase = z.infer<typeof SentimentPhaseSchema>

export const SentimentSeriesSchema = AnalyticsSectionBase.extend({
  dates: z.array(z.string()).optional(),
  labels: z.record(z.string(), z.string()).optional(),
  series: z.record(z.string(), z.array(NumOrNull)).optional(),
})
export type SentimentSeries = z.infer<typeof SentimentSeriesSchema>

/** 67 历史相似日：top-N 相似日 + 后继 5/10/20 日红盘占比分布 */
export const SimilarDayRowSchema = z.object({
  date: z.string(),
  dist: z.number().nullable().optional(),
  fwd: z.record(z.string(), NumOrNull).optional(),
}).catchall(z.unknown())
export const ForwardStatSchema = z.object({
  n: z.number().nullable().optional(),
  mean: NumOrNull.optional(),
  median: NumOrNull.optional(),
  p10: NumOrNull.optional(),
  p90: NumOrNull.optional(),
  up_ratio: NumOrNull.optional(),
}).catchall(z.unknown())
export const SimilarDaysSchema = AnalyticsSectionBase.extend({
  target_date: z.string().nullable().optional(),
  n_total: z.number().nullable().optional(),
  exclude_window: z.number().nullable().optional(),
  dims: z.array(z.string()).optional(),
  dropped: z.record(z.string(), z.unknown()).optional(),
  similar: z.array(SimilarDayRowSchema).optional(),
  forward_stats: z.record(z.string(), ForwardStatSchema).optional(),
})
export type SimilarDays = z.infer<typeof SimilarDaysSchema>

/** 68 情绪拐点扫描：z-score 极端后反转事件 */
export const InflectionEventSchema = z.object({
  dim: z.string(),
  label: z.string().nullable().optional(),
  date: z.string().nullable().optional(),
  type: z.string().nullable().optional(),
  extreme: NumOrNull.optional(),
  current: NumOrNull.optional(),
}).catchall(z.unknown())
export const InflectionScanSchema = AnalyticsSectionBase.extend({
  dims: z.array(z.string()).optional(),
  dropped: z.record(z.string(), z.unknown()).optional(),
  events: z.array(InflectionEventSchema).optional(),
})
export type InflectionScan = z.infer<typeof InflectionScanSchema>

/** 69 温度持续期：五档持续期 + 冰点回归中性磨底时长 */
export const DurationStatSchema = z.object({
  n: z.number().nullable().optional(),
  mean: NumOrNull.optional(),
  median: NumOrNull.optional(),
}).catchall(z.unknown())
export const RegimeDurationSchema = AnalyticsSectionBase.extend({
  band_labels: z.array(z.string()).optional(),
  durations: z.record(z.string(), DurationStatSchema).optional(),
  recovery: DurationStatSchema.nullable().optional(),
  total_runs: z.number().nullable().optional(),
})
export type RegimeDuration = z.infer<typeof RegimeDurationSchema>

export const BreadthAnalyticsSchema = z.object({
  data_as_of: z.string().nullable(),
  window: z.number(),
  reliable_dims: z.array(z.string()),
  reliable_labels: z.record(z.string(), z.string()),
  offline_missing: z.record(z.string(), z.string()),
  note: z.string(),
  sections: z.object({
    phase: z.object({
      current: SentimentPhaseSchema,
      series: SentimentSeriesSchema,
    }),
    similar: SimilarDaysSchema,
    inflection: InflectionScanSchema,
    duration: RegimeDurationSchema,
  }),
})
export type BreadthAnalytics = z.infer<typeof BreadthAnalyticsSchema>

/** 68 拐点扫描器单维度 z-score 轨迹（GET /breadth-zseries?dim=&window=）。
 * 真端点按 window 截末段并显式 truncated；dates/z/raw 等长，markers 下标已重映射。 */
export const ZSeriesSchema = z.object({
  dim: z.string(),
  label: z.string(),
  data_as_of: z.string().nullable(),
  window: z.number(),
  available: z.boolean(),
  reason: z.string().nullable(),
  dates: z.array(z.string()),
  z: z.array(NumOrNull),
  raw: z.array(NumOrNull),
  markers: z.array(z.number()),
  truncated: z.boolean(),
  note: z.string(),
})
export type ZSeries = z.infer<typeof ZSeriesSchema>

// ───────── 62 动量×广度 共振矩阵（GET /momentum-breadth，离线）─────────
export const MomentumCellSchema = z.object({
  available: z.boolean(),
  date: z.string().nullable().optional(),
  rr_band: NumOrNull.optional(),
  mom_band: NumOrNull.optional(),
  rr_label: z.string().nullable().optional(),
  mom_label: z.string().nullable().optional(),
  red_ratio: NumOrNull.optional(),
  zt_prev_ret: NumOrNull.optional(),
})
export type MomentumCell = z.infer<typeof MomentumCellSchema>

export const MomentumStatsSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  co_hot: NumOrNull.optional(),
  co_cold: NumOrNull.optional(),
  dominant_cell: z.array(z.unknown()).nullable().optional(),
  n_days: z.number().nullable().optional(),
})
export type MomentumStats = z.infer<typeof MomentumStatsSchema>

export const MomentumTrajectorySchema = z.object({
  available: z.boolean(),
  dates: z.array(z.string()),
  rr_band: z.array(z.number()),
  mom_band: z.array(z.number()),
})
export type MomentumTrajectory = z.infer<typeof MomentumTrajectorySchema>

export const MomentumBreadthSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  rr_labels: z.array(z.string()),
  mom_labels: z.array(z.string()),
  matrix: z.array(z.array(z.number())),
  totals_row: z.array(z.number()),
  totals_col: z.array(z.number()),
  n_days: z.number(),
  current: MomentumCellSchema,
  stats: MomentumStatsSchema,
  trajectory: MomentumTrajectorySchema,
  note: z.string(),
})
export type MomentumBreadth = z.infer<typeof MomentumBreadthSchema>

// ───────── 70 涨停复盘 × 龙头识别（GET /limit-up-review?date=，实时）─────────
export const LeaderRowSchema = z.object({
  name: z.string(),
  code: z.string(),
  industry: z.string(),
  boards: z.number(),
  score: NumOrNull.optional(),
  s_height: NumOrNull.optional(),
  s_seal: NumOrNull.optional(),
  s_ind: NumOrNull.optional(),
  s_amt: NumOrNull.optional(),
  ind_n: z.number().nullable().optional(),
  seal: NumOrNull.optional(),
  amount: NumOrNull.optional(),
  /** 该行不可得的字段名（缺列/缺格）；后端绝不用 0 冒充缺失。 */
  unavailable_fields: z.array(z.string()).optional(),
})
export type LeaderRow = z.infer<typeof LeaderRowSchema>

export const LimitUpPoolSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  date: z.string(),
  count: z.number(),
  first_boards: z.number(),
  connect_boards: z.number(),
  max_boards: z.number(),
  broken_count: z.number(),
  bands: z.record(z.string(), z.number()),
  rows: z.array(z.object({
    code: z.string(),
    name: z.string(),
    industry: z.string(),
    boards: z.number(),
    seal: NumOrNull.optional(),
    amount: NumOrNull.optional(),
    first_seal_band: z.string(),
    broken: z.number(),
    /** 该行不可得的字段名（缺列/缺格）；后端绝不用 0 冒充缺失。 */
    unavailable_fields: z.array(z.string()).optional(),
  })),
  leaderboard: z.array(LeaderRowSchema),
  themes: z.array(z.object({ industry: z.string(), count: z.number() })),
  broken_list: z.array(z.object({
    name: z.string(), code: z.string(), boards: z.number(), broken: z.number(),
  })),
  /** 整池不可得的字段名（对应列在源数据中缺失）。 */
  unavailable_fields: z.array(z.string()).optional(),
})
export type LimitUpPool = z.infer<typeof LimitUpPoolSchema>

export const LimitUpLadderSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  distribution: z.array(z.tuple([z.number(), z.number()])),
  max_boards: z.number(),
  total_connect: z.number(),
  gaps: z.array(z.number()),
})
export type LimitUpLadder = z.infer<typeof LimitUpLadderSchema>

export const LimitUpContextSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  fail_ratio: NumOrNull.optional(),
  limit_up_cnt: NumOrNull.optional(),
  cycle: z.string().nullable().optional(),
  temperature: NumOrNull.optional(),
  state: z.string().nullable().optional(),
  confidence: NumOrNull.optional(),
})
export type LimitUpContext = z.infer<typeof LimitUpContextSchema>

export const LimitUpReviewSchema = z.object({
  available: z.boolean(),
  date: z.string(),
  note: z.string(),
  pool: LimitUpPoolSchema,
  ladder: LimitUpLadderSchema,
  context: LimitUpContextSchema,
})
export type LimitUpReview = z.infer<typeof LimitUpReviewSchema>

// ───────── 50 市场情绪·广度与情绪温度计（GET /market-sentiment?days=，实时）─────────
export const SentimentIndicatorSchema = z.object({
  key: z.string(),
  name: z.string(),
  unit: z.string(),
  value: NumOrNull.optional(),
  spark: z.array(NumOrNull),
  heat: NumOrNull.optional(),
  available: z.boolean(),
})
export type SentimentIndicator = z.infer<typeof SentimentIndicatorSchema>

export const SentimentLevelSchema = z.object({
  label: z.string(),
  emoji: z.string(),
  color: z.string(),
})
export type SentimentLevel = z.infer<typeof SentimentLevelSchema>

export const MarketSentimentSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().optional(),
  data_as_of: z.string().nullable(),
  temperature: NumOrNull.optional(),
  level: SentimentLevelSchema.nullable(),
  dims: z.record(z.string(), z.array(SentimentIndicatorSchema)),
  unavailable: z.array(z.object({
    dim: z.string(), key: z.string(), reason: z.string(),
  })),
  note: z.string(),
})
export type MarketSentiment = z.infer<typeof MarketSentimentSchema>


// ───────── 59 市场温度计四块（GET /market-temperature?hist_days=60|250|2000）─────────
// 牧羊人指标热度贡献 / 极端区信号（sentiment_edge）/ 历史情境类比 / 基准窗口切换，
// 后端聚合端点一次带回。数值字段全部 nullable：缺失显「—」，绝不补 0。
export const TempContributionSchema = z
  .object({
    key: z.string(),
    name: z.string(),
    unit: z.string(),
    /** 方向：1=越大越热 / -1=越小越热 / 0=双向；缺失 nullable，不猜。 */
    dir: z.number().nullable().optional(),
    value: z.number().nullable().optional(),
    hot: z.number().nullable().optional(),
    warm: z.number().nullable().optional(),
    heat: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type TempContribution = z.infer<typeof TempContributionSchema>

export const TempExtremeHitSchema = z
  .object({
    key: z.string(),
    name: z.string(),
    value: z.number().nullable().optional(),
    threshold: z.number().nullable().optional(),
    prob: z.number().nullable().optional(),
    n: z.number().nullable().optional(),
    z: z.number().nullable().optional(),
    why: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type TempExtremeHit = z.infer<typeof TempExtremeHitSchema>

/** 类比日的后市统计（d5/d10/d20 同形）；三字段均可空，尚无后市数据时不补 0。 */
export const HorizonStatSchema = z
  .object({
    avg_red: z.number().nullable().optional(),
    up_frac: z.number().nullable().optional(),
    median_delta: z.number().nullable().optional(),
  })
  .catchall(z.unknown())
export type HorizonStat = z.infer<typeof HorizonStatSchema>

export const AnalogRowSchema = z
  .object({
    date: z.string(),
    distance: z.number().nullable().optional(),
    metrics: z.record(z.string(), z.number()).optional(),
    state: z.string().nullable().optional(),
    forward: z
      .object({
        d5: HorizonStatSchema,
        d10: HorizonStatSchema,
        d20: HorizonStatSchema,
      })
      .partial()
      .catchall(z.unknown())
      .optional(),
  })
  .catchall(z.unknown())
export type AnalogRow = z.infer<typeof AnalogRowSchema>

export const MarketTemperatureSchema = z
  .object({
    hist_days: z.number(),
    data_as_of: z.string().nullable().optional(),
    temperature: z
      .object({
        available: z.boolean(),
        temp: z.number().nullable().optional(),
        contributions: z.array(TempContributionSchema).optional(),
        reason: z.string().nullable().optional(),
        indicators_available: z.array(z.string()).optional(),
        /** 后端为 [key, 原因] 或 [key, 原因, 附加信息]，故第三位宽化为 unknown。 */
        indicators_unavailable: z
          .array(z.union([z.tuple([z.string(), z.string()]), z.tuple([z.string(), z.string(), z.unknown()])]))
          .optional(),
      })
      .catchall(z.unknown()),
    extreme_signal: z
      .object({
        available: z.boolean(),
        evaluated: z.boolean(),
        triggered: z.boolean(),
        hits: z.array(TempExtremeHitSchema).optional(),
        prob: z.number().nullable().optional(),
        base_rate: z.number().nullable().optional(),
        edge_pp: z.number().nullable().optional(),
        strength_hint: z.string().nullable().optional(),
        statement: z.string(),
        abstain: z.boolean().optional(),
        reason: z.string().nullable().optional(),
      })
      .catchall(z.unknown()),
    analogs: z
      .object({
        available: z.boolean(),
        today_metrics: z
          .object({
            red_ratio: z.number().nullable().optional(),
            limit_up: z.number().nullable().optional(),
            limit_down: z.number().nullable().optional(),
          })
          .catchall(z.unknown())
          .nullable()
          .optional(),
        analogs: z.array(AnalogRowSchema).optional(),
        reason: z.string().nullable().optional(),
      })
      .catchall(z.unknown()),
  })
  .catchall(z.unknown())
export type MarketTemperature = z.infer<typeof MarketTemperatureSchema>

/** 基准窗口白名单（与后端 hist_days 校验一致）：近一季 60 / 近一年 250 / 全历史 2007 起 2000。 */
export type MarketTemperatureWindow = 60 | 250 | 2000


// ───────── 决策闭环健康度（v2 全局停摆告警，AC3 严格契约）─────────
// 真值源 modules.decision.assess_decision_loop_health()；未知 status 一律 parse 失败，
// 前端进 error 态显示「健康状态不可得」，绝不把异常状态洗成 ok。
export const DecisionLoopHealthSchema = z.object({
  status: z.enum(['ok', 'warn', 'stale', 'dead', 'unknown']),
  rank: z.number().int().min(0).max(3),
  generated_at: z.string().nullable(),
  as_of: z.string().nullable(),
  gen_lag_hours: z.number().nullable(),
  data_lag_days: z.number().nullable(),
  message: z.string(),
})
export type DecisionLoopHealth = z.infer<typeof DecisionLoopHealthSchema>

// ───────── 个股事件追踪（stock-events / v1 23_事件追踪.py 迁移）─────────
// 后端契约 GET /api/v2/read/stock-events?code=600519&limit=50。
// 诚实红线：score/date/name/source/url 缺失必须是 null（页面渲染 '—'），
// 绝不用 0 / '' 伪造；distribution 三个字段是真实计数，为 0 即真实为 0。
export const StockEventItemSchema = z
  .object({
    date: z.string().nullable().optional(),
    title: z.string(),
    source: z.string().nullable().optional(),
    url: z.string().nullable().optional(),
    sentiment: z.string(),
    level: z.string(),
    score: z.number().nullable().optional(),
    is_major: z.boolean(),
  })
  .catchall(z.unknown())
export type StockEventItem = z.infer<typeof StockEventItemSchema>

export const StockEventSchema = z
  .object({
    code: z.string(),
    name: z.string().nullable().optional(),
    date: z.string().nullable().optional(),
    available: z.boolean(),
    events: z.array(StockEventItemSchema).default([]),
    distribution: z
      .object({
        正面: z.number().nullable().optional(),
        负面: z.number().nullable().optional(),
        中性: z.number().nullable().optional(),
      })
      .optional(),
    count: z.number(),
    note: z.string(),
  })
  .catchall(z.unknown())
export type StockEvent = z.infer<typeof StockEventSchema>

/**
 * I3 事件因子五源适配器（GET /event-factor）—— 与上方 DailySnapshot.event_factor
 * 的 `EventFactorSchema` 是两个不同契约，勿混用。字段逐字对齐后端 event_factor()。
 * 缺失数值一律 nullable（None），不补 0；失败态 available=false + reason 原样透出。
 */
export const EventFactorSignalSchema = z
  .object({
    available: z.boolean(),
    symbol: z.string(),
    score: z.number().nullable().optional(),
    signal: z.string().nullable().optional(),
    rank: z.number().nullable().optional(),
    date: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    horizon: z.unknown().optional(),
    hard_logic: z.unknown().optional(),
    reason: z.string().nullable().optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type EventFactorSignal = z.infer<typeof EventFactorSignalSchema>

/** I3 事件驱动看多榜单项（GET /event-long-list items[]）。 */
export const EventLongItemSchema = z
  .object({
    symbol: z.string().nullable().optional(),
    score: z.number().nullable().optional(),
    raw_rank: z.number().nullable().optional(),
    raw_pred: z.unknown().optional(),
    signal: z.string().nullable().optional(),
    source: z.string().nullable().optional(),
    horizon: z.unknown().optional(),
    hard_logic: z.unknown().optional(),
  })
  .catchall(z.unknown())
export type EventLongItem = z.infer<typeof EventLongItemSchema>

/** I3 事件驱动看多榜信封 data。 */
export const EventLongListSchema = z
  .object({
    items: z.array(EventLongItemSchema).default([]),
    count: z.number().default(0),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type EventLongList = z.infer<typeof EventLongListSchema>

/**
 * 毕设证据（GET /thesis-evidence）—— 三算法对照实验 / 第6章评估 / SHAP 归因 / 非对称发现。
 * 诚实红线：负向 verdict 原样透出不美化；缺失数值 null 不补 0；
 * 实验证据不是生产信号（note 原文展示）。
 */
const ThesisFindingSchema = z
  .object({
    title: z.string().optional(),
    advisor: z.string().optional(),
    verdict: z.string().optional(),
    verdict_cn: z.string().optional(),
    direction_hit: z.number().nullable().optional(),
    direction_hit_baseline: z.number().nullable().optional(),
    ic: z.number().nullable().optional(),
    ic_baseline: z.number().nullable().optional(),
    icir: z.number().nullable().optional(),
    icir_baseline: z.number().nullable().optional(),
    sharpe: z.number().nullable().optional(),
    sharpe_baseline_sign: z.number().nullable().optional(),
    sharpe_baseline_tanh: z.number().nullable().optional(),
    turnover: z.number().nullable().optional(),
    provenance: z.string().optional(),
  })
  .catchall(z.unknown())

export const ThesisFindingsSchema = z
  .object({
    core_innovation_cn: z.string().optional(),
    decision_closure_anchor: z
      .object({ accuracy: z.number().nullable().optional(), n: z.number().nullable().optional(), n_hit: z.number().nullable().optional() })
      .catchall(z.unknown())
      .optional(),
    findings: z.record(z.string(), ThesisFindingSchema).optional(),
    asymmetric_finding: z
      .object({
        defensive_total_pp: z.number().nullable().optional(),
        offensive_total_pp: z.number().nullable().optional(),
        annualized_offensive_cost_pp: z.number().nullable().optional(),
        note: z.string().optional(),
        provenance: z.string().optional(),
      })
      .catchall(z.unknown())
      .optional(),
    honest_redline: z.string().optional(),
    available: z.boolean().optional(),
    reason: z.string().optional(),
  })
  .catchall(z.unknown())

export const ThesisCh6Schema = z
  .object({
    available: z.boolean(),
    metrics: z.record(z.string(), z.unknown()).nullable().optional(),
    note: z.string().nullable().optional(),
  })
  .catchall(z.unknown())

export const ThesisShapSchema = z
  .object({
    available: z.boolean(),
    baseline: z.number().nullable().optional(),
    adjustments: z.record(z.string(), z.number()).optional(),
    adjustments_total: z.number().nullable().optional(),
    final_running: z.number().nullable().optional(),
    as_of: z.string().nullable().optional(),
    reason: z.string().nullable().optional(),
  })
  .catchall(z.unknown())

export const ThesisEvidenceSchema = z
  .object({
    findings: ThesisFindingsSchema,
    ch6: ThesisCh6Schema,
    shap_attribution: ThesisShapSchema,
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type ThesisEvidence = z.infer<typeof ThesisEvidenceSchema>
export type ThesisFinding = z.infer<typeof ThesisFindingSchema>
