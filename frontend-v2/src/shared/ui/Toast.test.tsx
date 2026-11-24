import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { useToast, ToastViewport } from './Toast'
import type { ToastItem, UseToast } from './Toast'

let api!: UseToast

function Harness() {
  api = useToast()
  return <ToastViewport toasts={api.toasts} onDismiss={api.dismiss} />
}

const toasts = (items: ToastItem[]) => (
  <ToastViewport toasts={items} onDismiss={() => {}} />
)

describe('Toast · useToast + ToastViewport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('push 后渲染消息，tone 对应状态色与 role', () => {
    render(<Harness />)
    act(() => {
      api.push('保存成功', 'ok')
      api.push('磁盘不足', 'warn')
      api.push('删除失败', 'danger')
      api.push('普通提示')
    })
    expect(screen.getByText('保存成功').className).toContain('text-sf-ok')
    expect(screen.getByText('磁盘不足').className).toContain('text-sf-warn')
    expect(screen.getByText('删除失败').className).toContain('text-sf-danger')
    expect(screen.getByText('普通提示').className).toContain('text-sf-accent')
    expect(screen.getAllByRole('status').length).toBe(2)
    expect(screen.getAllByRole('alert').length).toBe(2)
  })

  it('push 后 4s 自动移除（阈值前后各验一次）', () => {
    render(<Harness />)
    act(() => {
      api.push('稍后消失')
    })
    expect(screen.getByText('稍后消失')).toBeTruthy()
    act(() => {
      vi.advanceTimersByTime(3999)
    })
    expect(screen.getByText('稍后消失')).toBeTruthy()
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(screen.queryByText('稍后消失')).toBeNull()
  })

  it('dismiss 手动移除，且原定时器被清除', () => {
    render(<Harness />)
    act(() => {
      api.push('手动关闭', 'danger')
    })
    const close = screen.getByRole('button', { name: /关闭提示：手动关闭/ })
    fireEvent.click(close)
    expect(screen.queryByText('手动关闭')).toBeNull()
    act(() => {
      vi.advanceTimersByTime(4000)
    })
    expect(screen.queryByText('手动关闭')).toBeNull()
  })

  it('Viewport 固定右下角 + shadow-e3，传 toasts 可独立渲染', () => {
    const { container } = render(
      toasts([{ id: 'a', message: '只读取', tone: 'warn' }]),
    )
    const viewport = container.firstElementChild as HTMLElement
    expect(viewport.className).toContain('fixed')
    expect(viewport.className).toContain('bottom-4')
    expect(viewport.className).toContain('right-4')
    expect(viewport.firstElementChild!.className).toContain('shadow-e3')
    expect(viewport.firstElementChild!.className).toContain('border-sf-line')
  })

  it('卸载时清理未触发的定时器', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearTimeout')
    const { unmount } = render(<Harness />)
    act(() => {
      api.push('卸载清理')
    })
    const before = clearSpy.mock.calls.length
    unmount()
    expect(clearSpy.mock.calls.length).toBeGreaterThan(before)
  })
})
