import { z } from 'zod'

/**
 * 40/41/45 组合写端点契约（同源 modules.portfolio.PortfolioManager）。
 *
 * 诚实红线：
 *  - 写的是本地模拟/历史 CSV 账本，全站共享、非实盘、无用户隔离；
 *  - 卖出仅追加 trades，不回滚买入批次；失败由后端 422/404，前端原样抛错。
 */
export const PortfolioPositionInputSchema = z.object({
  ticker: z.string().regex(/^\d{6}$/, 'ticker 须为 6 位股票代码'),
  buy_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'buy_date 须为 YYYY-MM-DD'),
  buy_price: z.number().positive('buy_price 须为正数'),
  shares: z.number().int().positive('shares 须为正整数'),
  name: z.string().max(60).optional(),
  note: z.string().max(200).optional(),
})

export const PortfolioSellInputSchema = z.object({
  ticker: z.string().regex(/^\d{6}$/, 'ticker 须为 6 位股票代码'),
  sell_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'sell_date 须为 YYYY-MM-DD'),
  sell_price: z.number().positive('sell_price 须为正数'),
  sell_shares: z.number().int().positive('sell_shares 须为正整数'),
  name: z.string().max(60).optional(),
  note: z.string().max(200).optional(),
})

const PositionRecordSchema = z.object({
  ticker: z.string(),
  name: z.string().nullable().optional(),
  buy_date: z.string().nullable().optional(),
  buy_price: z.number().nullable().optional(),
  shares: z.number().nullable().optional(),
  cost: z.number().nullable().optional(),
  note: z.string().nullable().optional(),
})

const TradeRecordSchema = z.object({
  ticker: z.string(),
  name: z.string().nullable().optional(),
  sell_date: z.string().nullable().optional(),
  sell_price: z.number().nullable().optional(),
  sell_shares: z.number().nullable().optional(),
  proceeds: z.number().nullable().optional(),
  note: z.string().nullable().optional(),
})

const WriteResultSchema = z.object({
  note: z.string(),
})

export const PortfolioPositionAddedSchema = WriteResultSchema.extend({
  position: PositionRecordSchema,
})
export const PortfolioPositionDeletedSchema = WriteResultSchema.extend({
  removed: PositionRecordSchema,
})
export const PortfolioSellRecordedSchema = WriteResultSchema.extend({
  trade: TradeRecordSchema,
})

export type PortfolioPositionInput = z.infer<typeof PortfolioPositionInputSchema>
export type PortfolioSellInput = z.infer<typeof PortfolioSellInputSchema>
