import { useState } from 'react'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { Link, useNavigate } from '@tanstack/react-router'
import type { Fundamentals, FundamentalsPerf, Financials } from '@/api/schemas/stock'
import { useFundamentals, useFinancialsReport } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState, EmptyState } from '@/shared/ui/States'
import { CollapsibleCard } from '@/shared/ui/CollapsibleCard'
import { fmtNum } from '@/lib/format'
import { SectionTitle, LeadText } from '@/shared/ui/EmphasisText'
import { FinancialTrendChart, hasFinite } from './FinancialTrendChart'

/**
 * W4-B · 基本面分析页（/stock/fundamentals，旧 22 页）。
 * 数据源：getFundamentals + getFinancials（/api/v2/read/fundamentals | financials）。
 *
 * 诚实红线：null 数值显示「缺失」/「—」而非 0；date 为 null 显示「暂无权威数据日」，
 * 禁用当前日期兜底；spot_date 与 kline_date 分行独立展示、禁互兜底；note 原文展示。
 * 本轮不渲染任何涨跌色（只用 sf-warn / sf-accent 状态色），priceDomain 原文可见；
 * 旧 24 页 deep 的「价格域绿涨红跌 + 业绩域红涨绿跌」字段域级双语义留 W4-C 处理，本轮不碰。
 */
const CODE_RE = /^\d{6}$/
const DEFAULT_CODE = '600519'

/**
 * perf 9 指标中文标签（字段名真值 pages/22_基本面分析.py:374-379 _calc_perf）。
 * 补充裁决：perf 三形态 —— 正常=9 字段有值对象；全源失败=9 字段全 null 对象（后端实测）；
 * 保守上界=整体 null（Zod nullable 兼容）。本页把 null 逐字段显示「缺失」，绝不补 0。
 * revenue_yoy / profit_yoy 旧页语义为「与上一报告期比」的相邻期口径，字段名沿用旧页，
 * 标签不得写成「同比 / 去年同期」（避免误导）。
 */
export const PERF_LABELS: Record<keyof FundamentalsPerf, string> = {
  // 导出供 EarningsFinancialModal 复用（同一份 9 项标签，避免两处口径漂移）。
  revenue_yi: '营收(亿元)',
  revenue_yoy: '营收(较上一报告期 %)',
  net_profit_yi: '净利润(亿元)',
  profit_yoy: '净利(较上一报告期 %)',
  gross_margin: '毛利率(%)',
  roe: '净资产收益率(%)',
  alr: '资产负债率(%)',
  current_ratio: '流动比率',
  equity_ratio: '权益比率(%)',
}
const PERF_KEYS = Object.keys(PERF_LABELS) as (keyof FundamentalsPerf)[]

/**
 * 历史业绩趋势可选指标（三选一，均为 income 合并表列名）。
 * 同比取后端 `_compute_yoy` 算出的真实同比「_同比」列（仅 income 报表提供）；
 * 若 rows 中该指标无 `_同比` 列，图内只画柱并如实提示，不虚构序列。
 */
const TREND_METRICS = ['营业总收入', '归母净利润', '净资产收益率'] as const
type TrendMetric = (typeof TREND_METRICS)[number]

export interface FundamentalsViewProps {
  /** 来自 validateSearch 的 ?code=；缺/非法时默认 600519（与 W4-A SixDimView / 旧 search_ui.py:235 一致）。 */
  search?: { code?: string }
}

