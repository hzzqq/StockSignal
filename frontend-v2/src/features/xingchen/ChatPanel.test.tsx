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
        mode="quick"
        onStyleChange={() => {}}
        onModeChange={() => {}}
        onSend={() => {}}
      />,
    )
    expect(screen.getByText('🌟 星辰 AI')).toBeTruthy()
  })

  it('空态引导问题点击即发送，且如实标注能力边界', () => {
    const onPickChip = vi.fn()
    render(
      <ChatPanel
        messages={[]}
        style="quick"
        mode="quick"
        onStyleChange={() => {}}
        onModeChange={() => {}}
        onSend={() => {}}
        onPickChip={onPickChip}
      />,
    )
    expect(screen.getByText(/不提供实时行情，不构成投资建议/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '今日大盘怎么看？' }))
    expect(onPickChip).toHaveBeenCalledWith('今日大盘怎么看？')
  })

  it('渲染消息流', () => {
    render(
      <ChatPanel messages={msgs} style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={() => {}} />,
    )
    expect(screen.getByText('茅台怎么看')).toBeTruthy()
    expect(screen.getByText('结论是看好')).toBeTruthy()
  })

  it('顶部显示模型徽标（诚实态）', () => {
    const { rerender } = render(
      <ChatPanel messages={[]} style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={() => {}} />,
    )
    // 诚实态：未探测模型配置时不得声称「规则引擎模式」/具体模型，只给中性文案
    const badge = screen.getByText('模型：跟随后端配置')
    expect(badge).toBeTruthy()
    expect(badge.getAttribute('title')).toContain('前端不探测模型配置')
    rerender(
      <ChatPanel
        messages={[]}
        model="gpt-4o"
        style="quick"
        mode="quick"
        onStyleChange={() => {}}
        onModeChange={() => {}}
        onSend={() => {}}
      />,
    )
    expect(screen.getByText('gpt-4o')).toBeTruthy()
    expect(screen.getByText('gpt-4o').getAttribute('title')).toContain('最终以服务端配置为准')
  })

  it('在输入框发送 → onSend 被调用', () => {
    const onSend = vi.fn()
    render(
      <ChatPanel messages={msgs} style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={onSend} />,
    )
    const ta = screen.getByPlaceholderText(/问点什么/) as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '再问一句' } })
    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('再问一句')
  })
})
