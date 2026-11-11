import type { EChartsOption } from 'echarts'
import { useBreadthAnalytics } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { Loading, ErrorState, EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { AnalyticsHeader, DataBoundary, SectionState, show } from './shared'

const OFFSETS = ['5', '10', '20'] as const

/**
 * 67 历史相似日聚类 · 前向分布（v2 native /similar-days）。
 * 数据源：GET /api/v2/read/breadth-analytics 的 similar 段（similar_day_cluster 纯模块）。
 * 与 v1 对齐：top-N 相似日表、后 5/10/20 日红盘占比经验分布、数据闸门剔除项披露。
 * 诚实修正：v1 柱状图用 `.get(off, 0)` 把缺失补成 0；v2 缺样本送 null，ECharts 不画该柱。
 */
export function SimilarDays() {
  const q = useBreadthAnalytics()
  const d = q.data
  const sec = d?.sections.similar
  const fs = sec?.forward_stats ?? {}
  const rows = sec?.similar ?? []

  const barOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: OFFSETS.map((o) => `后 ${o} 日`),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      name: '红盘占比(%)',
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        name: '红盘占比(≥50%)',
        // 无样本不补 0：null 让该柱缺席，页面另标「无足够前向样本」。
        data: OFFSETS.map((o) => (fs[o]?.n ? fs[o]?.up_ratio ?? null : null)),
        itemStyle: { color: CHART.accent },
        label: { show: true, position: 'top', color: CHART.ink2, formatter: '{c}%' },
      },
    ],
  }

  return (
    <div className="space-y-4">
      <AnalyticsHeader
        title="历史相似日聚类 · 前向分布"
        caption="取最新一日真实广度向量，在全历史按标准化欧氏距离检索最相似 top-N 日，统计其后继 5/10/20 日红盘占比分布。历史类比，非预测。"
        data={d}
      />

      {q.isLoading && <Loading label="加载历史相似日统计…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '历史相似日统计加载失败'} />
      )}
      {!q.isLoading && !q.isError && !d && <EmptyState label="暂无历史相似日统计" />}

      {d && (
        <>
          <SectionState section={sec} label="历史相似日聚类">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat
                label="相似日样本"
                value={show(rows.length)}
                sub={`目标日 ${show(sec?.target_date)} · 排除末 ±${show(sec?.exclude_window)} 日防泄漏`}
              />
              {OFFSETS.map((o) => (
                <Stat
                  key={o}
                  label={`后 ${o} 日红盘占比`}
                  value={show(fs[o]?.up_ratio, '%')}
                  sub={`均值 ${show(fs[o]?.mean, '%')} · 中位 ${show(fs[o]?.median, '%')} · n=${show(fs[o]?.n)}`}
                />
              ))}
            </div>

            <Card title={`历史相似日（目标日 ${show(sec?.target_date)}）`} className="mt-3">
              <p className="text-xs text-sf-ink-3 mb-2">
                全历史样本 {show(sec?.n_total)} 日，排除末 ±{show(sec?.exclude_window)} 交易日防前视泄漏；
                使用维度 {show(sec?.dims?.length)} 个。
              </p>
              {OFFSETS.some((o) => !fs[o]?.n) && (
                <p className="text-xs text-sf-warn mb-2">
                  部分前向窗口无足够样本，对应柱不绘制（不补 0）。
                </p>
              )}
              <EChart
                option={barOption}
                height={280}
                ariaLabel="相似日后继 5/10/20 日红盘占比柱状图，无样本窗口不绘制"
              />
              <p className="mt-1 text-xs text-sf-ink-3">
                红盘占比(≥50%) 越高，说明历史上相似情境后继更常偏暖。仅描述经验分布，不保证复现。
              </p>
            </Card>

            <Card title="最相似历史日（按距离升序）">
              {rows.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                        <th className="py-2 pr-3">日期</th>
                        <th className="py-2 pr-3">距离</th>
                        <th className="py-2 pr-3">后 5 日红盘%</th>
                        <th className="py-2 pr-3">后 10 日红盘%</th>
                        <th className="py-2 pr-3">后 20 日红盘%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.date} className="border-b border-sf-line/60">
                          <td className="py-2 pr-3 text-sf-ink">{r.date}</td>
                          <td className="py-2 pr-3 text-sf-ink-2">{show(r.dist)}</td>
                          <td className="py-2 pr-3 text-sf-ink-2">{show(r.fwd?.['5'], '%')}</td>
                          <td className="py-2 pr-3 text-sf-ink-2">{show(r.fwd?.['10'], '%')}</td>
                          <td className="py-2 pr-3 text-sf-ink-2">{show(r.fwd?.['20'], '%')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <EmptyState label="暂无相似日样本" />
              )}
            </Card>
          </SectionState>

          <DataBoundary
            data={d}
            method="取最新一日向量，按标准化欧氏距离检索最相似日并排除末日邻居防前视泄漏；以相似日后继红盘占比构建经验分布（up_ratio = 红盘占比 ≥50% 的交易日占比）。"
            extra="⚠️ 相似度距离中 涨/跌/平家数 与 红盘占比 属同一信息族（red_ratio 由前三者派生），会放大「家数族」权重；结论应以「形态相似」定性参考，勿作精确趋同预期。"
          />
        </>
      )}
    </div>
  )
}
