import { apiFetch } from './client'
import {
  EarningsHunterSchema,
  type EarningsHunter,
  type EarningsHunterParams,
} from './schemas/earningsHunter'

/**
 * 77 财报猎手读端点（parity D）。走统一 apiFetch（Bearer + 401 单飞刷新 + 信封解包），
 * Zod 严格解析后才交给 UI。
 */
export async function getEarningsHunter(
  params: EarningsHunterParams,
): Promise<EarningsHunter> {
  const sp = new URLSearchParams({ period: params.period })
  if (params.min_pct != null && Number.isFinite(params.min_pct)) {
    sp.set('min_pct', String(params.min_pct))
  }
  if (params.signals && params.signals.length > 0) {
    sp.set('signals', params.signals.join(','))
  }
  const data = await apiFetch<unknown>(`/v2/read/earnings-hunter?${sp.toString()}`)
  return EarningsHunterSchema.parse(data)
}
