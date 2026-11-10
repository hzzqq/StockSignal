import { useState } from 'react'
import type { FinancialReport } from '@/api/stock'
import { useFinancialsReport } from '@/lib/queries'
import type { Financials } from '@/api/schemas/stock'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { fmtNum } from '@/lib/format'

/**
 * 77 财报猎手（/financial-hunter，v2 native，旧 77 财报猎手页）。
 * 数据源：getFinancials（/api/v2/read/financials），按报表（income/balance/cash）切换。
 *
 * 诚实红线（与 FundamentalsView 同款）：null 数值显示「缺失」/「—」而非 0；date 为 null
 * 显示「暂无权威数据日」，禁用当前日期兜底；note 原文展示，不改写、不包装成投资建议。
 * 重要边界：本页为「逐股票深挖」视图（输入代码 → 多期财报三表之一），不是跨股票筛选器——
 * v2 暂无跨股财报筛选端点，页面如实说明，绝不伪造筛选结果。
 */
const CODE_RE = /^\d{6}$/
const DEFAULT_CODE = '600519'
const REPORTS: { key: FinancialReport; label: string }[] = [
  { key: 'income', label: '利润表' },
  { key: 'balance', label: '资产负债表' },
  { key: 'cash', label: '现金流量表' },
]

export interface FinancialHunterProps {
  /** 来自 validateSearch 的 ?code=；缺/非法时默认 600519。 */
  search?: { code?: string }
}

export function FinancialHunter({ search }: FinancialHunterProps) {
  const [codeInput, setCodeInput] = useState(
    search?.code && CODE_RE.test(search.code) ? search.code : DEFAULT_CODE,
  )
  const [applied, setApplied] = useState(
    search?.code && CODE_RE.test(search.code) ? search.code : DEFAULT_CODE,
  )
  const [report, setReport] = useState<FinancialReport>('income')
  const q = useFinancialsReport(applied, report)

  const applyCode = () => {
    const v = codeInput.trim()
    if (CODE_RE.test(v)) setApplied(v)
  }

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">财报猎手</h2>
        <span className="text-label text-sf-ink-3">数据源 financials（三表合并，逐报表切换）</span>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex flex-col gap-1 text-label text-sf-ink-2">
          股票代码
          <input
            type="text"
            value={codeInput}
            onChange={(e) => setCodeInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applyCode()
            }}
            placeholder="6 位数字，如 600519"
            aria-label="股票代码"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink w-40"
          />
        </label>
        <button
          type="button"
          onClick={applyCode}
          disabled={!CODE_RE.test(codeInput.trim())}
          aria-label="查询财报"
          className="text-label px-3 py-1.5 rounded-tile border border-sf-line disabled:opacity-40"
        >
          查询
        </button>

        <div role="tablist" aria-label="报表类型" className="flex gap-2 ml-auto">
          {REPORTS.map((r) => (
            <button
              key={r.key}
              type="button"
              role="tab"
              aria-selected={report === r.key}
              onClick={() => setReport(r.key)}
              className={`text-label px-3 py-1.5 rounded-tile border ${
                report === r.key
                  ? 'border-sf-accent text-sf-accent'
                  : 'border-sf-line text-sf-ink-3'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!q.data && q.data.rows.length === 0}
        emptyLabel="暂无财报数据"
        emptyHint="rows 为空数组，未做填充"
      >
        {q.data ? <HunterBody data={q.data} code={applied} /> : null}
      </QueryState>
    </div>
  )
}

function HunterBody({ data, code }: { data: Financials; code: string }) {
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3 text-body">
        <span className="text-sf-ink-3">数据日</span>
        {data.date === null ? (
          <span role="status" className="text-sf-warn">
            暂无权威数据日
          </span>
        ) : (
          <span className="text-sf-ink tabular-nums">{`权威数据日：${data.date}`}</span>
        )}
        <span className="text-label text-sf-ink-3">{`代码 ${code}`}</span>
        <span className="text-label text-sf-ink-3">{`报表 ${data.report}`}</span>
      </div>

      <Card title="多期财报明细">
        <FinancialTable rows={data.rows} />
      </Card>

      <Card title="口径说明">
        <p className="text-body text-sf-ink-2">
          {data.note === null ? '原始响应未提供口径说明' : data.note}
        </p>
        <ul className="mt-3 space-y-1 text-label text-sf-ink-3 list-disc pl-5">
          <li>
            本页为「逐股票深挖」视图：输入 6 位代码后按所选报表展示多期财务数据；非跨股票筛选器
            （v2 暂无跨股财报筛选端点），不伪造筛选结果。
          </li>
          <li>数据日来自后端原始响应，可能来自过期缓存（旧交易日），不标注「今日」。</li>
        </ul>
      </Card>
    </div>
  )
}

/** 中文动态列名：判空后再取首行 keys 渲染，不做重排。 */
function FinancialTable({ rows }: { rows: Financials['rows'] }) {
  const cols = rows.length > 0 ? Object.keys(rows[0]) : []
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">多期财报明细，列名来自后端原始响应，未做重排</caption>
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
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-sf-line last:border-0">
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
  )
}
