import { useEffect, useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Card } from '@/shared/ui/Card'
import { EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import type { EChartsOption } from 'echarts'
import { CHART } from '@/shared/charts/palette'
import { getCompareOne, type ComparePeriod } from '@/api/stock'
import type { CompareOne } from '@/api/schemas/stock'
import { inkForCell } from '@/lib/domainColor'
import { fmtNum } from '@/lib/format'
import type { CompareRouteSearch } from '@/lib/deeplink'

/**
 * W4-C · 多股对比页（/stock/compare，旧 24 页衍生）。
 *
 * 数据源：getCompareOne（/api/v2/read/compare-one，单股通用快照透传）。
 *  - useCompareMany 对 codes 切片 ≤4 并发（A1 方案：批次内 useQueries 并发、批间
 *    靠 `enabled` 门控顺序推进），返回逐股结果与 4 态。
 *  - 通用对比表：列=股票代码、行=字段（取所有返回对象的 key 并集，排除元字段）；
 *    每格按 domainInk/inkForCell 域级双色（价格域红涨绿跌、报告体绿涨红跌，
 *    负值翻转到该域下挫墨色；未知域中性）。颜色仅作域区分/强弱信号，不篡改为
 *    「红绿即涨跌」越权语义。
 *  - 多股序列对比图：单色 accent + 不同 symbol/线型 + 图例 + 等价数据表，
 *    严禁从 palette.ts 取多色。
 *  - 逐股 4 态诚实降级：loading/error/empty/ok 分别渲染，error 不谎报为数据。
 */

const CODE_RE = /^\d{6}$/
const BATCH = 4
const FIVE_MIN = 5 * 60_000

/** 元字段：不参与「字段×股票」对比矩阵的渲染。 */
const META_FIELDS = new Set(['code', 'name', 'industry', 'date', 'note', 'period'])

/** 纯函数：把数组按 size 切片（供 ≤4 并发分批与单测复用）。 */
export function chunkCodes<T>(arr: T[], size: number): T[][] {
  if (size <= 0) return [arr]
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

export interface ComparePerCode {
  code: string
  isLoading: boolean
  isError: boolean
  error: unknown
}

export interface CompareResult {
  /** code → 单股快照（或 null：未取/空/降级）。 */
  rows: Record<string, CompareOne | null>
  perCode: ComparePerCode[]
  isLoading: boolean
  isError: boolean
}

/**
 * 多股扇出 hook：批次内 useQueries 并发、批间 `enabled` 门控顺序推进，保证任意时刻
 * 在途请求 ≤ BATCH。返回 {rows, perCode}；rows 的 value 为 null 表示该股当前无数据
 * （未取/空/降级），由渲染层据 perCode 区分 4 态。
 */
export function useCompareMany(
  codes: string[],
  period: ComparePeriod = 'daily',
): CompareResult {
  // 去重 + 仅保留 6 位合法码；顺序稳定，保障 useQueries 调用数量恒定（hooks 规则）。
  const validCodes = useMemo(
    () => Array.from(new Set(codes.filter((c) => CODE_RE.test(c)))),
    [codes],
  )
  const [batch, setBatch] = useState(0)

  const queries = useQueries({
    queries: validCodes.map((code) => {
      const idx = validCodes.indexOf(code)
      const b = Math.floor(idx / BATCH)
      return {
        queryKey: ['read', 'compare-one', code, period] as const,
        queryFn: () => getCompareOne(code, period),
        enabled: b <= batch,
        staleTime: FIVE_MIN,
      }
    }),
  })

  // 批间顺序推进：当前批次全部 settle 后放行下一批（最后一批不再推进）。
  useEffect(() => {
    const total = Math.max(1, Math.ceil(validCodes.length / BATCH))
    if (batch >= total - 1) return
    const start = batch * BATCH
    const batchQueries = queries.slice(start, start + BATCH)
    const allSettled = batchQueries.length > 0 && batchQueries.every((q) => !q.isLoading)
    if (allSettled) setBatch((b) => b + 1)
  }, [queries, batch, validCodes.length])

  const rows: Record<string, CompareOne | null> = {}
  const perCode: ComparePerCode[] = validCodes.map((code, i) => {
    const q = queries[i]
    rows[code] = q.data ?? null
    return { code, isLoading: q.isLoading, isError: q.isError, error: q.error }
  })

  return {
    rows,
    perCode,
    isLoading: queries.some((q) => q.isLoading),
    isError: queries.some((q) => q.isError),
  }
}

/** 取所有快照的非元字段并集（稳定顺序：首个有数据对象的 key 优先）。 */
function unionFields(rows: Record<string, CompareOne | null>): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const data of Object.values(rows)) {
    if (!data) continue
    for (const k of Object.keys(data)) {
      if (META_FIELDS.has(k)) continue
      if (!seen.has(k)) {
        seen.add(k)
        ordered.push(k)
      }
    }
  }
  return ordered
}

