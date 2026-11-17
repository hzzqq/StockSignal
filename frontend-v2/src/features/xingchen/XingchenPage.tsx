import { useEffect, useRef } from 'react'
import { useXingchen } from './useXingchen'
import { ConversationSidebar } from './ConversationSidebar'
import { ChatPanel } from './ChatPanel'
import { RetestButton } from '@/shared/ui/RetestButton'

/** 星辰 AI 页面容器：左侧会话侧栏 + 右侧对话面板。 */
export function XingchenPage() {
  const { bootstrap, active, style, mode, model, isRunning, booting, setStyle, setMode, submitQuestion, cancelCurrent } =
    useXingchen()
  const booted = useRef(false)

  useEffect(() => {
    if (!booted.current) {
      booted.current = true
      void bootstrap()
    }
  }, [bootstrap])

  const messages = active?.messages ?? []

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        {booting && (
          <span role="status" className="text-label text-sf-ink-3">
            正在载入历史会话…
          </span>
        )}
        <RetestButton
          label="重新载入会话"
          loading={booting}
          onRetest={() => { void bootstrap() }}
          hint="重取会话列表；不改写历史消息"
        />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="w-64 shrink-0 border-r border-sf-line bg-sf-surface">
          <ConversationSidebar />
        </div>
        <div className="min-w-0 min-h-0 flex-1">
          <ChatPanel
            messages={messages}
            model={model}
            style={style}
            mode={mode}
            isRunning={isRunning}
            onStyleChange={setStyle}
            onModeChange={setMode}
            onSend={submitQuestion}
            onStop={cancelCurrent}
            onPickChip={(c) => submitQuestion(c)}
            onPickParam={(p) => submitQuestion(p)}
          />
        </div>
      </div>
    </div>
  )
}
