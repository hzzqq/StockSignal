import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

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

import { exportConversationMarkdown, deleteConversation } from '@/api/chat'
import { useXingchenStore, resetXingchen } from './useXingchen'
import { ConversationSidebar } from './ConversationSidebar'

describe('ConversationSidebar', () => {
  beforeEach(() => {
    resetXingchen()
    vi.mocked(exportConversationMarkdown).mockReset()
    vi.mocked(deleteConversation).mockResolvedValue(undefined)
  })

  it('列出会话并提供新建按钮', () => {
    useXingchenStore.getState().createSession('茅台研判')
    useXingchenStore.getState().createSession('宁德时代')
    render(<ConversationSidebar />)
    expect(screen.getByText('茅台研判')).toBeTruthy()
    expect(screen.getByText('宁德时代')).toBeTruthy()
    expect(screen.getByText('＋ 新对话')).toBeTruthy()
  })

  it('点击「新对话」→ 新增一条会话', () => {
    render(<ConversationSidebar />)
    fireEvent.click(screen.getByText('＋ 新对话'))
    expect(useXingchenStore.getState().order.length).toBe(1)
  })

  it('点击删除 → 移除会话并调用 deleteConversation', () => {
    const st = useXingchenStore.getState()
    const id = st.createSession('待删')
    useXingchenStore.setState((s) => ({
      sessions: { ...s.sessions, [id]: { ...s.sessions[id], convId: 3 } },
    }))
    render(<ConversationSidebar />)
    const del = screen.getAllByLabelText('删除对话')[0]
    fireEvent.click(del)
    expect(useXingchenStore.getState().sessions[id]).toBeUndefined()
  })

  it('导出 MD → 调 exportConversationMarkdown（带 convId）', () => {
    const st = useXingchenStore.getState()
    const id = st.createSession('导出测试')
    useXingchenStore.setState((s) => ({
      sessions: { ...s.sessions, [id]: { ...s.sessions[id], convId: 7 } },
    }))
    vi.mocked(exportConversationMarkdown).mockResolvedValue('# 导出测试\n\n')
    render(<ConversationSidebar />)
    const mdBtn = screen.getAllByText('MD')[0]
    fireEvent.click(mdBtn)
    expect(exportConversationMarkdown).toHaveBeenCalledWith(7)
  })
})
