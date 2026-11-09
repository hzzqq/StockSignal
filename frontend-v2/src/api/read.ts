import { z } from 'zod'
import { apiFetch } from './client'
import {
  DailySnapshotSchema,
  P1SignalSchema,
  DailyRecommendationSchema,
  VirtualUsersSimSchema,
  PaperTradeSchema,
  ReviewNotesSchema,
  WebAppSchema,
  BreadthPointSchema,
  LadderDaySchema,
  BreadthHistoryPointSchema,
  EventPoolSchema,
  PredictionLogRowSchema,
  P1SyncStatusSchema,
  BacktestRunsSchema,
  DataRefreshStateSchema,
  FactorAnalysisSchema,
  BacktestSchema,
  MarketPanoramaSchema,
  type DailySnapshot,
  type P1Signal,
  type DailyRecommendation,
  type VirtualUsersSim,
  type PaperTrade,
  type ReviewNotes,
  type WebApp,
  type SnapshotDateList,
  type BreadthPoint,
  type LadderDay,
  type BreadthHistoryPoint,
  type EventPool,
  type PredictionLogRow,
  type P1SyncStatus,
  type BacktestRuns,
  type DataRefreshState,
  type FactorAnalysis,
  type Backtest,
  type MarketPanorama,
} from './schemas/read'

/**
 * W1 只读端点类型化封装。
 *
 * 设计：每个函数先 `apiFetch<unknown>` 取信封 data（已由 client 解包），
 * 再用专用 Zod schema `parse` 严格校验；缺失/类型不符即抛错（不兜底），
 * 与 PLAN.md §4.3 红线一致。路径斜杠与查询参数按契约精确拼接，不整体 encodeURIComponent
 * （否则会把 `/` 编码成 %2F 破坏路由）。
 */
async function readValidated<T>(
  source: string,
  schema: { parse: (input: unknown) => T },
): Promise<T> {
  const data = await apiFetch<unknown>(`/v2/read/${source}`)
  return schema.parse(data)
}

/** GET /api/v2/read/daily-snapshot —— 今日决策快照（54/90/98 页「今日」单一真理源） */
export function getDailySnapshot(): Promise<DailySnapshot> {
  return readValidated('daily-snapshot', DailySnapshotSchema)
}

/** GET /api/v2/read/snapshot-dates —— 可回放归档日期清单（97 页下拉源） */
export async function getSnapshotDates(): Promise<SnapshotDateList> {
  return z
    .array(z.string())
    .parse(await apiFetch<unknown>('/v2/read/snapshot-dates'))
}

/** GET /api/v2/read/snapshot/<date> —— 指定日期归档快照（97 页回放主体） */
export function getSnapshotByDate(date: string): Promise<DailySnapshot> {
  return readValidated(`snapshot/${encodeURIComponent(date)}`, DailySnapshotSchema)
}

/** GET /api/v2/read/p1-signals —— P1 量化信号目录（54/51 页多头侧参考） */
export async function getP1Signals(): Promise<Record<string, P1Signal>> {
  return z
    .record(z.string(), P1SignalSchema)
    .parse(await apiFetch<unknown>('/v2/read/p1-signals'))
}

/** GET /api/v2/read/daily-recommendation —— 每日荐股（36 页主体） */
export function getDailyRecommendation(): Promise<DailyRecommendation> {
  return readValidated('daily-recommendation', DailyRecommendationSchema)
}

/** GET /api/v2/read/virtual-users-sim —— 虚拟用户蒙特卡洛模拟（36 页历史模拟段） */
export function getVirtualUsersSim(): Promise<VirtualUsersSim> {
  return readValidated('virtual-users-sim', VirtualUsersSimSchema)
}

/** GET /api/v2/read/paper-trades?user=<user> —— 指定用户模拟账本（42 页） */
export function getPaperTrades(user: string): Promise<PaperTrade> {
  return readValidated(`paper-trades?user=${encodeURIComponent(user)}`, PaperTradeSchema)
}

/** GET /api/v2/read/review-notes?date=<date> —— 指定日期复盘笔记（51 页复盘段） */
export function getReviewNotes(date: string): Promise<ReviewNotes> {
  return readValidated(`review-notes?date=${encodeURIComponent(date)}`, ReviewNotesSchema)
}

/** GET /api/v2/read/webapps —— 网页作品集元数据（86 页作品清单） */
export async function getWebApps(): Promise<WebApp[]> {
  return z
    .array(WebAppSchema)
    .parse(await apiFetch<unknown>('/v2/read/webapps'))
}

/** GET /api/v2/read/alert-rules —— 告警规则配置（74 页规则配置） */
export async function getAlertRules(): Promise<Record<string, unknown>> {
  return z
    .record(z.string(), z.unknown())
    .parse(await apiFetch<unknown>('/v2/read/alert-rules'))
}

/** GET /api/v2/read/alert-log —— 告警触发日志原文（74 页写入日志） */
export async function getAlertLog(): Promise<string> {
  return z.string().parse(await apiFetch<unknown>('/v2/read/alert-log'))
}

