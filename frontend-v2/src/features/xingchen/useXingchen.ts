import { create } from 'zustand'
import { classifyIntent, type XcStyle } from './intent'
import {
  submitAiConsult,
  getAiConsultTask,
  cancelAiConsult,
  listConversations,
  createConversation,
  getConversationMessages,
  saveConversationMessages,
  deleteConversation,
  exportConversationMarkdown,
  exportConversationJson,
  getChatHistory,
} from '@/api/chat'
import type { ChatMessage, AiConsultTask, WireMessage } from '@/api/schemas/chat'

export type { XcStyle } from './intent'

/** 单会话（内存态；后端多会话持久化在 §10 第 5 步接入）。 */
export interface ChatSession {
  id: string
  title?: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
  convId?: number
  /** 后端消息是否已拉取（避免重复请求）。 */
  loaded?: boolean
}

const POLL_INTERVAL = 1500
const POLL_TIMEOUT = 30000
const SAVE_DEBOUNCE = 800

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

/** 后端 WireMessage → 前端 ChatMessage（user/assistant 落库形态还原）。 */
function wireToChat(m: { role: string; content: string; ts?: number }, i: number): ChatMessage {
  const role = m.role === 'user' ? 'user' : 'assistant'
  return {
    id: `w-${i}`,
    kind: role,
    role,
    content: m.content,
    status: 'done',
    ts: m.ts,
  }
}

/** 前端 ChatMessage → 后端 WireMessage（仅持久化 user/assistant 内容）。 */
function chatToWire(m: ChatMessage): WireMessage {
  return { role: m.role === 'user' ? 'user' : 'assistant', content: m.content, ts: m.ts }
}

