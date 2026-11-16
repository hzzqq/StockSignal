import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'
import { useWriteMutation } from '@/lib/mutations'
import * as api from '@/api/paperWrite'
import * as scan from '@/api/patternScan'
import { PatternScanSchema, type PatternScan } from '@/api/schemas/patternScan'
import {
  PaperTradeRecordSchema,
  PaperTradeDeleteResultSchema,
  type PaperTradeWriteInput,
  type PaperTradeRecord,
  type PaperTradeDeleteResult,
} from '@/api/schemas/paperWrite'

/**
 * parity C 前端写/执行层：形态扫描（纯函数 POST）+ 模拟账本写（本地 JSON）。
 * 全部经统一 apiMutate / useWriteMutation，成功后失效重取，禁止乐观更新。
 * 实盘交易链路不在此列（C 类红线）。
 */
export const C_KEYS = {
  patternScan: ['c', 'pattern-scan'] as const,
  paperTrades: ['read', 'paper-trades'] as const,
}

export function usePatternScanMutation(): UseMutationResult<
  PatternScan,
  Error,
  scan.PatternScanParams
> {
  return useWriteMutation<scan.PatternScanParams, PatternScan>({
    path: '/v2/pattern-scan',
    method: 'POST',
    body: (v) => v,
    schema: PatternScanSchema,
    invalidateKeys: [C_KEYS.patternScan],
  })
}

export function useAddPaperTrade(): UseMutationResult<
  PaperTradeRecord,
  Error,
  PaperTradeWriteInput
> {
  return useWriteMutation<PaperTradeWriteInput, PaperTradeRecord>({
    path: '/v2/paper-trades',
    method: 'POST',
    body: (v) => v,
    schema: PaperTradeRecordSchema,
    invalidateKeys: [C_KEYS.paperTrades],
  })
}

export function useDeletePaperTrade(): UseMutationResult<
  PaperTradeDeleteResult,
  Error,
  number
> {
  return useWriteMutation<number, PaperTradeDeleteResult>({
    path: (id: number) => `/v2/paper-trades/${id}`,
    method: 'DELETE',
    schema: PaperTradeDeleteResultSchema,
    invalidateKeys: [C_KEYS.paperTrades],
  })
}

export function useResetPaperBook(): UseMutationResult<unknown, Error, void> {
  const qc = useQueryClient()
  return useMutation<unknown, Error, void>({
    mutationFn: () => api.resetPaperBook(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...C_KEYS.paperTrades] })
    },
  })
}
