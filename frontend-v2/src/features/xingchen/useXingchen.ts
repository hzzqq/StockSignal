import { create } from 'zustand'
import { classifyIntent, extractTopic, STYLE_LABELS, DIMENSIONS, type XcStyle } from './intent'
import {
  submitAiConsult,
  submitAiResearch,
  getAiConsultTask,
  cancelAiConsult,
  listConversations,
  createConversation,
  getConversationMessages,
  saveConversationMessages,
  renameConversation,
  deleteConversation,
  exportConversationMarkdown,
  exportConversationJson,
  getChatHistory,
} from '@/api/chat'
import { ApiError } from '@/api/client'
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
/**
 * 前端轮询等待上限按任务类型分级（B 修复：此前统一 30s，对分钟级 ai_research/
 * quant_research 会「假超时」——后端仍在跑，前端却报错）。
 *  - ai_consult：短任务，30s；
 *  - ai_research / quant_research 及其他未知类型（保守放宽）：600s。
 * 超时 ≠ 后端失败：停止轮询并如实提示「任务仍在后台运行」，保留重新提问入口。
 */
const POLL_TIMEOUT_CONSULT = 30000
const POLL_TIMEOUT_RESEARCH = 600000

function pollTimeoutFor(taskType: string | undefined, mode: 'quick' | 'research'): number {
  if (mode === 'research') return POLL_TIMEOUT_RESEARCH
  if (taskType && taskType !== 'ai_consult') return POLL_TIMEOUT_RESEARCH
  return POLL_TIMEOUT_CONSULT
}
const SAVE_DEBOUNCE = 800
/** 会话标题上限，与后端 chat_routes._TITLE_MAX 保持一致。 */
const TITLE_MAX = 40

/** 标题规范化：trim → 空回退「新对话」→ 40 字截断（与后端 _norm_title 一致）。 */
function normalizeTitle(title: string): string {
  const t = (title || '').trim()
  return (t || '新对话').slice(0, TITLE_MAX)
}

/** 重命名结果：persisted=false 表示该会话无 convId，仅本地改名（如实标注）。 */
export interface RenameSessionResult {
  persisted: boolean
  /** 最终生效标题（成功时为服务端权威值，未持久化时为本地规范化值）。 */
  title: string
}

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

/**
 * 多轮承接：取会话最近 ≤8 条 user/assistant 纯文本，role 用后端认识的 user/assistant。
 * 超 8 条会被 AiResearchSubmitSchema.history.max(8) 拒绝，故必须切片（slice 取尾部）。
 * 纯前端态消息（param-prompt / 空占位 / tool）不进历史，不编造上下文。
 */
