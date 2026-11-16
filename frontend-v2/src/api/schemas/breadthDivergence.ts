import { z } from 'zod'

/**
 * GET /api/v2/read/breadth-divergence 的 v2 契约（parity B 批次）。
 *
 * 诚实原则：快照缺失的比率/计数一律 `.nullable()`，不允许 `.default()` / `?? 0` 补零；
 * 顶层与嵌套对象用 `.catchall(z.unknown())` 允许后端新增字段（与既有 read schema 同风格）。
 */

/** 分化事件行 / 当前观测共有的字段；比率与计数都可能为 null（快照缺该字段）。 */
export const BreadthDivergenceObservationSchema = z
  .object({
    date: z.string(),
    red_ratio: z.number().nullable(),
    limit_down: z.number().nullable(),
    limit_down_ratio: z.number().nullable(),
    zt_prev_ret: z.number().nullable(),
  })
  .catchall(z.unknown())
export type BreadthDivergenceObservation = z.infer<typeof BreadthDivergenceObservationSchema>

/** 当前状态：在观测行基础上多一个 is_divergent 判定（非 null，布尔）。 */
export const BreadthDivergenceCurrentSchema = z
  .object({
    date: z.string(),
    red_ratio: z.number().nullable(),
    limit_down: z.number().nullable(),
    limit_down_ratio: z.number().nullable(),
    is_divergent: z.boolean(),
  })
  .catchall(z.unknown())
export type BreadthDivergenceCurrent = z.infer<typeof BreadthDivergenceCurrentSchema>

/** 年×月日历热力图；z 单元格可能为 null（缺失月份 / 无数据），latest_year 可能为 null。 */
export const BreadthDivergenceCalendarSchema = z
  .object({
    available: z.boolean(),
    years: z.array(z.number()),
    months: z.array(z.number()),
    z: z.array(z.array(z.number().nullable())),
    latest_year: z.number().nullable(),
  })
  .catchall(z.unknown())
export type BreadthDivergenceCalendar = z.infer<typeof BreadthDivergenceCalendarSchema>

/** 分化主体段；ld_p90 与 current 可能为 null（样本不足 / 当前非事件日）。 */
export const BreadthDivergenceBlockSchema = z
  .object({
    available: z.boolean(),
    threshold_red: z.number(),
    ld_p90: z.number().nullable(),
    episodes: z.array(BreadthDivergenceObservationSchema),
    current: BreadthDivergenceCurrentSchema.nullable(),
    n_episodes: z.number().int(),
  })
  .catchall(z.unknown())
export type BreadthDivergenceBlock = z.infer<typeof BreadthDivergenceBlockSchema>

/** 时序段；两条序列的元素都可能为 null。 */
export const BreadthDivergenceTrendSchema = z
  .object({
    available: z.boolean(),
    dates: z.array(z.string()),
    red_ratio: z.array(z.number().nullable()),
    limit_down: z.array(z.number().nullable()),
  })
  .catchall(z.unknown())
export type BreadthDivergenceTrend = z.infer<typeof BreadthDivergenceTrendSchema>

export const BreadthDivergenceSchema = z
  .object({
    available: z.boolean(),
    calendar: BreadthDivergenceCalendarSchema,
    divergence: BreadthDivergenceBlockSchema,
    trend: BreadthDivergenceTrendSchema,
  })
  .catchall(z.unknown())
export type BreadthDivergence = z.infer<typeof BreadthDivergenceSchema>
