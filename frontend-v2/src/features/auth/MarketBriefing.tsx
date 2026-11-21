import { useQuery } from '@tanstack/react-query'
import type { EChartsOption } from 'echarts'
import { getPublicIndexIntraday, getPublicOverview, getPublicPicks } from '@/api/read'
import { EChart } from '@/shared/charts/EChart'

/**
 * 登录页左栏行情台（2026-11-21 老板需求：三块合一组件）。
 *
 * 把原先散在 LoginPage 内的 品牌卡 / 资金温度 / 今日市场 / AI 信号 合并为一个
 * 组件 `MarketBriefing`，并按本轮需求升级：
 *   1. 新增「上证分时」：当日 5 分钟分时线（新公开端点 public-index-intraday，
 *      昨收基准真实取自上一交易日收盘 bar；非交易时段/取数失败 → 诚实空态）；
 *   2. 「AI 信号」改为「今日推荐」：P1 量化信号 top_long 前 5（带信号数据日）
 *      + 行业资金流净额前 3 板块（public-picks 端点）——比孤零零的「看多 20 只」
 *      更贴近股民口味，且每条数据都有真实出处与数据日标注。
 *
 * 诚实红线（与 public-overview 一致）：
 *   - 全部无鉴权脱敏只读端点；缺失字段显「—」，不补 0、不编造；
 *   - 推荐只是灰度参考，disclaimer 原文透传；
 *   - 涨跌配色用交易屏语义（涨红跌绿）：--color-ss-up / --color-ss-down。
 */
export function MarketBriefing() {
  const overview = useQuery({
    queryKey: ['read', 'public-overview'],
    queryFn: getPublicOverview,
    retry: false,
  })
  const intraday = useQuery({
    queryKey: ['read', 'public-index-intraday'],
    queryFn: getPublicIndexIntraday,
    retry: false,
    // 登录页停留期间盘中分时 60s 轻刷新（TTL_TIERS.quote 同档）
    refetchInterval: 60_000,
  })
  const picks = useQuery({
    queryKey: ['read', 'public-picks'],
    queryFn: getPublicPicks,
    retry: false,
  })

  const data = overview.data
  const ind = (data?.indicators ?? {}) as Record<string, unknown>
  const num = (v: unknown): number | null =>
    typeof v === 'number' && Number.isFinite(v) ? v : null

  const temperature = num(data?.temperature)
  const up = num(ind.up_count)
  const down = num(ind.down_count)
  const limitUp = num(ind.limit_up)
  const limitDown = num(ind.limit_down)
  const redRatio = num(ind.red_ratio)
  const medianChg = num(ind.median_chg)
  const tempWidth = temperature == null ? 0 : Math.max(0, Math.min(100, temperature))
  const dash = '—'

  return (
    <div className="space-y-4">
      {/* 品牌区 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-3xl" aria-hidden="true">📊</span>
          <div>
            <div className="text-[1.25rem] font-extrabold text-sf-ink">StockSignal</div>
            <div className="text-label text-sf-ink-3">A股事件驱动投资分析平台</div>
          </div>
        </div>
        <p className="text-[0.86rem] text-sf-ink-2 leading-relaxed m-0">
          事件驱动的选股与仓位决策闭环：情绪温度 → 事件因子 → 仓位建议，逐日回测实证。
        </p>
      </div>

      {/* 资金温度 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-title font-medium text-sf-ink-2">资金温度</span>
          <span
            className="text-label font-semibold rounded-full px-2 py-0.5"
            style={{
              background: 'color-mix(in srgb, var(--color-brand-1) 12%, transparent)',
              color: 'var(--color-brand-1)',
              border: '1px solid color-mix(in srgb, var(--color-brand-1) 30%, transparent)',
            }}
          >
            {data?.cycle ?? '快照'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div
            className="text-[2rem] font-black tabular-nums min-w-[62px] text-center"
            style={{ color: 'var(--color-brand-1)' }}
          >
            {temperature == null ? dash : Math.round(temperature)}
          </div>
          <div
            className="flex-1 h-2.5 rounded-full overflow-hidden"
            style={{ background: 'color-mix(in srgb, var(--color-brand-1) 14%, var(--color-sf-line))' }}
            role="img"
            aria-label={
              temperature == null ? '资金温度暂无数据' : `资金温度 ${Math.round(temperature)} / 100`
            }
          >
            <div
              className="h-full rounded-full"
              style={{
                width: `${tempWidth}%`,
                background: 'linear-gradient(90deg, var(--color-brand-1), var(--color-brand-2))',
              }}
            />
          </div>
        </div>
        <div className="text-label text-sf-ink-3 mt-2">
          快照数据日：{data?.date ?? dash}
          {data?.as_of && data.as_of !== data.date ? ` · 生成于 ${data.as_of}` : ''}
        </div>
      </div>

      {/* 今日市场 */}
      <div className="rounded-card bg-sf-surface border border-sf-line p-5">
        <div className="text-title font-medium text-sf-ink-2 mb-3">今日市场</div>
        <div className="grid grid-cols-2 gap-3">
          <DeskMetric label="上涨家数" value={up} color="var(--color-ss-up)" dash={dash} />
          <DeskMetric label="下跌家数" value={down} color="var(--color-ss-down)" dash={dash} />
          <DeskMetric label="涨停" value={limitUp} color="var(--color-ss-up)" dash={dash} />
          <DeskMetric label="跌停" value={limitDown} color="var(--color-ss-down)" dash={dash} />
        </div>
        <div className="text-label text-sf-ink-3 mt-3 leading-relaxed">
          红盘占比 {redRatio == null ? dash : `${redRatio.toFixed(1)}%`} · 个股中位涨幅{' '}
          {medianChg == null ? dash : `${medianChg >= 0 ? '+' : ''}${medianChg.toFixed(2)}%`}
        </div>
      </div>

      {/* 上证分时（当日 5 分钟分时线 + 昨收基准） */}
      <IndexIntradayCard
        date={intraday.data?.date ?? null}
        prevClose={num(intraday.data?.prev_close)}
        rows={(intraday.data?.rows ?? []).map((r) => ({
          time: r.time,
          close: r.close,
        }))}
      />

      {/* 今日推荐：P1 量化信号 top_long 前 5 + 行业资金流净额前 3 */}
      <PicksCard picks={picks.data ?? null} dash={dash} />
    </div>
  )
}

