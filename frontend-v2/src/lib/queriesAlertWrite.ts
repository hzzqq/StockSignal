import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useWriteMutation } from '@/lib/mutations'
import {
  listPriceAlerts,
  listMarketAlerts,
  getMarketAlertConfig,
  type MarketAlertsParams,
} from '@/api/alertWrite'
import {
  PriceAlertSchema,
  AlertConfigSchema,
  ScanResultSchema,
  type PriceAlert,
  type PriceAlertList,
  type MarketAlertList,
  type AlertConfig,
  type MarketAlertConfigGet,
  type ScanResult,
  type CreatePriceAlertInput,
} from '@/api/schemas/alertWrite'

/**
 * 价格预警 / 市场告警的读写 hooks（v1→v2 能力对齐批次）。
 *
 * - 读 queryKey 统一前缀 ['alert-write', ...]，与只读 queries.ts 的 ['read', ...] 分离。
 * - 写全部经统一工厂 useWriteMutation：mutationFn 固定走 apiMutate，成功后
 *   invalidateQueries 让相关读缓存失效并重新取数（服务端才是真理源），
 *   禁止乐观更新、禁止把失败洗成成功。
 */

const K_PRICE = ['alert-write', 'price-alerts'] as const
const K_MARKET = ['alert-write', 'market-alerts'] as const
const K_CONFIG = ['alert-write', 'market-config'] as const

/** queryKey 里的空参数用模块级常量，避免每次渲染新建对象导致 key 抖动。 */
const EMPTY_MARKET_PARAMS: MarketAlertsParams = {}

export function usePriceAlerts(): UseQueryResult<PriceAlertList> {
  return useQuery({ queryKey: K_PRICE, queryFn: listPriceAlerts, retry: false })
}

export function useMarketAlerts(params: MarketAlertsParams = EMPTY_MARKET_PARAMS): UseQueryResult<MarketAlertList> {
  return useQuery({
    queryKey: [...K_MARKET, params],
    queryFn: () => listMarketAlerts(params),
    retry: false,
  })
}

/** 配置读取仅管理员可用；enabled=false 时零请求（非管理员不显示配置区）。 */
export function useMarketAlertConfig(enabled = true): UseQueryResult<MarketAlertConfigGet> {
  return useQuery({
    queryKey: K_CONFIG,
    queryFn: getMarketAlertConfig,
    enabled,
    retry: false,
  })
}

export function useCreatePriceAlert() {
  return useWriteMutation<CreatePriceAlertInput, PriceAlert>({
    path: '/price-alerts',
    method: 'POST',
    body: (v) => v,
    schema: PriceAlertSchema,
    invalidateKeys: [K_PRICE],
  })
}

export function useTogglePriceAlert() {
  return useWriteMutation<{ id: number }, PriceAlert>({
    path: (v) => `/price-alerts/${v.id}/toggle`,
    method: 'PUT',
    schema: PriceAlertSchema,
    invalidateKeys: [K_PRICE],
  })
}

export function useDeletePriceAlert() {
  return useWriteMutation<{ id: number }, unknown>({
    path: (v) => `/price-alerts/${v.id}`,
    method: 'DELETE',
    schema: null,
    invalidateKeys: [K_PRICE],
  })
}

export function useMarkMarketAlertRead() {
  return useWriteMutation<{ id: number }, unknown>({
    path: (v) => `/market-alerts/${v.id}/read`,
    method: 'POST',
    schema: null,
    invalidateKeys: [K_MARKET],
  })
}

export function useMarkAllMarketAlertsRead() {
  return useWriteMutation<void, unknown>({
    path: '/market-alerts/read-all',
    method: 'POST',
    schema: null,
    invalidateKeys: [K_MARKET],
  })
}

export function useScanMarketAlerts() {
  return useWriteMutation<void, ScanResult>({
    path: '/market-alerts/scan',
    method: 'POST',
    schema: ScanResultSchema,
    invalidateKeys: [K_MARKET],
  })
}

export function useUpdateMarketAlertConfig() {
  return useWriteMutation<{ config: Record<string, unknown> }, AlertConfig>({
    path: '/market-alerts/config',
    method: 'POST',
    body: (v) => v.config,
    schema: AlertConfigSchema,
    invalidateKeys: [K_CONFIG],
  })
}
