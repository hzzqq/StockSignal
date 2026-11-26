import { useState } from 'react'
import {
  EARNINGS_PERIODS,
  EARNINGS_PERIOD_LABELS,
  EARNINGS_SIGNAL_ORDER,
  type EarningsHunter,
  type EarningsPeriod,
  type EarningsSignal,
} from '@/api/schemas/earningsHunter'
import { useEarningsHunter } from '@/lib/queriesBatchD'
import { Card } from '@/shared/ui/Card'
import { CollapsibleCard } from '@/shared/ui/CollapsibleCard'
import { QueryState } from '@/shared/ui/States'
import { Select } from '@/shared/ui/Field'
import { fmtNum } from '@/lib/format'

/**
 * 77 财报猎手 · 业绩预告信号扫描面板（parity D，跨股筛选能力真承接）。
 *
 * 诚实红线：
 *  - available=false 时按 reason 原文透出（未到披露期 / 接口异常），不伪造预告行；
 *  - 信号级别是启发式文本映射（预增/扭亏→利好 等），不是预测；预增≠必涨，预告也可能被修正；
 *  - NaN 已由后端转 null，UI 显示「—」，绝不补 0。
 */
const SIGNAL_HINT: Record<EarningsSignal, string> = {
  利好: '预增 / 扭亏',
  偏多: '略增 / 续盈',
  中性: '持平 / 不明',
  偏空: '略减 / 续亏',
  利空: '预减 / 首亏',
}

const LABEL_CLS = 'block text-label text-sf-ink-3'
const INPUT_CLS =
  'mt-1 rounded-tile border border-sf-line bg-sf-surface px-2.5 py-1.5 text-body text-sf-ink outline-none focus:border-sf-accent'