/** 单股是否有可对比的非元字段（无 → empty 态）。 */
function hasMetrics(data: CompareOne | null): boolean {
  if (!data) return false
  return Object.keys(data).some((k) => !META_FIELDS.has(k))
}

// 多系列图：单色 accent + 不同 symbol/线型（禁止 palette 多色）。
const SERIES_SYMBOLS = ['circle', 'rect', 'triangle', 'diamond', 'pin', 'arrow'] as const
const SERIES_LINETYPES = ['solid', 'dashed', 'dotted'] as const

export interface CompareViewProps {
  /** 来自 resolveCompareSearch 的 {codes?, period?}；全 optional，E2E 可直接传字面量。 */
  search?: CompareRouteSearch
}

export function CompareView({ search }: CompareViewProps) {
  const [codesInput, setCodesInput] = useState<string>(
    () => (search?.codes ?? []).join(','),
  )
  const period = (search?.period as ComparePeriod) ?? 'daily'

  const codes = useMemo(() => {
    const fromInput = codesInput
      .split(',')
      .map((s) => s.trim())
      .filter((c) => CODE_RE.test(c))
    return Array.from(new Set([...(search?.codes ?? []), ...fromInput]))
  }, [codesInput, search?.codes])

  const { rows, perCode } = useCompareMany(codes, period)
  const fields = unionFields(rows)

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">个股对比</h2>
        <span className="text-label text-sf-ink-3">数据源 compare-one</span>
      </div>

      {/* 代码输入：逗号分隔；组件内过滤 6 位，非法码静默忽略（不写进查询）。 */}
      <label className="flex flex-wrap items-center gap-3 text-body">
        <span className="text-label text-sf-ink-3">股票代码（逗号分隔）</span>
        <input
          type="text"
          inputMode="numeric"
          value={codesInput}
          onChange={(e) => setCodesInput(e.target.value)}
          aria-label="股票代码（逗号分隔）"
          placeholder="600519,000001"
          className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2 text-body text-sf-ink tabular-nums"
        />
        <span className="text-label text-sf-ink-3">{`已选 ${codes.length} 只`}</span>
      </label>

      {codes.length === 0 ? (
        <Card title="对比矩阵">
          <div role="status" className="py-10 text-center text-body text-sf-ink-2">
            请输入至少一只 6 位数字股票代码
          </div>
        </Card>
      ) : (
        <>
          <Card title="通用对比表（列=代码，行=字段）">
            {!perCode.some((p) => p.isLoading) && fields.length === 0 ? (
              <EmptyState
                label="暂无对比数据"
                hint="所有个股均无可用指标字段（取数失败或返回空）"
              />
            ) : (
              <CompareTable rows={rows} perCode={perCode} fields={fields} />
            )}
          </Card>

          <CompareChart rows={rows} perCode={perCode} fields={fields} />
        </>
      )}
    </div>
  )
}

