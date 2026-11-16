import { apiFetch } from './client'
import { apiMutate } from './write'
import {
  BreadthDivergenceSchema,
  type BreadthDivergence,
} from './schemas/breadthDivergence'
import {
  TemperatureBacktestSchema,
  type TemperatureBacktest,
} from './schemas/temperatureBacktest'
import {
  UserDashboardWriteSchema,
  UserDashboardDataSchema,
  ReviewNotesWriteSchema,
  ReviewNotesDataSchema,
  type UserDashboardData,
  type ReviewNotesData,
} from './schemas/batchBWrite'

/**
 * parity B 批次 API client。
 * 读：apiFetch<unknown> 取信封 data（client 已解包），专用 Zod schema.parse 严格校验；
 * 写：统一走 apiMutate（Bearer + 401 单飞刷新 + 信封解包），入参先 parse 挡非法值，
 *     响应 schema 严格解包。路径按契约拼到 /api 前缀之后，不整体 encode。
 */

export interface BreadthDivergenceParams {
  red_thresh?: number
  ld_quantile?: number
  window_days?: number
}

/** GET /api/v2/read/breadth-divergence?red_thresh=&ld_quantile=&window_days= */
export function getBreadthDivergence(params?: BreadthDivergenceParams): Promise<BreadthDivergence> {
  const q = new URLSearchParams()
  if (params?.red_thresh !== undefined) q.set('red_thresh', String(params.red_thresh))
  if (params?.ld_quantile !== undefined) q.set('ld_quantile', String(params.ld_quantile))
  if (params?.window_days !== undefined) q.set('window_days', String(params.window_days))
  const suffix = q.toString()
  const path = suffix
    ? `/v2/read/breadth-divergence?${suffix}`
    : '/v2/read/breadth-divergence'
  return apiFetch<unknown>(path).then((raw) => BreadthDivergenceSchema.parse(raw))
}

export interface TemperatureBacktestParams {
  window_days?: number
}

/** GET /api/v2/read/temperature-backtest?window_days= （window_days 可省略） */
export function getTemperatureBacktest(
  params?: TemperatureBacktestParams,
): Promise<TemperatureBacktest> {
  const q = new URLSearchParams()
  if (params?.window_days !== undefined) q.set('window_days', String(params.window_days))
  const suffix = q.toString()
  const path = suffix ? `/v2/read/temperature-backtest?${suffix}` : '/v2/read/temperature-backtest'
  return apiFetch<unknown>(path).then((raw) => TemperatureBacktestSchema.parse(raw))
}

/** PUT /api/v2/read/user-dashboard —— 入参为 widget id 数组（顺序即展示顺序），包成契约 body。 */
export function putUserDashboard(widgets: string[]): Promise<UserDashboardData> {
  const body = UserDashboardWriteSchema.parse({ widgets })
  return apiMutate<UserDashboardData>(
    '/v2/read/user-dashboard',
    'PUT',
    body,
    UserDashboardDataSchema,
  )
}

/** PUT /api/v2/read/review-notes —— 保存指定日期复盘笔记（按当前用户隔离）。 */
export function putReviewNotes(input: { date: string; content: string }): Promise<ReviewNotesData> {
  const body = ReviewNotesWriteSchema.parse(input)
  return apiMutate<ReviewNotesData>('/v2/read/review-notes', 'PUT', body, ReviewNotesDataSchema)
}
