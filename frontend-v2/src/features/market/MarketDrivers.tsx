import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import type { MarketSentiment, SentimentIndicator } from '@/api/schemas/read'
import { useMarketSentiment } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/**
 * 15 市场驱动力 · 五维归一化子图 / 相关热力 / CSV 导出。
 *
 * 数据源：现成端点 GET /api/v2/read/market-sentiment（50 页同源，四层已接线：
 * MarketSentimentSchema / getMarketSentiment / useMarketSentiment），21 指标按
 * 资金/情绪/估值/宏观/技术五维返回 dims，每指标带近 40 点 spark。
 *
 * 诚实红线：端点没有 v1 的上证参考线，也没有全 180 天原始归一化面板。本页的
 * 归一化叠加、相关热力、CSV 全部是**派生**视图（起点=100 / Pearson / 本地 Blob），
 * 页面与映射表均显式标注「派生、口径不同」；缺值显「—」或留空，绝不补 0。
 */

const DAYS = 180

interface NormalizedSeries {
  key: string
  name: string
  values: Array<number | null>
}

/** 派生：按 spark 首个有效值=100 归一化；null 保留，不补零。首个有效值为 0 时不参与归一化。 */
export function normalizeSpark(it: SentimentIndicator): NormalizedSeries {
  const baseIdx = it.spark.findIndex(
    (v) => typeof v === 'number' && Number.isFinite(v) && v !== 0,
  )
  const base = baseIdx >= 0 ? it.spark[baseIdx] : null
  return {
    key: it.key,
    name: it.name,
    values:
      base === null
        ? it.spark.map(() => null)
        : it.spark.map((v) =>
            typeof v === 'number' && Number.isFinite(v) ? (v / base) * 100 : null,
          ),
  }
}

function hasPlot(series: NormalizedSeries): boolean {
  return series.values.some((v) => v !== null)
}

function pearson(rows: Array<[number, number]>): number | null {
  const n = rows.length
  if (n < 3) return null
  let sx = 0
  let sy = 0
  for (const [x, y] of rows) {
    sx += x
    sy += y
  }
  const mx = sx / n
  const my = sy / n
  let num = 0
  let dx = 0
  let dy = 0
  for (const [x, y] of rows) {
    const a = x - mx
    const b = y - my
    num += a * b
    dx += a * a
    dy += b * b
  }
  if (dx <= 0 || dy <= 0) return null
  const r = num / Math.sqrt(dx * dy)
  return Number.isFinite(r) ? Math.max(-1, Math.min(1, r)) : null
}

/** 派生相关矩阵：x/y 均为指标下标，值为 Pearson；样本不足或常量序列为 null（画空，不补零）。 */
export function deriveCorrelation(items: SentimentIndicator[]) {
  const names = items.map((it) => it.name)
  const sparks = items.map((it) => it.spark)
  const data: Array<[number, number, number | null]> = []
  for (let i = 0; i < items.length; i += 1) {
    for (let j = 0; j < items.length; j += 1) {
      if (i === j) {
        data.push([j, i, 1])
        continue
      }
      const rows: Array<[number, number]> = []
      const n = Math.min(sparks[i].length, sparks[j].length)
      for (let k = 0; k < n; k += 1) {
        const a = sparks[i][k]
        const b = sparks[j][k]
        if (
          typeof a === 'number' && Number.isFinite(a) &&
          typeof b === 'number' && Number.isFinite(b)
        ) {
          rows.push([a, b])
        }
      }
      data.push([j, i, pearson(rows)])
    }
  }
  return { names, data }
}

function csvCell(v: string): string {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
}

function cellValue(v: number | null | undefined): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : ''
}

