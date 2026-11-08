import { useState } from 'react'
import { useReviewNotes } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'

const INPUT_CLS =
  'mt-1 bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/** 51 每日晨报 · 复盘笔记：按日期拉取 review_notes_<date>.md 原文（缺失即诚实报错）。
 * 诚实红线：v2 没有「可用笔记日期清单」端点，机器当前日期不是数据日，
 * 故默认留空、不预选、不发请求，避免一进页面就把「查不到」伪装成今天的数据。
 */
export function MorningReport() {
  const [date, setDate] = useState('')
  const q = useReviewNotes(date)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">每日晨报 · 复盘笔记</h2>
      <Card>
        <label className="text-xs text-sf-ink-2">日期（复盘笔记按日期归档，请手动选择）</label>
        <input
          type="date"
          className={INPUT_CLS}
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </Card>
      {!date && (
        <p role="status" className="text-label text-sf-ink-3">
          未选择日期，不发起查询。机器当前日期不作为默认数据日。
        </p>
      )}
      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={!!date && !q.data}>
        {q.data && (
          <Card title={`复盘笔记 ${q.data.date}`}>
            <pre className="whitespace-pre-wrap text-sm text-sf-ink-2 font-sans">
              {q.data.content}
            </pre>
          </Card>
        )}
      </QueryState>
    </div>
  )
}
