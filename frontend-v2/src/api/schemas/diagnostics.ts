import { z } from 'zod'

/**
 * W4-D · 数据源 / 接口检测契约。
 *
 * 诚实红线：
 *  - 每个检测项都带 available 布尔标志；取数失败时 available=false + reason，
 *    不得把空数组包装成「全部正常」。
 *  - as_of / lag_days 是各源**真实数据截止日**，允许 null；禁止用探测时刻冒充。
 *  - probe 默认 null（零网络）；只有显式触发才有值。
 *  - 接口清单来自后端 Flask url_map 动态枚举，前端不硬编码端点列表。
 */
const NullableString = z.string().nullable()
const NullableNumber = z.number().nullable()

export const DiagnosticsSourceItemSchema = z.object({
  key: z.string(),
  label: z.string(),
  ok: z.boolean(),
  detail: NullableString,
  tables: z.record(z.string(), z.number()).nullable().optional(),
})
export type DiagnosticsSourceItem = z.infer<typeof DiagnosticsSourceItemSchema>

export const DiagnosticsSourcesSchema = z.object({
  available: z.boolean(),
  summary: NullableString,
  checked_at: NullableString,
  items: z.array(DiagnosticsSourceItemSchema),
  reason: NullableString,
})
export type DiagnosticsSources = z.infer<typeof DiagnosticsSourcesSchema>

export const DiagnosticsFreshnessRowSchema = z.object({
  key: z.string(),
  name: z.string(),
  as_of: NullableString,
  lag_days: NullableNumber,
  status: z.string(),
})
export type DiagnosticsFreshnessRow = z.infer<typeof DiagnosticsFreshnessRowSchema>

export const DiagnosticsFreshnessSchema = z.object({
  available: z.boolean(),
  rows: z.array(DiagnosticsFreshnessRowSchema),
  reason: NullableString,
})
export type DiagnosticsFreshness = z.infer<typeof DiagnosticsFreshnessSchema>

export const DiagnosticsEndpointSchema = z.object({
  path: z.string(),
  needs_params: z.boolean(),
  probe_path: NullableString,
  // 必填 query 参数名；需参端点不得自动探测。示例参数仅数据浏览器使用。
  required_query: z.array(z.string()).default([]),
  sample_query: NullableString.default(null),
})
export type DiagnosticsEndpoint = z.infer<typeof DiagnosticsEndpointSchema>

export const DiagnosticsProbeLevelSchema = z.object({
  level: z.string(),
  ok: z.boolean(),
  detail: NullableString,
  latency_ms: NullableNumber,
})
export type DiagnosticsProbeLevel = z.infer<typeof DiagnosticsProbeLevelSchema>

export const DiagnosticsProbeSchema = z.object({
  available: z.boolean(),
  levels: z.array(DiagnosticsProbeLevelSchema),
  reason: NullableString,
}).nullable()
export type DiagnosticsProbe = z.infer<typeof DiagnosticsProbeSchema>

export const DiagnosticsSchema = z.object({
  sources: DiagnosticsSourcesSchema,
  freshness: DiagnosticsFreshnessSchema,
  endpoints: z.array(DiagnosticsEndpointSchema),
  probe: DiagnosticsProbeSchema,
  note: z.string(),
})
export type Diagnostics = z.infer<typeof DiagnosticsSchema>

/** 单个接口的真实 GET 探测结果（浏览器 → Vite proxy → 后端，端到端）。 */
export interface EndpointProbeResult {
  path: string
  httpStatus: number | null
  envelopeStatus: string | null
  ok: boolean
  latencyMs: number | null
  detail: string
}
