import { useState } from 'react'
import { useReviewNotes } from '@/lib/queries'
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
    </div>
  )
}
