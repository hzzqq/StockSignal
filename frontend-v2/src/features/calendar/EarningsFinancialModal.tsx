import { useEffect, useState } from 'react'
import type { FundamentalsPerf } from '@/api/schemas/stock'
import { useFundamentals, useFinancialsReport } from '@/lib/queries'
import { fmtNum } from '@/lib/format'
import { classifyDomain, inkForCell } from '@/lib/domainColor'
import { QueryState } from '@/shared/ui/States'
import { openKLine } from '@/features/stock/charts/klineOverlayStore'
import { FinancialTable, PERF_LABELS } from '../stock/FundamentalsView'

/**
 * 财报弹窗（财报日历行点击详情），壳形态完全仿 KLineModal：
 *  - open + 6 位 code 即弹出；open=false / code=null 时 return null，
 *    两个 useQuery 依赖 enabled=/^\d{6}$/ 拦截空 code —— 弹窗关闭时不发任何请求。
 *  - 关闭：右上角按钮 / 点遮罩 / Esc；role=dialog + aria-modal 保证读屏可达。
 *
 * 内容（全部复用现有端点，零新端点）：
 *  - 头部信息卡：useFundamentals → name/industry/price/pe_ttm/market_cap + perf 9 项；
 *    缺失字段如实「—」。A 股涨跌色只对 price 域字段用 domainColor 现有语义（涨红跌绿），
 *    非涨跌字段（毛利率/ROE 等）一律中性墨色，不借用红绿。
 *  - 财报三表：useFinancialsReport(code, report) + income/balance/cash 三 tab 受控切换；
 *    表格直接复用 stock/FundamentalsView 的 FinancialTable（中文动态列名原样渲染）。
 *  - 底部「查看 K 线」：调全局 openKLine(code, name, 'market')（AppShell 已挂 GlobalKLineOverlay）。
 *
 * 诚实红线：perf 整体 null → 如实提示；rows 空 → 空态；note 只以低强小字出现，不展开大段原文。
 */
export interface EarningsFinancialModalProps {
  open: boolean
  onClose: () => void
  /** 选中个股代码（6 位纯数字）；null 时不渲染。 */
  code: string | null
  /** 行内股票简称（日历行带来）；缺失时回落 fundamentals.name，再缺失回落 code。 */
  name?: string
}

const REPORT_TABS = [
  { key: 'income', label: '利润表' },
  { key: 'balance', label: '资产负债表' },
  { key: 'cash', label: '现金流量表' },
] as const
type ReportKey = (typeof REPORT_TABS)[number]['key']

const PERF_KEYS = Object.keys(PERF_LABELS) as (keyof FundamentalsPerf)[]

/** 涨跌色闸门：仅 price 域字段走 inkForCell（market 红涨绿跌）；其余中性墨色。 */
function valueInk(field: string, value: unknown): string {
  return classifyDomain(field) === 'price' ? inkForCell(field, value) : 'var(--color-sf-ink)'
}

function HeadStat({ label, field, value }: { label: string; field?: string; value: unknown }) {
  const missing = value === null || value === undefined || value === ''
  return (
    <div className="rounded-tile border border-sf-line bg-sf-surface px-2.5 py-2">
      <div className="text-label text-sf-ink-3">{label}</div>
      <div
        className="text-body tabular-nums text-sf-ink"
        style={field && !missing ? { color: valueInk(field, value) } : undefined}
      >
        {missing ? '—' : fmtNum(value)}
      </div>
    </div>
  )
}

export function EarningsFinancialModal({ open, onClose, code, name }: EarningsFinancialModalProps) {
  const [report, setReport] = useState<ReportKey>('income')
  const fund = useFundamentals(code ?? '')
  const fin = useFinancialsReport(code ?? '', report)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !code) return null

  const fundData = fund.data
  const perf = fundData?.perf ?? null
  const finRows = fin.data?.rows ?? []
  const title = name ?? fundData?.name ?? code

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(8,8,18,0.6)' }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${title} 财报详情`}
        className="w-full max-w-[960px] max-h-[90vh] overflow-auto rounded-card border border-sf-line bg-sf-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-title font-semibold text-sf-ink">
            {title}
            <span className="text-label text-sf-ink-3 font-normal"> · 财报详情</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭财报弹窗"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-ink"
          >
            ✕ 关闭
          </button>
        </div>

        {/* 头部信息卡（fundamentals：基础 5 项 + perf 9 项） */}
        <QueryState
          isLoading={fund.isLoading}
          isError={fund.isError}
          error={fund.error}
          isEmpty={false}
        >
          {fundData ? (
            <div className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                <HeadStat label="名称" value={fundData.name} />
                <HeadStat label="行业" value={fundData.industry} />
                <HeadStat label="现价" field="price" value={fundData.price} />
                <HeadStat label="PE(TTM)" field="pe_ttm" value={fundData.pe_ttm} />
                <HeadStat label="总市值" field="market_cap" value={fundData.market_cap} />
              </div>
              {perf === null ? (
                <p role="status" className="mt-3 text-label text-sf-ink-3">
                  perf 整体未取到（9 项业绩指标缺失），如实留空、不补 0
                </p>
              ) : (
                <div className="mt-3 grid grid-cols-2 md:grid-cols-3 gap-2">
                  {PERF_KEYS.map((k) => (
                    <div
                      key={k}
                      className="flex items-center justify-between rounded-tile border border-sf-line bg-sf-surface px-2.5 py-2"
                    >
                      <span className="text-label text-sf-ink-3">{PERF_LABELS[k]}</span>
                      <span
                        data-testid={`perf-${k}`}
                        className={`text-body tabular-nums ${perf[k] === null ? 'text-sf-ink-3' : 'text-sf-ink'}`}
                      >
                        {perf[k] === null ? '—' : fmtNum(perf[k])}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </QueryState>

        {/* 财报三表：income / balance / cash 受控切换 */}
        <div className="mt-4">
          <div role="radiogroup" aria-label="选择财报类型" className="mb-3 flex flex-wrap gap-2">
            {REPORT_TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="radio"
                aria-checked={report === t.key}
                data-testid={`fin-tab-${t.key}`}
                onClick={() => setReport(t.key)}
                className={`rounded-full border px-3 py-1 text-label transition-colors ${
                  report === t.key
                    ? 'border-sf-accent text-sf-accent'
                    : 'border-sf-line text-sf-ink-3 hover:text-sf-ink-2'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <QueryState
            isLoading={fin.isLoading}
            isError={fin.isError}
            error={fin.error}
            isEmpty={!!fin.data && finRows.length === 0}
            emptyLabel="暂无财报数据"
            emptyHint="rows 为空数组，未做填充"
          >
            <FinancialTable rows={finRows} />
          </QueryState>
        </div>

        {/* note 只以低强小字出现，不展开大段原文 */}
        {fundData?.note && <p className="mt-3 text-xs text-sf-ink-3">{fundData.note}</p>}

        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={() => openKLine(code, name ?? fundData?.name ?? undefined, 'market')}
            className="rounded-tile border border-sf-accent px-3 py-1.5 text-label text-sf-accent hover:bg-sf-accent hover:text-white"
          >
            查看 K 线
          </button>
        </div>
      </div>
    </div>
  )
}