/** 浏览器下载（jsdom/无 document 时静默跳过）。 */
function downloadText(filename: string, text: string, mime: string): void {
  if (typeof document === 'undefined') return
  try {
    const blob = new Blob([text], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch {
    // 下载失败不影响会话本身
  }
}

const saveTimers = new Map<string, ReturnType<typeof setTimeout>>()

interface XingchenState {
  sessions: Record<string, ChatSession>
  order: string[]
  activeId: string
  style: XcStyle
  model: string | undefined
  runningTaskId: string | null
  runningMsgId: string | null
  booting: boolean

  setStyle: (s: XcStyle) => void
  setModel: (m?: string) => void
  createSession: (title?: string) => string
  deleteSession: (id: string) => void
  setActive: (id: string) => void
  renameSession: (id: string, title: string) => void
  openConversation: (convId: number) => Promise<void>
  bootstrap: () => Promise<void>
  exportSession: (id: string, fmt: 'markdown' | 'json') => Promise<void>
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateMessage: (sessionId: string, msgId: string, patch: Partial<ChatMessage>) => void
  appendProcessStep: (sessionId: string, msgId: string, step: string) => void
  submitQuestion: (q: string) => Promise<void>
  cancelCurrent: () => Promise<void>
}

/** 懒建后端会话：本会话无 convId 时调用 createConversation，并把 convId 写回 store。 */
async function ensureConv(sid: string): Promise<number | null> {
  const s = useXingchenStore.getState().sessions[sid]
  if (!s) return null
  if (s.convId != null) return s.convId
  try {
    const conv = await createConversation(s.title ?? '新对话')
    if (!conv || typeof conv.id !== 'number') return null
    useXingchenStore.setState((st) => ({
      sessions: { ...st.sessions, [sid]: { ...st.sessions[sid], convId: conv.id } },
    }))
    return conv.id
  } catch {
    return null // 后端不可用：本地继续，不阻断
  }
}

/** 防抖保存本会话的 user/assistant 消息到后端（失败静默）。 */
function scheduleSave(sid: string, convId: number): void {
  const existing = saveTimers.get(sid)
  if (existing) clearTimeout(existing)
  const t = setTimeout(() => {
    saveTimers.delete(sid)
    const s = useXingchenStore.getState().sessions[sid]
    if (!s) return
    const wire = s.messages
      .filter((m) => m.kind === 'user' || m.kind === 'assistant')
      .map(chatToWire)
    void saveConversationMessages(convId, wire).catch(() => {})
  }, SAVE_DEBOUNCE)
  saveTimers.set(sid, t)
}

export const useXingchenStore = create<XingchenState>((set, get) => ({
  sessions: {},
  order: [],
  activeId: '',
  style: 'quick',
  model: undefined,
  runningTaskId: null,
  runningMsgId: null,
  booting: false,

  setStyle: (s) => set({ style: s }),
  setModel: (m) => set({ model: m }),

  createSession: (title) => {
    const id = genId('s')
    const now = nowSec()
    const session: ChatSession = {
      id,
      title: title || undefined,
      messages: [],
      createdAt: now,
      updatedAt: now,
    }
    set((st) => ({
      sessions: { ...st.sessions, [id]: session },
      order: [...st.order, id],
      activeId: id,
    }))
    return id
  },

  deleteSession: (id) => {
    const s = get().sessions[id]
    if (s?.convId != null) void deleteConversation(s.convId).catch(() => {})
    set((st) => {
      const sessions = { ...st.sessions }
      delete sessions[id]
      const order = st.order.filter((x) => x !== id)
      const activeId = st.activeId === id ? order[order.length - 1] ?? '' : st.activeId
      return { sessions, order, activeId }
    })
  },

  setActive: (id) => {
    if (get().sessions[id]) set({ activeId: id })
  },

  renameSession: (id, title) =>
    set((st) => {
      const s = st.sessions[id]
      if (!s) return {}
      return { sessions: { ...st.sessions, [id]: { ...s, title, updatedAt: nowSec() } } }
    }),

  openConversation: async (convId) => {
    const sid = Object.keys(get().sessions).find(
      (k) => get().sessions[k].convId === convId,
    )
    if (!sid) return
    set({ activeId: sid })
    const s = get().sessions[sid]
    if (s.loaded) return
    try {
      const resp = await getConversationMessages(convId)
      set((st) => ({
        sessions: {
          ...st.sessions,
          [sid]: {
            ...st.sessions[sid],
            title: resp.title ?? s.title,
            messages: (resp.messages ?? []).map((m, i) => wireToChat(m, i)),
            loaded: true,
          },
        },
      }))
    } catch {
      set((st) => ({
        sessions: { ...st.sessions, [sid]: { ...st.sessions[sid], loaded: true } },
      }))
    }
  },

  bootstrap: async () => {
    if (get().booting) return
    set({ booting: true })
    try {
      const list = await listConversations()
      const convs = list.conversations
      if (convs.length > 0) {
        const sessions: Record<string, ChatSession> = {}
        const order: string[] = []
        for (const c of convs) {
          const id = `s-${c.id}`
          sessions[id] = {
            id,
            title: c.title,
            convId: c.id,
            messages: [],
            createdAt: nowSec(),
            updatedAt: nowSec(),
            loaded: false,
          }
          order.push(id)
        }
        set({ sessions, order, activeId: order[0] })
        await get().openConversation(convs[0].id)
      } else {
        get().createSession('新对话')
      }
    } catch {
      // 404 / 多会话接口不可用 → 旧单记录模式回退
      try {
        const hist = await getChatHistory()
        const id = 's-legacy'
        set({
          sessions: {
            [id]: {
              id,
              title: '历史对话',
              messages: hist.messages.map((m, i) => wireToChat(m, i)),
              createdAt: nowSec(),
              updatedAt: nowSec(),
              loaded: true,
            },
          },
          order: [id],
          activeId: id,
        })
      } catch {
        get().createSession('新对话')
      }
    } finally {
      set({ booting: false })
    }
  },

  exportSession: async (id, fmt) => {
    const s = get().sessions[id]
    if (!s || s.convId == null) return
    try {
      if (fmt === 'json') {
        const data = await exportConversationJson(s.convId)
        downloadText(`${s.title ?? 'conversation'}.json`, JSON.stringify(data, null, 2), 'application/json')
      } else {
        const md = await exportConversationMarkdown(s.convId)
        downloadText(`${s.title ?? 'conversation'}.md`, md, 'text/markdown')
      }
    } catch {
      // 导出失败不影响会话
    }
  },

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
    const sid =
      state.activeId && state.sessions[state.activeId]
        ? state.activeId
        : state.createSession()
    // 懒建后端会话（失败静默，本地继续）
    const convId = await ensureConv(sid)
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
      if (convId != null) scheduleSave(sid, convId)
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
      if (convId != null) scheduleSave(sid, convId)
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
    if (convId != null) scheduleSave(sid, convId)
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
    const convId = activeId ? get().sessions[activeId]?.convId ?? null : null
    if (convId != null) scheduleSave(activeId, convId)
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
    booting: false,
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
  const openConversation = useXingchenStore((s) => s.openConversation)
  const bootstrap = useXingchenStore((s) => s.bootstrap)
  const exportSession = useXingchenStore((s) => s.exportSession)

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
    openConversation,
    bootstrap,
    exportSession,
  }
}
