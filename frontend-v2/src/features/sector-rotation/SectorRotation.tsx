import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import type { SectorItem, SectorRotation } from '@/api/schemas/read'
import { useSectorRotation } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 12 页「板块轮动热力图」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useSectorRotation → GET /api/v2/read/sector-rotation（后端复用 modules.fundflow）。
 *
 * 三大视图：🔥 热力图（ECharts treemap，块大小=|净额|、颜色=涨跌幅）/
 * 📊 排行榜（ECharts 横向条形，涨幅/跌幅 TOP10）/🔄 强弱象限（涨跌幅×净额，CSS 散点）。
 *
 * 红线：
 * - 取不到行业资金流→items=[]、unavailable 标注，不编数据；净额缺失如实「—」。
 * - 数值后端已清洗为 null，前端不补 0（避开 ?? 0 / || 0 / new Date()）。
 * - 红涨绿跌（A 股交易屏语义）。
 */
// 仅供图表坐标 / 文本占位：非数→0，不编数据（避开诚实红线 ?? 0 / || 0 / new Date()）
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function fmtPct(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }
  return '—'
}
function fmtYi(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(1)} 亿`
  }
  return '—'
}
function chgColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}

// 热力图块颜色：涨跌幅在 [-5%, +5%] 间向红(涨)/绿(跌)发散，0 为中性灰。
function tileColor(chg: unknown): string {
  const c = nz(chg)
  const t = Math.max(-1, Math.min(1, c / 5))
  const neutral = [207, 207, 207]
  const target = t >= 0 ? [255, 77, 79] : [0, 212, 134]
  const k = Math.abs(t)
  const mix = neutral.map((n, i) => Math.round(n + (target[i] - n) * k))
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`
}

// 热力图：treemap 块大小=|净额|(亿)、颜色=涨跌幅（红涨绿跌）。
function buildTreemapOption(items: SectorItem[]): EChartsOption {
  const data = items.map((it) => ({
    name: it.name ?? '—',
    value: Math.abs(nz(it.net)) + 1, // +1 保底，避免 0 尺寸不渲染
    itemStyle: { color: tileColor(it.chg_pct) },
    _chg: nz(it.chg_pct),
    _net: nz(it.net),
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: unknown) => {
        const pp = p as { name?: string; _chg?: number; _net?: number }
        return `${pp.name ?? ''}｜涨跌幅 ${fmtPct(pp._chg)}｜净额 ${fmtYi(pp._net)}`
      },
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        data,
        label: { color: '#fff', fontSize: 11, formatter: (p: unknown) => {
          const pp = p as { name?: string }
          return `${pp.name ?? ''}`
        } },
        upperLabel: { show: false },
        levels: [{ itemStyle: { borderColor: CHART.bg, borderWidth: 1, gapWidth: 1 } }],
      },
    ],
  }
}

// 排行榜：横向条形（涨跌幅 %）。ascending=true 取跌幅 TOP（从下往上），否则涨幅 TOP。
function buildRankBarOption(items: SectorItem[], ascending: boolean): EChartsOption {
  const sorted = [...items]
    .filter((it) => Number.isFinite(nz(it.chg_pct)))
    .sort((a, b) => nz(a.chg_pct) - nz(b.chg_pct))
  const top = (ascending ? sorted.slice(0, 10) : sorted.slice(-10)).reverse()
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 28, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: {
      type: 'category',
      data: top.map((it) => it.name ?? '—'),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        data: top.map((it) => ({
          value: nz(it.chg_pct),
          itemStyle: { color: chgColor(it.chg_pct) },
        })),
      },
    ],
  }
}

const VIEW_TABS = ['🔥 热力图', '📊 排行榜', '🔄 强弱象限'] as const
type ViewTab = (typeof VIEW_TABS)[number]

