import { useState, type FormEvent } from 'react'
import { useNlScreenExecute } from '@/lib/queriesBatchD'
import { Card } from '@/shared/ui/Card'
import { CollapsibleCard } from '@/shared/ui/CollapsibleCard'
import { Select } from '@/shared/ui/Field'
import { fmtNum } from '@/lib/format'

/**
 * 81 自然语言选股 · 执行筛选（parity D，挂 /stock/screener 语义解析卡之下）。
 *
 * 诚实红线（照 v1 口径）：
 *  - 执行依赖联网取数（local_api / akspot / all 三级降级）；候选池取不到 → available=false
 *    + reason 原文透出（离线环境本就只展示解析，这是能力边界不是故障）；
 *  - 结果是真实筛选行，绝不伪造；二道闸排雷异常降级放行时如实标注 note。
 */
const LABEL_CLS = 'block text-label text-sf-ink-3'
const INPUT_CLS =
  'mt-1 rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'
const BTN_CLS =
  'rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50'
const SCOPES = [
  { value: 'local_api', label: '本地 API 池' },
  { value: 'akspot', label: '实时行情快照' },
  { value: 'all', label: '三级降级（本地→实时→自选）' },
] as const

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

export function NlExecutePanel() {
  const [query, setQuery] = useState('创业板 市盈率<30 前10')
  const [scope, setScope] = useState<(typeof SCOPES)[number]['value']>('all')
  const [customCodes, setCustomCodes] = useState('')
  const ex = useNlScreenExecute()

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    ex.reset()
    ex.mutate({
      query: query.trim(),
      scope,
      custom_codes: customCodes.trim() || undefined,
    })
  }

  const d = ex.data

  return (
    <Card title="自然语言选股 · 执行筛选（81 页执行链路，需联网取候选池）">
      <form onSubmit={submit} className="space-y-3">
        <label className={LABEL_CLS}>
          选股意图（大白话）
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="自然语言执行条件"
            placeholder="例：创业板 市盈率<30 且 营收增长>20% 剔除ST 前10"
            className={`${INPUT_CLS} w-full`}
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <Select
            label="候选池"
            aria-label="候选池来源"
            value={scope}
            onChange={(e) => setScope(e.target.value as typeof scope)}
          >
            {SCOPES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </Select>
          <label className={LABEL_CLS}>
            自定义代码池（可选，逗号分隔 6 位代码）
            <input
              aria-label="自定义代码池"
              value={customCodes}
              onChange={(e) => setCustomCodes(e.target.value)}
              placeholder="600519,000001"
              className={INPUT_CLS}
            />
          </label>
        </div>
        <button type="submit" disabled={!query.trim() || ex.isPending} className={BTN_CLS}>
          {ex.isPending ? '执行中…' : '🚀 执行筛选'}
        </button>
        {ex.isError && (
          <p className="text-label text-sf-danger">执行请求失败：{errText(ex.error)}</p>
        )}
      </form>

      {d && !d.available && (
        <div className="mt-3 space-y-1 rounded-tile border border-sf-line p-3">
          <p className="text-label text-sf-danger">本次执行未产出结果</p>
          <p className="text-label text-sf-ink-2">{d.reason ?? '后端未返回原因'}</p>
          {d.spec && d.spec.unparsed.length > 0 && (
            <p className="text-label text-sf-ink-3">未理解词：{d.spec.unparsed.join('；')}</p>
          )}
        </div>
      )}

      {d?.available && (
        <div className="mt-3 space-y-3">
          <p className="text-label text-sf-ink-2">
            候选池 {d.n_universe} → 条件命中 {d.n_matched} → 二道闸排雷后 {d.rows.length} 行
            （耗时 {d.elapsed_ms}ms{d.source_used ? `，来源 ${d.source_used}` : ''}）
          </p>
          {d.gated_out.count > 0 && (
            <p className="text-label text-sf-warn">
              二道闸排除 {d.gated_out.count} 只
              {d.gated_out.items.length > 0 &&
                `：${d.gated_out.items
                  .map((k) => `${String(k.name ?? k.code)}(${String(k.code ?? '')})`)
                  .join('、')}`}
            </p>
          )}
          {d.gated_out.note && (
            <p className="text-label text-sf-warn">{d.gated_out.note}</p>
          )}
          {d.spec && d.spec.unparsed.length > 0 && (
            <p className="text-label text-sf-ink-3">未理解词已如实标注：{d.spec.unparsed.join('；')}</p>
          )}
          {d.rows.length === 0 ? (
            <p className="text-xs text-sf-ink-3">条件命中为空（或全部被二道闸排除），不伪造结果行。</p>
          ) : (
            /* 结果明细动辄数十行，默认折叠为一行摘要；候选池/命中/排雷统计与空态提示留在折叠卡外，不被藏匿。 */
            <CollapsibleCard
              title="执行结果明细"
              summary={`命中 ${d.rows.length} 条`}
              defaultOpen={false}
            >
              <NlRowsTable rows={d.rows} />
            </CollapsibleCard>
          )}
          <p className="text-xs text-sf-ink-3">{d.note ?? ''}</p>
        </div>
      )}
    </Card>
  )
}

/** 动态中文列名来自后端原始记录；NaN 已由后端转 null，fmtNum 显示「—」。 */
function NlRowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = rows.length > 0 ? Object.keys(rows[0]) : []
  return (
    <div className="max-h-80 overflow-auto rounded-tile border border-sf-line">
      <table className="w-full text-body">
        <caption className="sr-only">自然语言选股执行结果，列名来自后端原始记录</caption>
        <thead className="sticky top-0 bg-sf-surface">
          <tr className="text-label text-sf-ink-3 text-left">
            {cols.map((c) => (
              <th key={c} className="py-1 px-2 font-normal">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-sf-line">
              {cols.map((c) => (
                <td key={c} className="py-1 px-2 tabular-nums">{fmtNum(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
