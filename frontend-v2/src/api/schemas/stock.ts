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

// ═══════════════════ W4-B · 个股域三端点响应 data 严格 Zod 校验 ═══════════════════
// 契约（team-lead 已拍板，字段名不得改；与 backend/api/read_routes.py:957-1058 对齐）：
//  - 数值 z.number().nullable()、字符串 z.string().nullable()，禁 .default() / ?? 0 / ?? ''；
//  - perf 三形态（补充裁决）：正常=9 字段有值对象；全源失败=9 字段全 null 对象（后端实测）；
//    保守上界=整体 null。Zod 用 .nullable() 兼容「对象」与「null」两种、不二选一；
//    逐字段独立降级、缺失为 null，绝不补 0；
//  - rows 为「中文动态列名」list[dict]，可空数组 []，用 z.record(z.string(), z.unknown())；
//  - date 为权威数据日，取不到为 null，禁 now() 兜底；spot_date / kline_date 独立、禁互兜底；
//  - 解析失败即抛错（不兜底），与 W4-A 一致。

const NullableString = z.string().nullable()

/** fundamentals.perf：9 项业绩指标，每项 number|null（取数失败为 null，绝不补 0）。 */
export const FundamentalsPerfSchema = z.object({
  revenue_yi: NullableNumber,
  revenue_yoy: NullableNumber,
  net_profit_yi: NullableNumber,
  profit_yoy: NullableNumber,
  gross_margin: NullableNumber,
  roe: NullableNumber,
  alr: NullableNumber,
  current_ratio: NullableNumber,
  equity_ratio: NullableNumber,
})
export type FundamentalsPerf = z.infer<typeof FundamentalsPerfSchema>

/** GET /api/v2/read/fundamentals?code=<6位> 的 data。 */
export const FundamentalsSchema = z.object({
  code: z.string(),
  name: NullableString,
  industry: NullableString,
  price: NullableNumber,
  pe_ttm: NullableNumber,
  market_cap: NullableNumber,
  spot_date: NullableString,
  kline_date: NullableString,
  perf: FundamentalsPerfSchema.nullable(),
  priceDomain: z.string(),
  date: NullableString,
  note: NullableString,
})
export type Fundamentals = z.infer<typeof FundamentalsSchema>

/** 财报/K 线 rows：中文动态列名 list[dict]，值类型未知，交由 fmtNum 诚实渲染。 */
const RowSchema = z.record(z.string(), z.unknown())

/** GET /api/v2/read/financials?code=<6位>&report=...&limit=... 的 data。 */
export const FinancialsSchema = z.object({
  code: z.string(),
  report: z.string(),
  rows: z.array(RowSchema),
  date: NullableString,
  note: NullableString,
})
export type Financials = z.infer<typeof FinancialsSchema>

/** GET /api/v2/read/stock-kline?code=<6位>&period=...&limit=... 的 data。 */
export const StockKlineSchema = z.object({
  code: z.string(),
  period: z.string(),
  rows: z.array(RowSchema),
  date: NullableString,
  note: NullableString,
})
export type StockKline = z.infer<typeof StockKlineSchema>

// ═══════════════════ W4-C · 多股对比 / 深度分析 通用透传契约 ═══════════════════
// 这两类响应字段多、随后端演进，前端按 key 渲染、不强约束具体字段名（与 W4-B
// rows 的 z.record(z.string(), z.unknown()) 同一思路）。类型侧 cast 为
// Record<string, unknown>，任何解析失败即抛错（不兜底），与全站一致。

/** GET /api/v2/read/compare-one?code=<6位>&period=... 的 data（通用透传）。 */
export const CompareOneSchema = z.record(z.string(), z.unknown())
export type CompareOne = z.infer<typeof CompareOneSchema>

/** GET /api/v2/read/research-deep?code=<6位> 的 data（通用透传，含技术字段与豁免键）。 */
export const ResearchDeepSchema = z.record(z.string(), z.unknown())
export type ResearchDeep = z.infer<typeof ResearchDeepSchema>