export function buildRecentHistory(
  messages: ChatMessage[] | undefined,
  limit = 8,
): { role: string; content: string }[] {
  if (!messages) return []
  return messages
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && !!m.content?.trim())
    .slice(-limit)
    .map((m) => ({ role: m.role, content: m.content }))
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
  /** 咨询模式：quick=单轮 ai_consult；research=多步工具调用 ai_research（引用溯源） */
  mode: 'quick' | 'research'
  model: string | undefined
  runningTaskId: string | null
  runningMsgId: string | null
  booting: boolean
  /** 删除会话失败时的可见错误（侧栏 role="alert" 展示，可手动清除）。 */
  deleteError: string | null

  setStyle: (s: XcStyle) => void
  setMode: (m: 'quick' | 'research') => void
  setModel: (m?: string) => void
  createSession: (title?: string) => string
  deleteSession: (id: string) => Promise<void>
  clearDeleteError: () => void
  setActive: (id: string) => void
  renameSession: (id: string, title: string) => Promise<RenameSessionResult>
  openConversation: (convId: number) => Promise<void>
  bootstrap: () => Promise<void>
  exportSession: (id: string, fmt: 'markdown' | 'json') => Promise<void>
  addMessage: (sessionId: string, msg: ChatMessage) => void
  updateMessage: (sessionId: string, msgId: string, patch: Partial<ChatMessage>) => void
  appendProcessStep: (sessionId: string, msgId: string, step: string) => void
  markRevealed: (msgId: string) => void
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
  mode: 'quick',
  model: undefined,
  runningTaskId: null,
  runningMsgId: null,
  booting: false,
  deleteError: null,

  setStyle: (s) => set({ style: s }),
  setMode: (m) => set({ mode: m }),
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

  deleteSession: async (id) => {
    const s = get().sessions[id]
    if (!s) return
    // 记录原始位置/激活项，供后端删除失败时精确回滚（避免前后端状态分叉）
    const originalIndex = get().order.indexOf(id)
    const originalActiveId = get().activeId
    let postDeleteActiveId = originalActiveId
    // 乐观本地删除：成功路径行为与旧实现一致
    set((st) => {
      const sessions = { ...st.sessions }
      delete sessions[id]
      const order = st.order.filter((x) => x !== id)
      const activeId = st.activeId === id ? order[order.length - 1] ?? '' : st.activeId
      postDeleteActiveId = activeId
      return { sessions, order, activeId, deleteError: null }
    })
    // 本地会话无后端记录：直接删除完成，不调后端
    if (s.convId == null) return
    try {
      await deleteConversation(s.convId)
    } catch {
      // 后端删除失败：把会话插回原 order 位置并暴露可见错误，绝不静默吞
      set((st) => {
        if (st.sessions[id]) return { deleteError: '删除失败，请重试' }
        const sessions = { ...st.sessions, [id]: s }
        const order = [...st.order]
        order.splice(originalIndex < 0 ? order.length : originalIndex, 0, id)
        // 用户若已在等待期间主动切换会话，则尊重新选择，不强行还原
        const activeId = st.activeId === postDeleteActiveId ? originalActiveId : st.activeId
        return { sessions, order, activeId, deleteError: '删除失败，请重试' }
      })
    }
  },

  clearDeleteError: () => set({ deleteError: null }),

  setActive: (id) => {
    if (get().sessions[id]) set({ activeId: id })
  },

  renameSession: async (id, title) => {
    const original = get().sessions[id]
    if (!original) throw new Error('会话不存在，无法重命名')
    const finalTitle = normalizeTitle(title)
    const prevTitle = original.title
    const prevUpdatedAt = original.updatedAt

    // 乐观更新：标题与更新时间即时反馈，不等后端往返
    set((st) => {
      const s = st.sessions[id]
      if (!s) return {}
      return {
        sessions: { ...st.sessions, [id]: { ...s, title: finalTitle, updatedAt: nowSec() } },
      }
    })

    // 无后端 id：只改内存，并如实标注未持久化（不假装已保存）
    if (original.convId == null) {
      return { persisted: false, title: finalTitle }
    }

    try {
      const res = await renameConversation(original.convId, finalTitle)
      // 服务端权威标题回填（含规范化/截断）；若期间已发起更新的重命名则跳过，避免旧响应覆盖新标题
      set((st) => {
        const s = st.sessions[id]
        if (!s || s.title !== finalTitle) return {}
        return {
          sessions: { ...st.sessions, [id]: { ...s, title: res.title, updatedAt: nowSec() } },
        }
      })
      return { persisted: true, title: res.title }
    } catch (e) {
      // 失败回滚内存标题（同样避免旧响应覆盖新标题），给中文错误提示，绝不静默吞
      set((st) => {
        const s = st.sessions[id]
        if (!s || s.title !== finalTitle) return {}
        return {
          sessions: {
            ...st.sessions,
            [id]: { ...s, title: prevTitle, updatedAt: prevUpdatedAt },
          },
        }
      })
      const reason =
        e instanceof ApiError ? e.reason : e instanceof Error ? e.message : '未知错误'
      throw new Error(`重命名失败：${reason}`)
    }
  },

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

  // 流式揭示完成：清 fresh，避免历史重载/重挂载时再次触发动画
  markRevealed: (msgId) =>
    set((st) => {
      const sessions = { ...st.sessions }
      for (const sid of Object.keys(sessions)) {
        const s = sessions[sid]
        const idx = s.messages.findIndex((m) => m.id === msgId && m.fresh)
        if (idx >= 0) {
          sessions[sid] = {
            ...s,
            messages: s.messages.map((m) => (m.id === msgId ? { ...m, fresh: false } : m)),
          }
          break
        }
      }
      return { sessions }
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

    // 多轮承接：在追加本轮问题之前抓取历史（历史 = 本轮之前的轮次），≤8 条由 buildRecentHistory 切片
    const history = buildRecentHistory(get().sessions[sid]?.messages)

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

    // assistant 占位（流式）：携带分析卡步骤 + 全面化外壳元数据，等待轮询回填。
    // analysisMeta 在提交即写入（意图已判定），使轮询期也能展示标题卡 + 维度卡（分析中），
    // 而非成功后才出现，对标 FinPilot「生成中即展示研究框架」。
    const aId = genId('a')
    get().addMessage(sid, {
      id: aId,
      kind: 'assistant',
      role: 'assistant',
      content: '',
      status: 'streaming',
      process: intent.processSteps,
      analysisMeta: {
        topic: extractTopic(question),
        styleLabel: STYLE_LABELS[get().style],
        dimensions: DIMENSIONS[intent.kind],
      },
      ts: nowSec(),
      model: get().model,
    })

    let taskId: string
    try {
      if (get().mode === 'research') {
        // 深度研究：多步工具调用 + 引用溯源（style=report 输出研报结构）。
        // 用当前页面风格决定合成方式：report→研报结构，其余→简洁。
        const researchStyle = get().style === 'report' ? 'report' : 'quick'
        taskId = await submitAiResearch({
          question,
          style: researchStyle,
          max_steps: 8,
          ...(history.length > 0 ? { history } : {}),
        })
      } else {
        // ai_consult 的 schema 无 history 字段，走 context（后端 ai_answer 读 context['history']）。
        // 无历史时不下发 context，保持首轮 payload 形状不变。
        taskId = await submitAiConsult({
          question,
          style: get().style,
          model: get().model,
          ...(history.length > 0 ? { context: { history } } : {}),
        })
      }
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
    // 轮询 ai_consult 任务态（对齐 v1 run_every=1.5s）；等待上限按任务类型分级
    let timeoutMs = pollTimeoutFor(undefined, get().mode)
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
      // 后端 task_type 是权威：首次拿到后即时校正等待上限（quick 提交也可能被后端升格 research）
      timeoutMs = pollTimeoutFor(task.task_type, get().mode)
      get().updateMessage(sid, aId, { toolCall: task })

      if (task.status === 'success') {
        const result = (task.result ?? null) as { answer?: string; specialist?: string } | null
        const answer = result?.answer ?? ''
        // analysisMeta 已在提交占位时写入；此处仅回填正文 + 触发组件层流式揭示
        get().updateMessage(sid, aId, {
          status: 'done',
          content: answer,
          model: result?.specialist ?? get().model,
          chips: intent.suggestionChips,
          fresh: true,
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
      if (Date.now() - started > timeoutMs) {
        // 等待上限到达 ≠ 后端失败：任务仍在后台运行。诚实提示 + 原问题作为
        // 「重新查询」入口（点击即重发同一问题），不报错、不伪造完成态。
        get().updateMessage(sid, aId, {
          status: 'done',
          content:
            '⏳ 前端等待超时：该任务耗时较长，仍在后台运行（未失败），结果不会自动推送。' +
            '可点击下方「重新查询」再次发起同一问题。',
          chips: [question],
          fresh: true,
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
    mode: 'quick',
    model: undefined,
    runningTaskId: null,
    runningMsgId: null,
    booting: false,
    deleteError: null,
  })
}

/** 顶层 hook：暴露 active 会话与动作（供 XingchenPage / 测试消费）。 */
export function useXingchen() {
  const sessions = useXingchenStore((s) => s.sessions)
  const order = useXingchenStore((s) => s.order)
  const activeId = useXingchenStore((s) => s.activeId)
  const style = useXingchenStore((s) => s.style)
  const model = useXingchenStore((s) => s.model)
  const mode = useXingchenStore((s) => s.mode)
  const setMode = useXingchenStore((s) => s.setMode)
  const booting = useXingchenStore((s) => s.booting)
  const runningTaskId = useXingchenStore((s) => s.runningTaskId)
  const setStyle = useXingchenStore((s) => s.setStyle)
  const setModel = useXingchenStore((s) => s.setModel)
  const submitQuestion = useXingchenStore((s) => s.submitQuestion)
  const cancelCurrent = useXingchenStore((s) => s.cancelCurrent)
  const createSession = useXingchenStore((s) => s.createSession)
  const setActive = useXingchenStore((s) => s.setActive)
  const deleteSession = useXingchenStore((s) => s.deleteSession)
  const deleteError = useXingchenStore((s) => s.deleteError)
  const clearDeleteError = useXingchenStore((s) => s.clearDeleteError)
  const renameSession = useXingchenStore((s) => s.renameSession)
  const openConversation = useXingchenStore((s) => s.openConversation)
  const bootstrap = useXingchenStore((s) => s.bootstrap)
  const exportSession = useXingchenStore((s) => s.exportSession)
  const markRevealed = useXingchenStore((s) => s.markRevealed)

  const active = activeId ? sessions[activeId] : undefined
  return {
    sessions,
    order,
    activeId,
    active,
    style,
    mode,
    model,
    booting,
    isRunning: !!runningTaskId,
    setStyle,
    setMode,
    setModel,
    submitQuestion,
    cancelCurrent,
    createSession,
    setActive,
    deleteSession,
    deleteError,
    clearDeleteError,
    renameSession,
    openConversation,
    bootstrap,
    exportSession,
    markRevealed,
  }
}

/**
 * 顶栏运行徽标等跨页组件订阅的轻量只读 hook：
 * 只关心 runningTaskId 是否有值，不暴露 store 动作面，切页卸载不会打断后台轮询。
 */
export function useXingchenRunning(): boolean {
  return useXingchenStore((s) => s.runningTaskId !== null)
}
