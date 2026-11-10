import { apiFetch } from './client'
import {
  SixDimSchema,
  FundamentalsSchema,
  FinancialsSchema,
  StockKlineSchema,
  StockIntradaySchema,
  IndexQuotesSchema,
  IndexKlineSchema,
  CompareOneSchema,
  ResearchDeepSchema,
  type SixDim,
  type Fundamentals,
  type Financials,
  type StockKline,
  type StockIntraday,
  type IndexQuotes,
  type IndexKline,
  type CompareOne,
  type ResearchDeep,
} from './schemas/stock'

export type ComparePeriod = 'daily' | 'weekly' | 'monthly'

/**
 * W4-A · 个股六维评分（GET /api/v2/read/six-dim?code=<6位>）。
 *
 * 6 位代码校验通过后才发请求；信封已由 apiFetch 解包（并对非 ok 状态抛 ApiError），
 * data 再经 SixDimSchema 严格校验，任何类型不符即抛错（不兜底、不补默认值）。
 */
export async function getSixDim(code: string): Promise<SixDim> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/six-dim?code=${encodeURIComponent(code)}`)
  return SixDimSchema.parse(data)
}

/**
 * W4-B · 个股域三端点（fundamentals / financials / stock-kline）。
 * 一律照 getSixDim：6 位代码校验 → apiFetch 解包信封 → 对应 Schema.parse（解析失败即抛错）。
 * report / period / limit 由后端取默认值（income / daily / 8|120），本轮不提供切换控件，
 * 故不额外透传，保持与 W4-A 一致的最小入参。
 */
export async function getFundamentals(code: string): Promise<Fundamentals> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/fundamentals?code=${encodeURIComponent(code)}`)
  return FundamentalsSchema.parse(data)
}

/** 财报三表口径：利润表 / 资产负债表 / 现金流量表。 */
export type FinancialReport = 'income' | 'balance' | 'cash'

export async function getFinancials(
  code: string,
  report: FinancialReport = 'income',
): Promise<Financials> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  if (report !== 'income' && report !== 'balance' && report !== 'cash') {
    throw new Error('report 须为 income / balance / cash')
  }
  const data = await apiFetch<unknown>(
    `/v2/read/financials?code=${encodeURIComponent(code)}&report=${encodeURIComponent(report)}`,
  )
  return FinancialsSchema.parse(data)
}

export async function getStockKline(code: string): Promise<StockKline> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/stock-kline?code=${encodeURIComponent(code)}`)
  return StockKlineSchema.parse(data)
}

/**
 * 个股分时（GET /api/v2/read/stock-intraday?code=<6位>）。
 * 形态与 getStockKline 一致：6 位代码校验 → apiFetch 解包信封 → Schema.parse（失败即抛）。
 * prev_close 由后端透传，取不到时为 null（前端不画基准线）。
 */
export async function getStockIntraday(code: string): Promise<StockIntraday> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/stock-intraday?code=${encodeURIComponent(code)}`)
  return StockIntradaySchema.parse(data)
}

/**
 * 主要指数报价（GET /api/v2/read/index-quotes）。
 * 外部卡片视角数据源；无需代码入参，逐指数独立降级（取不到 -> 该项全 null）。
 */
export async function getIndexQuotes(): Promise<IndexQuotes> {
  const data = await apiFetch<unknown>('/v2/read/index-quotes')
  return IndexQuotesSchema.parse(data)
}

/**
 * 指数日线 K 线（GET /api/v2/read/index-kline?code=<sh/sz+6位>）。
 * 形态与 getStockKline 一致：指数代码校验 → apiFetch 解包信封 → IndexKlineSchema.parse。
 * rows 英文列与 KLineChart 共用；取数失败进入 error 态，由页面诚实渲染。
 */
export async function getIndexKline(code: string): Promise<IndexKline> {
  if (!/^(sh|sz)\d{6}$/.test(code)) {
    throw new Error('指数代码须为 sh/sz + 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/index-kline?code=${encodeURIComponent(code)}`)
  return IndexKlineSchema.parse(data)
}

// ═══════════════════ W4-C · 多股对比 / 深度分析（镜像 getStockKline）══════════════════
// 一律：6 位代码校验 → apiFetch 解包信封 → 对应 Schema.parse（解析失败即抛错，不兜底）。

/** GET /api/v2/read/compare-one?code=<6位>&period=...：单股通用对比快照（透传）。 */
export async function getCompareOne(
  code: string,
  period: ComparePeriod = 'daily',
): Promise<CompareOne> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(
    `/v2/read/compare-one?code=${encodeURIComponent(code)}&period=${encodeURIComponent(period)}`,
  )
  return CompareOneSchema.parse(data)
}

/** GET /api/v2/read/research-deep?code=<6位>：单股 56 键深度分析（透传，含豁免键）。 */
export async function getResearchDeep(code: string): Promise<ResearchDeep> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/research-deep?code=${encodeURIComponent(code)}`)
  return ResearchDeepSchema.parse(data)
}
