import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '@/api/schemas/chat'
import { MessageBubble } from './MessageBubble'
import { Composer } from './Composer'
import { ModelBadge } from './ModelBadge'
import type { XcStyle } from './intent'

/** 消息流容器：顶栏 ModelBadge + 自动滚到底部 + 回到底部按钮 + Composer。 */
export function ChatPanel({
  messages,
  model,
  style,
  isRunning = false,
  onStyleChange,
  onSend,
  onStop,
  onPickChip,
  onPickParam,
}: {
  messages: ChatMessage[]
  model?: string
  style: XcStyle
  isRunning?: boolean
  onStyleChange: (s: XcStyle) => void
  onSend: (q: string) => void
  onStop?: () => void
  onPickChip?: (c: string) => void
  onPickParam?: (p: string) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [showJump, setShowJump] = useState(false)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    if (nearBottom) el.scrollTop = el.scrollHeight
  }, [messages])

  function onScroll() {
    const el = scrollRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    setShowJump(!nearBottom)
  }

  function jumpToBottom() {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
    setShowJump(false)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-sf-line px-4 py-2">
        <h2 className="text-title font-medium text-sf-ink-2">星辰 AI</h2>
        <ModelBadge model={model} />
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="absolute inset-0 space-y-3 overflow-y-auto px-4 py-4"
        >
          {messages.length === 0 ? (
            <div className="flex h-full items-center justify-center text-center">
              <div className="text-sf-ink-3">
                <div className="text-title text-sf-ink-2">🌟 星辰 AI</div>
                <p className="mt-2 text-body">把你的投资疑问抛过来，我来帮你拆解研判。</p>
              </div>
            </div>
          ) : (
            messages.map((m) => (
              <MessageBubble key={m.id} msg={m} onPickChip={onPickChip} onPickParam={onPickParam} />
            ))
          )}
        </div>

        {showJump && (
          <button
            type="button"
            onClick={jumpToBottom}
            aria-label="回到底部"
            className="absolute bottom-4 right-4 flex h-9 w-9 items-center justify-center rounded-full border border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
          >
            ↓
          </button>
        )}
      </div>

      <div className="border-t border-sf-line p-3">
        <Composer
          style={style}
          onStyleChange={onStyleChange}
          onSend={onSend}
          onStop={onStop}
          isRunning={isRunning}
        />
      </div>
    </div>
  )
}
