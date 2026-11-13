import { create } from 'zustand'
import { classifyIntent, type XcStyle } from './intent'
import {
  submitAiConsult,
  getAiConsultTask,
  cancelAiConsult,
} from '@/api/chat'
import type { ChatMessage, AiConsultTask } from '@/api/schemas/chat'

export type { XcStyle } from './intent'

/** 单会话（内存态；后端多会话持久化在 §10 第 5 步接入）。 */
export interface ChatSession {
  id: string
  title?: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
  convId?: number
}

const POLL_INTERVAL = 1500
const POLL_TIMEOUT = 30000

let _seq = 0
function genId(prefix: string): string {
  _seq += 1
  return `${prefix}-${Date.now().toString(36)}-${_seq.toString(36)}`
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

function nowSec(): number {
  return Math.floor(Date.now() / 1000)
}

interface XingchenState {
  sessions: Record<string, ChatSession>
  order: string[]
  activeId: string
  style: XcStyle
  model: string | undefined
  runningTaskId: string | null
  runningMsgId: string | null

  setStyle: (s: XcStyle) => void
  setModel: (m?: string) => void
  createSession: () => string
  deleteSession: (id: string) => void
  setActive: (id: string) => void
  renameSession: (id: string, title: string) => void
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateMessage: (sessionId: string, msgId: string, patch: Partial<ChatMessage>) => void
  appendProcessStep: (sessionId: string, msgId: string, step: string) => void
  submitQuestion: (q: string) => Promise<void>
  cancelCurrent: () => Promise<void>
}

export const useXingchenStore = create<XingchenState>((set, get) => ({
  sessions: {},
  order: [],
  activeId: '',
  style: 'quick',
  model: undefined,
  runningTaskId: null,
  runningMsgId: null,

  setStyle: (s) => set({ style: s }),
  setModel: (m) => set({ model: m }),

  createSession: () => {
    const id = genId('s')
    const now = nowSec()
    const session: ChatSession = { id, messages: [], createdAt: now, updatedAt: now }
    set((st) => ({
      sessions: { ...st.sessions, [id]: session },
      order: [...st.order, id],
      activeId: id,
    }))
    return id
  },

  deleteSession: (id) =>
    set((st) => {
      const sessions = { ...st.sessions }
      delete sessions[id]
      const order = st.order.filter((x) => x !== id)
      const activeId = st.activeId === id ? order[order.length - 1] ?? '' : st.activeId
      return { sessions, order, activeId }
    }),

  setActive: (id) => {
    if (get().sessions[id]) set({ activeId: id })
  },

  renameSession: (id, title) =>
    set((st) => {
      const s = st.sessions[id]
      if (!s) return {}
      return { sessions: { ...st.sessions, [id]: { ...s, title, updatedAt: nowSec() } } }
    }),

  addMessage: (sessionId, msg) =>
    set((st) => {
      const s = st.sessions[sessionId]
      if (!s) return {}
      return {
        sessions: {
          ...st.sessions,
          [sessionId]: { ...s, messages: [...s.messages, msg], updatedAt: nowSec() },
        },
      }
    }),

  updateMessage: (sessionId, msgId, patch) =>
    set((st) => {
      const s = st.sessions[sessionId]
      if (!s) return {}
      return {
        sessions: {
          ...st.sessions,
          [sessionId]: {
            ...s,
            updatedAt: nowSec(),
            messages: s.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)),
          },
        },
      }
    }),

  appendProcessStep: (sessionId, msgId, step) =>
    set((st) => {
      const s = st.sessions[sessionId]
      if (!s) return {}
      return {
        sessions: {
          ...st.sessions,
          [sessionId]: {
            ...s,
            messages: s.messages.map((m) =>
              m.id === msgId ? { ...m, process: [...(m.process ?? []), step] } : m,
            ),
          },
        },
      }
    }),

  submitQuestion: async (q) => {
    const question = (q || '').trim()
    if (!question) return
    if (get().runningTaskId) return // 已有任务在跑，忽略重复提交

    const state = get()
    const sid = state.activeId && state.sessions[state.activeId] ? state.activeId : state.createSession()
    const intent = classifyIntent(question)

    // 用户消息
    get().addMessage(sid, {
      id: genId('u'),
      kind: 'user',
      role: 'user',
      content: question,
      status: 'done',
      ts: nowSec(),
    })

    // 边界拒绝：缺分析标的 → 缺参追问卡片，不提交后端
    if (intent.needsParam) {
      get().addMessage(sid, {
        id: genId('p'),
        kind: 'param-prompt',
        role: 'tool',
        content: '',
        paramPrompt: intent.paramPrompts,
        ts: nowSec(),
        status: 'done',
      })
      return
    }

    // assistant 占位（流式）：携带分析卡步骤，等待轮询回填
    const aId = genId('a')
    get().addMessage(sid, {
      id: aId,
      kind: 'assistant',
      role: 'assistant',
      content: '',
      status: 'streaming',
      process: intent.processSteps,
      ts: nowSec(),
      model: get().model,
    })

    let taskId: string
    try {
      taskId = await submitAiConsult({ question, style: get().style, model: get().model })
    } catch (e) {
      get().updateMessage(sid, aId, {
        status: 'error',
        errors: [e instanceof Error ? e.message : '提交失败'],
      })
      return
    }

    set({ runningTaskId: taskId, runningMsgId: aId })
    const started = Date.now()
    // 轮询 ai_consult 任务态（对齐 v1 run_every=1.5s）
    while (true) {
      await delay(POLL_INTERVAL)
      let task: AiConsultTask
      try {
        task = await getAiConsultTask(taskId)
      } catch (e) {
        get().updateMessage(sid, aId, {
          status: 'error',
          errors: [e instanceof Error ? e.message : '轮询失败'],
        })
        break
      }
      get().updateMessage(sid, aId, { toolCall: task })

      if (task.status === 'success') {
        const result = (task.result ?? null) as { answer?: string; specialist?: string } | null
        get().updateMessage(sid, aId, {
          status: 'done',
          content: result?.answer ?? '',
          model: result?.specialist ?? get().model,
          chips: intent.suggestionChips,
        })
        break
      }
      if (task.status === 'error') {
        get().updateMessage(sid, aId, {
          status: 'error',
          errors: [task.error ?? '后台任务出错'],
        })
        break
      }
      if (task.status === 'cancelled') {
        get().updateMessage(sid, aId, {
          status: 'error',
          errors: ['已停止等待（后台已标记取消）'],
        })
        break
      }
      if (Date.now() - started > POLL_TIMEOUT) {
        get().updateMessage(sid, aId, {
          status: 'error',
          errors: ['后台响应超时，请稍后重试'],
        })
        break
      }
    }
    set({ runningTaskId: null, runningMsgId: null })
  },

  cancelCurrent: async () => {
    const { runningTaskId, runningMsgId, activeId } = get()
    if (!runningTaskId) return
    try {
      await cancelAiConsult(runningTaskId)
    } catch {
      // 取消失败也照常本地收尾
    }
    if (runningMsgId && activeId && get().sessions[activeId]) {
      get().updateMessage(activeId, runningMsgId, {
        status: 'error',
        errors: ['已停止等待'],
      })
    }
    set({ runningTaskId: null, runningMsgId: null })
  },
}))

