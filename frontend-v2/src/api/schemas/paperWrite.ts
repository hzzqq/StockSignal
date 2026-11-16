import { z } from 'zod'

/**
 * parity C：模拟账本写契约（纯本地 JSON，绝不触真实券商）。
 * 与 GET /api/v2/read/paper-trades 读同一份 paper_<user>.json（用户取自 JWT），原子写。
 * 后端真契约见 backend/api/paper_write_routes.py：side 为中文「买」「卖」、qty 100 倍数。
 *
 * ⚠️ 这是模拟盘语义，与实盘 action=buy|sell / 券商通道无关，C 类红线不触碰。
 */
export const PaperTradeWriteInputSchema = z.object({
  code: z.string().regex(/^\d{6}$/, 'code 须为 6 位股票代码'),
  side: z.enum(['买', '卖']),
  price: z.number().positive(),
  qty: z.number().int().min(100).refine((v) => v % 100 === 0, 'qty 须为 100 的整数倍'),
  name: z.string().max(64).optional(),
})
export type PaperTradeWriteInput = z.infer<typeof PaperTradeWriteInputSchema>

export const PaperTradeRecordSchema = z
  .object({
    id: z.number().int(),
    time: z.string(),
    code: z.string(),
    name: z.string(),
    side: z.string(),
    price: z.number(),
    qty: z.number(),
    amount: z.number(),
  })
  .catchall(z.unknown())
export type PaperTradeRecord = z.infer<typeof PaperTradeRecordSchema>

export const PaperTradeDeleteResultSchema = z
  .object({
    deleted_id: z.number().int(),
    remaining: z.number().int().nonnegative(),
  })
  .catchall(z.unknown())
export type PaperTradeDeleteResult = z.infer<typeof PaperTradeDeleteResultSchema>