/** GET /api/v2/read/breadth-timeseries —— 广度时序（snapshots 聚合，W3 广度页时序源） */
export async function getBreadthTimeseries(): Promise<BreadthPoint[]> {
  return z
    .array(BreadthPointSchema)
    .parse(await apiFetch<unknown>('/v2/read/breadth-timeseries'))
}

/** GET /api/v2/read/ladder-detail —— 连板梯队历史明细（W3 连板共振页数据源） */
export async function getLadderDetail(): Promise<LadderDay[]> {
  return z
    .array(LadderDaySchema)
    .parse(await apiFetch<unknown>('/v2/read/ladder-detail'))
}

/** GET /api/v2/read/breadth-history —— 长周期广度历史（shepherd_history，2007→2026） */
export async function getBreadthHistory(): Promise<BreadthHistoryPoint[]> {
  return z
    .array(BreadthHistoryPointSchema)
    .parse(await apiFetch<unknown>('/v2/read/breadth-history'))
}

// ───────── W3 后续簇（5 个真实本地 JSON 数据源，2026-11-07 真扫字段名）─────────
// 全部走 readValidated / z.*.parse 严格校验；解析失败即抛错，禁止 `?? 0` 兜底。
// 数据缺失时后端返回 200 + status=error，client 层会抛 ApiError，页面渲染错误态。

/** GET /api/v2/read/event-pool —— 事件因子池（data/event_pool_brief.json） */
export function getEventPool(): Promise<EventPool> {
  return readValidated('event-pool', EventPoolSchema)
}

/** GET /api/v2/read/prediction-log —— 决策预测校准日志（data/prediction_log.json） */
export async function getPredictionLog(): Promise<PredictionLogRow[]> {
  return z
    .array(PredictionLogRowSchema)
    .parse(await apiFetch<unknown>('/v2/read/prediction-log'))
}

/** GET /api/v2/read/p1-sync-status —— P1 信号同步状态（后端已递归剔除 target_dir 绝对路径） */
export function getP1SyncStatus(): Promise<P1SyncStatus> {
  return readValidated('p1-sync-status', P1SyncStatusSchema)
}

/** GET /api/v2/read/backtest-runs —— 回测运行记录（data/backtest_runs.json） */
export function getBacktestRuns(): Promise<BacktestRuns> {
  return readValidated('backtest-runs', BacktestRunsSchema)
}

/** GET /api/v2/read/data-refresh-state —— 数据刷新状态（data/data_refresh_state.json） */
export function getDataRefreshState(): Promise<DataRefreshState> {
  return readValidated('data-refresh-state', DataRefreshStateSchema)
}

// ───────── 因子分析（factor-analysis / modules.factor_analysis 纯函数）─────────
// 逐标的实时取数（page_utils.hist_cached）、独立降级；有效标的<3 时后端返回
// status=error（insufficient_data），client 抛 ApiError → 页面渲染错误态，不兜底。
export interface FactorAnalysisParams {
  codes: string[]
  days?: number
  factor?: string
  n_layers?: number
  forward?: number
}

/** GET /api/v2/read/factor-analysis —— IC/IR、分层收益、多空组合（71 页因子分析 V2 化） */
export function getFactorAnalysis(params: FactorAnalysisParams): Promise<FactorAnalysis> {
  const q = new URLSearchParams()
  if (params.codes?.length) q.set('codes', params.codes.join(','))
  q.set('days', String(params.days ?? 250))
  q.set('factor', params.factor ?? 'momentum')
  q.set('n_layers', String(params.n_layers ?? 5))
  q.set('forward', String(params.forward ?? 1))
  return readValidated(`factor-analysis?${q.toString()}`, FactorAnalysisSchema)
}

// ───────── 策略回测（backtest / modules.backtest.Backtester）─────────
// 单标的实时取数回测；取数为空时后端返回 status=error（insufficient_data），
// client 抛 ApiError → 页面渲染错误态，不兜底补零曲线。
export interface BacktestParams {
  ticker: string
  start?: string
  end?: string
  strategy?: string
}

/** GET /api/v2/read/backtest —— 单标的多因子/均线/事件驱动回测（30 页策略回测 V2 化） */
export function getBacktest(params: BacktestParams): Promise<Backtest> {
  const q = new URLSearchParams()
  q.set('ticker', params.ticker.trim())
  if (params.start) q.set('start', params.start)
  if (params.end) q.set('end', params.end)
  q.set('strategy', params.strategy ?? 'multi_factor')
  return readValidated(`backtest?${q.toString()}`, BacktestSchema)
}

// ───────── 市场全景 / 状态机（market-panorama：regime_report + shepherd 广度）─────────
// 56 页「市场状态机」与 57 页「市场全景」共享同一后端；regime 不可用时后端返回
// status=error（insufficient_data），client 抛 ApiError → 页面渲染错误态，不兜底。
export interface MarketPanoramaParams {
  k?: number
}

/** GET /api/v2/read/market-panorama —— 市场状态五档 + 历史相似日 + 广度快照（56/57 页 V2 化） */
export function getMarketPanorama(params: MarketPanoramaParams = {}): Promise<MarketPanorama> {
  const q = new URLSearchParams()
  q.set('k', String(params.k ?? 8))
  return readValidated(`market-panorama?${q.toString()}`, MarketPanoramaSchema)
}