export function FundamentalsView({ search }: FundamentalsViewProps) {
  const navigate = useNavigate()
  const code = search?.code && CODE_RE.test(search.code) ? search.code : DEFAULT_CODE
  const fund = useFundamentals(code)
  // 趋势图与财报表共用同一 income 报表源（useFinancials 即 report 固定 income 的快捷方式）。
  const fin = useFinancialsReport(code, 'income')

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <SectionTitle as="h2">基本面分析</SectionTitle>
        <span className="text-label text-sf-ink-3">数据源 fundamentals / financials</span>
        <Link
          to="/stock/research"
          search={{ view: 'quick', code }}
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          查看详细 K 线与技术面
        </Link>
        <Link
          to="/stock/research"
          search={{ view: 'deep', code }}
          className="text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          去个股研究（深度分析）
        </Link>
      </div>

      <div className="w-72">
        <StockSearchInput
          value={code}
          label="切换股票（代码 / 名称 / 首字母）"
          onSelect={(next) => void navigate({ to: '/stock/fundamentals', search: { code: next } })}
        />
      </div>

      <QueryState
        isLoading={fund.isLoading}
        isError={fund.isError}
        error={fund.error}
        isEmpty={false}
        emptyLabel="暂无基本面数据"
      >
        {fund.data ? <FundamentalsBody data={fund.data} fin={fin} code={code} /> : null}
      </QueryState>
    </div>
  )
}