/** 通用对比矩阵：逐股 4 态降级 + 域级双色。 */
function CompareTable({
  rows,
  perCode,
  fields,
}: {
  rows: Record<string, CompareOne | null>
  perCode: ComparePerCode[]
  fields: string[]
}) {
  const statusOf = (code: string) => perCode.find((p) => p.code === code)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-body border-collapse">
        <caption className="sr-only">多股字段对比矩阵，列名取后端原始响应 key，未做重排</caption>
        <thead>
          <tr className="text-label text-sf-ink-3 border-b border-sf-line">
            <th scope="col" className="text-left py-2 pr-3 font-normal sticky left-0 bg-sf-surface">字段</th>
            {perCode.map((p) => (
              <th key={p.code} scope="col" className="text-left py-2 pr-3 font-normal tabular-nums">
                {p.code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-sf-ink-2">
          {fields.map((field) => (
            <tr key={field} className="border-b border-sf-line last:border-0">
              <th
                scope="row"
                className="text-left py-1.5 pr-3 font-normal text-sf-ink-3 sticky left-0 bg-sf-surface"
                style={{ color: inkForCell(field, undefined) }}
              >
                {field}
              </th>
              {perCode.map((p) => {
                const st = statusOf(p.code)!
                if (st.isLoading) {
                  return (
                    <td key={p.code} className="py-1.5 pr-3">
                      <span role="status" className="text-sf-ink-3">加载中…</span>
                    </td>
                  )
                }
                if (st.isError) {
                  return (
                    <td key={p.code} className="py-1.5 pr-3">
                      <span role="alert" className="text-sf-warn">
                        获取失败
                      </span>
                    </td>
                  )
                }
                const data = rows[p.code]
                if (!hasMetrics(data)) {
                  return (
                    <td key={p.code} className="py-1.5 pr-3 text-sf-ink-3">—</td>
                  )
                }
                const value = (data as Record<string, unknown>)[field]
                return (
                  <td
                    key={p.code}
                    className="py-1.5 pr-3 tabular-nums"
                    style={value === null || value === undefined ? undefined : { color: inkForCell(field, value) }}
                  >
                    {fmtNum(value)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * 多股序列对比图：取数值型字段，x=股票代码、每字段一条 series（单色 accent，
 * 不同 symbol/线型区分），配图例。禁用 palette 多色。下方附等价数据表（图非唯一
 * 信息载体，满足无障碍）。无任何数值字段时不渲染图（诚实：不画空图表）。
 */
function CompareChart({
  rows,
  perCode,
  fields,
}: {
  rows: Record<string, CompareOne | null>
  perCode: ComparePerCode[]
  fields: string[]
}) {
  const numericFields = useMemo(
    () =>
      fields.filter((f) => {
        for (const p of perCode) {
          const v = rows[p.code]
          if (v && typeof (v as Record<string, unknown>)[f] === 'number') return true
        }
        return false
      }),
    [fields, rows, perCode],
  )

  if (numericFields.length === 0) return null

  const codes = perCode.map((p) => p.code)
  const series = numericFields.map((field, i) => ({
    name: field,
    type: 'line' as const,
    symbol: SERIES_SYMBOLS[i % SERIES_SYMBOLS.length],
    symbolSize: 8,
    itemStyle: { color: CHART.accent },
    lineStyle: { color: CHART.accent, type: SERIES_LINETYPES[i % SERIES_LINETYPES.length], width: 2 },
    data: codes.map((code) => {
      const v = rows[code]
      const val = v ? (v as Record<string, unknown>)[field] : null
      return typeof val === 'number' ? val : null
    }),
  }))

  // ⚠️ ECharts 是 canvas，吃不到 CSS 变量，颜色一律用 CHART hex 常量（经 EChart 的
  // remapChartColors 在 light 主题自动重映射）。仅取单色 accent（多色集合禁用），
  // 多股区分靠 symbol/线型 + 图例。
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    color: [CHART.accent],
    tooltip: { trigger: 'axis' as const },
    legend: { data: numericFields, textStyle: { color: CHART.ink2 } },
    grid: { left: 48, right: 24, top: 36, bottom: 36 },
    xAxis: {
      type: 'category' as const,
      data: codes,
      axisLine: { lineStyle: { color: CHART.line } },
      axisLabel: { color: CHART.ink3 },
    },
    yAxis: {
      type: 'value' as const,
      axisLine: { lineStyle: { color: CHART.line } },
      axisLabel: { color: CHART.ink3 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series,
  }

  return (
    <Card title="多股数值对比图（单色 + 形状/线型区分）">
      <EChart option={option} height={280} ariaLabel="多股数值字段对比折线图，关键数值见下方等价数据表" />
      {/* 等价数据表：图形不是唯一信息载体 */}
      <div className="overflow-x-auto mt-3">
        <table className="w-full text-body border-collapse">
          <caption className="sr-only">多股数值字段对比等价数据表</caption>
          <thead>
            <tr className="text-label text-sf-ink-3 border-b border-sf-line">
              <th scope="col" className="text-left py-2 pr-3 font-normal">字段</th>
              {codes.map((c) => (
                <th key={c} scope="col" className="text-left py-2 pr-3 font-normal tabular-nums">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody className="text-sf-ink-2">
            {numericFields.map((field) => (
              <tr key={field} className="border-b border-sf-line last:border-0">
                <th scope="row" className="text-left py-1.5 pr-3 font-normal text-sf-ink-3">{field}</th>
                {codes.map((c) => {
                  const v = rows[c]
                  const val = v ? (v as Record<string, unknown>)[field] : null
                  return (
                    <td key={c} className="py-1.5 pr-3 tabular-nums" style={typeof val === 'number' ? { color: inkForCell(field, val) } : undefined}>
                      {fmtNum(val)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
