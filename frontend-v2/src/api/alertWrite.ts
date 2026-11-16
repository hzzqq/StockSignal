import { apiFetch } from './client'
import { apiMutate } from './write'
import {
  PriceAlertSchema,
  PriceAlertListSchema,
  MarketAlertListSchema,
  AlertConfigSchema,
  MarketAlertConfigGetSchema,
  ScanResultSchema,
  type PriceAlert,
  type PriceAlertList,
  type MarketAlertList,
  type AlertConfig,
  type MarketAlertConfigGet,
  type ScanResult,
  type CreatePriceAlertInput,
} from './schemas/alertWrite'

/**
 * 价格预警 / 市场指标异动提醒 · 类型化端点封装（v1→v2 能力对齐批次）。
 *
 * - 读：一律 `apiFetch<unknown>` 取信封 data，再用专用 Zod schema 严格 parse
 *   （缺字段/类型不符即抛错，绝不兜底），与 src/api/read.ts 同源。
 * - 写：一律走统一写层 `apiMutate`（Bearer + 401 单飞刷新 + 信封解包）。
 *   无响应体的端点（DELETE / read / read-all）显式传 schema=null 表示「不解析」，
 *   不是静默成功。
 *
 * 红线：本文件只碰 /api/price-alerts 与 /api/market-alerts；
 * 条件单与真实券商下单链路属 C 类实盘红线，v2 明确不接入。
 */

export interface MarketAlertsParams {
  limit?: number
  offset?: number
  unread_only?: boolean
}

/** GET /api/price-alerts —— 当前用户全部预警（含已触发）。 */
export async function listPriceAlerts(): Promise<PriceAlertList> {
  return PriceAlertListSchema.parse(await apiFetch<unknown>('/price-alerts'))
}

/** GET /api/market-alerts?limit&offset&unread_only=1 —— 列表 + 未读数。 */
export async function listMarketAlerts(params: MarketAlertsParams = {}): Promise<MarketAlertList> {
  const q = new URLSearchParams()
  if (params.limit !== undefined) q.set('limit', String(params.limit))
  if (params.offset !== undefined) q.set('offset', String(params.offset))
  if (params.unread_only === true) q.set('unread_only', '1')
  const qs = q.toString()
  return MarketAlertListSchema.parse(await apiFetch<unknown>(`/market-alerts${qs ? `?${qs}` : ''}`))
}

/** GET /api/market-alerts/config —— 扫描策略配置（@admin_required）。 */
export async function getMarketAlertConfig(): Promise<MarketAlertConfigGet> {
  return MarketAlertConfigGetSchema.parse(await apiFetch<unknown>('/market-alerts/config'))
}

/** POST /api/price-alerts —— 创建四类预警之一，返回创建后的告警对象。 */
export function createPriceAlert(input: CreatePriceAlertInput): Promise<PriceAlert> {
  return apiMutate<PriceAlert>('/price-alerts', 'POST', input, PriceAlertSchema)
}

/** PUT /api/price-alerts/:id/toggle —— 启用/停用切换，返回切换后的告警对象。 */
export function togglePriceAlert(id: number): Promise<PriceAlert> {
  return apiMutate<PriceAlert>(`/price-alerts/${id}/toggle`, 'PUT', undefined, PriceAlertSchema)
}

/** DELETE /api/price-alerts/:id —— 仅 message，无 data。 */
export function deletePriceAlert(id: number): Promise<unknown> {
  return apiMutate<unknown>(`/price-alerts/${id}`, 'DELETE', undefined, null)
}

/** POST /api/market-alerts/:id/read —— 单条已读，仅 message。 */
export function markMarketAlertRead(id: number): Promise<unknown> {
  return apiMutate<unknown>(`/market-alerts/${id}/read`, 'POST', undefined, null)
}

/** POST /api/market-alerts/read-all —— 全部已读，仅 message。 */
export function markAllMarketAlertsRead(): Promise<unknown> {
  return apiMutate<unknown>('/market-alerts/read-all', 'POST', undefined, null)
}

/** POST /api/market-alerts/scan —— 管理员扫描（@admin_required），返回 { inserted }。 */
export function scanMarketAlerts(): Promise<ScanResult> {
  return apiMutate<ScanResult>('/market-alerts/scan', 'POST', undefined, ScanResultSchema)
}

/** POST /api/market-alerts/config —— 管理员更新策略（@admin_required），返回 { config }。 */
export function updateMarketAlertConfig(config: Record<string, unknown>): Promise<AlertConfig> {
  return apiMutate<AlertConfig>('/market-alerts/config', 'POST', config, AlertConfigSchema)
}
