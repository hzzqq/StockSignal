import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/api/chat', () => ({
  submitAiConsult: vi.fn(),
  getAiConsultTask: vi.fn(),
  cancelAiConsult: vi.fn(),
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversationMessages: vi.fn(),
  saveConversationMessages: vi.fn(),
  deleteConversation: vi.fn(),
  exportConversationJson: vi.fn(),
  exportConversationMarkdown: vi.fn(),
  getChatHistory: vi.fn(),
}))

import {
  submitAiConsult,
  getAiConsultTask,
  cancelAiConsult,
  listConversations,
  createConversation,
  getConversationMessages,
  deleteConversation,
  exportConversationMarkdown,
  getChatHistory,
} from '@/api/chat'
import { useXingchenStore, resetXingchen } from './useXingchen'

const mockedSubmit = vi.mocked(submitAiConsult)
const mockedPoll = vi.mocked(getAiConsultTask)
const mockedCancel = vi.mocked(cancelAiConsult)

const RUNNING = {
  task_id: 't1',
  task_type: 'ai_consult',
  status: 'running',
  progress: 0.5,
  stage: 'analyzing',
  logs: [{ stage: 'analyzing', message: '演示进度', ts: 1 }],
  result: null,
}
const SUCCESS = {
  ...RUNNING,
  status: 'success',
  progress: 1,
  stage: 'done',
  result: { answer: '结论：看好', independent: true },
}

