import type { EChartsOption } from 'echarts'
import type { Theme, ThemeConcept } from '@/api/schemas/read'
import { useTheme, useThemeTransmission } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 75 页「题材热点」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useTheme → GET /api/v2/read/theme（后端复用 modules.theme_heat）。
 * ④ 事件传导图谱：useThemeTransmission（按需触发，默认不自动请求）。
 *
 * 红线：
 * - 取不到快照→concepts=[]、unavailable 标注，不编数据；生命周期为启发式分类，非预测。
 * - 数值后端已清洗为 null，前端不补 0（避开 ?? 0 / || 0 / new Date()）。
 */
// 仅供图表坐标 / 文本占位：非数→0，不编数据（避开诚实红线 ?? 0 / || 0 / new Date()）
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

const LIFECYCLE_ORDER = ['高潮', '发酵', '退潮', '平淡', '未知']
const LIFECYCLE_COLOR: Record<string, string> = {
  高潮: '#dc2626',
  发酵: '#f97316',
  退潮: '#16a34a',
  平淡: '#64748b',
  未知: '#94a3b8',
}

function fmtChgPct(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }
  return '—'
}
function chgColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}

function treemapValue(c: ThemeConcept): number {
  const mv = typeof c.mv === 'number' && Number.isFinite(c.mv) ? c.mv : null
  if (mv != null && mv > 0) return mv
  const chg = typeof c.chg === 'number' && Number.isFinite(c.chg) ? Math.abs(c.chg) : 0
  return chg + 1
}

function buildTreemapOption(concepts: ThemeConcept[]): EChartsOption {
  const data = concepts.map((c) => ({
    name: c.name ?? '—',
    value: treemapValue(c),
    itemStyle: { color: chgColor(c.chg) },
  }))
  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter: (p: unknown) => {
        const pp = p as { name?: string; value?: number }
        return `${pp.name ?? ''}｜市值 ${nz(pp.value) / 1e8 >= 1 ? `${(nz(pp.value) / 1e8).toFixed(0)} 亿` : `${nz(pp.value)}`}`
      },
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        data,
        label: { color: '#fff', fontSize: 11 },
        upperLabel: { show: false },
        levels: [{ itemStyle: { borderColor: CHART.bg, borderWidth: 1, gapWidth: 1 } }],
      },
    ],
  }
}

function buildLifecycleOption(counts: Record<string, number>): EChartsOption {
  const order = LIFECYCLE_ORDER.filter((k) => nz(counts[k]) > 0)
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: CHART.ink2 }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: {
      type: 'category',
      data: order,
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        data: order.map((k) => ({
          value: counts[k],
          itemStyle: { color: LIFECYCLE_COLOR[k] ?? CHART.ink2 },
        })),
      },
    ],
  }
}

