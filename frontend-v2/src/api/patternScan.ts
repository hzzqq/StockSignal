import { apiMutate } from './write'
import { PatternScanSchema, type PatternScan } from './schemas/patternScan'

export interface PatternScanParams {
  codes: string[]
  window_days?: number
}

/** POST /api/v2/pattern-scan —— 纯函数形态识别，不联网取数（K线由后端读本地缓存）。 */
export function postPatternScan(params: PatternScanParams): Promise<PatternScan> {
  if (!Array.isArray(params.codes) || params.codes.length < 1 || params.codes.length > 50) {
    throw new Error('codes 须为 1–50 个股票代码')
  }
  return apiMutate<PatternScan>(
    '/v2/pattern-scan',
    'POST',
    params,
    PatternScanSchema,
  )
}

/** 供契约漂移 B 段探针复用（只读端点清单不含本 POST，显式导出）。 */
export function patternScanPath(): string {
  return '/api/v2/pattern-scan'
}