/** 测试间复位内存态（保留 actions）。 */
export function resetXingchen(): void {
  useXingchenStore.setState({
    sessions: {},
    order: [],
    activeId: '',
    style: 'quick',
    model: undefined,
    runningTaskId: null,
    runningMsgId: null,
  })
}

/** 顶层 hook：暴露 active 会话与动作（供 XingchenPage / 测试消费）。 */
export function useXingchen() {
  const sessions = useXingchenStore((s) => s.sessions)
  const order = useXingchenStore((s) => s.order)
  const activeId = useXingchenStore((s) => s.activeId)
  const style = useXingchenStore((s) => s.style)
  const model = useXingchenStore((s) => s.model)
  const runningTaskId = useXingchenStore((s) => s.runningTaskId)
  const setStyle = useXingchenStore((s) => s.setStyle)
  const setModel = useXingchenStore((s) => s.setModel)
  const submitQuestion = useXingchenStore((s) => s.submitQuestion)
  const cancelCurrent = useXingchenStore((s) => s.cancelCurrent)
  const createSession = useXingchenStore((s) => s.createSession)
  const setActive = useXingchenStore((s) => s.setActive)
  const deleteSession = useXingchenStore((s) => s.deleteSession)
  const renameSession = useXingchenStore((s) => s.renameSession)

  const active = activeId ? sessions[activeId] : undefined
  return {
    sessions,
    order,
    activeId,
    active,
    style,
    model,
    isRunning: !!runningTaskId,
    setStyle,
    setModel,
    submitQuestion,
    cancelCurrent,
    createSession,
    setActive,
    deleteSession,
    renameSession,
  }
}
