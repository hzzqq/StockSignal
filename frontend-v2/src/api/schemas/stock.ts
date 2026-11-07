import { z } from 'zod'

/**
 * W4-A · 个股六维评分（GET /api/v2/read/six-dim）响应 data 的 Zod 严格校验。
 *
 * 诚实红线（契约已定死，字段名不得改）：
 *  - dims 六键固定顺序，值为 number|null；null = 该维取数失败，必须如实显示「缺失」，
 *    禁止补 0 / 不画 0 分点 / 不默认掩饰；
 *  - date 可为 null（无权威数据日），禁止用当前日期兜底；
 *  - overall / raw 各字段均可为 null；note 可为 null；
 *  - 解析失败即抛错（不兜底），与 PLAN.md §4.3 一致。
 */

/** 六维键固定顺序（技术/资金/价值/成长/基本面/周期），与 dims 字段一一对应。 */
export const DIM_KEYS = [
  'technical',
  'capital',
  'value',
  'growth',
  'fundamental',
  'cycle',
] as const
export type DimKey = (typeof DIM_KEYS)[number]

/** 缺失语义：数值或 null，绝不提供默认值。 */
const NullableNumber = z.number().nullable()

/** raw 为逐维取数的原始指标，字段可为 null（取数失败或该股不适用）。
 *  state 例外：后端把市场状态机结果统一转成 str|null（非数值），
 *  故此处按 string|null 严格校验，与 backend/api/read_routes.py 的 six_dim() 对齐。 */
export const SixDimRawSchema = z.object({
  pe: NullableNumber,
  pb: NullableNumber,
  roe: NullableNumber,
  profit_yoy: NullableNumber,
  state: z.string().nullable(),
  turnover: NullableNumber,
  vol_ratio: NullableNumber,
  pos60: NullableNumber,
})

export const SixDimSchema = z.object({
  code: z.string(),
  dims: z.object({
    technical: NullableNumber,
    capital: NullableNumber,
    value: NullableNumber,
    growth: NullableNumber,
    fundamental: NullableNumber,
    cycle: NullableNumber,
  }),
  overall: NullableNumber,
  coverage: z.number(),
  missing: z.array(z.string()),
  date: z.string().nullable(),
  raw: SixDimRawSchema,
  note: z.string().nullable(),
})

export type SixDim = z.infer<typeof SixDimSchema>
export type SixDimRaw = z.infer<typeof SixDimRawSchema>
