import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ErrorState, QueryState } from './States'

describe('ErrorState · 可选页内重试', () => {
  it('无 onRetry：只渲染错误文案，无重试按钮（零视觉回归）', () => {
    const { container } = render(<ErrorState message="加载失败" />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('加载失败')
    expect(screen.queryByRole('button')).toBeNull()
    // 容器内仍只有琥珀点 + 文案两个 span，无多余空节点
    expect(alert.children).toHaveLength(2)
    expect(alert.className).toContain('border-sf-line')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })

  it('有 onRetry：点击「重试」按钮触发回调一次', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="加载失败" onRetry={onRetry} />)
    const btn = screen.getByRole('button', { name: '重试' }) as HTMLButtonElement
    expect(btn.textContent).toBe('重试')
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('retrying=true：按钮 disabled 且文案为「重试中…」', () => {
    const onRetry = vi.fn()
    render(<ErrorState message="加载失败" onRetry={onRetry} retrying />)
    const btn = screen.getByRole('button', { name: '重试中…' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.textContent).toBe('重试中…')
  })
})

describe('QueryState · 错误分支透传重试参数', () => {
  it('isError 时把 onRetry / retrying 透传给 ErrorState', () => {
    const onRetry = vi.fn()
    render(
      <QueryState
        isLoading={false}
        isError
        error={new Error('网络错误')}
        onRetry={onRetry}
        retrying
      >
        <div>有数据时才显示</div>
      </QueryState>,
    )
    expect(screen.getByRole('alert').textContent).toContain('网络错误')
    const btn = screen.getByRole('button', { name: '重试中…' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    fireEvent.click(btn)
    expect(onRetry).not.toHaveBeenCalled()
  })
})
