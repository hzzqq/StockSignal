import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { getEarningsHunter } from '@/api/earningsHunter'
import type { EarningsHunter, EarningsHunterParams } from '@/api/schemas/earningsHunter'
import { useWriteMutation } from './mutations'
import { NlExecuteResultSchema, type NlExecuteInput, type NlExecuteResult } from '@/api/schemas/nlExecute'

const FIVE_MIN = 5 * 60 * 1000

/**
 * 77 财报猎手 · 业绩预告信号扫描（parity D）。
 * 后端 best-effort 取东财业绩预告（30 分钟缓存）；available=false 属业务降级非接口错误，
 * 由组件按 reason 原文透出。
 */
export function useEarningsHunter(
  params: EarningsHunterParams,
  enabled: boolean,
): UseQueryResult<EarningsHunter> {
  return useQuery({
    queryKey: ['read', 'earnings-hunter', params.period, params.min_pct ?? null, params.signals ?? null],
    queryFn: () => getEarningsHunter(params),
    enabled,
    staleTime: FIVE_MIN,
  })
}

/**
 * 81 自然语言选股 · 执行（parity D）。POST 走统一写层；无缓存失效（一次性执行结果）。
 * available=false 属业务降级（候选池取不到 / 全未理解），由 UI 按 reason 原文透出。
 */
export function useNlScreenExecute() {
  return useWriteMutation<NlExecuteInput, NlExecuteResult>({
    path: '/v2/nl-screen/execute',
    method: 'POST',
    body: (vars) => ({ query: vars.query, scope: vars.scope, custom_codes: vars.custom_codes }),
    schema: NlExecuteResultSchema,
    invalidateKeys: [],
  })
}
