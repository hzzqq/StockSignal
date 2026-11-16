import { z } from 'zod'
import { apiFetch } from './client'
import { apiMutate } from './write'
import {
  WatchlistItemSchema,
  JunkStockItemSchema,
  UserScoreSchema,
  BatchResultSchema,
  AddItemResultSchema,
  WatchlistBatchDeleteResultSchema,
  JunkBatchDeleteResultSchema,
  WatchlistAddInputSchema,
  JunkStockAddInputSchema,
  WatchlistBatchAddInputSchema,
  WatchlistBatchDeleteInputSchema,
  JunkBatchDeleteInputSchema,
  UpsertUserScoreInputSchema,
  type WatchlistItem,
  type JunkStockItem,
  type UserScore,
  type BatchResult,
  type AddItemResult,
  type WatchlistBatchDeleteResult,
  type JunkBatchDeleteResult,
  type WatchlistAddInput,
  type JunkStockAddInput,
  type WatchlistBatchAddInput,
  type WatchlistBatchDeleteInput,
  type JunkBatchDeleteInput,
  type UpsertUserScoreInput,
} from './schemas/userCollections'

/**
 * 用户三组写能力 API 客户端（对齐 backend/api/config_routes.py L119-295 与
 * backend/api/stock_tag_routes.py L21-187）。全部端点 @jwt_required、按当前用户隔离。
 *
 * 设计（与 api/admin.ts 同款）：
 *  - GET 用 apiFetch 取信封 data，再用专用 Zod schema.parse 严格校验；
 *  - 写请求一律走统一写层 apiMutate（Bearer + 401 单飞刷新 + 信封解包）；
 *  - 入参先由专用 input schema.parse 挡住非法值（stock_code 非空 / score 0–100 整数）；
 *  - 无响应体的端点（DELETE 单条）传 schema=null，显式「不解析」而非静默成功；
 *  - 路径按契约精确拼接，动态段用 encodeURIComponent 收窄，不整体编码。
 */

const WatchlistListSchema = z.array(WatchlistItemSchema)
const JunkStockListSchema = z.array(JunkStockItemSchema)
const UserScoreListSchema = z.array(UserScoreSchema)
const UserScoreSingleSchema = UserScoreSchema.nullable()
const AddItemNullableSchema = AddItemResultSchema.nullable()

// ───────────────────────── 自选股 ─────────────────────────

/** GET /api/watchlist */
export async function getWatchlist(): Promise<WatchlistItem[]> {
  const data = await apiFetch<unknown>('/watchlist')
  return WatchlistListSchema.parse(data)
}

/** POST /api/watchlist —— 已存在时 data=null、message="已在自选股中" */
export async function addWatchlistItem(input: WatchlistAddInput): Promise<AddItemResult | null> {
  const body = WatchlistAddInputSchema.parse(input)
  return apiMutate<AddItemResult | null>('/watchlist', 'POST', body, AddItemNullableSchema)
}

/** DELETE /api/watchlist/:id —— 仅 message，无 data */
export async function deleteWatchlistItem(id: number): Promise<unknown> {
  return apiMutate<unknown>(`/watchlist/${id}`, 'DELETE', undefined, null)
}

/** POST /api/watchlist/batch —— {added, skipped, failed} */
export async function addWatchlistBatch(input: WatchlistBatchAddInput): Promise<BatchResult> {
  const body = WatchlistBatchAddInputSchema.parse(input)
  return apiMutate<BatchResult>('/watchlist/batch', 'POST', body, BatchResultSchema)
}

/** DELETE /api/watchlist/batch —— {deleted, forbidden, not_found} */
export async function deleteWatchlistBatch(
  input: WatchlistBatchDeleteInput,
): Promise<WatchlistBatchDeleteResult> {
  const body = WatchlistBatchDeleteInputSchema.parse(input)
  return apiMutate<WatchlistBatchDeleteResult>(
    '/watchlist/batch',
    'DELETE',
    body,
    WatchlistBatchDeleteResultSchema,
  )
}

// ───────────────────────── 垃圾股 ─────────────────────────

/** GET /api/junk-stocks —— 列表形状与 watchlist 相同 */
export async function getJunkStocks(): Promise<JunkStockItem[]> {
  const data = await apiFetch<unknown>('/junk-stocks')
  return JunkStockListSchema.parse(data)
}

/** POST /api/junk-stocks —— 已存在时 data=null、message="已在垃圾股中" */
export async function addJunkStock(input: JunkStockAddInput): Promise<AddItemResult | null> {
  const body = JunkStockAddInputSchema.parse(input)
  return apiMutate<AddItemResult | null>('/junk-stocks', 'POST', body, AddItemNullableSchema)
}

/** DELETE /api/junk-stocks/:id —— 仅 message，无 data */
export async function deleteJunkStock(id: number): Promise<unknown> {
  return apiMutate<unknown>(`/junk-stocks/${id}`, 'DELETE', undefined, null)
}

/** DELETE /api/junk-stocks/batch —— {deleted: number[]} */
export async function deleteJunkStockBatch(
  input: JunkBatchDeleteInput,
): Promise<JunkBatchDeleteResult> {
  const body = JunkBatchDeleteInputSchema.parse(input)
  return apiMutate<JunkBatchDeleteResult>(
    '/junk-stocks/batch',
    'DELETE',
    body,
    JunkBatchDeleteResultSchema,
  )
}

// ───────────────────────── 用户自定义打分 ─────────────────────────

/** GET /api/user-scores */
export async function getUserScores(): Promise<UserScore[]> {
  const data = await apiFetch<unknown>('/user-scores')
  return UserScoreListSchema.parse(data)
}

/** GET /api/user-scores/:code —— 单条或 null */
export async function getUserScore(code: string): Promise<UserScore | null> {
  const data = await apiFetch<unknown>(`/user-scores/${encodeURIComponent(code)}`)
  return UserScoreSingleSchema.parse(data)
}

/** POST /api/user-scores —— upsert，score 越界由后端返回 400 */
export async function upsertUserScore(input: UpsertUserScoreInput): Promise<UserScore> {
  const body = UpsertUserScoreInputSchema.parse(input)
  return apiMutate<UserScore>('/user-scores', 'POST', body, UserScoreSchema)
}

/** DELETE /api/user-scores/:code —— 仅 message，无 data */
export async function deleteUserScore(code: string): Promise<unknown> {
  return apiMutate<unknown>(`/user-scores/${encodeURIComponent(code)}`, 'DELETE', undefined, null)
}