export function Theme() {
  const q = useTheme()
  const d = q.data
  const tx = useThemeTransmission(60, false)

  const concepts = d?.concepts ?? []
  const summary = d?.summary ?? null
  const lifecycleCounts = d?.lifecycle_counts ?? {}
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')

  const withMv = concepts.filter((c) => typeof c.mv === 'number' && Number.isFinite(c.mv) && (c.mv as number) > 0)
  const showTreemap = withMv.length > 0
  const showLifecycle = Object.keys(lifecycleCounts).length > 0
  const ranked = [...concepts].sort((a, b) => {
    const av = typeof a.chg === 'number' && Number.isFinite(a.chg) ? a.chg : -Infinity
    const bv = typeof b.chg === 'number' && Number.isFinite(b.chg) ? b.chg : -Infinity
    return bv - av
  })
  const topRanked = ranked.slice(0, 20)
  const isEmpty = !!d && concepts.length === 0

  return (
    <div className="theme">
      <h2 className="text-lg font-semibold">题材热点</h2>
      <div className="text-xs text-sf-ink-3">
        概念板块 treemap 热力图（面积=总市值，颜色=涨跌幅，红涨绿跌）+ 生命周期（发酵/高潮/退潮/平淡）。
        数据源东财概念板块快照；生命周期为启发式分类，非预测。事件传导图谱按需生成（手动触发，取不到不顶替）。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="概念板块快照未就绪"
        emptyHint="取数失败（离线 / 接口受限 / 非交易时段）；后端已诚实降级，未编造题材"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="概念板块数" value={summary?.count == null ? '—' : String(summary.count)} />
              <Stat label="上涨板块" value={summary?.n_up == null ? '—' : String(summary.n_up)} color={CHART.up} />
              <Stat label="下跌板块" value={summary?.n_down == null ? '—' : String(summary.n_down)} color={CHART.down} />
              <Stat
                label="领涨题材"
                value={summary?.top_name ?? '—'}
                sub={fmtChgPct(summary?.top_chg)}
                color={summary?.top_chg == null ? undefined : chgColor(summary.top_chg)}
              />
            </div>

            {showTreemap && (
              <Card title="题材热力图（面积=总市值，颜色=涨跌幅）">
                <EChart option={buildTreemapOption(withMv)} height={460} ariaLabel="题材板块 treemap 热力图" />
                <div className="mt-2 text-xs text-sf-ink-3">红=上涨、绿=下跌；方块面积越大表示板块总市值越高。</div>
              </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card title="生命周期分布">
                {showLifecycle ? (
                  <EChart option={buildLifecycleOption(lifecycleCounts)} height={Math.max(160, LIFECYCLE_ORDER.length * 36)} ariaLabel="题材生命周期分布条形图" />
                ) : (
                  <div className="text-xs text-sf-ink-3">本批数据无生命周期分布（取数受限）。</div>
                )}
              </Card>
              <Card title={`热度榜（涨幅 Top ${topRanked.length}）`}>
                {topRanked.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-sf-ink">
                      <thead>
                        <tr className="text-sf-ink-3 border-b border-sf-line">
                          <th className="text-left py-1.5 pr-3">题材</th>
                          <th className="text-right py-1.5 pr-3">涨跌幅</th>
                          <th className="text-left py-1.5 pr-3">生命周期</th>
                          <th className="text-left py-1.5">领涨股</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topRanked.map((c, i) => (
                          <tr key={c.name ?? i} className="border-b border-sf-line/60">
                            <td className="py-1.5 pr-3">{c.name ?? '—'}</td>
                            <td className="py-1.5 pr-3 text-right font-medium" style={{ color: chgColor(c.chg) }}>
                              {fmtChgPct(c.chg)}
                            </td>
                            <td className="py-1.5 pr-3">
                              <span style={{ color: LIFECYCLE_COLOR[c.lifecycle ?? '未知'] ?? CHART.ink2 }}>{c.lifecycle ?? '未知'}</span>
                            </td>
                            <td className="py-1.5">{c.leader ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-xs text-sf-ink-3">无题材排名数据。</div>
                )}
              </Card>
            </div>

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            <div className="text-xs text-sf-ink-3">
              口径与来源：概念板块涨跌幅/换手率/市值=东财概念板块实时快照（akshare stock_board_concept_name_em，120 秒缓存，非实时行情）；
              生命周期=涨跌幅+换手分位启发式分类，描述当下状态，非预测；事件传导=近期新闻标题共现（手动触发，取不到不顶替）。不构成投资建议。
            </div>
          </div>
        ) : null}
      </QueryState>

      <div className="mt-8">
        <h3 className="text-base font-semibold mt-2">事件传导图谱</h3>
        <div className="text-xs text-sf-ink-3">
          从「一条消息」走到「谁可能受影响」——文本共现关联度，非收益预测。默认不自动抓取，避免每次进入页面空等网络。
        </div>
        <button
          type="button"
          className="mt-2 px-4 py-1.5 rounded-md bg-sf-accent text-white text-sm font-medium disabled:opacity-60"
          disabled={tx.isFetching}
          onClick={() => tx.refetch()}
        >
          {tx.isFetching ? '生成中…' : '🔍 生成传导图谱'}
        </button>
        {tx.isError && (
          <div className="mt-3 text-xs text-sf-down border-l-2 border-sf-down pl-3">传导生成失败，请稍后重试。</div>
        )}
        {tx.data && tx.data.status === 'unavailable' && (
          <div className="mt-3 text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
            ⚠️ 传导不可用：{String((tx.data as unknown as { reason?: string }).reason ?? '未取到真实概念数据')}
            —— 不展示任何臆造的题材关联表。
          </div>
        )}
        {tx.data && tx.data.status === 'empty' && (
          <div className="mt-3 text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
            📭 {String((tx.data as unknown as { reason?: string }).reason ?? '标题里没有命中任何已知概念')}
            （已分析 {nz(tx.data.n_titles)} 条标题）
          </div>
        )}
        {tx.data && (tx.data.status === 'ok' || (tx.data.entries && tx.data.entries.length > 0)) && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-sf-ink-3">
              最近一次生成：新闻标题 {nz(tx.data.n_titles)} 条｜命中概念 {nz(tx.data.n_concepts)} 个。
              {tx.data.basis ? `｜口径：${tx.data.basis}` : ''}
            </div>
            {tx.data.members_unavailable && tx.data.members_unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下概念取不到成分股（接口失败，不等于「无成分股」），已从结果中排除：{tx.data.members_unavailable.join('、')}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-sf-ink">
                <thead>
                  <tr className="text-sf-ink-3 border-b border-sf-line">
                    <th className="text-right py-1.5 pr-3">#</th>
                    <th className="text-left py-1.5 pr-3">标的</th>
                    <th className="text-right py-1.5 pr-3">关联度</th>
                    <th className="text-left py-1.5 pr-3">方向</th>
                    <th className="text-left py-1.5 pr-3">命中概念</th>
                    <th className="text-left py-1.5">证据标题</th>
                  </tr>
                </thead>
                <tbody>
                  {(tx.data.entries ?? []).map((e, i) => (
                    <tr key={`${e.code ?? ''}-${i}`} className="border-b border-sf-line/60">
                      <td className="py-1.5 pr-3 text-right opacity-50">{i + 1}</td>
                      <td className="py-1.5 pr-3">
                        <b>{e.name ?? '—'}</b>
                        <span className="opacity-50 text-[11px]"> {e.code ?? ''}</span>
                      </td>
                      <td className="py-1.5 pr-3 text-right font-medium">{typeof e.score === 'number' ? e.score : '—'}</td>
                      <td className="py-1.5 pr-3" style={{ color: e.dir_color ?? CHART.ink2 }}>{e.direction ?? '—'}</td>
                      <td className="py-1.5 pr-3 opacity-85 text-[11px]">{e.concepts ?? '—'}</td>
                      <td className="py-1.5 opacity-60 text-[11px]">{e.evidence ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {tx.data.disclaimer && <div className="text-xs text-sf-ink-3">⚠️ {tx.data.disclaimer}</div>}
          </div>
        )}
      </div>
    </div>
  )
}
