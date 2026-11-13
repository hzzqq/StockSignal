import type { ChatMessage, AiConsultTask } from '@/api/schemas/chat'
import { Markdown } from './Markdown'
import { ProcessCard } from './ProcessCard'
import { TaskCard } from './TaskCard'
import { ParamPromptCard } from './ParamPromptCard'
import { SuggestionChips } from './SuggestionChips'
import { copyText } from './util'

function fmtTs(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 按 msg.kind 判别渲染（借鉴 FinPilot MessageBubble）。 */
export function MessageBubble({
  msg,
  onPickChip,
  onPickParam,
}: {
  msg: ChatMessage
  onPickChip?: (c: string) => void
  onPickParam?: (p: string) => void
}) {
  // 用户：右对齐气泡
  if (msg.kind === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-tile bg-brand-1 px-3 py-2 text-body text-white">
          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
          {msg.ts && (
            <div className="mt-1 text-right text-[0.7rem] text-white/70">{fmtTs(msg.ts)}</div>
          )}
        </div>
      </div>
    )
  }

  // 缺参追问卡片
  if (msg.kind === 'param-prompt') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[90%]">
          <ParamPromptCard prompts={msg.paramPrompt ?? []} onPick={onPickParam} />
        </div>
      </div>
    )
  }

  // assistant（含 tool 态：toolCall/process 均为前端态）
  const task = msg.toolCall as AiConsultTask | undefined
  const isStreaming = msg.status === 'streaming'
  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-tile border border-sf-line bg-sf-surface px-3 py-2 text-body text-sf-ink-2">
        {msg.process && msg.process.length > 0 && (
          <ProcessCard steps={msg.process} defaultOpen={isStreaming} />
        )}

        {isStreaming && task && <TaskCard task={task} className="mt-2" />}
        {isStreaming && !msg.content && !task && (
          <div className="mt-1 flex items-center gap-2 text-label text-sf-ink-3">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sf-accent animate-pulse" />
            思考中…
          </div>
        )}

        {msg.status === 'error' ? (
          <div role="alert" className="mt-1 flex items-start gap-2 text-sf-danger">
            <span aria-hidden="true">⚠️</span>
            <span>{(msg.errors && msg.errors[0]) || '生成失败'}</span>
          </div>
        ) : msg.content ? (
          <div className="mt-1">
            <Markdown content={msg.content} />
          </div>
        ) : null}

        {msg.chips && msg.chips.length > 0 && !isStreaming && (
          <SuggestionChips chips={msg.chips} onPick={onPickChip} />
        )}

        {msg.content && msg.status !== 'error' && (
          <div className="mt-1 flex items-center justify-between text-[0.7rem] text-sf-ink-3">
            <span>{fmtTs(msg.ts)}</span>
            <button
              type="button"
              onClick={() => copyText(msg.content)}
              className="hover:text-sf-accent"
            >
              ⧉ 复制
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
