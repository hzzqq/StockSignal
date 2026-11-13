import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatPanel } from './ChatPanel'
import type { ChatMessage } from '@/api/schemas/chat'

const msgs: ChatMessage[] = [
  { id: 'u1', kind: 'user', role: 'user', content: '茅台怎么看', status: 'done', ts: 1763023200 },
  {
    id: 'a1',
    kind: 'assistant',
    role: 'assistant',
    content: '结论是看好',
    status: 'done',
    ts: 1763023260,
  },
]

describe('ChatPanel', () => {
  it('空消息 → 显示欢迎 hero', () => {
    render(
      <ChatPanel
        messages={[]}
        style="quick"
        onStyleChange={() => {}}
        onSend={() => {}}
      />,
    )
    expect(screen.getByText('🌟 星辰 AI')).toBeTruthy()
  })

  it('渲染消息流', () => {
    render(
      <ChatPanel messages={msgs} style="quick" onStyleChange={() => {}} onSend={() => {}} />,
    )
    expect(screen.getByText('茅台怎么看')).toBeTruthy()
    expect(screen.getByText('结论是看好')).toBeTruthy()
  })

  it('顶部显示模型徽标（诚实态）', () => {
    const { rerender } = render(
      <ChatPanel messages={[]} style="quick" onStyleChange={() => {}} onSend={() => {}} />,
    )
    expect(screen.getByText('规则引擎模式')).toBeTruthy()
    rerender(
      <ChatPanel
        messages={[]}
        model="gpt-4o"
        style="quick"
        onStyleChange={() => {}}
        onSend={() => {}}
      />,
    )
    expect(screen.getByText('gpt-4o')).toBeTruthy()
  })

  it('在输入框发送 → onSend 被调用', () => {
    const onSend = vi.fn()
    render(
      <ChatPanel messages={msgs} style="quick" onStyleChange={() => {}} onSend={onSend} />,
    )
    const ta = screen.getByPlaceholderText(/问点什么/) as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '再问一句' } })
    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('再问一句')
  })
})
