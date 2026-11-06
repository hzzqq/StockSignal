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
