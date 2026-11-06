import { useState } from 'react'
import { useReviewNotes } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'

const INPUT_CLS =
  'mt-1 bg-sf-bg border border-sf-border text-sf-txt rounded px-2 py-1.5 outline-none focus:border-ss-up'

/** 51 每日晨报 · 复盘笔记：按日期拉取 review_notes_<date>.md 原文（缺失即诚实报错）。 */
export function MorningReport() {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const q = useReviewNotes(date)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">每日晨报 · 复盘笔记</h2>
      <Card>
        <label className="text-xs text-sf-txt/60">日期</label>
        <input
          type="date"
          className={INPUT_CLS}
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Card>
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={!q.data}>
        {q.data && (
          <Card title={`复盘笔记 ${q.data.date}`}>
            <pre className="whitespace-pre-wrap text-sm text-sf-txt/80 font-sans">
              {q.data.content}
            </pre>
          </Card>
        )}
      </QueryState>
    </div>
  )
}