/** 上证分时卡：折线 + 半透明面积；涨跌色随当日涨跌切换（交易屏语义）。 */
function IndexIntradayCard({
  date,
  prevClose,
  rows,
}: {
  date: string | null
  prevClose: number | null
  rows: { time: string; close: number }[]
}) {
  const last = rows.length ? rows[rows.length - 1].close : null
  const pct =
    last != null && prevClose != null && prevClose !== 0
      ? ((last - prevClose) / prevClose) * 100
      : null
  const lineColor = pct == null ? 'var(--color-brand-1)' : pct >= 0 ? 'var(--color-ss-up)' : 'var(--color-ss-down)'

  const option: EChartsOption = {
    grid: { left: 46, right: 12, top: 14, bottom: 22 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (typeof v === 'number' ? v.toFixed(2) : String(v)),
    },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.time.slice(11, 16)),
      axisLabel: { fontSize: 10, interval: Math.max(0, Math.floor(rows.length / 6) - 1) },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { fontSize: 10 },
      splitLine: { lineStyle: { opacity: 0.25 } },
    },
    series: [
      {
        type: 'line',
        data: rows.map((r) => r.close),
        showSymbol: false,
        lineStyle: { color: lineColor, width: 1.6 },
        areaStyle: { color: lineColor, opacity: 0.12 },
      },
    ],
  }

  return (
    <div className="rounded-card bg-sf-surface border border-sf-line p-5">
      <div className="flex items-baseline justify-between mb-2">
        <span
          className="text-title font-medium text-sf-ink-2 border-l-[3px] pl-2"
          style={{ borderColor: 'var(--color-brand-1)' }}
        >
          上证分时
        </span>
        <span className="text-label text-sf-ink-3 tabular-nums">
          {date ?? '—'}
          {pct != null ? (
            <b style={{ color: lineColor }} className="ml-1.5">
              {pct >= 0 ? '+' : ''}
              {pct.toFixed(2)}%
            </b>
          ) : null}
        </span>
      </div>
      {rows.length ? (
        <EChart
          option={option}
          height={140}
          ariaLabel={`上证指数 ${date ?? ''} 当日分时走势，最新 ${last ?? '—'}，较昨收 ${pct == null ? '未知' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`}`}
        />
      ) : (
        <div className="text-label text-sf-ink-3 py-6 text-center">
          暂无分时数据（非交易时段或数据源不可用），不做任何合成
        </div>
      )}
      <div className="text-label text-sf-ink-3 mt-1">
        5 分钟分时 · 昨收基准 {prevClose == null ? '—' : prevClose.toFixed(2)}（取上一交易日收盘，真实数据）
      </div>
    </div>
  )
}

/** 今日推荐卡：股票 top5 + 板块 top3；全部带真实数据日/资金流出处。 */
function PicksCard({ picks, dash }: { picks: PublicPicksView | null; dash: string }) {
  const stocks = picks?.stocks ?? []
  const sectors = picks?.sectors ?? []

  return (
    <div className="rounded-card bg-sf-surface border border-sf-line p-5">
      <div
        className="text-title font-medium text-sf-ink-2 mb-2 border-l-[3px] pl-2"
        style={{ borderColor: 'var(--color-brand-2)' }}
      >
        今日推荐
      </div>

      {/* 股票（P1 量化信号 top_long 前 5） */}
      <div className="text-label text-sf-ink-3 mb-1">
        强信号股票（量化灰度参考）
        {picks?.stocks_as_of ? ` · 信号数据日 ${picks.stocks_as_of}` : ''}
      </div>
      {stocks.length ? (
        <ul className="m-0 p-0 list-none space-y-1 mb-3">
          {stocks.map((s) => (
            <li key={s.code} className="flex items-center justify-between text-[0.86rem]">
              <span className="text-sf-ink">
                {s.name ?? dash}
                <span className="text-sf-ink-3 text-label ml-1.5">{s.code}</span>
              </span>
              <span className="tabular-nums" style={{ color: 'var(--color-brand-1)' }}>
                {s.pred == null ? dash : `+${(s.pred * 100).toFixed(1)}%`}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-label text-sf-ink-3 mb-3">{dash} 暂无信号标的</div>
      )}

      {/* 板块（行业资金流净额前 3） */}
      <div className="text-label text-sf-ink-3 mb-1">活跃板块（行业资金净流入领先）</div>
      {sectors.length ? (
        <ul className="m-0 p-0 list-none space-y-1">
          {sectors.map((s) => {
            // 净额为文本（后端补「亿」单位）；'-' 前缀 = 净流出 → 绿（交易屏语义）
            const netOut = typeof s.net === 'string' && s.net.trim().startsWith('-')
            return (
              <li key={s.industry} className="flex items-center justify-between text-[0.86rem]">
                <span className="text-sf-ink font-medium">{s.industry}</span>
                <span className="tabular-nums font-semibold" style={{ color: netOut ? 'var(--color-ss-down)' : 'var(--color-ss-up)' }}>
                  {s.net ?? dash}
                  {s.chg_pct != null ? (
                    <span
                      className="ml-1.5 font-medium"
                      style={{ color: s.chg_pct >= 0 ? 'var(--color-ss-up)' : 'var(--color-ss-down)' }}
                    >
                      {s.chg_pct >= 0 ? '+' : ''}
                      {s.chg_pct.toFixed(2)}%
                    </span>
                  ) : null}
                </span>
              </li>
            )
          })}
        </ul>
      ) : (
        <div className="text-label text-sf-ink-3">{dash} 暂无板块资金流数据</div>
      )}

      <div className="text-label text-sf-ink-3 mt-3 leading-relaxed">
        {picks?.disclaimer ?? '灰度参考，不构成投资建议'}
      </div>
    </div>
  )
}

/** PicksCard 入参视图类型（与 PublicPicks schema 字段一致，null 化可选值）。 */
interface PublicPicksView {
  stocks: { code: string; name: string | null; pred: number | null }[]
  stocks_as_of?: string | null
  sectors: { industry: string; chg_pct?: number | null; net?: string | null }[]
  disclaimer?: string | null
}

/** 行情台单指标：数值用等宽数字，缺失显示「—」并显式标注（不补 0）。 */
function DeskMetric({
  label,
  value,
  color,
  dash,
}: {
  label: string
  value: number | null
  color: string
  dash: string
}) {
  return (
    <div>
      <div className="text-label text-sf-ink-3">{label}</div>
      <div className="text-[1.4rem] font-bold tabular-nums" style={{ color }}>
        {value == null ? dash : value}
      </div>
    </div>
  )
}
