import { useQuery, type UseQueryResult, type UseMutationResult } from '@tanstack/react-query'
import { useWriteMutation } from '@/lib/mutations'
import * as api from '@/api/userCollections'
import {
  AddItemResultSchema,
  BatchResultSchema,
  WatchlistBatchDeleteResultSchema,
  JunkBatchDeleteResultSchema,
  UserScoreSchema,
  type WatchlistItem,
  type JunkStockItem,
  type UserScore,
  type AddItemResult,
  type BatchResult,
  type WatchlistBatchDeleteResult,
  type JunkBatchDeleteResult,
  type WatchlistAddInput,
  type JunkStockAddInput,
  type WatchlistBatchAddInput,
  type WatchlistBatchDeleteInput,
  type JunkBatchDeleteInput,
  type UpsertUserScoreInput,
} from '@/api/schemas/userCollections'

/**
 * 用户三组写能力 · TanStack Query 层（单一真理源）。
 *
 * 读：useQuery，queryKey 统一前缀 ['user-collections', ...]。
 * 写：全部走统一 mutation 工厂 useWriteMutation（内部固定 apiMutate），
 *     禁止页面自己 useMutation + fetch；成功后 invalidateKeys 覆盖本组全部读 key，
 *     让三个列表与单条打分缓存一并失效重取（服务端才是真理源，不做乐观更新）。
 * 失败：不改缓存、不吞错，error 原样交给页面如实渲染。
 */

export const USER_COLLECTIONS_KEYS = {
  watchlist: ['user-collections', 'watchlist'] as const,
  junkStocks: ['user-collections', 'junk-stocks'] as const,
  userScores: ['user-collections', 'user-scores'] as const,
  /** 单条打分查询的前缀（实际 key 还会追加 code） */
  userScore: ['user-collections', 'user-score'] as const,
}

/** 本组全部读 key；每个写操作成功后统一失效。 */
const ALL_READ_KEYS: readonly (readonly unknown[])[] = [
  USER_COLLECTIONS_KEYS.watchlist,
  USER_COLLECTIONS_KEYS.junkStocks,
  USER_COLLECTIONS_KEYS.userScores,
  USER_COLLECTIONS_KEYS.userScore,
]

// ───────────────────────── 读 ─────────────────────────

export function useWatchlistQuery(): UseQueryResult<WatchlistItem[]> {
  return useQuery({
    queryKey: USER_COLLECTIONS_KEYS.watchlist,
    queryFn: api.getWatchlist,
  })
}

export function useJunkStocksQuery(): UseQueryResult<JunkStockItem[]> {
  return useQuery({
    queryKey: USER_COLLECTIONS_KEYS.junkStocks,
    queryFn: api.getJunkStocks,
  })
}

export function useUserScoresQuery(): UseQueryResult<UserScore[]> {
  return useQuery({
    queryKey: USER_COLLECTIONS_KEYS.userScores,
    queryFn: api.getUserScores,
  })
}

/** GET /api/user-scores/:code —— 单条或 null；code 为空时不发请求。 */
export function useUserScoreQuery(code: string): UseQueryResult<UserScore | null> {
  return useQuery({
    queryKey: [...USER_COLLECTIONS_KEYS.userScore, code],
    queryFn: () => api.getUserScore(code),
    enabled: code.length > 0,
  })
}

// ───────────────────────── 写 ─────────────────────────

export function useAddWatchlist(): UseMutationResult<AddItemResult | null, Error, WatchlistAddInput> {
  return useWriteMutation<WatchlistAddInput, AddItemResult | null>({
    path: '/watchlist',
    method: 'POST',
    body: (vars) => vars,
    schema: AddItemResultSchema.nullable(),
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useDeleteWatchlist(): UseMutationResult<unknown, Error, { id: number }> {
  return useWriteMutation<{ id: number }, unknown>({
    path: (vars) => `/watchlist/${vars.id}`,
    method: 'DELETE',
    schema: null,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useAddWatchlistBatch(): UseMutationResult<BatchResult, Error, WatchlistBatchAddInput> {
  return useWriteMutation<WatchlistBatchAddInput, BatchResult>({
    path: '/watchlist/batch',
    method: 'POST',
    body: (vars) => vars,
    schema: BatchResultSchema,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useDeleteWatchlistBatch(): UseMutationResult<
  WatchlistBatchDeleteResult,
  Error,
  WatchlistBatchDeleteInput
> {
  return useWriteMutation<WatchlistBatchDeleteInput, WatchlistBatchDeleteResult>({
    path: '/watchlist/batch',
    method: 'DELETE',
    body: (vars) => vars,
    schema: WatchlistBatchDeleteResultSchema,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useAddJunkStock(): UseMutationResult<AddItemResult | null, Error, JunkStockAddInput> {
  return useWriteMutation<JunkStockAddInput, AddItemResult | null>({
    path: '/junk-stocks',
    method: 'POST',
    body: (vars) => vars,
    schema: AddItemResultSchema.nullable(),
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useDeleteJunkStock(): UseMutationResult<unknown, Error, { id: number }> {
  return useWriteMutation<{ id: number }, unknown>({
    path: (vars) => `/junk-stocks/${vars.id}`,
    method: 'DELETE',
    schema: null,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useDeleteJunkStockBatch(): UseMutationResult<
  JunkBatchDeleteResult,
  Error,
  JunkBatchDeleteInput
> {
  return useWriteMutation<JunkBatchDeleteInput, JunkBatchDeleteResult>({
    path: '/junk-stocks/batch',
    method: 'DELETE',
    body: (vars) => vars,
    schema: JunkBatchDeleteResultSchema,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useUpsertUserScore(): UseMutationResult<UserScore, Error, UpsertUserScoreInput> {
  return useWriteMutation<UpsertUserScoreInput, UserScore>({
    path: '/user-scores',
    method: 'POST',
    body: (vars) => vars,
    schema: UserScoreSchema,
    invalidateKeys: ALL_READ_KEYS,
  })
}

export function useDeleteUserScore(): UseMutationResult<unknown, Error, { code: string }> {
  return useWriteMutation<{ code: string }, unknown>({
    path: (vars) => `/user-scores/${encodeURIComponent(vars.code)}`,
    method: 'DELETE',
    schema: null,
    invalidateKeys: ALL_READ_KEYS,
  })
}
