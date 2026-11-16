import { apiMutate } from './write'
import { NlExecuteResultSchema, type NlExecuteInput, type NlExecuteResult } from './schemas/nlExecute'

/**
 * 81 自然语言选股 · 执行（parity D）。POST 走统一写层 apiMutate（Bearer + 401 刷新 + 信封解包）。
 */
export function postNlScreenExecute(input: NlExecuteInput): Promise<NlExecuteResult> {
  return apiMutate('/v2/nl-screen/execute', 'POST', input, NlExecuteResultSchema)
}
