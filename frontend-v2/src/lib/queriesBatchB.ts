import { useQuery, useMutation, type UseQueryResult, type UseMutationResult } from '@tanstack/react-query'
import { useWriteMutation } from '@/lib/mutations'
import * as api from '@/api/batchB'
import type { BreadthDivergenceParams } from '@/api/batchB'
import type { BreadthDivergence } from '@/api/schemas/breadthDivergence'
import type { TemperatureBacktest } from '@/api/schemas/temperatureBacktest'
import {
  UserDashboardDataSchema,
  ReviewNotesDataSchema,
  type ReviewNotesWrite,
  type UserDashboardData,
  type ReviewNotesData,
  type ReviewImageUploadData,
} from '@/api/schemas/batchBWrite'

/**
 * parity B 批次 TanStack Query 层。
 * 读：useQuery，queryKey 前缀统一 ['batch-b', ...]。
 * 写：全部走统一 mutation 工厂 useWriteMutation（内部固定 apiMutate），禁止页面自己 fetch；
 *     onSuccess 只 invalidate 对应读 key（含既有 ['read', ...] 读 key），不做乐观更新；
 *     失败不改缓存、不吞错。
 */

export const BATCH_B_KEYS = {
  breadthDivergence: ['batch-b', 'breadth-divergence'] as const,
  temperatureBacktest: ['batch-b', 'temperature-backtest'] as const,
  userDashboard: ['batch-b', 'user-dashboard'] as const,
  reviewNotes: ['batch-b', 'review-notes'] as const,
}

/** 既有 read 读 key（写入后一并失效，让已有页面重取真实值）。 */
const LEGACY_DASHBOARD_READ_KEY = ['read', 'user-dashboard'] as const
const LEGACY_REVIEW_NOTES_READ_KEY = ['read', 'review-notes'] as const

// ───────────────────────── 读 ─────────────────────────

export function useBreadthDivergence(
  params?: BreadthDivergenceParams,
): UseQueryResult<BreadthDivergence> {
  return useQuery({
    queryKey: params ? [...BATCH_B_KEYS.breadthDivergence, params] : BATCH_B_KEYS.breadthDivergence,
    queryFn: () => api.getBreadthDivergence(params),
  })
}

export function useTemperatureBacktest(
  params?: { window_days?: number },
): UseQueryResult<TemperatureBacktest> {
  const windowDays = params?.window_days
  return useQuery({
    queryKey:
      windowDays === undefined
        ? BATCH_B_KEYS.temperatureBacktest
        : [...BATCH_B_KEYS.temperatureBacktest, windowDays],
    queryFn: () => api.getTemperatureBacktest(params),
  })
}

// ───────────────────────── 写 ─────────────────────────

/**
 * 看板偏好保存：页面传 string[]（组件 id 顺序即展示顺序），本层包成契约的
 * { widgets: string[] } 请求体；响应由 UserDashboardDataSchema 严格解包。
 */
export function useUpdateUserDashboard(): UseMutationResult<
  UserDashboardData,
  Error,
  string[]
> {
  return useWriteMutation<string[], UserDashboardData>({
    path: '/v2/read/user-dashboard',
    method: 'PUT',
    body: (vars) => ({ widgets: vars }),
    schema: UserDashboardDataSchema,
    invalidateKeys: [BATCH_B_KEYS.userDashboard, LEGACY_DASHBOARD_READ_KEY],
  })
}

/** 复盘笔记保存：页面直接传 { date, content }。 */
export function useSaveReviewNotes(): UseMutationResult<
  ReviewNotesData,
  Error,
  ReviewNotesWrite
> {
  return useWriteMutation<ReviewNotesWrite, ReviewNotesData>({
    path: '/v2/read/review-notes',
    method: 'PUT',
    body: (vars) => vars,
    schema: ReviewNotesDataSchema,
    invalidateKeys: [BATCH_B_KEYS.reviewNotes, LEGACY_REVIEW_NOTES_READ_KEY],
  })
}

/**
 * 复盘图片上传（POST multipart /api/v2/read/review-images，51 晨报 parity）。
 *
 * 不走 useWriteMutation：该工厂经 apiMutate 发请求，会把 body JSON.stringify 并强制
 * Content-Type: application/json，而 multipart 必须原样传 FormData（见 apiMutateForm 注释），
 * 故这里直接用 useMutation 调专用 api.uploadReviewImage。
 * 上传不产生任何读端点可感知的状态变化（图片无列表读接口，链接由笔记文本承载），
 * 故无 invalidateKeys；失败原样抛 Error，由页面内联展示（与保存笔记的错误呈现惯例一致）。
 */
export function useUploadReviewImage(): UseMutationResult<
  ReviewImageUploadData,
  Error,
  { file: File; date: string }
> {
  return useMutation<ReviewImageUploadData, Error, { file: File; date: string }>({
    mutationFn: ({ file, date }) => api.uploadReviewImage(file, date),
  })
}
