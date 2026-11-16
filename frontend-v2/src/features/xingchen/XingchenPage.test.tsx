import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

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

import { listConversations } from '@/api/chat'
import { resetXingchen, useXingchenStore } from './useXingchen'
import { XingchenPage } from './XingchenPage'

describe('XingchenPage', () => {
  beforeEach(() => {
    resetXingchen()
    vi.mocked(listConversations).mockReset()
  })

  it('挂载即 bootstrap，渲染侧栏 + 空态 hero', async () => {
    vi.mocked(listConversations).mockResolvedValue({ conversations: [] } as never)
    render(<XingchenPage />)
    // 侧栏头部
    expect(screen.getByText('对话')).toBeTruthy()
    expect(screen.getByText('＋ 新对话')).toBeTruthy()
    // 空态 hero（ChatPanel）
    expect(screen.getByText('🌟 星辰 AI')).toBeTruthy()
    // 输入框常驻可见：高度链塌陷时最容易整块消失的部分
    expect(screen.getByPlaceholderText(/问点什么/)).toBeTruthy()
    // 主动重取入口
    expect(screen.getByRole('button', { name: /重新载入会话/ })).toBeTruthy()
  })

  it('会话载入中显示状态条，不把空白当成正常', () => {
    vi.mocked(listConversations).mockImplementation(() => new Promise(() => {}))
    useXingchenStore.setState({ booting: true })
    render(<XingchenPage />)
    expect(screen.getByRole('status').textContent).toContain('正在载入历史会话')
    // 加载中也保留可解释空态与输入框，绝不白屏
    expect(screen.getByText('🌟 星辰 AI')).toBeTruthy()
    expect(screen.getByPlaceholderText(/问点什么/)).toBeTruthy()
    useXingchenStore.setState({ booting: false })
  })
})
