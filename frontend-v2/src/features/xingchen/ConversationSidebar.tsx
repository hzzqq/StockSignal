import { useXingchen } from './useXingchen'
import type { ChatSession } from './useXingchen'

function sessionLabel(s: ChatSession): string {
  if (s.title && s.title.trim()) return s.title.trim()
  const firstUser = s.messages.find((m) => m.kind === 'user')
  if (firstUser && firstUser.content.trim()) {
    const t = firstUser.content.trim()
    return t.length > 16 ? `${t.slice(0, 16)}…` : t
  }
  return '新对话'
}

/** 会话侧栏：列表 / 新建 / 删除 / 导出 markdown|json。 */
export function ConversationSidebar() {
  const { order, sessions, activeId, createSession, openConversation, deleteSession, exportSession } =
    useXingchen()

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-sf-line px-3 py-2">
        <span className="text-title font-medium text-sf-ink-2">对话</span>
        <button
          type="button"
          onClick={() => createSession('新对话')}
          aria-label="新建对话"
          className="rounded-md border border-sf-line px-2 py-1 text-sm text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
        >
          ＋ 新对话
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
        {order.length === 0 ? (
          <div className="px-2 py-6 text-center text-sm text-sf-ink-3">
            暂无对话，点击「新对话」开始
          </div>
        ) : (
          order.map((id) => {
            const s = sessions[id]
            if (!s) return null
            const active = id === activeId
            return (
              <div
                key={id}
                className={`group rounded-lg border px-2 py-2 ${
                  active
                    ? 'border-brand-1 bg-brand-1/10'
                    : 'border-sf-line bg-sf-surface hover:border-sf-accent'
                }`}
              >
                <button
                  type="button"
                  onClick={() => (s.convId != null ? openConversation(s.convId) : undefined)}
                  className="block w-full truncate text-left text-sm text-sf-ink-2"
                  title={sessionLabel(s)}
                >
                  {sessionLabel(s)}
                </button>
                <div className="mt-1 flex items-center gap-1 opacity-0 transition group-hover:opacity-100">
                  <button
                    type="button"
                    onClick={() => exportSession(id, 'markdown')}
                    className="rounded border border-sf-line px-1.5 py-0.5 text-xs text-sf-ink-3 hover:border-sf-accent hover:text-sf-accent"
                  >
                    MD
                  </button>
                  <button
                    type="button"
                    onClick={() => exportSession(id, 'json')}
                    className="rounded border border-sf-line px-1.5 py-0.5 text-xs text-sf-ink-3 hover:border-sf-accent hover:text-sf-accent"
                  >
                    JSON
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteSession(id)}
                    aria-label="删除对话"
                    className="ml-auto rounded border border-sf-line px-1.5 py-0.5 text-xs text-sf-warn hover:border-sf-warn"
                  >
                    🗑
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
