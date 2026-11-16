import { useEffect, useState, type FormEvent } from 'react'
import { useReviewNotes } from '@/lib/queries'
import { useSaveReviewNotes } from '@/lib/queriesBatchB'
import { Card } from '@/shared/ui/Card'
import { EmptyState } from '@/shared/ui/States'

const INPUT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/**
 * 99 决策问答（v2 native /review-notes）：逐日复盘笔记（51 页复盘段的原文 md）。
 * 复用 /review-notes?date=。诚实红线：本地若无该日期复盘笔记（review_notes_<date>.md 缺失），
 * 后端返回 not_found → 页面显「该日期暂无复盘笔记」，不编造内容；内容按纯文本呈现（不引入 markdown 依赖）。
 * 注：本环境尚未生成任何 review_notes 文件，故默认即诚实空态；若日后生成则自动显示。
 */
export function ReviewNotes() {
  const [date, setDate] = useState<string>('2026-09-21')
  const q = useReviewNotes(date)
  const saveM = useSaveReviewNotes()
  const [draft, setDraft] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  // 切换日期只复位编辑区与保存态：不自动把原文回填进 textarea，
  // 否则同一段正文会在只读区与编辑框重复出现；需要修改时主动点「载入原文」。
  useEffect(() => {
    setDraft('')
    setNotice(null)
    saveM.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date])

  function handleSave(e: FormEvent) {
    e.preventDefault()
    setNotice(null)
    saveM.reset()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      setNotice('日期须为真实 YYYY-MM-DD')
      return
    }
    saveM.mutate(
      { date, content: draft },
      { onSuccess: () => setNotice(`已保存 ${date} 的复盘笔记（服务端原文）`) },
    )
  }

  const saveError = saveM.error instanceof Error ? saveM.error.message : null

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">决策问答</h2>
      <p className="text-xs text-sf-ink-3">
        逐日复盘笔记（只读视图）。本地若无该日期复盘笔记，会如实显示「暂无」，不编造。
      </p>

      <Card>
        <label className="text-xs text-sf-ink-2">
          选择日期
          <input
            type="date"
            className={INPUT_CLS}
            value={date}
            onChange={(e) => setDate(e.target.value || '')}
          />
        </label>
        {q.isLoading && <span className="ml-2 text-xs text-sf-ink-3">加载中…</span>}
      </Card>

      {q.data && (
        <Card title={`复盘笔记 · ${q.data.date}`}>
          <pre className="whitespace-pre-wrap text-sm text-sf-ink-2">{q.data.content}</pre>
        </Card>
      )}
      {q.isError && (
        <EmptyState
          label="该日期暂无复盘笔记"
          hint={q.error instanceof Error ? q.error.message : undefined}
        />
      )}

      <Card title="编辑并保存复盘笔记">
        <form onSubmit={handleSave} className="space-y-2">
          <textarea
            aria-label="复盘笔记正文"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            placeholder="填写该日期的 Markdown 复盘笔记；保存后覆盖服务端同名文件。"
            className={`${INPUT_CLS} whitespace-pre-wrap font-mono`}
          />
          <div className="flex flex-wrap items-center gap-3">
            {q.data?.content && (
              <button
                type="button"
                onClick={() => setDraft(q.data?.content ?? '')}
                className="text-label px-3 py-1.5 rounded-tile border border-sf-line"
              >
                载入原文到编辑区
              </button>
            )}
            <button
              type="submit"
              disabled={saveM.isPending}
              className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-50"
            >
              {saveM.isPending ? '保存中…' : `保存 ${date} 的笔记`}
            </button>
            {saveError && <span className="text-label text-sf-danger">保存失败：{saveError}</span>}
            {notice && !saveError && <span className="text-label text-sf-ink-2">{notice}</span>}
          </div>
        </form>
      </Card>
    </div>
  )
}
