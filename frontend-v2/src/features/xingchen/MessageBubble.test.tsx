import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from './MessageBubble'
import type { ChatMessage } from '@/api/schemas/chat'

function msg(p: Partial<ChatMessage>): ChatMessage {
  return {
    id: 'm1',
    kind: 'assistant',
    role: 'assistant',
    content: '',
    ...p,
  } as ChatMessage
}

describe('MessageBubble 判别渲染', () => {
  it('user → 右气泡显示文本', () => {
    render(<MessageBubble msg={msg({ kind: 'user', content: '茅台怎么看' })} />)
    expect(screen.getByText('茅台怎么看')).toBeTruthy()
  })

  it('assistant 带正文 → 渲染 Markdown + 复制按钮', () => {
    render(<MessageBubble msg={msg({ content: '结论是 **看好**', status: 'done' })} />)
    expect(screen.getByText('结论是')).toBeTruthy()
    expect(screen.getByText('⧉ 复制')).toBeTruthy()
  })

  it('assistant 带 process → 渲染问题分析卡（默认折叠）', () => {
    render(<MessageBubble msg={msg({ content: 'x', status: 'done', process: ['步骤一'] })} />)
    expect(screen.queryByText('步骤一')).toBeNull()
  })

  it('assistant error → 错误态', () => {
    render(<MessageBubble msg={msg({ status: 'error', errors: ['后台开小差'] })} />)
    expect(screen.getByText('后台开小差')).toBeTruthy()
  })

  it('param-prompt → 缺参追问卡片', () => {
    render(
      <MessageBubble
        msg={msg({ kind: 'param-prompt', paramPrompt: ['请补充股票代码'] })}
      />,
    )
    expect(screen.getByText('需要补充一点信息')).toBeTruthy()
    expect(screen.getByText(/请补充股票代码/)).toBeTruthy()
  })
})
