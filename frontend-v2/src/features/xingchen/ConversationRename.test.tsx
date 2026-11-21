import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

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

import { renameConversation } from '@/api/chat'
import { ApiError } from '@/api/client'
import { useXingchenStore, resetXingchen } from './useXingchen'
import { ConversationSidebar } from './ConversationSidebar'

function seed(id: string, patch: Record<string, unknown> = {}): void {
  useXingchenStore.setState((st) => ({
    sessions: {
      ...st.sessions,
      [id]: {
        id,
        title: '旧标题',
        messages: [],
        createdAt: 1,
        updatedAt: 1,
        convId: 12,
        ...patch,
      },
    },
    order: [...st.order, id],
    activeId: id,
  }))
}

describe('会话重命名（守卫）', () => {
  beforeEach(() => {
    resetXingchen()
    vi.clearAllMocks()
  })

  it('有 convId：乐观更新即时可见 → 调 PATCH 接口 → 服务端标题回填', async () => {
    seed('s-1')
    vi.mocked(renameConversation).mockResolvedValue({ id: 12, title: '新标题' })

    const p = useXingchenStore.getState().renameSession('s-1', '  新标题  ')
    // async action 在第一个 await 之前同步完成乐观更新
    expect(useXingchenStore.getState().sessions['s-1'].title).toBe('新标题')

    const r = await p
    expect(renameConversation).toHaveBeenCalledWith(12, '新标题')
    expect(r).toEqual({ persisted: true, title: '新标题' })
    expect(useXingchenStore.getState().sessions['s-1'].title).toBe('新标题')
  })

  it('失败：回滚内存标题并抛中文错误，不静默吞', async () => {
    seed('s-1')
    vi.mocked(renameConversation).mockRejectedValue(
      new ApiError('server_error', '会话不存在或无权修改'),
    )

    await expect(
      useXingchenStore.getState().renameSession('s-1', '改坏标题'),
    ).rejects.toThrow('重命名失败：会话不存在或无权修改')
    expect(useXingchenStore.getState().sessions['s-1'].title).toBe('旧标题')
  })

  it('无 convId：仅本地改名，如实标注未持久化且不调接口', async () => {
    seed('s-2', { convId: undefined })
    const r = await useXingchenStore.getState().renameSession('s-2', '本地名')
    expect(renameConversation).not.toHaveBeenCalled()
    expect(r).toEqual({ persisted: false, title: '本地名' })
    expect(useXingchenStore.getState().sessions['s-2'].title).toBe('本地名')
  })

  it('规范化：空标题回退「新对话」，超长截断到 40 字（与后端一致）', async () => {
    seed('s-e', { convId: undefined })
    const empty = await useXingchenStore.getState().renameSession('s-e', '   ')
    expect(empty.title).toBe('新对话')

    seed('s-l', { convId: undefined, title: '长标题' })
    const long = await useXingchenStore.getState().renameSession('s-l', 'x'.repeat(50))
    expect(long.title).toHaveLength(40)
  })

  it('侧栏：点铅笔 → 内联编辑（预填当前标题）→ Enter 保存并 trim', async () => {
    seed('s-1')
    vi.mocked(renameConversation).mockResolvedValue({ id: 12, title: '界面改名' })
    render(<ConversationSidebar />)

    fireEvent.click(screen.getByLabelText('重命名对话'))
    const input = screen.getByLabelText('重命名输入') as HTMLInputElement
    expect(input.value).toBe('旧标题')
    fireEvent.change(input, { target: { value: '  界面改名  ' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    await waitFor(() => expect(renameConversation).toHaveBeenCalledWith(12, '界面改名'))
    expect(screen.getByText('界面改名')).toBeTruthy()
  })

  it('侧栏：Esc 取消编辑，不调接口、不改标题', () => {
    seed('s-1')
    render(<ConversationSidebar />)

    fireEvent.click(screen.getByLabelText('重命名对话'))
    const input = screen.getByLabelText('重命名输入')
    fireEvent.change(input, { target: { value: '不要保存' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(screen.queryByLabelText('重命名输入')).toBeNull()
    expect(renameConversation).not.toHaveBeenCalled()
    expect(useXingchenStore.getState().sessions['s-1'].title).toBe('旧标题')
  })
})