export function EarningsHunterPanel() {
  const [period, setPeriod] = useState<EarningsPeriod>('20260630')
  const [minPct, setMinPct] = useState('0')
  const [signals, setSignals] = useState<EarningsSignal[]>(['利好', '偏多'])
  const [enabled, setEnabled] = useState(false)

  const parsedMinPct = Number(minPct)
  const minPctValid = minPct.trim() !== '' && Number.isFinite(parsedMinPct)
  const q = useEarningsHunter(
    { period, min_pct: minPctValid ? parsedMinPct : undefined, signals },
    enabled,
  )

  return (
    <Card title="业绩预告信号扫描（跨股）">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-3">
          <Select
            label="预告报告期"
            aria-label="业绩预告报告期"
            value={period}
            onChange={(e) => {
              setPeriod(e.target.value as EarningsPeriod)
              setEnabled(false)
            }}
          >
            {EARNINGS_PERIODS.map((p) => (
              <option key={p} value={p}>
                {EARNINGS_PERIOD_LABELS[p]}（{p}）
              </option>
            ))}
          </Select>
          <label className={LABEL_CLS}>
            最小业绩变动幅度（%，-200~200）
            <input
              aria-label="最小业绩变动幅度"
              type="number"
              min={-200}
              max={200}
              step={10}
              value={minPct}
              onChange={(e) => {
                // 与报告期/信号级别同语义：条件变更即失效旧结果，必须重新点扫描。
                // 不失效的话 queryKey 随输入逐字变化自动 fetch——用户敲 "-" 的中间态
                // 会以 min_pct=undefined（无下限过滤）发请求并把结果表闪换成未过滤数据。
                setEnabled(false)
                setMinPct(e.target.value)
              }}
              className={INPUT_CLS}
            />
          </label>
          <fieldset className={LABEL_CLS}>
            <legend>只看信号级别</legend>
            <div className="mt-1 flex flex-wrap gap-2">
              {EARNINGS_SIGNAL_ORDER.map((s) => (
                <label
                  key={s}
                  className="flex items-center gap-1 text-label text-sf-ink-2"
                  title={SIGNAL_HINT[s]}
                >
                  <input
                    type="checkbox"
                    aria-label={`信号级别 ${s}`}
                    checked={signals.includes(s)}
                    onChange={(e) => {
                      setEnabled(false)
                      setSignals((cur) =>
                        e.target.checked ? [...cur, s] : cur.filter((x) => x !== s),
                      )
                    }}
                  />
                  {s}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        {minPct.trim() !== '' && !minPctValid && (
          <p className="text-label text-sf-danger">变动幅度须为数字，未发起扫描</p>
        )}

        <button
          type="button"
          disabled={!minPctValid}
          onClick={() => {
            if (enabled) {
              // 已启用（条件未变再点 = 强制刷新）：refetch 用当前渲染闭包的 key，正确。
              q.refetch()
            } else {
              // 首次/条件变更后：false→true 自动 fetch，key 来自最新状态，
              // 避免在同一同步块 refetch 旧闭包 key（切期后首扫会以旧 period 发冗余请求）。
              setEnabled(true)
            }
          }}
          className="rounded-tile border border-sf-line px-3 py-1.5 text-label text-sf-ink-2 hover:text-sf-accent disabled:opacity-50"
        >
          扫描业绩预告
        </button>

        {enabled && (
          <QueryState
            isLoading={q.isFetching && !q.data}
            isError={q.isError}
            error={q.error}
            isEmpty={!!q.data && !q.data.available}
            emptyLabel={q.data?.available === false ? '本期无可用预告数据' : undefined}
            emptyHint={q.data?.reason ?? undefined}
          >
            {q.data?.available && (
              <EarningsHunterBody
                key={`${period}-${minPct}-${signals.join(',')}`}
                data={q.data}
              />
            )}
          </QueryState>
        )}
      </div>
    </Card>
  )
}

function EarningsHunterBody({ data }: { data: EarningsHunter }) {
  const cols = data.rows.length > 0 ? Object.keys(data.rows[0]) : []
  return (
    <div className="space-y-3">
      <p className="text-label text-sf-ink-3">
        共 {data.n_scanned ?? '—'} 条预告，筛选命中 {data.n_total ?? '—'} 条
        {data.n_total != null && data.rows.length < data.n_total ? `（仅展示前 ${data.rows.length} 条）` : ''}。
        信号级别是启发式文本映射，不是预测；预增≠必涨，预告也可能被修正。
      </p>
      <div className="flex flex-wrap gap-2">
        {EARNINGS_SIGNAL_ORDER.map((s) => (
          <span
            key={s}
            className="rounded-tile border border-sf-line px-2 py-0.5 text-label text-sf-ink-2"
          >
            {s}：{data.signal_counts[s] != null ? data.signal_counts[s] : '—'}
          </span>
        ))}
      </div>
      {data.rows.length === 0 ? (
        <p className="text-xs text-sf-ink-3">筛选条件下无命中预告（不放宽条件重试请自行调整）。</p>
      ) : (
        /* 扫描结果默认折叠为一行摘要（命中数 + 各信号计数，全部真实统计自 signal_counts）；
           扫描统计与空态提示留在折叠卡外，不被藏匿。 */
        <CollapsibleCard
          title="扫描结果明细"
          summary={`命中 ${data.n_total ?? '—'} 条 · ${EARNINGS_SIGNAL_ORDER.map(
            (s) => `${s} ${data.signal_counts[s] != null ? data.signal_counts[s] : '—'}`,
          ).join(' · ')}`}
          defaultOpen={false}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-body border-collapse">
              <caption className="sr-only">业绩预告扫描结果，列名来自东财原始响应</caption>
              <thead>
                <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                  {cols.map((c) => (
                    <th key={c} scope="col" className="text-left py-2 pr-3 font-normal">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="text-sf-ink-2">
                {data.rows.map((r, i) => (
                  <tr key={i} className="border-b border-sf-line last:border-0 hover:bg-sf-surface-2">
                    {cols.map((c) => (
                      <td key={c} className="py-1.5 pr-3 tabular-nums">
                        {fmtNum(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleCard>
      )}
    </div>
  )
}
