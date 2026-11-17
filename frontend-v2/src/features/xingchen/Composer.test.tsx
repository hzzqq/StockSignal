import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Composer } from './Composer'

describe('Composer', () => {
  it('输入 + Enter 发送', () => {
    const onSend = vi.fn()
    render(<Composer style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={onSend} />)
    const ta = screen.getByPlaceholderText(/问点什么/) as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '茅台怎么看' } })
    fireEvent.keyDown(ta, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('茅台怎么看')
  })

  it('点击发送按钮发送', () => {
    const onSend = vi.fn()
    render(<Composer style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={onSend} />)
    const ta = screen.getByPlaceholderText(/问点什么/) as HTMLTextAreaElement
    fireEvent.change(ta, { target: { value: '大盘' } })
    fireEvent.click(screen.getByText('发送'))
    expect(onSend).toHaveBeenCalledWith('大盘')
  })

  it('运行中禁用发送、显示停止按钮', () => {
    const onStop = vi.fn()
    render(
      <Composer
        style="quick"
        mode="quick"
        onStyleChange={() => {}}
        onModeChange={() => {}}
        onSend={() => {}}
        onStop={onStop}
        isRunning
      />,
    )
    expect(screen.getByText('发送').closest('button')?.hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByText(/停止生成/))
    expect(onStop).toHaveBeenCalled()
  })

  it('聚焦弹出快捷指令，点击直接发送', () => {
    const onSend = vi.fn()
    render(<Composer style="quick" mode="quick" onStyleChange={() => {}} onModeChange={() => {}} onSend={onSend} />)
    const ta = screen.getByPlaceholderText(/问点什么/) as HTMLTextAreaElement
    fireEvent.focus(ta)
    fireEvent.click(screen.getByText('半导体板块有哪些机会？'))
    expect(onSend).toHaveBeenCalledWith('半导体板块有哪些机会？')
  })
})

  it('深度研究模式：点击切换 → aria-pressed 变化并回调', () => {
    const onModeChange = vi.fn()
    render(
      <Composer style="quick" mode="quick" onStyleChange={() => {}}
        onModeChange={onModeChange} onSend={() => {}} />,
    )
    const btn = screen.getByRole('button', { name: '深度研究模式' })
    expect(btn.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(btn)
    expect(onModeChange).toHaveBeenCalledWith('research')
  })
