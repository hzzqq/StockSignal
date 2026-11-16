import { apiMutate } from './write'
import {
  PaperTradeWriteInputSchema,
  PaperTradeRecordSchema,
  PaperTradeDeleteResultSchema,
  type PaperTradeWriteInput,
  type PaperTradeRecord,
  type PaperTradeDeleteResult,
} from './schemas/paperWrite'

/** POST /api/v2/paper-trades —— 记一笔模拟成交（JWT 用户隔离，纯本地账本）。 */
export function postPaperTrade(input: PaperTradeWriteInput): Promise<PaperTradeRecord> {
  const body = PaperTradeWriteInputSchema.parse(input)
  return apiMutate<PaperTradeRecord>(
    '/v2/paper-trades',
    'POST',
    body,
    PaperTradeRecordSchema,
  )
}

/** DELETE /api/v2/paper-trades/<id> —— 删除一条模拟成交记录（不回滚现金/持仓）。 */
export function deletePaperTrade(id: number): Promise<PaperTradeDeleteResult> {
  return apiMutate<PaperTradeDeleteResult>(
    `/v2/paper-trades/${id}`,
    'DELETE',
    undefined,
    PaperTradeDeleteResultSchema,
  )
}

/** POST /api/v2/paper-trades/reset —— 重置当前用户模拟账本。 */
export function resetPaperBook(): Promise<unknown> {
  return apiMutate<unknown>('/v2/paper-trades/reset', 'POST', undefined, null)
}
