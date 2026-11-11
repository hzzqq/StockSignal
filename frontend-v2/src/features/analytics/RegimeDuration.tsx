import type { EChartsOption } from 'echarts'
import { useBreadthAnalytics } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { Loading, ErrorState, EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { AnalyticsHeader, DataBoundary, SectionState, show } from './shared'

const BAND_COLORS = ['#3b82f6', '#06b6d4', CHART.ok, CHART.warn, CHART.danger]

/**
 * 69 温度持续期与回归时长（v2 native /regime-duration）。
 * 数据源：GET /api/v2/read/breadth-analytics 的 duration 段（regime_duration 纯模块）。
 * 与 v1 对齐：五档持续中位柱状图、逐档明细、冰点→回归中性磨底时长。
 * 诚实修正：v1 柱状图把 median 为 None 补成 0；v2 送 null 不画柱，并显式标 n=0。
 */
export function RegimeDuration() {
  const q = useBreadthAnalytics()
  const d = q.data
  const sec = d?.sections.duration
  const bands = sec?.band_labels ?? []
  const durations = sec?.durations ?? {}
  const rec = sec?.recovery

  const barOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: bands,
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      name: '中位持续天数',
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        name: '中位持续天数',
        // 无样本不补 0：null 让该柱缺席。
        data: bands.map((_, i) => durations[String(i)]?.median ?? null),
        itemStyle: {
          color: (params: { dataIndex: number }) =>
            BAND_COLORS[params.dataIndex % BAND_COLORS.length],
        },
      },
    ],
  }

  return (
    <div className="space-y-4">
      <AnalyticsHeader
        title="温度持续期与回归时长"
        caption="以红盘占比五档（冰点 / 偏冷 / 中性 / 活跃 / 狂热）作为温度代理，统计每段连续同档 run 的时长分布，并测算冰点回归中性的磨底时长。历史统计描述，非预测。"
        data={d}
      />

      {q.isLoading && <Loading label="加载温度持续期统计…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '温度持续期统计加载失败'} />
      )}
      {!q.isLoading && !q.isError && !d && <EmptyState label="暂无温度持续期统计" />}

      {d && (
        <>
          <SectionState section={sec} label="温度持续期">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat
                label="冰点档持续中位"
                value={show(durations['0']?.median, ' 天')}
                sub={`run 数 n=${show(durations['0']?.n)}`}
              />
              <Stat
                label="狂热档持续中位"
                value={show(durations['4']?.median, ' 天')}
                sub={`run 数 n=${show(durations['4']?.n)}`}
              />
              <Stat
                label="冰点→回归中性磨底"
                value={show(rec?.median, ' 天')}
                sub={`均值 ${show(rec?.mean, ' 天')} · n=${show(rec?.n)} 段`}
              />
              <Stat label="历史 run 总数" value={show(sec?.total_runs)} sub="五档连续段合计" />
            </div>

            <Card title="各温度档持续期（中位天数）" className="mt-3">
              {bands.length > 0 ? (
                <>
                  <EChart
                    option={barOption}
                    height={320}
                    ariaLabel="五个温度档连续 run 的中位持续天数柱状图，无样本档不绘制"
                  />
                  <p className="mt-1 text-xs text-sf-ink-3">
                    每根柱 = 该温度档历史连续 run 的中位天数；无样本档不绘制、不补 0。仅描述历史停留时长，不预测未来。
                  </p>
                </>
              ) : (
                <EmptyState label="暂无温度档位定义" />
              )}
            </Card>

            <Card title="持续期明细">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                      <th className="py-2 pr-3">温度档</th>
                      <th className="py-2 pr-3">run 数</th>
                      <th className="py-2 pr-3">均值(天)</th>
                      <th className="py-2 pr-3">中位(天)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bands.map((b, i) => (
                      <tr key={b} className="border-b border-sf-line/60">
                        <td className="py-2 pr-3 text-sf-ink">{b}</td>
                        <td className="py-2 pr-3 text-sf-ink-2">{show(durations[String(i)]?.n)}</td>
                        <td className="py-2 pr-3 text-sf-ink-2">{show(durations[String(i)]?.mean)}</td>
                        <td className="py-2 pr-3 text-sf-ink-2">{show(durations[String(i)]?.median)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="冰点 → 回归中性 磨底时长">
              {rec?.n ? (
                <>
                  <p className="text-sm text-sf-ink-2">
                    中位 {show(rec.median, ' 天')} ｜ 均值 {show(rec.mean, ' 天')} ｜ 样本 {show(rec.n)} 段
                  </p>
                  <p className="mt-1 text-xs text-sf-ink-3">
                    统计自每段「冰点」run 结束到首个 ≥中性 交易日的间隔天数；描述历史磨底节奏，非预测。
                  </p>
                </>
              ) : (
                <EmptyState label="历史中无完整「冰点→回归中性」样本可供统计" />
              )}
            </Card>
          </SectionState>

          <DataBoundary
            data={d}
            method="以红盘占比五档作为温度代理，对每日标档后统计连续同档 run 的时长分布，并测算冰点 run 到首次回到 ≥中性 的中位天数；全部基于 shepherd_history 内部 red_ratio。"
            extra="本页「温度」是红盘占比(red_ratio) 五档代理，并非综合 8 指标的 0–100 合成温度——连板梯队类维度离线缺真值，无法合成综合温度。不引入指数/行业/资金流等编造数据。"
          />
        </>
      )}
    </div>
  )
}
