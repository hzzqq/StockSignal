import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * 精致层次档 · 轻量 Toast（页面级局部状态，不引入全局 Context Provider）。
 * tone 只用 sf-ok / sf-warn / sf-danger / sf-accent 状态令牌，绝不用涨跌色。
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

export function useToast(): UseToast {
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
