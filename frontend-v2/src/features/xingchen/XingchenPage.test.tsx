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
import { resetXingchen } from './useXingchen'
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
  })
})
