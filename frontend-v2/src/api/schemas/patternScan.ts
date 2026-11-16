import { z } from 'zod'

/**
 * parity C：/api/v2/pattern-scan 的形态识别契约。
 * 后端 modules/pattern_scan.py 是纯函数（MACD / 均线 / KDJ 金叉死叉 + 顶底背离），
 * 单股失败 available=false + reason 原样透出，缺失绝不补零 / 伪造形态。
 */
export const PatternItemSchema = z
  .object({
    date: z.string(),
    name: z.string(),
    bias: z.string(),
    desc: z.string().optional(),
  })
  .catchall(z.unknown())
export type PatternItem = z.infer<typeof PatternItemSchema>

export const PatternScanResultSchema = z
  .object({
    code: z.string(),
    name: z.string().optional(),
    available: z.boolean(),
    patterns: z.array(PatternItemSchema),
    reason: z.string().nullable().optional(),
    n_bars: z.number().int().nonnegative(),
  })
  .catchall(z.unknown())
export type PatternScanResult = z.infer<typeof PatternScanResultSchema>

export const PatternScanSchema = z
  .object({
    results: z.array(PatternScanResultSchema),
    n_scanned: z.number().int().nonnegative(),
    available: z.boolean(),
    reason: z.string().nullable().optional(),
  })
  .catchall(z.unknown())
export type PatternScan = z.infer<typeof PatternScanSchema>
