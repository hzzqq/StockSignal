import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button } from './Button'

const buttonOf = (container: HTMLElement) => container.querySelector('button')!

describe('Button · 四变体 / 属性透传 / 无障碍', () => {
  it('primary / secondary / ghost / danger 四变体均渲染且带对应令牌类', () => {
    const { rerender, container } = render(<Button variant="primary">主按钮</Button>)
    expect(buttonOf(container).className).toContain('from-brand-1')
    expect(screen.getByRole('button', { name: '主按钮' })).toBeTruthy()

    rerender(<Button variant="secondary">次按钮</Button>)
    expect(buttonOf(container).className).toContain('bg-sf-surface-2')
    expect(buttonOf(container).className).toContain('border-sf-line')

    rerender(<Button variant="ghost">幽灵按钮</Button>)
    expect(buttonOf(container).className).toContain('bg-transparent')

    rerender(<Button variant="danger">危险按钮</Button>)
    expect(buttonOf(container).className).toContain('bg-sf-danger-soft')
    expect(buttonOf(container).className).toContain('text-sf-danger')
  })

  it('disabled / type / aria-* 标准属性透传', () => {
    render(
      <Button disabled type="submit" aria-label="提交表单">
        提交
      </Button>,
    )
    const btn = screen.getByRole('button', { name: '提交表单' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.type).toBe('submit')
    expect(btn.className).toContain('disabled:opacity-50')
  })

  it('onClick 触发一次，默认 type=button 避免误提交', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>点我</Button>)
    const btn = screen.getByRole('button', { name: '点我' }) as HTMLButtonElement
    expect(btn.type).toBe('button')
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('className 与基础类合并，不互相覆盖', () => {
    render(<Button className="w-full">宽按钮</Button>)
    const cls = screen.getByRole('button', { name: '宽按钮' }).className
    expect(cls).toContain('w-full')
    expect(cls).toContain('rounded-tile')
    expect(cls).toContain('hover:shadow-e2')
  })

  it('sm / md 两档尺寸使用字号令牌，不写死 px', () => {
    const { rerender, container } = render(<Button size="sm">小</Button>)
    expect(buttonOf(container).className).toContain('text-label')
    rerender(<Button size="md">中</Button>)
    expect(buttonOf(container).className).toContain('text-body')
  })
})
