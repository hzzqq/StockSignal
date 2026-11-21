import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'

vi.mock('@/api/chat', () => ({
  submitAiConsult: vi.fn(),
  submitAiResearch: vi.fn(),
  getAiConsultTask: vi.fn(),
  cancelAiConsult: vi.fn(),
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversationMessages: vi.fn(),
  saveConversationMessages: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  exportConversationJson: vi.fn(),
  exportConversationMarkdown: vi.fn(),
  getChatHistory: vi.fn(),
}))

import { submitAiConsult, getAiConsultTask } from '@/api/chat'
import { useXingchenStore, resetXingchen, useXingchenRunning } from './useXingchen'
import { MessageBubble } from './MessageBubble'
import type { ChatMessage } from '@/api/schemas/chat'

const RUNNING_TASK = {
  task_id: 't-guard',
  task_type: 'ai_consult',
  status: 'running',
  progress: 0.4,
  stage: 'analyzing',
  logs: [],
  result: null,
}
const SUCCESS_TASK = {
  ...RUNNING_TASK,
  status: 'success',
  progress: 1,
  stage: 'done',
  result: { answer: '结论：看好', independent: true },
}

/** 顶栏徽标消费者：验证只读 hook useXingchenRunning 的订阅行为。 */
function RunBadge() {
  const running = useXingchenRunning()
  return <span>{running ? 'RUNNING_BADGE' : 'IDLE_BADGE'}</span>
}

/** 模拟「页面」：卸载它即等价于切走路由（不调用 cancelCurrent）。 */
function XingchenView() {
  const sessions = useXingchenStore((s) => s.sessions)
  const runningTaskId = useXingchenStore((s) => s.runningTaskId)
  const msgs = Object.values(sessions).flatMap((s) => s.messages)
  return (
    <div>
      <RunBadge />
      <span data-testid="task">{runningTaskId ?? 'none'}</span>
      <span data-testid="msg-count">{msgs.length}</span>
    </div>
  )
}

describe('星辰 AI 运行中切页不打断（守卫）', () => {
  beforeEach(() => {
    resetXingchen()
    vi.clearAllMocks()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('运行中卸载组件（导航离开）→ 后台任务继续，store 仍持有消息与 runningTaskId', async () => {
    vi.mocked(submitAiConsult).mockResolvedValue('t-guard')
    vi.mocked(getAiConsultTask).mockResolvedValue(RUNNING_TASK as never)

    vi.useFakeTimers()
    const p = useXingchenStore.getState().submitQuestion('茅台 600519 怎么样？')
    // 推进微任务：submitAiConsult resolve，runningTaskId 落位，开始等待首次轮询
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    const view = render(<XingchenView />)
    expect(screen.getByText('RUNNING_BADGE')).toBeTruthy()
    expect(screen.getByTestId('task').textContent).toBe('t-guard')
    expect(screen.getByTestId('msg-count').textContent).toBe('2')

    // 模拟切页：卸载组件，不触发 cancelCurrent，也没有 AbortController
    view.unmount()

    // 卸载不影响模块级 store：任务 id 与消息都还在
    const st = useXingchenStore.getState()
    expect(st.runningTaskId).toBe('t-guard')
    expect(Object.values(st.sessions).flatMap((s) => s.messages)).toHaveLength(2)

    // 轮询继续推进到 success：卸载组件并未打断运行
    vi.mocked(getAiConsultTask).mockResolvedValueOnce(SUCCESS_TASK as never)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    await p

    const st2 = useXingchenStore.getState()
    expect(st2.runningTaskId).toBeNull()
    const assistant = Object.values(st2.sessions)
      .flatMap((s) => s.messages)
      .find((m) => m.kind === 'assistant')!
    expect(assistant.status).toBe('done')
    expect(assistant.content).toBe('结论：看好')
  })

  it('揭示动画中途切页 → 重挂载后正文完整、动画不重播', async () => {
    const content = '结论：看好'
    // 刻意传 fresh:true 的旧对象给重挂载：即便 store 标记滞后，模块级 Set 也应阻止重播
    const freshMsg: ChatMessage = {
      id: 'guard-reveal-1',
      kind: 'assistant',
      role: 'assistant',
      content,
      status: 'done',
      fresh: true,
    }
    const sid = useXingchenStore.getState().createSession('揭示测试')
    useXingchenStore.getState().addMessage(sid, freshMsg)

    vi.useFakeTimers()
    // 首次进入：动画启动，正文尚未完整揭示
    const first = render(<MessageBubble msg={freshMsg} />)
    expect(screen.getByText('正在生成结论…')).toBeTruthy()
    expect(screen.queryByText(content)).toBeNull()

    // 动画进行到一半即切页卸载
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200)
    })
    first.unmount()

    // store 里正文始终完整（揭示动画只裁渲染，不裁 store 内容）
    const stored = useXingchenStore.getState().sessions[sid].messages[0]
    expect(stored.content).toBe(content)

    // 切回：同一消息重挂载，直接显示全文，无「正在生成结论…」，显示「分析完成」
    render(<MessageBubble msg={freshMsg} />)
    expect(screen.getByText(content)).toBeTruthy()
    expect(screen.queryByText('正在生成结论…')).toBeNull()
    expect(screen.getByText('分析完成')).toBeTruthy()
  })
})
