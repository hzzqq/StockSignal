import { z } from 'zod'

/**
 * 81 自然语言选股 · 执行链路（parity D）。POST /api/v2/nl-screen/execute。
 *
 * 诚实红线（照 v1 口径）：
 *  - 候选池获取失败 / 全部未理解 → available=false + reason 原文，绝不伪造结果行；
 *  - spec 原样摊开（解析了什么透明展示，未理解词如实标注 unparsed）；
 *  - 执行依赖联网取数，离线环境本就只展示解析——这是能力边界不是故障；
 *  - 二道闸排雷异常时降级放行并如实标注 note。
 */

/** QuerySpec 原样摊开（与后端 _spec_payload 同构；filters 元素为任意规则对象）。 */
export const NlSpecSchema = z.object({
  boards: z.array(z.string()).default([]),
  filters: z.array(z.record(z.string(), z.unknown())).default([]),
  sort: z.string().nullable().default(null),
  sort_dir: z.string().nullable().default(null),
  limit: z.number().nullable().optional(),
  concepts: z.array(z.string()).default([]),
  exclude_boards: z.array(z.string()).default([]),
  exclude_concepts: z.array(z.string()).default([]),
  unparsed: z.array(z.string()).default([]),
  errors: z.array(z.unknown()).default([]),
})

export type NlSpec = z.infer<typeof NlSpecSchema>

export const NlGatedOutSchema = z.object({
  count: z.number().int().nonnegative().default(0),
  items: z
    .array(
      z.object({
        code: z.unknown().optional(),
        name: z.unknown().optional(),
        reasons: z.array(z.string()).default([]),
      }),
    )
    .default([]),
  note: z.string().nullable().default(null),
})

export type NlGatedOut = z.infer<typeof NlGatedOutSchema>

export const NlExecuteResultSchema = z.object({
  available: z.boolean(),
  reason: z.string().nullable().default(null),
  query: z.string().default(''),
  scope: z.string().default(''),
  spec: NlSpecSchema.optional(),
  source_used: z.string().nullable().optional(),
  source_notes: z.array(z.string()).optional(),
  n_universe: z.number().int().nonnegative().default(0),
  n_matched: z.number().int().nonnegative().default(0),
  n_rows: z.number().int().nonnegative().optional(),
  rows: z.array(z.record(z.string(), z.unknown())).default([]),
  gated_out: NlGatedOutSchema.default({ count: 0, items: [], note: null }),
  elapsed_ms: z.number().nonnegative().default(0),
  note: z.string().nullable().optional(),
})

export type NlExecuteResult = z.infer<typeof NlExecuteResultSchema>

export interface NlExecuteInput {
  query: string
  scope?: 'local_api' | 'akspot' | 'all'
  custom_codes?: string
}
