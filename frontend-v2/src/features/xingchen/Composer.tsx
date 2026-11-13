import { useState, type KeyboardEvent } from 'react'
import { StyleSelector } from './StyleSelector'
import type { XcStyle } from './intent'

const QUICK_COMMANDS = [
  '分析贵州茅台 600519',
  '今日大盘怎么看？',
  '半导体板块有哪些机会？',
  '止损应该怎么设？',
  '新能源板块后市怎么走？',
]

/** 输入框（借鉴 FinPilot ChatInput）：液态玻璃输入 + 内嵌样式选择器 + 聚焦弹出快捷指令面板 + 发送/停止。 */
export function Composer({
  style,
  onStyleChange,
  onSend,
  onStop,
  isRunning = false,
}: {
  style: XcStyle
  onStyleChange: (s: XcStyle) => void
  onSend: (q: string) => void
  onStop?: () => void
  isRunning?: boolean
}) {
  const [text, setText] = useState('')
  const [quickOpen, setQuickOpen] = useState(false)
  const canSend = text.trim().length > 0 && !isRunning

  function send() {
    const q = text.trim()
    if (!q || isRunning) return
    onSend(q)
    setText('')
    setQuickOpen(false)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="rounded-card border border-sf-line bg-sf-surface p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <StyleSelector value={style} onChange={onStyleChange} />
        {isRunning && onStop && (
          <button
            type="button"
            onClick={onStop}
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-danger hover:text-sf-danger"
          >
            ⏹ 停止生成
          </button>
        )}
      </div>

      {quickOpen && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {QUICK_COMMANDS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => {
                setText(c)
                setQuickOpen(false)
                onSend(c)
              }}
              className="rounded-tile border border-sf-line bg-sf-surface-2 px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
            >
              {c}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setQuickOpen(true)}
          rows={2}
          placeholder="问点什么？Enter 发送，Shift+Enter 换行"
          className="min-h-[2.5rem] flex-1 resize-none rounded-tile border border-sf-line bg-sf-bg px-3 py-2 text-body text-sf-ink placeholder:text-sf-ink-3 focus:border-sf-accent"
        />
        <button
          type="button"
          onClick={send}
          disabled={!canSend}
          className="rounded-tile bg-brand-1 px-4 py-2 text-body text-white disabled:opacity-40"
        >
          发送
        </button>
      </div>
    </div>
  )
}
