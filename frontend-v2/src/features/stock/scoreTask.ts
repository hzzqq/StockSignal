import { create } from 'zustand'
import { z } from 'zod'
import { apiFetch } from '@/api/client'
import { apiMutate } from '@/api/write'

/**
 * 五维综合评分（旧版 analysis_engine 异步任务）的前端任务态模块。
 *
 * 契约（backend/api/task_routes.py + backend/tasks/worker.py，已读源确认）：
 *  - 提交：POST /api/tasks  body {type:'analysis', payload:{ticker:code}}，
 *    信封 data = {task_id, status:'pending'}；task_type 白名单含 'analysis'。
 *  - 轮询：GET /api/tasks/<task_id>，data = Task.to_dict()：
 *    {task_id, task_type, payload, created_at, updated_at, status, progress,
 *     stage, logs, result, error}；status ∈ pending/running/success/error/cancelled。
 *  - 结果：worker._handle_analysis → modules.analysis_engine.run_analysis(...) 的
 *    result dict（字段全集见 analysis_engine.py:502-558）；前端只取评分键
 *    composite/verdict/tech_score/news_score/macro_score/vol_score/sector_score，
 *    其余字段（含 df 等大对象）由 Zod 剥离，逐键 optional + nullable（宽松解析，
 *    缺键 = 后端没给，如实显示缺失，绝不补 0 / 编造 verdict）。
 *
 * 生命周期红线：轮询是**模块级 async 循环**，不挂在组件生命周期上——
 * 用户切页不打断，同会话切回来结果还在（zustand store 模块级单例）；
 * 刷新页面后内存态清空属可接受（结果可在服务端 task 缓存内重查，不造假分）。
 */

// ───────────── 轮询节奏（默认 1.5s / 上限 60s；测试可用 setPollTiming 加速）─────────────
let POLL_INTERVAL_MS = 1500
let POLL_TIMEOUT_MS = 60_000

/** 仅测试用：调整轮询间隔与总时长上限。生产代码不得调用。 */
export function setPollTiming(intervalMs: number, timeoutMs: number): void {
  POLL_INTERVAL_MS = intervalMs
  POLL_TIMEOUT_MS = timeoutMs
}

// ───────────── 后端响应 Zod（宽松：只取所需键，其余剥离）─────────────

/** POST /api/tasks 的 data：{task_id, status:'pending'}。 */
const TaskSubmitResultSchema = z.object({
  task_id: z.string(),
  status: z.string().optional(),
})

/** 轮询单条 log（worker Task.logs 元素：{stage, message, ts}）。 */
const TaskLogSchema = z.object({
  stage: z.string().optional(),
  message: z.string().optional(),
})

/** GET /api/tasks/<id> 的 data（Task.to_dict 全集，按需取键）。 */
const TaskStatusSchema = z.object({
  status: z.string(),
  progress: z.number().optional(),
  stage: z.string().optional(),
  logs: z.array(TaskLogSchema).optional(),
  result: z.unknown().optional(),
  error: z.string().nullable().optional(),
})

/**
 * analysis 任务 result 中前端消费的评分键（run_analysis result 全集的子集，
 * 逐键 optional + nullable：后端某项算不出会缺键或为 null，前端如实缺失）。
 */
export const CompositeResultSchema = z.object({
  ticker: z.string().optional(),
  display_name: z.string().nullable().optional(),
  composite: z.number().nullable().optional(),
  verdict: z.string().nullable().optional(),
  tech_score: z.number().nullable().optional(),
  news_score: z.number().nullable().optional(),
  macro_score: z.number().nullable().optional(),
  vol_score: z.number().nullable().optional(),
  sector_score: z.number().nullable().optional(),
})
export type CompositeResult = z.infer<typeof CompositeResultSchema>

// ───────────── store（zustand，模块级单例，keyed by code）─────────────

export type CompositePhase = 'idle' | 'submitting' | 'polling' | 'done' | 'error'

export interface CompositeTaskState {
  phase: CompositePhase
  taskId: string | null
  /** 提交时刻（ms，Date.now），用于「已用时」展示，非数据日语义。 */
  startedAt: number | null
  /** 最近一次阶段回报（task.stage 或末条 log.message），轮询中展示。 */
  stage: string | null
  /** 最近一次轮询的 elapsed 秒数（轮询节拍更新，不做本地计时器）。 */
  elapsedS: number | null
  result: CompositeResult | null
  error: string | null
}

const IDLE_STATE: CompositeTaskState = Object.freeze({
  phase: 'idle',
  taskId: null,
  startedAt: null,
  stage: null,
  elapsedS: null,
  result: null,
  error: null,
})

