import { useRef, useState } from 'react'
import { Button } from '@/shared/ui/Button'
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

type RenameHint = { id: string; text: string; error?: boolean }

/** 会话侧栏：列表 / 新建 / 重命名 / 删除 / 导出 markdown|json。 */
export function ConversationSidebar() {
  const {
    order,
    sessions,
    activeId,
    createSession,
    openConversation,
    deleteSession,
    deleteError,
    clearDeleteError,
    exportSession,
    renameSession,
  } = useXingchen()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [hint, setHint] = useState<RenameHint | null>(null)
  // 删除就地二次确认：记录正在确认的会话 id，避免误触即删
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)
  // Enter 保存会触发输入卸载，blur 可能随之而来；用 ref 防重复提交 / Esc 后误保存
  const finishedRef = useRef(false)

  const beginEdit = (s: ChatSession) => {
    finishedRef.current = false
    setEditingId(s.id)
    // 预填当前标题；无显式标题时用 sessionLabel 作回退（首条用户消息 / 「新对话」）
    setDraft(s.title?.trim() || sessionLabel(s))
    setHint((h) => (h?.id === s.id ? null : h))
  }

  const finishEdit = () => {
    finishedRef.current = true
    setEditingId(null)
  }

  const cancelEdit = () => {
    finishEdit()
    setDraft('')
  }

  const commitEdit = async (id: string) => {
    if (finishedRef.current) return
    finishEdit()
    // trim / 空回退「新对话」/ 40 字截断由 store 的 renameSession 统一规范化（与后端一致）
    const value = draft.trim() || '新对话'
    try {
      const res = await renameSession(id, value)
      // convId 缺失时如实标注「未持久化」，不假装已保存
      setHint(res.persisted ? null : { id, text: '未持久化：仅本地改名，后端未记录' })
    } catch (e) {
      setHint({
        id,
        text: e instanceof Error ? e.message : '重命名失败',
        error: true,
      })
    }
  }

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

      {deleteError && (
        <div
          role="alert"
          className="flex items-center justify-between gap-2 border-b border-sf-line bg-sf-danger-soft px-3 py-2 text-label text-sf-danger"
        >
          <span>{deleteError}</span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="关闭错误提示"
            onClick={clearDeleteError}
          >
            知道了
          </Button>
        </div>
      )}

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
                <div className="flex items-center gap-1">
                  {editingId === id ? (
                    <input
                      autoFocus
                      value={draft}
                      maxLength={40}
                      aria-label="重命名输入"
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          void commitEdit(id)
                        } else if (e.key === 'Escape') {
                          e.preventDefault()
                          cancelEdit()
                        }
                      }}
                      onBlur={() => {
                        void commitEdit(id)
                      }}
                      className="min-w-0 flex-1 rounded border border-sf-accent bg-sf-bg px-2 py-1 text-sm text-sf-ink-2 outline-none"
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => (s.convId != null ? openConversation(s.convId) : undefined)}
                      className="block min-w-0 flex-1 truncate text-left text-sm text-sf-ink-2"
                      title={sessionLabel(s)}
                    >
                      {sessionLabel(s)}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={editingId === id}
                    onClick={() => beginEdit(s)}
                    aria-label="重命名对话"
                    title="重命名"
                    className="shrink-0 rounded px-1 py-0.5 text-xs text-sf-ink-3 hover:border-sf-accent hover:text-sf-accent"
                  >
                    ✎
                  </button>
                </div>
                <div className="mt-1 flex items-center gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100 group-focus-within:opacity-100">
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
                  {confirmingDeleteId === id ? (
                    <div className="ml-auto flex items-center gap-1">
                      <span className="text-xs text-sf-ink-2">确认删除？</span>
                      <Button
                        type="button"
                        variant="danger"
                        size="sm"
                        aria-label="确认删除对话"
                        onClick={() => {
                          setConfirmingDeleteId(null)
                          void deleteSession(id)
                        }}
                      >
                        确认删除
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirmingDeleteId(null)}
                      >
                        取消
                      </Button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmingDeleteId(id)}
                      aria-label="删除对话"
                      className="ml-auto rounded border border-sf-line px-1.5 py-0.5 text-xs text-sf-warn hover:border-sf-warn"
                    >
                      🗑
                    </button>
                  )}
                </div>
                {hint?.id === id && (
                  <div
                    role={hint.error ? 'alert' : undefined}
                    className={`mt-1 text-xs ${hint.error ? 'text-sf-danger' : 'text-sf-ink-3'}`}
                  >
                    {hint.text}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