/** 派生 CSV：缺失值留空单元格，不补 0；序列列取自端点 spark 的归一化派生。 */
export function buildDerivedCsv(data: MarketSentiment): string {
  const rows: string[][] = [
    ['维度', '指标key', '指标名称', '单位', '最新值', '热度', '派生归一化序列(起点=100,近40点)'],
  ]
  for (const [dim, items] of Object.entries(data.dims)) {
    for (const it of items) {
      rows.push([
        dim,
        it.key,
        it.name,
        it.unit || '',
        cellValue(it.value),
        cellValue(it.heat),
        normalizeSpark(it).values.map(cellValue).join('|'),
      ])
    }
  }
  return `\uFEFF${rows.map((r) => r.map(csvCell).join(',')).join('\n')}`
}

function totalIndicators(data: MarketSentiment): number {
  return Object.values(data.dims).reduce((n, items) => n + items.length, 0)
}

function shortName(name: string): string {
  return name.length > 6 ? `${name.slice(0, 6)}…` : name
}

export function MarketDrivers() {
  const q = useMarketSentiment(DAYS)
  const data = q.data

  const downloadCsv = () => {
    if (!data) return
    const blob = new Blob([buildDerivedCsv(data)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `市场驱动力派生_${data.data_as_of ?? 'unknown'}.csv`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">市场驱动力 · 五维归一化</h2>
        <span className="text-label text-sf-ink-3">
          数据源 /market-sentiment（21 指标五维，近 40 点派生）
        </span>
        <a
          href="/market-sentiment"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          市场情绪温度计 →
        </a>
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={!!data && (!data.available || totalIndicators(data) === 0)}
        emptyLabel="暂无市场驱动力数据"
        emptyHint={data?.reason ?? data?.note ?? '端点未返回可用指标，未做任何填充'}
        onRetry={() => q.refetch()}
        retrying={q.isRefetching}
      >
        {data ? <MarketDriversBody data={data} onDownload={downloadCsv} /> : null}
      </QueryState>
    </div>
  )
}

function MarketDriversBody({
  data,
  onDownload,
}: {
  data: MarketSentiment
  onDownload: () => void
}) {
  const dims = useMemo(() => Object.entries(data.dims), [data.dims])
  const allItems = useMemo(() => dims.flatMap(([, items]) => items), [dims])
  const usable = useMemo(
    () =>
      allItems.filter((it) =>
        it.spark.some((v) => typeof v === 'number' && Number.isFinite(v)),
      ),
    [allItems],
  )
  const corr = useMemo(() => deriveCorrelation(usable), [usable])

  // 相关性用中性发散色（负=弱文灰蓝 / 零=表面 / 正=强调紫），不借用涨跌红绿语义。
  const corrOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { position: 'top' },
    grid: { left: 88, right: 24, top: 16, bottom: 92 },
    xAxis: {
      type: 'category',
      data: corr.names.map(shortName),
      axisLabel: { color: CHART.ink2, rotate: 45, hideOverlap: true, fontSize: 10 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      data: corr.names.map(shortName),
      axisLabel: { color: CHART.ink2, fontSize: 10 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    visualMap: {
      min: -1,
      max: 1,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: [CHART.ink3, CHART.surface2, CHART.accent] },
      textStyle: { color: CHART.ink2 },
    },
    series: [
      {
        type: 'heatmap',
        data: corr.data,
        label: { show: false },
        emphasis: { itemStyle: { borderColor: CHART.ink2, borderWidth: 1 } },
      },
    ],
  }

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="可用指标" value={fmtNum(totalIndicators(data))} sub="21 指标全集" />
        <Stat label="可参与热力" value={fmtNum(usable.length)} sub="近 40 点有值" />
        <Stat label="数据截至" value={data.data_as_of ?? '—'} />
        <Stat
          label="综合温度"
          value={fmtNum(data.temperature)}
          sub={data.level?.label ?? '样本不足'}
        />
      </div>

      <Card title="口径说明（派生，非 v1 原样迁移）">
        <p className="text-body text-sf-ink-2">
          v1《市场驱动力》用 21 指标按资金/情绪/估值/宏观/技术五维分组，叠加上证参考线，
          全部归一化到起点=100（约 180 天）。本页复用现成端点{' '}
          <code>/api/v2/read/market-sentiment</code>：仅拿到每个指标近 40 点原始 spark，
          因此下方五维叠加图、相关热力与 CSV 均为<strong style={{ color: 'var(--color-brand-1)' }}>派生</strong>视图（起点=100 / Pearson / 本地 Blob），
          口径与 v1 不同。
        </p>
        <p className="text-label text-sf-ink-3 mt-2">
          端点未提供上证参考线，也未提供全 180 天原始归一化面板；<strong style={{ color: 'var(--color-brand-1)' }}>本页不编造这两项</strong>。
          缺值显「—」或留空，不补零。
        </p>
      </Card>

      {dims.length === 0 ? (
        <Card title="五维归一化子图">
          <div className="text-body text-sf-ink-3">—｜端点未返回任何维度数据</div>
        </Card>
      ) : (
        dims.map(([dim, items]) => (
          <Card key={dim} title={`${dim}维度 · 归一化叠加（派生）`}>
            {items.length === 0 ? (
              <div className="text-body text-sf-ink-3">—｜该维度暂无可用指标</div>
            ) : (
              <NormalizedPanel items={items} dim={dim} />
            )}
          </Card>
        ))
      )}

      <Card title="指标相关性热力（派生）">
        {usable.length < 2 ? (
          <div className="text-body text-sf-ink-3">—｜可用指标不足 2 项，无法计算相关性</div>
        ) : (
          <>
            <EChart
              option={corrOption}
              height={Math.max(280, usable.length * 22)}
              ariaLabel={`指标派生皮尔逊相关系数热力图，共${usable.length}个可用指标`}
            />
            <p className="text-label text-sf-ink-3 mt-1">
              派生：基于端点近 40 点原始序列逐对计算 Pearson 系数；横纵轴为指标简称，
              样本不足的配对留空不补零。
            </p>
          </>
        )}
      </Card>

      <Card title="CSV 导出（派生）">
        <button
          type="button"
          onClick={onDownload}
          className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1.5 text-body text-sf-ink hover:border-sf-accent"
        >
          导出派生 CSV（近 40 点）
        </button>
        <p className="text-label text-sf-ink-3 mt-2">
          导出内容为端点 spark 的派生归一化序列；缺失值留空单元格，绝不补 0。
          文件名取自真实数据日 {data.data_as_of ?? '—'}。
        </p>
      </Card>

      {data.unavailable.length > 0 && (
        <Card title="不可用指标（诚实降级）">
          <div className="flex flex-wrap gap-2 text-label text-sf-ink-2">
            {data.unavailable.map((u, i) => (
              <span
                key={`${u.dim}-${u.key}-${i}`}
                className="rounded-tile bg-sf-surface-2 px-2 py-1"
              >
                {u.dim}/{u.key}：{u.reason}
              </span>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function NormalizedPanel({ items, dim }: { items: SentimentIndicator[]; dim: string }) {
  const usable = items.map(normalizeSpark).filter(hasPlot)
  if (usable.length === 0) {
    return <div className="text-body text-sf-ink-3">—｜该维度无可用序列</div>
  }
  const length = Math.max(...usable.map((s) => s.values.length))
  const option: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: usable.map((s) => s.name), textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 48, right: 16, top: 28, bottom: 28 },
    xAxis: {
      type: 'category',
      data: Array.from({ length }, (_, i) => `T-${length - i}`),
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      name: '起点=100',
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: usable.map((s) => ({
      name: s.name,
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: s.values,
      lineStyle: { width: 1.5 },
    })),
  }
  return (
    <div>
      <EChart
        option={option}
        height={Math.max(200, usable.length * 26)}
        ariaLabel={`${dim}维度指标归一化叠加折线图，起点设为100，基于端点近40点派生`}
      />
      <div className="text-label text-sf-ink-3 mt-1">
        派生：按各指标 spark 首个有效值=100 归一化；端点未提供日期与上证参考线，
        横轴为相对位置 T-n。
      </div>
    </div>
  )
}