function FundamentalsBody({
  data,
  fin,
  code,
}: {
  data: Fundamentals
  fin: ReturnType<typeof useFinancialsReport>
  code: string
}) {
  const perf = data.perf
  const degraded = data.date === null || perf === null
  const [metric, setMetric] = useState<TrendMetric>('营业总收入')
  const finRows = fin.data?.rows ?? []
  const hasFinRows = finRows.length > 0
  const latest = finRows[0] ?? {}

  return (
    <div className="flow">
      {/* 数据日条：date 为权威数据日；为 null 时如实显示，禁止今天日期兜底。 */}
      <div className="flex flex-wrap items-center gap-3 text-body">
        <span className="text-sf-ink-3">数据日</span>
        {data.date === null ? (
          <span role="status" className="text-sf-warn">暂无权威数据日</span>
        ) : (
          <span className="text-sf-ink tabular-nums">{`权威数据日：${data.date}`}</span>
        )}
        <span className="text-label text-sf-ink-3">{`代码 ${code}`}</span>
      </div>

      {/* spot_date / kline_date 分行独立，禁互兜底 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-label text-sf-ink-3">
        <div>{`行情快照日 spot_date：${fmtNum(data.spot_date)}`}</div>
        <div>{`K 线数据日 kline_date：${fmtNum(data.kline_date)}`}</div>
      </div>

      {/* 降权态：权威数据日或 perf 缺失时明确告知，不掩饰。 */}
      {degraded && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2"
        >
          <span aria-hidden="true" className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-sf-warn" />
          <span>
            <LeadText>部分基本面数据未取到，缺失项如实留空，未做补零或日期兜底</LeadText>
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label="名称" value={fmtNum(data.name)} />
        <Stat label="行业" value={fmtNum(data.industry)} />
        <Stat label="现价" value={fmtNum(data.price)} />
        <Stat label="PE(TTM)" value={fmtNum(data.pe_ttm)} />
        <Stat label="总市值" value={fmtNum(data.market_cap)} />
        <Stat label="价格域 priceDomain" value={data.priceDomain} />
      </div>

      <Card title="业绩核心指标（9 项）">
        {perf === null ? (
          <EmptyState label="暂无绩效指标" hint="perf 整体未取到，未做补零" />
        ) : (
          <ul className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {PERF_KEYS.map((k) => (
              <li
                key={k}
                className="flex items-center justify-between rounded-tile border border-sf-line bg-sf-surface-2 px-3.5 py-3"
              >
                <span className="text-label text-sf-ink-3">{PERF_LABELS[k]}</span>
                <span
                  data-testid={`perf-${k}`}
                  className={`text-kpi tabular-nums ${perf[k] === null ? 'text-sf-ink-3' : 'text-sf-ink'}`}
                >
                  {perf[k] === null ? '缺失' : fmtNum(perf[k])}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 有 rows：趋势卡 + 折叠财报表；无 rows / 取数中 / 失败：诚实态只呈现一次，
          避免错误 alert 重复（副源失败不得刷屏），趋势卡此时不渲染、不造假图。 */}
      {hasFinRows ? (
        <>
          <Card title="历史业绩趋势">
            <div role="radiogroup" aria-label="选择业绩指标" className="mb-3 flex flex-wrap gap-2">
              {TREND_METRICS.map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={metric === m}
                  data-testid={`metric-${m}`}
                  onClick={() => setMetric(m)}
                  className={`rounded-full border px-3 py-1 text-label transition-colors ${
                    metric === m
                      ? 'border-sf-accent text-sf-accent'
                      : 'border-sf-line text-sf-ink-3 hover:text-sf-ink-2'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
            {hasFinite(finRows, metric) ? (
              <FinancialTrendChart rows={finRows} metric={metric} />
            ) : (
              <EmptyState
                label={`「${metric}」在当前财报 rows 中无有效数值`}
                hint="null / 缺失期不绘图、不补零"
              />
            )}
            {!hasFinite(finRows, `${metric}_同比`) && (
              <p role="status" className="mt-2 text-label text-sf-ink-3">
                {`该指标无同比序列（当前财报未提供「${metric}_同比」），仅绘制柱体，不补零`}
              </p>
            )}
          </Card>

          <CollapsibleCard
            title="多期财报（三表合并）"
            summary={`${finRows.length} 期 · 最新报告期 ${fmtNum(latest['报告期'])} · 营业总收入 ${fmtNum(latest['营业总收入'])} 亿`}
            defaultOpen={false}
          >
            <FinancialTable rows={finRows} />
          </CollapsibleCard>
        </>
      ) : (
        <Card title="多期财报（三表合并）">
          <QueryState
            isLoading={fin.isLoading}
            isError={fin.isError}
            error={fin.error}
            isEmpty={!!fin.data && fin.data.rows.length === 0}
            emptyLabel="暂无财报数据"
            emptyHint="rows 为空数组，未做填充"
          >
            {null}
          </QueryState>
        </Card>
      )}

      <Card title="口径说明">
        {/* note 为后端原文，原样展示，不改写、不包装成投资建议。 */}
        <p className="text-body text-sf-ink-2">{data.note === null ? '原始响应未提供口径说明' : data.note}</p>
        {/* 补充裁决：如实交代数据日来源、report 语义、yoy 口径、三表合并，避免误读。 */}
        <ul className="mt-3 space-y-1 text-label text-sf-ink-3 list-disc pl-5">
          <li>财报为利润表 / 资产负债表 / 现金流量表三表合并指标，暂不支持单表切换（report 固定 income）。</li>
          <li>权威数据日与行情快照日均为数据自带时间戳，可能来自过期缓存（旧交易日），不标注「今日」。</li>
          <li>营收 / 净利变化率（revenue_yoy、profit_yoy）为「与上一报告期比」的相邻期口径，非同比或去年同期。</li>
          <li>历史业绩趋势图的同比为后端 _compute_yoy 算出的真实同比（「_同比」字段），与上方相邻期口径不同；缺失的报告期不绘图、不补零。</li>
        </ul>
      </Card>
    </div>
  )
}

/** 中文动态列名（含 _同比/_环比）：判空后再取首行 keys 渲染，不做重排。 */
/** 导出供 EarningsFinancialModal（财报日历行点击弹窗）复用，列名渲染口径单一来源。 */
export function FinancialTable({ rows }: { rows: Financials['rows'] }) {
  const cols = rows.length > 0 ? Object.keys(rows[0]) : []
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">多期财报明细，列名来自后端原始响应，未做重排</caption>
        <thead>
          <tr className="text-label text-sf-ink-3 border-b border-sf-line">
            {cols.map((c) => (
              <th key={c} scope="col" className="text-left py-2 pr-3 font-normal">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-sf-line last:border-0">
              {cols.map((c) => (
                <td key={c} className="py-1.5 pr-3 tabular-nums">{fmtNum(r[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
