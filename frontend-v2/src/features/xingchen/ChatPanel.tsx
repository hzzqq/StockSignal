import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '@/api/schemas/chat'
import { MessageBubble } from './MessageBubble'
import { Composer } from './Composer'
import { ModelBadge } from './ModelBadge'
import { SuggestionChips } from './SuggestionChips'
import type { XcStyle } from './intent'

/** 空态引导问题：点击即发送，不假装有预设答案、不伪造行情数值。 */
const STARTER_QUESTIONS = [
  '今日大盘怎么看？',
  '分析贵州茅台 600519',
  '半导体板块有哪些机会？',
  '止损应该怎么设？',
]

/**
 * 消息流容器：顶栏 ModelBadge + 自动滚到底部 + 回到底部按钮 + Composer。
 *
 * 2026-11-16 空白页根治：原实现把滚动区用 `absolute inset-0` 钉在一个
 * `relative flex-1` 里，而 AppShell <main> 没有确定高度（html/body/#root 未设高、
 * 外壳只有 min-h-screen、main 缺 min-h-0），百分比高度链一断，滚动区高度算成 0，
 * 欢迎语与 Composer 整块消失，表现为「页面是空的」。
 * 现改为正常弹性列：滚动区自身就是 flex-1 可滚动元素并带 min-h-[240px]，
 * 即使外层高度仍不确定，顶栏 / 空态 / 输入框也会依次可见，绝不再整片塌陷。
 */
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
    <div className="relative flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-sf-line px-4 py-2">
        <h2 className="text-title font-medium text-sf-ink-2">星辰 AI</h2>
        <ModelBadge model={model} />
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-[240px] flex-1 space-y-3 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 ? (
          <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
            <div className="text-title text-sf-ink-2">🌟 星辰 AI</div>
            <p className="text-body text-sf-ink-3">把你的投资疑问抛过来，我来帮你拆解研判。</p>
            <p className="max-w-md text-label text-sf-ink-3">
              回答基于本系统已有数据与规则引擎，不提供实时行情，不构成投资建议。
            </p>
            <SuggestionChips chips={STARTER_QUESTIONS} onPick={onPickChip} />
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
          className="absolute bottom-28 right-4 flex h-9 w-9 items-center justify-center rounded-full border border-sf-line bg-sf-surface-2 text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
        >
          ↓
        </button>
      )}

      <div className="shrink-0 border-t border-sf-line p-3">
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
