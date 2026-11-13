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
}))

import { submitAiConsult, getAiConsultTask, cancelAiConsult } from '@/api/chat'
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
