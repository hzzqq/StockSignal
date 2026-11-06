import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import * as api from '@/api/read'
import type {
  DailySnapshot,
  P1Signal,
  DailyRecommendation,
  VirtualUsersSim,
  PaperTrade,
  ReviewNotes,
  WebApp,
  SnapshotDateList,
  BreadthPoint,
  LadderDay,
} from '@/api/schemas/read'

/**
 * 只读端点的 TanStack Query hooks（W1）。
 * 缓存分层（PLAN.md §7）：快照 5min / 历史归档 30min / 作品集静态 Infinity。
 * 取数失败（Zod 解析失败 / 网络错误 / 401）→ query 进入 error 态，由页面渲染错误态，不兜底。
 */

const FIVE_MIN = 5 * 60_000
const THIRTY_MIN = 30 * 60_000

export function useDailySnapshot(): UseQueryResult<DailySnapshot> {
  return useQuery({
    queryKey: ['read', 'daily-snapshot'],
    queryFn: api.getDailySnapshot,
    staleTime: FIVE_MIN,
  })
}

export function useSnapshotDates(): UseQueryResult<SnapshotDateList> {
  return useQuery({
    queryKey: ['read', 'snapshot-dates'],
    queryFn: api.getSnapshotDates,
    staleTime: THIRTY_MIN,
  })
}

export function useSnapshot(date: string | null): UseQueryResult<DailySnapshot> {
  return useQuery({
    queryKey: ['read', 'snapshot', date],
    queryFn: () => api.getSnapshotByDate(date as string),
    enabled: !!date,
    staleTime: THIRTY_MIN,
  })
}

export function useP1Signals(): UseQueryResult<Record<string, P1Signal>> {
  return useQuery({
    queryKey: ['read', 'p1-signals'],
    queryFn: api.getP1Signals,
    staleTime: THIRTY_MIN,
  })
}

export function useDailyRecommendation(): UseQueryResult<DailyRecommendation> {
  return useQuery({
    queryKey: ['read', 'daily-recommendation'],
    queryFn: api.getDailyRecommendation,
    staleTime: THIRTY_MIN,
  })
}

export function useVirtualUsersSim(): UseQueryResult<VirtualUsersSim> {
  return useQuery({
    queryKey: ['read', 'virtual-users-sim'],
    queryFn: api.getVirtualUsersSim,
    staleTime: THIRTY_MIN,
  })
}

export function usePaperTrades(user: string): UseQueryResult<PaperTrade> {
  return useQuery({
    queryKey: ['read', 'paper-trades', user],
    queryFn: () => api.getPaperTrades(user),
    staleTime: THIRTY_MIN,
  })
}

export function useReviewNotes(date: string): UseQueryResult<ReviewNotes> {
  return useQuery({
    queryKey: ['read', 'review-notes', date],
    queryFn: () => api.getReviewNotes(date),
    enabled: !!date,
    staleTime: THIRTY_MIN,
  })
}

export function useWebApps(): UseQueryResult<WebApp[]> {
  return useQuery({
    queryKey: ['read', 'webapps'],
    queryFn: api.getWebApps,
    staleTime: Infinity,
  })
}

export function useAlertRules(): UseQueryResult<Record<string, unknown>> {
  return useQuery({
    queryKey: ['read', 'alert-rules'],
    queryFn: api.getAlertRules,
    staleTime: THIRTY_MIN,
  })
}

export function useAlertLog(): UseQueryResult<string> {
  return useQuery({
    queryKey: ['read', 'alert-log'],
    queryFn: api.getAlertLog,
    staleTime: THIRTY_MIN,
  })
}

export function useBreadthTimeseries(): UseQueryResult<BreadthPoint[]> {
  return useQuery({
    queryKey: ['read', 'breadth-timeseries'],
    queryFn: api.getBreadthTimeseries,
    staleTime: THIRTY_MIN,
  })
}

export function useLadderDetail(): UseQueryResult<LadderDay[]> {
  return useQuery({
    queryKey: ['read', 'ladder-detail'],
    queryFn: api.getLadderDetail,
    staleTime: THIRTY_MIN,
  })
}
