import { z } from 'zod'

/**
 * 77 财报猎手 · 业绩预告信号扫描（parity D）。
 * 后端 GET /api/v2/read/earnings-hunter 封装 modules.financial_hunter.scan
 * + modules.fundflow.get_earnings_forecast（东财业绩预告，best-effort，30 分钟缓存）。
 *
 * 诚实红线：available=false 时 rows 为空数组且 reason 原文透出（未到披露期 / 接口异常），
 * 绝不伪造预告行、绝不补 0；NaN 已由后端转为 null。
 */
export const EARNINGS_PERIODS = [
  '20260630',
  '20260331',
  '20251231',
  '20250930',
  '20250630',
] as const

export type EarningsPeriod = (typeof EARNINGS_PERIODS)[number]

export const EARNINGS_PERIOD_LABELS: Record<EarningsPeriod, string> = {
  '20260630': '2026 中报',
  '20260331': '2026 一季报',
  '20251231': '2025 年报',
  '20250930': '2025 三季报',
  '20250630': '2025 中报',
}

/** v1 77 页同款五档信号级别（modules.financial_hunter.SIGNAL_ORDER）。 */
export const EARNINGS_SIGNAL_ORDER = ['利好', '偏多', '中性', '偏空', '利空'] as const

export type EarningsSignal = (typeof EARNINGS_SIGNAL_ORDER)[number]

/** 预告行：列名来自东财原始响应（中文动态列），值已 null 安全化。 */
export const EarningsHunterRowSchema = z.record(z.string(), z.unknown())

export const EarningsHunterSchema = z.object({
  available: z.boolean(),
  rows: z.array(EarningsHunterRowSchema).default([]),
  n_total: z.number().int().nonnegative().nullable().default(null),
  n_scanned: z.number().int().nonnegative().nullable().default(null),
  signal_counts: z.record(z.string(), z.number().int().nonnegative()).default({}),
  reason: z.string().nullable().default(null),
})

export type EarningsHunterRow = z.infer<typeof EarningsHunterRowSchema>
export type EarningsHunter = z.infer<typeof EarningsHunterSchema>

export interface EarningsHunterParams {
  period: EarningsPeriod
  min_pct?: number
  signals?: EarningsSignal[]
}