describe('useXingchen 提交+轮询', () => {
  beforeEach(() => {
    resetXingchen()
    mockedSubmit.mockReset()
    mockedPoll.mockReset()
    mockedCancel.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('提交 → 轮询到 success → 回填 assistant 消息', async () => {
    mockedSubmit.mockResolvedValue('t1')
    mockedPoll.mockResolvedValueOnce(RUNNING as never).mockResolvedValueOnce(SUCCESS as never)

    vi.useFakeTimers()
    const p = useXingchenStore.getState().submitQuestion('茅台 600519 怎么样？')
    await vi.advanceTimersByTimeAsync(1500)
    await vi.advanceTimersByTimeAsync(1500)
    await p

    expect(mockedPoll).toHaveBeenCalledTimes(2)
    const st = useXingchenStore.getState()
    const sid = st.activeId
    const msgs = st.sessions[sid].messages
    expect(msgs).toHaveLength(2)
    expect(msgs[0].kind).toBe('user')
    expect(msgs[1].kind).toBe('assistant')
    expect(msgs[1].status).toBe('done')
    expect(msgs[1].content).toBe('结论：看好')
    expect(msgs[1].chips?.length).toBeGreaterThan(0)
  })

  it('缺分析标的 → 不提交后端，生成缺参追问', async () => {
    const p = useXingchenStore.getState().submitQuestion('你好')
    await p
    expect(mockedSubmit).not.toHaveBeenCalled()
    expect(mockedPoll).not.toHaveBeenCalled()
    const st = useXingchenStore.getState()
    const msgs = st.sessions[st.activeId].messages
    expect(msgs).toHaveLength(2)
    expect(msgs[1].kind).toBe('param-prompt')
  })

  it('取消 → 调 cancelAiConsult 并将流式消息置为 error', async () => {
    mockedSubmit.mockResolvedValue('t1')
    mockedPoll.mockResolvedValue(RUNNING as never)

    vi.useFakeTimers()
    const p = useXingchenStore.getState().submitQuestion('茅台 600519')
    // 推进微任务，使 runningTaskId 被设置（submitAiConsult resolve + set）
    await vi.advanceTimersByTimeAsync(0)
    await useXingchenStore.getState().cancelCurrent()

    expect(mockedCancel).toHaveBeenCalledWith('t1')
    const st = useXingchenStore.getState()
    const msgs = st.sessions[st.activeId].messages
    const a = msgs.find((m) => m.kind === 'assistant')
    expect(a?.status).toBe('error')
    expect(a?.errors?.[0]).toBe('已停止等待')
    void p // 让挂起的轮询自然结束，不阻塞测试
  })
})

describe('useXingchen 多会话持久化', () => {
  beforeEach(() => {
    resetXingchen()
    vi.mocked(listConversations).mockReset()
    vi.mocked(getConversationMessages).mockReset()
    vi.mocked(createConversation).mockReset()
    vi.mocked(deleteConversation).mockReset()
    vi.mocked(deleteConversation).mockResolvedValue(undefined)
    vi.mocked(exportConversationMarkdown).mockReset()
    vi.mocked(getChatHistory).mockReset()
  })

  it('bootstrap：列表非空 → 建会话并拉取首条消息', async () => {
    vi.mocked(listConversations).mockResolvedValue({
      conversations: [{ id: 5, title: '茅台研判', updated_at: '2026-11-13T10:00:00Z' }],
    } as never)
    vi.mocked(getConversationMessages).mockResolvedValue({
      id: 5,
      title: '茅台研判',
      messages: [{ role: 'user', content: '分析茅台', ts: 1763023200 }],
    } as never)

    await useXingchenStore.getState().bootstrap()

    const st = useXingchenStore.getState()
    expect(st.order).toContain('s-5')
    expect(st.activeId).toBe('s-5')
    const s = st.sessions['s-5']
    expect(s.convId).toBe(5)
    expect(s.loaded).toBe(true)
    expect(s.messages).toHaveLength(1)
    expect(s.messages[0].kind).toBe('user')
  })

  it('bootstrap：列表 404 → 回退旧单记录历史', async () => {
    vi.mocked(listConversations).mockRejectedValue(new Error('404'))
    vi.mocked(getChatHistory).mockResolvedValue({
      messages: [{ role: 'user', content: '旧历史', ts: 1763023200 }],
    } as never)

    await useXingchenStore.getState().bootstrap()

    const st = useXingchenStore.getState()
    expect(st.order).toContain('s-legacy')
    expect(st.activeId).toBe('s-legacy')
    expect(st.sessions['s-legacy'].messages[0].content).toBe('旧历史')
  })

  it('openConversation：拉取会话消息并标记 loaded', async () => {
    useXingchenStore.setState({
      sessions: {
        's-9': { id: 's-9', convId: 9, messages: [], createdAt: 1, updatedAt: 1, loaded: false },
      },
      order: ['s-9'],
      activeId: 's-9',
    })
    vi.mocked(getConversationMessages).mockResolvedValue({
      id: 9,
      title: '已读',
      messages: [{ role: 'assistant', content: '你好', ts: 1 }],
    } as never)

    await useXingchenStore.getState().openConversation(9)
    const s = useXingchenStore.getState().sessions['s-9']
    expect(s.loaded).toBe(true)
    expect(s.messages[0].kind).toBe('assistant')
  })

  it('deleteSession：有 convId → 调 deleteConversation', async () => {
    useXingchenStore.setState({
      sessions: {
        's-3': { id: 's-3', convId: 3, messages: [], createdAt: 1, updatedAt: 1 },
      },
      order: ['s-3'],
      activeId: 's-3',
    })
    await useXingchenStore.getState().deleteSession('s-3')
    expect(deleteConversation).toHaveBeenCalledWith(3)
    expect(useXingchenStore.getState().sessions['s-3']).toBeUndefined()
  })

  it('exportSession：markdown → 调 exportConversationMarkdown', async () => {
    useXingchenStore.setState({
      sessions: {
        's-7': { id: 's-7', convId: 7, title: '对话7', messages: [], createdAt: 1, updatedAt: 1 },
      },
      order: ['s-7'],
    })
    vi.mocked(exportConversationMarkdown).mockResolvedValue('# 对话7\n\n')
    await useXingchenStore.getState().exportSession('s-7', 'markdown')
    expect(exportConversationMarkdown).toHaveBeenCalledWith(7)
  })
})

