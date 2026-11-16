import { z } from 'zod'

/**
 * GET /api/v2/read/temperature-backtest 的 v2 契约（parity B 批次）。
 *
 * ⚠️ available:false 时后端只返回 { available:false, reason }，其余字段全无。
 * 因此除 available 外所有字段都 `.optional()`；带宽内的数值字段按契约也是可选，
 * 绝不能用 `.default()` 把「缺失」洗成 0。catchall 允许后端新增字段。
 */

export const TemperatureBacktestDataSchema = z
  .object({
    rows: z.number().int(),
    start: z.string(),
    end: z.string(),
  })
  .catchall(z.unknown())
export type TemperatureBacktestData = z.infer<typeof TemperatureBacktestDataSchema>

export const TemperatureBacktestBaselineSchema = z
  .object({
    n: z.number().int(),
    next_mean_delta: z.number(),
    next_impr_rate: z.number(),
    d5_mean_delta: z.number(),
    d5_impr_rate: z.number(),
  })
  .catchall(z.unknown())
export type TemperatureBacktestBaseline = z.infer<typeof TemperatureBacktestBaselineSchema>

/** 单温度带；available:false 的带可能没有任何统计字段（只有 level/label/color/n/available）。 */
export const TemperatureBacktestBandSchema = z
  .object({
    level: z.number(),
    label: z.string(),
    color: z.string(),
    n: z.number().int(),
    available: z.boolean(),
    next_mean_delta: z.number().optional(),
    next_impr_rate: z.number().optional(),
    d5_mean_delta: z.number().optional(),
    d5_impr_rate: z.number().optional(),
    avg_next_red: z.number().optional(),
    avg_d5_red: z.number().optional(),
  })
  .catchall(z.unknown())
export type TemperatureBacktestBand = z.infer<typeof TemperatureBacktestBandSchema>

export const TemperatureBacktestSchema = z
  .object({
    available: z.boolean(),
    reason: z.string().optional(),
    data: TemperatureBacktestDataSchema.optional(),
    baseline: TemperatureBacktestBaselineSchema.optional(),
    bands: z.array(TemperatureBacktestBandSchema).optional(),
    note: z.string().optional(),
  })
  .catchall(z.unknown())
export type TemperatureBacktest = z.infer<typeof TemperatureBacktestSchema>
