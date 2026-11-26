import { useCallback, useContext, useEffect, useRef, useState, createContext } from 'react'
import type { ReactNode } from 'react'

/**
 * 精致层次档 · 轻量 Toast（全局 Provider 版）。
 * tone 只用 sf-ok / sf-warn / sf-danger / sf-accent 状态令牌，绝不用涨跌色。
 *
 * 用法：应用根部（providers.tsx）挂一次 <ToastProvider>（自带 ToastViewport 渲染），
 * 任意页面组件内 const { push } = useToast(); push('消息', 'ok') 即可。
 * 兼容性：无 Provider 时 useToast 返回 no-op（toasts 恒空、push/dismiss 静默丢弃），
 * 纯组件单测 / renderToStaticMarkup 等场景不崩、不吐 toast——有意选择 no-op 而非 throw，
 * 因为 toast 是纯增强型反馈，缺失 Provider 不应让页面渲染失败。
 */
export type ToastTone = 'ok' | 'warn' | 'danger' | 'info'

export interface ToastItem {
  id: string
  message: string
  tone: ToastTone
}

export interface UseToast {
  toasts: ToastItem[]
  push: (message: string, tone?: ToastTone) => string
  dismiss: (id: string) => void
}

const TIMEOUT_MS = 4000

/** 内部状态实现：Provider 持有，页面只读。 */
function useToastStore(): UseToast {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())
  const seq = useRef(0)

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback((message: string, tone: ToastTone = 'info') => {
    const id = `toast-${++seq.current}`
    setToasts((prev) => [...prev, { id, message, tone }])
    const timer = setTimeout(() => {
      timers.current.delete(id)
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, TIMEOUT_MS)
    timers.current.set(id, timer)
    return id
  }, [])

  useEffect(
    () => () => {
      timers.current.forEach((timer) => clearTimeout(timer))
      timers.current.clear()
    },
    [],
  )

  return { toasts, push, dismiss }
}

/** 无 Provider 时的默认值：全 no-op（见文件头注释）。 */
const NOOP_TOAST_API: UseToast = {
  toasts: [],
  push: () => '',
  dismiss: () => {},
}

const ToastContext = createContext<UseToast>(NOOP_TOAST_API)

/** 全局 Toast Provider：持有状态，并在根部代渲染 ToastViewport（页面无需再挂）。 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const store = useToastStore()
  return (
    <ToastContext.Provider value={store}>
      {children}
      <ToastViewport toasts={store.toasts} onDismiss={store.dismiss} />
    </ToastContext.Provider>
  )
}

/** 消费全局 Toast：必须在 <ToastProvider> 内调用，否则得到 no-op（不崩、不显示）。 */
export function useToast(): UseToast {
  return useContext(ToastContext)
}

const TONE_CLASS: Record<
  ToastTone,
  { text: string; dot: string; role: 'status' | 'alert' }
> = {
  ok: { text: 'text-sf-ok', dot: 'bg-sf-ok', role: 'status' },
  warn: { text: 'text-sf-warn', dot: 'bg-sf-warn', role: 'alert' },
  danger: { text: 'text-sf-danger', dot: 'bg-sf-danger', role: 'alert' },
  info: { text: 'text-sf-accent', dot: 'bg-sf-accent', role: 'status' },
}

const cx = (...parts: Array<string | false | null | undefined>) =>
  parts.filter(Boolean).join(' ')

export interface ToastViewportProps {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

export function ToastViewport({ toasts, onDismiss }: ToastViewportProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-72 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((toast) => {
        const tone = TONE_CLASS[toast.tone]
        return (
          <div
            key={toast.id}
            role={tone.role}
            className="flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2 shadow-e3"
          >
            <span
              aria-hidden="true"
              className={cx('mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full', tone.dot)}
            />
            <span className={cx('flex-1 text-body', tone.text)}>{toast.message}</span>
            <button
              type="button"
              aria-label={`关闭提示：${toast.message}`}
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 rounded-tile text-label text-sf-ink-3 hover:text-sf-ink"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 16 16"
                fill="none"
                className="h-3.5 w-3.5"
              >
                <path
                  d="m4 4 8 8m0-8-8 8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          </div>
        )
      })}
    </div>
  )
}
