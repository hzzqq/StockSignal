import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import * as api from '@/api/read'
import { getSixDim } from '@/api/stock'
import type { SixDim } from '@/api/schemas/stock'
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
  BreadthHistoryPoint,
  EventPool,
  PredictionLogRow,
  P1SyncStatus,
  BacktestRuns,
  DataRefreshState,
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

export function useBreadthHistory(): UseQueryResult<BreadthHistoryPoint[]> {
  return useQuery({
    queryKey: ['read', 'breadth-history'],
    queryFn: api.getBreadthHistory,
    staleTime: THIRTY_MIN,
  })
}

// ───────── W3 后续簇（5 个真实数据源）─────────
// 事件池/预测日志/回测记录属「日更或更低频」，30min；同步状态与刷新状态属运维态，
// 变化比行情慢但需比归档勤，统一 5min（不设 refetchOnWindowFocus，由全局默认关闭）。

export function useEventPool(): UseQueryResult<EventPool> {
  return useQuery({
    queryKey: ['read', 'event-pool'],
    queryFn: api.getEventPool,
    staleTime: THIRTY_MIN,
  })
}

export function usePredictionLog(): UseQueryResult<PredictionLogRow[]> {
  return useQuery({
    queryKey: ['read', 'prediction-log'],
    queryFn: api.getPredictionLog,
    staleTime: THIRTY_MIN,
  })
}

export function useP1SyncStatus(): UseQueryResult<P1SyncStatus> {
  return useQuery({
    queryKey: ['read', 'p1-sync-status'],
    queryFn: api.getP1SyncStatus,
    staleTime: FIVE_MIN,
  })
}

export function useBacktestRuns(): UseQueryResult<BacktestRuns> {
  return useQuery({
    queryKey: ['read', 'backtest-runs'],
    queryFn: api.getBacktestRuns,
    staleTime: THIRTY_MIN,
  })
}

export function useDataRefreshState(): UseQueryResult<DataRefreshState> {
  return useQuery({
    queryKey: ['read', 'data-refresh-state'],
    queryFn: api.getDataRefreshState,
    staleTime: FIVE_MIN,
  })
}

// ───────── W4-A · 个股六维评分（按 6 位代码查询，5min 缓存）─────────
// 非法代码 enabled=false，不发起请求；取数失败进入 error 态，由页面诚实渲染。
export function useSixDim(code: string): UseQueryResult<SixDim> {
  return useQuery({
    queryKey: ['read', 'six-dim', code],
    queryFn: () => getSixDim(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: FIVE_MIN,
  })
}