interface ScoreTaskStoreShape {
  states: Record<string, CompositeTaskState>
  patch: (code: string, next: Partial<CompositeTaskState>) => void
}

const useScoreTaskStoreBase = create<ScoreTaskStoreShape>((set) => ({
  states: {},
  patch: (code, next) =>
    set((s) => ({
      states: { ...s.states, [code]: { ...stateOf(s.states, code), ...next } },
    })),
}))

function stateOf(states: Record<string, CompositeTaskState>, code: string): CompositeTaskState {
  return states[code] ?? IDLE_STATE
}

/** 组件订阅入口：返回该 code 的任务态（idle 为共享冻结对象，引用稳定）。 */
export function useCompositeTask(code: string): CompositeTaskState {
  return useScoreTaskStoreBase((s) => stateOf(s.states, code))
}

/** 非组件读取入口（测试 / 模块间读取当前任务态）。 */
export function getCompositeTaskState(code: string): CompositeTaskState {
  return stateOf(useScoreTaskStoreBase.getState().states, code)
}

function patchState(code: string, next: Partial<CompositeTaskState>): void {
  useScoreTaskStoreBase.getState().patch(code, next)
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** 模块级轮询循环：与组件生命周期完全解耦，切页不打断。 */
async function pollLoop(code: string, taskId: string, startedAt: number): Promise<void> {
  while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
    await sleep(POLL_INTERVAL_MS)
    let raw: unknown
    try {
      raw = await apiFetch<unknown>(`/tasks/${encodeURIComponent(taskId)}`)
    } catch (e) {
      patchState(code, { phase: 'error', error: `轮询任务状态失败：${errMsg(e)}` })
      return
    }
    const parsed = TaskStatusSchema.safeParse(raw)
    if (!parsed.success) {
      patchState(code, { phase: 'error', error: '任务状态响应不符合契约（轮询终止）' })
      return
    }
    const t = parsed.data
    const elapsedS = Math.round((Date.now() - startedAt) / 100) / 10
    const lastLog = t.logs && t.logs.length > 0 ? t.logs[t.logs.length - 1] : undefined
    const stage = t.stage || lastLog?.message || null

    if (t.status === 'success') {
      if (t.result === undefined || t.result === null) {
        patchState(code, {
          phase: 'error',
          elapsedS,
          error: '任务标记成功但未返回结果（后端未产出评分），不伪造分数',
        })
        return
      }
      const res = CompositeResultSchema.safeParse(t.result)
      if (!res.success) {
        patchState(code, { phase: 'error', elapsedS, error: '任务结果不符合评分字段契约' })
        return
      }
      patchState(code, { phase: 'done', stage: null, elapsedS, result: res.data, error: null })
      return
    }
    if (t.status === 'error') {
      patchState(code, {
        phase: 'error',
        elapsedS,
        error: t.error ? `后台任务失败：${t.error}` : '后台任务失败（后端未给出原因）',
      })
      return
    }
    if (t.status === 'cancelled') {
      patchState(code, { phase: 'error', elapsedS, error: '任务已取消' })
      return
    }
    // pending / running：更新阶段提示后继续轮询
    patchState(code, { phase: 'polling', stage, elapsedS })
  }
  patchState(code, {
    phase: 'error',
    error: `轮询超时（约 ${Math.round(POLL_TIMEOUT_MS / 1000)} 秒）任务仍未完成，已停止等待`,
  })
}

/**
 * 提交五维综合评分任务并启动模块级轮询。UI 只在用户点击按钮时调用（不自动发）；
 * 进行中（submitting/polling）重复调用为 no-op，防止双任务。
 */
export function submitAnalysisTask(code: string): void {
  if (!/^\d{6}$/.test(code)) return
  const cur = useScoreTaskStoreBase.getState().states[code]
  if (cur && (cur.phase === 'submitting' || cur.phase === 'polling')) return

  const startedAt = Date.now()
  patchState(code, {
    phase: 'submitting',
    taskId: null,
    startedAt,
    stage: null,
    elapsedS: 0,
    result: null,
    error: null,
  })

  // fire-and-forget：模块级 async 链，任何组件卸载都不影响
  void (async () => {
    try {
      const data = await apiMutate<unknown>('/tasks/', 'POST', {
        type: 'analysis',
        payload: { ticker: code },
      })
      const submit = TaskSubmitResultSchema.parse(data)
      patchState(code, { phase: 'polling', taskId: submit.task_id })
      await pollLoop(code, submit.task_id, startedAt)
    } catch (e) {
      patchState(code, { phase: 'error', error: errMsg(e) })
    }
  })()
}
