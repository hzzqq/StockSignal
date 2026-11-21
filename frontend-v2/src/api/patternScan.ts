import { apiFetch } from './client'
import { apiMutate } from './write'
import { TaskSubmitResultSchema, AiConsultTaskSchema, type AiConsultTask } from './schemas/chat'
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

/** 异步形态扫描任务提交端点路径（POST /api/v2/pattern-scan/tasks）。 */
export function patternScanTaskPath(): string {
  return '/api/v2/pattern-scan/tasks'
}

/**
 * POST /api/v2/pattern-scan/tasks —— 提交异步形态扫描任务，返回 task_id。
 * 轮询复用通用任务端点 GET /api/tasks/<id>；切页不打断（模块级 store 轮询）。
 */
export async function submitPatternScanTask(params: PatternScanParams): Promise<string> {
  if (!Array.isArray(params.codes) || params.codes.length < 1 || params.codes.length > 50) {
    throw new Error('codes 须为 1–50 个股票代码')
  }
  const parsed = await apiMutate(
    '/v2/pattern-scan/tasks',
    'POST',
    params,
    TaskSubmitResultSchema,
  )
  return parsed.task_id
}

/** GET /api/tasks/<id> —— 轮询 pattern_scan 任务态；success 时 result 形如 PatternScan。 */
export async function getPatternScanTask(taskId: string): Promise<AiConsultTask> {
  const data = await apiFetch<unknown>(`/tasks/${taskId}`)
  return AiConsultTaskSchema.parse(data)
}

/** pattern_scan 任务成功态 result 的校验（任务信封宽、result 严：缺失/畸形即抛错不伪造）。 */
export function parsePatternScanResult(raw: unknown): PatternScan {
  return PatternScanSchema.parse(raw)
}
