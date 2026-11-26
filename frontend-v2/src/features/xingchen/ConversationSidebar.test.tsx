import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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

  it('点击删除 → 就地二次确认后移除会话并调用 deleteConversation', () => {
    const st = useXingchenStore.getState()
    const id = st.createSession('待删')
    useXingchenStore.setState((s) => ({
      sessions: { ...s.sessions, [id]: { ...s.sessions[id], convId: 3 } },
    }))
    render(<ConversationSidebar />)
    // 单击只进入确认态，绝不立即删除
    fireEvent.click(screen.getAllByLabelText('删除对话')[0])
    expect(useXingchenStore.getState().sessions[id]).toBeDefined()
    expect(screen.getByLabelText('确认删除对话')).toBeTruthy()
    // 确认按钮才真正执行删除
    fireEvent.click(screen.getByLabelText('确认删除对话'))
    expect(deleteConversation).toHaveBeenCalledWith(3)
    expect(useXingchenStore.getState().sessions[id]).toBeUndefined()
  })

  it('删除确认态点「取消」→ 不删除会话', () => {
    const id = useXingchenStore.getState().createSession('保留')
    render(<ConversationSidebar />)
    fireEvent.click(screen.getAllByLabelText('删除对话')[0])
    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByLabelText('确认删除对话')).toBeNull()
    expect(useXingchenStore.getState().sessions[id]).toBeDefined()
    expect(deleteConversation).not.toHaveBeenCalled()
  })

  it('后端删除失败 → 会话回滚到原 order 位置并显示错误提示', async () => {
    const st = useXingchenStore.getState()
    const a = st.createSession('会话A')
    const id = st.createSession('会话B')
    const c = st.createSession('会话C')
    useXingchenStore.setState((s) => ({
      sessions: { ...s.sessions, [id]: { ...s.sessions[id], convId: 9 } },
      activeId: id,
    }))
    vi.mocked(deleteConversation).mockRejectedValue(new Error('后端 500'))
    render(<ConversationSidebar />)
    fireEvent.click(screen.getAllByLabelText('删除对话')[1])
    fireEvent.click(screen.getByLabelText('确认删除对话'))

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('删除失败，请重试')
    })
    const state = useXingchenStore.getState()
    expect(state.sessions[id]).toBeDefined()
    expect(state.order).toEqual([a, id, c])
    expect(state.activeId).toBe(id)

    // 错误提示可手动关闭（clearDeleteError 入口）
    fireEvent.click(screen.getByLabelText('关闭错误提示'))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(useXingchenStore.getState().deleteError).toBeNull()
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
