import { create } from 'zustand'
import {
  submitPatternScanTask,
  getPatternScanTask,
  parsePatternScanResult,
} from '@/api/patternScan'
import type { PatternScan } from '@/api/schemas/patternScan'

/**
 * 形态扫描异步任务 store（对齐 useXingchen 的模块级轮询范式）。
 *
 * 设计要点：
 *  - store 建在模块级（非组件内），轮询循环不挂在组件上：切页卸载不打断，
 *    同会话切回页面结果仍在；
 *  - 轮询间隔 1.5s（对齐星辰），上限 120s（50 只并行取数的最坏等待，
 *    比同步串行的数十秒放宽一倍）；
 *  - 超时诚实语义：不报错、不伪造失败——停止轮询并如实提示
 *    「任务仍在后台运行」，保留 requery 入口接续既有 task_id（不重复提交）；
 *  - 内存态：刷新即清（与星辰一致），页面加低强说明。
 */

const POLL_INTERVAL = 1500
/** 50 只 × 并行取数的最坏等待上限；超时后任务仍在后台跑（诚实提示，非报错）。 */
const POLL_TIMEOUT = 120000

export type PatternScanPhase =
  | 'idle' // 未提交
  | 'submitting' // 提交任务中
  | 'polling' // 轮询中
  | 'done' // 成功，result 可用
  | 'error' // 提交失败 / 后台任务 error / 轮询失败 / 已取消
  | 'timeout' // 前端等待超时：任务仍在后台运行（非错误态）

interface PatternScanState {
  phase: PatternScanPhase
  taskId: string | null
  /** 后端上报的完成进度（0~100；未上报为 0）。 */
  progress: number
  result: PatternScan | null
  error: string | null
  /** 超时后接续轮询既有任务（不重复提交）；无 taskId 时为 no-op。 */
  requery: () => void
  reset: () => void
}

export const usePatternScanStore = create<PatternScanState>((set, get) => ({
  phase: 'idle',
  taskId: null,
  progress: 0,
  result: null,
  error: null,
  requery: () => {
    const taskId = get().taskId
    if (!taskId) return
    set({ phase: 'polling', progress: 0, error: null })
    void pollTask(taskId)
  },
  reset: () => set({ phase: 'idle', taskId: null, progress: 0, result: null, error: null }),
}))

/** 轮询防重入：requery 与新提交并发时只允许一个循环在跑。 */
let _polling = false

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** 模块级轮询循环：不挂组件，切页卸载不影响。 */
async function pollTask(taskId: string): Promise<void> {
  if (_polling) return
  _polling = true
  const started = Date.now()
  try {
    while (true) {
      await delay(POLL_INTERVAL)
      let task
      try {
        task = await getPatternScanTask(taskId)
      } catch (e) {
        // 轮询本身失败（网络/契约解析）：如实报错，可 requery 接续
        usePatternScanStore.setState({
          phase: 'error',
          error: e instanceof Error ? e.message : '轮询失败',
        })
        return
      }
      if (usePatternScanStore.getState().taskId !== taskId) {
        // 期间用户重新提交了新任务：旧循环退出，不覆盖新任务状态
        return
      }
      usePatternScanStore.setState({ progress: typeof task.progress === 'number' ? task.progress : 0 })

      if (task.status === 'success') {
        try {
          const result = parsePatternScanResult(task.result)
          usePatternScanStore.setState({ phase: 'done', result, error: null })
        } catch (e) {
          // result 契约不符：诚实报错，不伪造形态结果
          usePatternScanStore.setState({
            phase: 'error',
            error: e instanceof Error ? `结果解析失败: ${e.message}` : '结果解析失败',
          })
        }
        return
      }
      if (task.status === 'error') {
        usePatternScanStore.setState({ phase: 'error', error: task.error ?? '后台任务出错' })
        return
      }
      if (task.status === 'cancelled') {
        usePatternScanStore.setState({ phase: 'error', error: '任务已停止（后台已标记取消）' })
        return
      }
      // pending / running：继续等；到达上限 → 诚实超时（任务仍在后台，未失败）
      if (Date.now() - started > POLL_TIMEOUT) {
        usePatternScanStore.setState({ phase: 'timeout' })
        return
      }
    }
  } finally {
    _polling = false
  }
}

/** 提交异步扫描任务并开始轮询（表单校验由页面负责；此处二次防御 codes 形状）。 */
export async function submitPatternScan(codes: string[], windowDays?: number): Promise<void> {
  if (!Array.isArray(codes) || codes.length < 1 || codes.length > 50) {
    usePatternScanStore.setState({ phase: 'error', error: 'codes 须为 1–50 个股票代码' })
    return
  }
  usePatternScanStore.setState({ phase: 'submitting', taskId: null, progress: 0, result: null, error: null })
  let taskId: string
  try {
    taskId = await submitPatternScanTask({ codes, window_days: windowDays })
  } catch (e) {
    usePatternScanStore.setState({
      phase: 'error',
      error: e instanceof Error ? e.message : '提交失败',
    })
    return
  }
  usePatternScanStore.setState({ phase: 'polling', taskId })
  await pollTask(taskId)
}

/** 顶层 hook：页面消费 store 状态与动作。 */
export function usePatternScan() {
  const phase = usePatternScanStore((s) => s.phase)
  const taskId = usePatternScanStore((s) => s.taskId)
  const progress = usePatternScanStore((s) => s.progress)
  const result = usePatternScanStore((s) => s.result)
  const error = usePatternScanStore((s) => s.error)
  const requery = usePatternScanStore((s) => s.requery)
  const reset = usePatternScanStore((s) => s.reset)
  return { phase, taskId, progress, result, error, requery, reset, submit: submitPatternScan }
}

/**
 * 顶栏运行徽标等跨页组件订阅的轻量只读 hook：
 * submitting/polling 视为运行中（timeout 后任务虽仍在后台，但前端已停止轮询，不再占徽标）。
 */
export function usePatternScanRunning(): boolean {
  return usePatternScanStore((s) => s.phase === 'submitting' || s.phase === 'polling')
}