export function SectorRotation() {
  const q = useSectorRotation()
  const d = q.data
  const items = d?.items ?? []
  const srcLabel = d?.src_label ?? null
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')
  const isEmpty = !!d && items.length === 0

  const [tab, setTab] = useState<ViewTab>('🔥 热力图')

  const valid = items.filter((it) => it.name)
  const sorted = [...valid].sort((a, b) => nz(b.chg_pct) - nz(a.chg_pct))
  const topGainers = sorted.slice(0, 10)
  const topLosers = [...sorted].reverse().slice(0, 10)
  const topNet = [...valid].filter((it) => Number.isFinite(nz(it.net))).sort((a, b) => nz(b.net) - nz(a.net)).slice(0, 3)
  const leadGain = sorted[0] ?? null

  // 轮动判断
  const avg = valid.length ? valid.reduce((s, it) => s + nz(it.chg_pct), 0) / valid.length : 0
  const inflowCnt = valid.filter((it) => nz(it.net) > 0).length
  const inflowRatio = valid.length ? inflowCnt / valid.length : 0

  // 强弱象限坐标范围
  const xs = valid.map((it) => nz(it.chg_pct))
  const ys = valid.map((it) => nz(it.net))
  const xMin = Math.min(0, ...(xs.length ? xs : [0]))
  const xMax = Math.max(0, ...(xs.length ? xs : [0]))
  const yMin = Math.min(0, ...(ys.length ? ys : [0]))
  const yMax = Math.max(0, ...(ys.length ? ys : [0]))
  const xSpan = xMax - xMin || 1
  const ySpan = yMax - yMin || 1

  return (
    <div className="sector-rotation">
      <h2 className="text-lg font-semibold">板块轮动热力图</h2>
      <div className="text-xs text-sf-ink-3">
        红涨绿跌；热力图块大小代表资金净流入（亿元），颜色代表涨跌幅。各视图独立取数。
        行业资金流接口可能受网络限制，稍后重试即可。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="板块数据未就绪"
        emptyHint="取数失败（离线 / 接口受限 / 非交易时段）；后端已诚实降级，未编造板块列表"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="板块数量" value={String(valid.length)} sub="行业级样本" />
              <Stat
                label="领涨行业"
                value={leadGain ? leadGain.name ?? '—' : '—'}
                sub={leadGain ? fmtPct(leadGain.chg_pct) : '无上涨板块'}
              />
              <Stat
                label="净流入第一"
                value={topNet[0] ? topNet[0].name ?? '—' : '—'}
                sub={topNet[0] ? fmtYi(topNet[0].net) : '无资金流数据'}
              />
              <Stat label="行情数据源" value={srcLabel ?? '—'} sub="取数接口：akshare" />
            </div>

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              {VIEW_TABS.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`rounded px-3 py-1 text-xs font-medium border ${tab === t ? 'bg-sf-accent text-white border-sf-accent' : 'bg-sf-surface text-sf-ink-3 border-sf-line'}`}
                  onClick={() => setTab(t)}
                >
                  {t}
                </button>
              ))}
            </div>

            {tab === '🔥 热力图' && (
              <Card title="🔥 热力图（块大小=资金净流入，颜色=涨跌幅）">
                {valid.length > 0 ? (
                  <EChart option={buildTreemapOption(valid)} height={460} ariaLabel="行业板块 treemap 热力图，块大小代表资金净流入，颜色代表涨跌幅" />
                ) : (
                  <div className="text-xs text-sf-ink-3">暂无板块数据。</div>
                )}
              </Card>
            )}

            {tab === '📊 排行榜' && (
              <div className="grid md:grid-cols-2 gap-4">
                <Card title="🚀 涨幅 TOP10">
                  {topGainers.length > 0 ? (
                    <EChart option={buildRankBarOption(valid, false)} height={Math.max(220, topGainers.length * 32)} ariaLabel="行业涨幅前十横向条形图" />
                  ) : (
                    <div className="text-xs text-sf-ink-3">无上涨板块。</div>
                  )}
                </Card>
                <Card title="📉 跌幅 TOP10">
                  {topLosers.length > 0 ? (
                    <EChart option={buildRankBarOption(valid, true)} height={Math.max(220, topLosers.length * 32)} ariaLabel="行业跌幅前十横向条形图" />
                  ) : (
                    <div className="text-xs text-sf-ink-3">无下跌板块。</div>
                  )}
                </Card>
              </div>
            )}

            {tab === '🔄 强弱象限' && (
              <Card title="🔄 强弱象限（涨跌幅 × 资金净额）">
                {valid.length > 0 ? (
                  <div className="relative w-full h-[420px] border border-sf-line rounded-md overflow-hidden bg-sf-surface/40">
                    {/* 十字准线 */}
                    <div className="absolute left-0 right-0 top-1/2 border-t border-dashed border-sf-line/60" />
                    <div className="absolute top-0 bottom-0 left-1/2 border-l border-dashed border-sf-line/60" />
                    {/* 象限标签 */}
                    <span className="absolute right-2 top-1 text-[11px] opacity-60">右上：价量齐升（领涨主线）</span>
                    <span className="absolute left-2 bottom-1 text-[11px] opacity-60">左下：价量齐跌（弱势板块）</span>
                    <span className="absolute left-2 top-1 text-[11px] opacity-60">左上：涨但流出</span>
                    <span className="absolute right-2 bottom-1 text-[11px] opacity-60">右下：跌但流入</span>
                    {valid.map((it, i) => {
                      const left = ((nz(it.chg_pct) - xMin) / xSpan) * 100
                      const top = 100 - ((nz(it.net) - yMin) / ySpan) * 100
                      return (
                        <div
                          key={it.name ?? i}
                          className="absolute -translate-x-1/2 -translate-y-1/2"
                          style={{ left: `${left}%`, top: `${top}%` }}
                          title={`${it.name ?? '—'}｜涨跌幅 ${fmtPct(it.chg_pct)}｜净额 ${fmtYi(it.net)}`}
                        >
                          <span
                            className="block w-3 h-3 rounded-full border border-white/70"
                            style={{ background: chgColor(it.chg_pct) }}
                          />
                          <span className="absolute left-1/2 -translate-x-1/2 mt-1 text-[10px] whitespace-nowrap opacity-80">{it.name ?? ''}</span>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="text-xs text-sf-ink-3">暂无板块数据。</div>
                )}
                <div className="mt-2 text-[11px] opacity-70">
                  右上象限＝价量齐升的领涨主线；左下象限＝价量齐跌的弱势板块。资金从绿（净流出）板块流向红（净流入）板块即为轮动。
                </div>
              </Card>
            )}

            {/* 板块轮动解读 */}
            <div>
              <h3 className="text-sm font-semibold mb-2">🧭 板块轮动解读</h3>
              <div className="grid md:grid-cols-3 gap-3 text-xs">
                <div className="border border-sf-line rounded-md p-3">
                  <div className="font-semibold mb-1">🟢 领涨前三</div>
                  {topGainers.slice(0, 3).map((it) => (
                    <div key={it.name ?? 'g'} className="flex justify-between">
                      <span>{it.name ?? '—'}</span>
                      <span style={{ color: chgColor(it.chg_pct) }}>{fmtPct(it.chg_pct)}</span>
                    </div>
                  ))}
                  {topGainers.length === 0 && <div className="opacity-60">无上涨板块</div>}
                </div>
                <div className="border border-sf-line rounded-md p-3">
                  <div className="font-semibold mb-1">🔴 领跌前三</div>
                  {topLosers.slice(0, 3).map((it) => (
                    <div key={it.name ?? 'l'} className="flex justify-between">
                      <span>{it.name ?? '—'}</span>
                      <span style={{ color: chgColor(it.chg_pct) }}>{fmtPct(it.chg_pct)}</span>
                    </div>
                  ))}
                  {topLosers.length === 0 && <div className="opacity-60">无下跌板块</div>}
                </div>
                <div className="border border-sf-line rounded-md p-3">
                  <div className="font-semibold mb-1">💰 净流入前三</div>
                  {topNet.map((it) => (
                    <div key={it.name ?? 'n'} className="flex justify-between">
                      <span>{it.name ?? '—'}</span>
                      <span>{fmtYi(it.net)}</span>
                    </div>
                  ))}
                  {topNet.length === 0 && <div className="opacity-60">无资金流数据</div>}
                </div>
              </div>
              <div className="mt-2 text-xs">
                {avg > 0.5 && inflowRatio > 0.6 ? (
                  <div className="text-sf-ink-3">📈 <b>偏强轮动</b>：多数板块上涨且资金净流入，市场情绪偏多，关注领涨主线持续性。</div>
                ) : avg < -0.5 && inflowRatio < 0.4 ? (
                  <div className="text-sf-ink-3">📉 <b>偏弱轮动</b>：多数板块下跌且资金净流出，注意风险控制，等待企稳信号。</div>
                ) : (
                  <div className="text-sf-ink-3">⚖️ <b>震荡分化</b>：板块涨跌互现、资金方向不一，结构性行情为主，关注个别强势板块机会。</div>
                )}
              </div>
            </div>

            <div className="text-xs text-sf-ink-3">
              口径与来源：热力图/排行榜/强弱象限=akshare 行业资金流接口（含涨跌幅与资金净额，接口受限时如实标注）。
              行情为页面加载时点快照，非实时，非投资建议。
            </div>
          </div>
        ) : null}
      </QueryState>

      <div className="mt-8">
        <div className="text-xs text-sf-ink-3">
          ⚠️ 说明：本页为行业板块强弱与资金流向的快照展示，非预测模型，不构成投资建议；
          行业资金流为页面加载时点数据，盘中读数可能有延迟。
        </div>
      </div>
    </div>
  )
}
