import { useEffect, useRef } from 'react'
import { useXingchen } from './useXingchen'
import { ConversationSidebar } from './ConversationSidebar'
import { ChatPanel } from './ChatPanel'

/** 星辰 AI 页面容器：左侧会话侧栏 + 右侧对话面板。 */
export function XingchenPage() {
  const { bootstrap, active, style, model, isRunning, setStyle, submitQuestion, cancelCurrent } =
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
    <div className="flex h-full min-h-0">
      <div className="w-64 shrink-0 border-r border-sf-line bg-sf-surface">
        <ConversationSidebar />
      </div>
      <div className="min-w-0 flex-1">
        <ChatPanel
          messages={messages}
          model={model}
          style={style}
          isRunning={isRunning}
          onStyleChange={setStyle}
          onSend={submitQuestion}
          onStop={cancelCurrent}
          onPickChip={(c) => submitQuestion(c)}
          onPickParam={(p) => submitQuestion(p)}
        />
      </div>
    </div>
  )
}
