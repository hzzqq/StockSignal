import { z } from 'zod'

/**
 * 价格预警 / 市场指标异动提醒 · 写端点契约。
 *
 * 对齐 backend/api/alert_routes.py、backend/api/market_alert_routes.py 与
 * backend/models.py::PriceAlert::to_dict / MarketAlert::to_dict（逐字段核实）。
 *
 * 红线：严格 Zod、nullable 显式、禁止 default 补零（字段缺失/类型不符即抛错，
 * 由页面渲染错误态，绝不 `?? 0` 兜底）。
 *
 * 注意读写形状不对称：
 *  - 创建入参的 `params` 是对象（后端 json_body() 当 dict 读，再 json.dumps 落库）；
 *  - 读回的 PriceAlert.params 是 JSON 文本字符串或 null（DB Text 列原样返回）。
 */

/** 后端 ALERT_TYPES = ("price","pattern","volume","announcement") */
export const ALERT_TYPES = ['price', 'pattern', 'volume', 'announcement'] as const
export const AlertTypeSchema = z.enum(ALERT_TYPES)
export type AlertType = z.infer<typeof AlertTypeSchema>

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  price: '价格预警',
  pattern: '技术形态预警',
  volume: '成交量异动预警',
  announcement: '公告预警',
}

export const PriceAlertConditionSchema = z.enum(['above', 'below'])
export type PriceAlertCondition = z.infer<typeof PriceAlertConditionSchema>
export const CONDITION_LABELS: Record<PriceAlertCondition, string> = {
  above: '上破',
  below: '下破',
}

export const MarketSeveritySchema = z.enum(['info', 'warning', 'danger'])
export type MarketSeverity = z.infer<typeof MarketSeveritySchema>
/** 文字标签是 severity 的主信息载体，颜色只作辅助（不得用颜色传递唯一信息）。 */
export const SEVERITY_LABELS: Record<MarketSeverity, string> = {
  info: '提示',
  warning: '警告',
  danger: '危险',
}

/** PriceAlert.to_dict() —— GET /price-alerts 列表项、POST 创建 / PUT toggle 的 data。 */
export const PriceAlertSchema = z.object({
  id: z.number().int(),
  user_id: z.number().int(),
  stock_code: z.string(),
  stock_name: z.string(),
  alert_type: AlertTypeSchema,
  condition: PriceAlertConditionSchema,
  target_price: z.number(),
  params: z.string().nullable(),
  active: z.boolean(),
  triggered: z.boolean(),
  triggered_at: z.string().nullable(),
  created_at: z.string().nullable(),
})
export type PriceAlert = z.infer<typeof PriceAlertSchema>

/** GET /api/price-alerts → data: PriceAlert[] */
export const PriceAlertListSchema = z.array(PriceAlertSchema)
export type PriceAlertList = z.infer<typeof PriceAlertListSchema>

/**
 * 创建入参（POST /api/price-alerts）。按 alert_type 做 discriminatedUnion，
 * 四类必填参数逐条复刻后端校验规则：
 *  - price        : target_price > 0 且 condition ∈ {above,below}
 *  - pattern      : params.pattern_name 非空
 *  - volume       : params.volume_ratio > 0
 *  - announcement : params.keyword 非空
 * 公共：stock_code 非空，stock_name 可省（后端落 ""）。
 */
const CreateAlertBase = {
  stock_code: z.string().min(1, '股票代码不能为空'),
  stock_name: z.string().optional(),
}

export const CreatePriceAlertInputSchema = z.discriminatedUnion('alert_type', [
  z.object({
    ...CreateAlertBase,
    alert_type: z.literal('price'),
    condition: PriceAlertConditionSchema,
    target_price: z.number().positive('目标价格必须大于 0'),
  }),
  z.object({
    ...CreateAlertBase,
    alert_type: z.literal('pattern'),
    params: z.object({ pattern_name: z.string().min(1, '形态预警需指定 pattern_name') }),
  }),
  z.object({
    ...CreateAlertBase,
    alert_type: z.literal('volume'),
    params: z.object({ volume_ratio: z.number().positive('volume_ratio 必须大于 0') }),
  }),
  z.object({
    ...CreateAlertBase,
    alert_type: z.literal('announcement'),
    params: z.object({ keyword: z.string().min(1, '公告预警需指定 keyword') }),
  }),
])
export type CreatePriceAlertInput = z.infer<typeof CreatePriceAlertInputSchema>

/** MarketAlert.to_dict() —— GET /market-alerts 列表项。value/threshold 取不到时为 null。 */
export const MarketAlertSchema = z.object({
  id: z.number().int(),
  metric_key: z.string(),
  metric_name: z.string(),
  severity: MarketSeveritySchema,
  message: z.string(),
  value: z.number().nullable(),
  threshold: z.number().nullable(),
  created_at: z.string().nullable(),
})
export type MarketAlert = z.infer<typeof MarketAlertSchema>

/** GET /api/market-alerts → data:{ items, unread_count, total, last_seen } */
export const MarketAlertListSchema = z.object({
  items: z.array(MarketAlertSchema),
  unread_count: z.number().int(),
  total: z.number().int(),
  last_seen: z.string().nullable(),
})
export type MarketAlertList = z.infer<typeof MarketAlertListSchema>

/**
 * POST /api/market-alerts/config → data:{ config }。
 * config 为任意键值策略对象（值类型由后端决定，前端只展示/回传，故 z.unknown()）。
 */
export const AlertConfigSchema = z.object({
  config: z.record(z.string(), z.unknown()),
})
export type AlertConfig = z.infer<typeof AlertConfigSchema>

/** GET /api/market-alerts/config → data:{ config, runtime_overrides } */
export const MarketAlertConfigGetSchema = AlertConfigSchema.extend({
  runtime_overrides: z.record(z.string(), z.unknown()),
})
export type MarketAlertConfigGet = z.infer<typeof MarketAlertConfigGetSchema>

/** POST /api/market-alerts/scan → data:{ inserted } */
export const ScanResultSchema = z.object({
  inserted: z.number().int(),
})
export type ScanResult = z.infer<typeof ScanResultSchema>
