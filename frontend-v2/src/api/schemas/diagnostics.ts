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

/** 后端「诚实业务降级」业务码（HTTP 200 + status=error）。
 *  与 backend/api/read_routes.py 里 fail(..., http_status=200) 的 code 集合同源：
 *  数据缺失 / 样本不足 / 计算不可用。这些不是接口故障，但**仍不算成功**；
 *  诊断页单独标注，绝不把 error 洗成 ok。 */
export const BUSINESS_DEGRADED_CODES: Record<string, string> = {
  not_found: '数据文件缺失',
  invalid_data: '本地数据解析失败',
  unavailable: '数据源暂不可用',
  compute_error: '计算降级',
  insufficient_data: '样本不足',
}

export type ProbeKind = 'ok' | 'degraded' | 'failure'

/** 纯函数：区分「成功 / 业务诚实降级 / 真接口故障」，UI 与测试共用。 */
export function probeKind(
  r: Pick<EndpointProbeResult, 'ok' | 'httpStatus' | 'envelopeStatus' | 'envelopeCode'>,
): ProbeKind {
  if (r.ok) return 'ok'
  const code = r.envelopeCode
  const is2xx = r.httpStatus !== null && r.httpStatus >= 200 && r.httpStatus < 300
  if (is2xx && r.envelopeStatus === 'error' && code && BUSINESS_DEGRADED_CODES[code]) {
    return 'degraded'
  }
  return 'failure'
}

/** 单个接口的真实 GET 探测结果（浏览器 → Vite proxy → 后端，端到端）。 */
export interface EndpointProbeResult {
  path: string
  httpStatus: number | null
  envelopeStatus: string | null
  /** 后端信封 code；用于区分业务降级与接口故障，缺失为 null。 */
  envelopeCode: string | null
  ok: boolean
  latencyMs: number | null
  detail: string
}
