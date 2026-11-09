import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import * as api from '@/api/read'
import type { FactorAnalysisParams, BacktestParams, MarketPanoramaParams, PortfolioParams } from '@/api/read'
import { getSixDim, getFundamentals, getFinancials, getStockKline, getStockIntraday, getIndexQuotes, getIndexKline } from '@/api/stock'
import { getDiagnostics } from '@/api/diagnostics'
import type { SixDim, Fundamentals, Financials, StockKline, StockIntraday, IndexQuotes, IndexKline } from '@/api/schemas/stock'
import type { Diagnostics } from '@/api/schemas/diagnostics'
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
  FactorAnalysis,
  Backtest,
  MarketPanorama,
  Portfolio,
  FundFlow,
  TradingAccount,
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

// ───────── 因子分析（factor-analysis / 71 页 V2 化）─────────
// 逐标的实时取数，参数变化即重新取；有效标的<3 时后端返回 status=error → 进入 error 态。
export function useFactorAnalysis(params: FactorAnalysisParams): UseQueryResult<FactorAnalysis> {
  return useQuery({
    queryKey: ['read', 'factor-analysis', params],
    queryFn: () => api.getFactorAnalysis(params),
    staleTime: THIRTY_MIN,
  })
}

export function useBacktest(params: BacktestParams): UseQueryResult<Backtest> {
  return useQuery({
    queryKey: ['read', 'backtest', params],
    queryFn: () => api.getBacktest(params),
    staleTime: THIRTY_MIN,
  })
}

export function useMarketPanorama(params: MarketPanoramaParams = {}): UseQueryResult<MarketPanorama> {
  return useQuery({
    queryKey: ['read', 'market-panorama', params],
    queryFn: () => api.getMarketPanorama(params),
    staleTime: THIRTY_MIN,
  })
}

export function usePortfolio(params: PortfolioParams = {}): UseQueryResult<Portfolio> {
  return useQuery({
    queryKey: ['read', 'portfolio', params],
    queryFn: () => api.getPortfolio(params),
    staleTime: THIRTY_MIN,
  })
}

// ───────── 资金流向（fund-flow / 35 页 V2 化）─────────
// 四块各自独立 available；离线/接口受限时该块诚实降级，页面如实标注、不补零。
export function useFundFlow(): UseQueryResult<FundFlow> {
  return useQuery({
    queryKey: ['read', 'fund-flow'],
    queryFn: api.getFundFlow,
    staleTime: THIRTY_MIN,
  })
}

/** 实盘交易只读概览（43 页 V2 化）：账户 / 持仓 / 订单流水，聚合本地模拟账本。 */
export function useTradingAccount(): UseQueryResult<TradingAccount> {
  return useQuery({
    queryKey: ['read', 'trading-account'],
    queryFn: api.getTradingAccount,
    staleTime: THIRTY_MIN,
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

// ───────── W4-B · 个股域三端点（按 6 位代码查询，5min 缓存）─────────
// 非法代码 enabled=false，不发起请求；取数失败进入 error 态，由页面诚实渲染。
export function useFundamentals(code: string): UseQueryResult<Fundamentals> {
  return useQuery({
    queryKey: ['read', 'fundamentals', code],
    queryFn: () => getFundamentals(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: FIVE_MIN,
  })
}

export function useFinancials(code: string): UseQueryResult<Financials> {
  return useQuery({
    queryKey: ['read', 'financials', code],
    queryFn: () => getFinancials(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: FIVE_MIN,
  })
}

export function useStockKline(code: string): UseQueryResult<StockKline> {
  return useQuery({
    queryKey: ['read', 'stock-kline', code],
    queryFn: () => getStockKline(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: FIVE_MIN,
  })
}

// ───────── 个股分时（staleTime 60s：分时数据时效性高，快过 K 线）─────────
// 非法代码 enabled=false，不发起请求；取数失败进入 error 态，由页面诚实渲染。
export function useStockIntraday(code: string): UseQueryResult<StockIntraday> {
  return useQuery({
    queryKey: ['read', 'stock-intraday', code],
    queryFn: () => getStockIntraday(code),
    enabled: /^\d{6}$/.test(code),
    staleTime: 60 * 1000,
  })
}

// ───────── 主要指数报价（staleTime 5min：指数日级，变化慢）─────────
export function useIndexQuotes(): UseQueryResult<IndexQuotes> {
  return useQuery({
    queryKey: ['read', 'index-quotes'],
    queryFn: () => getIndexQuotes(),
    staleTime: FIVE_MIN,
  })
}

// ───────── 指数日线 K 线（staleTime 5min：日级，变化慢）─────────
// 非法代码 enabled=false，不发起请求；取数失败进入 error 态，由页面诚实渲染。
export function useIndexKline(code: string): UseQueryResult<IndexKline> {
  return useQuery({
    queryKey: ['read', 'index-kline', code],
    queryFn: () => getIndexKline(code),
    enabled: /^(sh|sz)\d{6}$/.test(code),
    staleTime: FIVE_MIN,
  })
}

// ───────── 数据源 / 接口检测（staleTime 0：检测是即时动作，不缓存旧结论）─────────
// probe 进 queryKey：默认零网络；点「真实网络探测」时才切到 probe=true 重新取一次。
// nonce 让「重新探测」每次点击都换 queryKey —— 旧实现只 setWantProbe(true)，
// 第二次点击 React bail out、queryKey 不变，按钮是彻底 no-op。
export function useDiagnostics(probe = false, nonce = 0): UseQueryResult<Diagnostics> {
  return useQuery({
    queryKey: ['read', 'diagnostics', probe, nonce],
    queryFn: () => getDiagnostics(probe),
    staleTime: 0,
    retry: false,
  })
}
