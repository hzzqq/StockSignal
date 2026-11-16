import { z } from 'zod'

/**
 * 用户三组写能力契约（对齐 backend/api/config_routes.py L119-295、
 * backend/api/stock_tag_routes.py L21-187，及 backend/models.py 各 to_dict）。
 *
 * 严格 .object()：字段逐个声明，缺失 / 类型不符即抛错（不兜底、不补零）；
 * 可空字段一律显式 .nullable()，避免用 default 把「缺失」洗成 0 / 空串。
 * 与管理端 schemas/admin.ts 同款：响应 data 由专用 schema.parse 严格校验。
 */

/** 单个自选股列表项：GET /api/watchlist 数组元素 */
export const WatchlistItemSchema = z.object({
  id: z.number().int(),
  stock_code: z.string(),
  stock_name: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
})
export type WatchlistItem = z.infer<typeof WatchlistItemSchema>

/** 单个垃圾股列表项：GET /api/junk-stocks 数组元素（与 watchlist 同形状） */
export const JunkStockItemSchema = z.object({
  id: z.number().int(),
  stock_code: z.string(),
  stock_name: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
})
export type JunkStockItem = z.infer<typeof JunkStockItemSchema>

/** 单条打分：UserStockScore.to_dict() */
export const UserScoreSchema = z.object({
  id: z.number().int(),
  user_id: z.number().int(),
  stock_code: z.string(),
  stock_name: z.string(),
  score: z.number().int().min(0).max(100),
  updated_at: z.string(),
})
export type UserScore = z.infer<typeof UserScoreSchema>

/** POST /api/watchlist/batch 的 data：{added, skipped, failed} */
export const BatchResultSchema = z.object({
  added: z.array(z.string()),
  skipped: z.array(z.string()),
  failed: z.array(z.object({ code: z.string(), reason: z.string() })),
})
export type BatchResult = z.infer<typeof BatchResultSchema>

/** POST /api/watchlist | POST /api/junk-stocks 的 data（已存在时后端返回 data=null） */
export const AddItemResultSchema = z.object({
  id: z.number().int(),
  stock_code: z.string(),
})
export type AddItemResult = z.infer<typeof AddItemResultSchema>

/** DELETE /api/watchlist/batch 的 data：{deleted, forbidden, not_found} */
export const WatchlistBatchDeleteResultSchema = z.object({
  deleted: z.array(z.string()),
  forbidden: z.array(z.object({ code: z.string(), reason: z.string() })),
  not_found: z.array(z.string()),
})
export type WatchlistBatchDeleteResult = z.infer<typeof WatchlistBatchDeleteResultSchema>

/** DELETE /api/junk-stocks/batch 的 data：{deleted: number[]} */
export const JunkBatchDeleteResultSchema = z.object({
  deleted: z.array(z.number().int()),
})
export type JunkBatchDeleteResult = z.infer<typeof JunkBatchDeleteResultSchema>

// ───────────────────────── 输入 schema（带校验）─────────────────────────
// 校验口径与后端一致：stock_code 非空、score 为 0–100 整数。
// 后端才是真理源；这些 schema 在 api/userCollections.ts 写函数里 parse，
// 让任何直接调用方在发出请求前就挡住非法入参（不静默接受）。

export const WatchlistAddInputSchema = z.object({
  stock_code: z.string().trim().min(1, '股票代码不能为空'),
  note: z.string().optional(),
})
export type WatchlistAddInput = z.infer<typeof WatchlistAddInputSchema>

export const JunkStockAddInputSchema = z.object({
  stock_code: z.string().trim().min(1, '股票代码不能为空'),
  note: z.string().optional(),
})
export type JunkStockAddInput = z.infer<typeof JunkStockAddInputSchema>

export const WatchlistBatchAddInputSchema = z.object({
  codes: z.array(z.string().trim().min(1)).min(1, 'codes 不能为空且须为数组'),
  note: z.string().optional(),
})
export type WatchlistBatchAddInput = z.infer<typeof WatchlistBatchAddInputSchema>

export const WatchlistBatchDeleteInputSchema = z
  .object({
    ids: z.array(z.number().int()).optional(),
    codes: z.array(z.string()).optional(),
  })
  .refine(
    (d) => (d.ids != null && d.ids.length > 0) || (d.codes != null && d.codes.length > 0),
    'ids 或 codes 至少提供一个数组',
  )
export type WatchlistBatchDeleteInput = z.infer<typeof WatchlistBatchDeleteInputSchema>

export const JunkBatchDeleteInputSchema = z.object({
  ids: z.array(z.number().int()).min(1, 'ids 不能为空且须为数组'),
})
export type JunkBatchDeleteInput = z.infer<typeof JunkBatchDeleteInputSchema>

export const UpsertUserScoreInputSchema = z.object({
  stock_code: z.string().trim().min(1, '股票代码不能为空'),
  stock_name: z.string().optional(),
  score: z.number().int().min(0, '分数须在 0–100 之间').max(100, '分数须在 0–100 之间'),
})
export type UpsertUserScoreInput = z.infer<typeof UpsertUserScoreInputSchema>
