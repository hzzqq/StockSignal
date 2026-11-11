import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { useBreadthAnalytics, useBreadthZSeries } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { Loading, ErrorState, EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { AnalyticsHeader, DataBoundary, SectionState, show } from './shared'

const SELECT_CLS =
  'mt-1 w-full bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/**
 * 68 情绪拐点扫描器（v2 native /inflection-scan）。
 * 数据源：breadth-analytics 的 inflection 段（事件表）+ 独立按需端点
 * GET /api/v2/read/breadth-zseries?dim=&window=（单维度 z-score 轨迹，避免聚合包塞 4771 点）。
 * 与 v1 对齐：维度下拉、事件表、z-score 折线 + 拐点标注 + ±2/±1 阈值线。
 */
export function InflectionScan() {
  const q = useBreadthAnalytics()
  const d = q.data
  const sec = d?.sections.inflection
  const dims = sec?.dims ?? []
  const [picked, setPicked] = useState<string>('')
  const dim = picked && dims.includes(picked) ? picked : dims[0] ?? ''
  const zq = useBreadthZSeries(dim, 250, !!dim)
  const events = sec?.events ?? []
  const labels = d?.reliable_labels ?? {}

  const zData = zq.data?.z ?? []
  const markers = zq.data?.markers ?? []
  const zOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    xAxis: {
      type: 'category',
      data: zq.data?.dates ?? [],
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'value',
      name: 'z-score(60日)',
      nameTextStyle: { color: CHART.ink3 },
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        name: 'z-score',
        type: 'line',
        showSymbol: false,
        data: zData,
        lineStyle: { color: CHART.accent, width: 1.6 },
        itemStyle: { color: CHART.accent },
        connectNulls: false,
        markPoint: {
          symbolSize: 10,
          itemStyle: { color: CHART.warn },
          // 极值/缺失点不补 0：只标注真实有 z 值的下标。
          data: markers.flatMap((m) => {
            const v = zData[m]
            return v === null || v === undefined ? [] : [{ name: '拐点', xAxis: m, yAxis: v }]
          }),
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: CHART.ink3 },
          data: [2, -2, 1, -1].map((y) => ({ yAxis: y })),
        },
      },
    ],
  }

  return (
    <div className="space-y-4">
      <AnalyticsHeader
        title="情绪拐点扫描器"
        caption="对离线可靠广度维度计算 60 日滚动 z-score，检测「极端后反转」形态（触底反转 / 触顶回落）。仅描述历史形态，非预测。"
        data={d}
      />

      {q.isLoading && <Loading label="加载拐点扫描结果…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '拐点扫描结果加载失败'} />
      )}
      {!q.isLoading && !q.isError && !d && <EmptyState label="暂无拐点扫描结果" />}

      {d && (
        <>
          <SectionState section={sec} label="拐点扫描">
            {dims.length === 0 ? (
              <EmptyState label="无可用广度维度生成拐点扫描" hint="数据不足或维度被数据闸门剔除" />
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Stat label="扫描维度" value={show(dims.length)} sub="离线可靠广度字段（数据闸门放行）" />
                  <Stat label="近期拐点事件" value={show(events.length)} sub="触底反转 / 触顶回落累计" />
                  <Stat label="z-score 窗口" value="60 日" sub="极端阈值 ±2，确认阈值 ∓1" />
                  <Stat label="数据截至" value={show(d.data_as_of)} sub="离线健康镜像快照" />
                </div>

                <Card title="近期拐点事件（末 20 交易日）">
                  {events.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                            <th className="py-2 pr-3">日期</th>
                            <th className="py-2 pr-3">维度</th>
                            <th className="py-2 pr-3">类型</th>
                            <th className="py-2 pr-3">极值</th>
                            <th className="py-2 pr-3">现值</th>
                          </tr>
                        </thead>
                        <tbody>
                          {events.map((e, i) => (
                            <tr key={`${e.dim}-${e.date}-${i}`} className="border-b border-sf-line/60">
                              <td className="py-2 pr-3 text-sf-ink">{show(e.date)}</td>
                              <td className="py-2 pr-3 text-sf-ink-2">{show(e.label)}</td>
                              <td className="py-2 pr-3 text-sf-ink-2">{show(e.type)}</td>
                              <td className="py-2 pr-3 text-sf-ink-2">{show(e.extreme)}</td>
                              <td className="py-2 pr-3 text-sf-ink-2">{show(e.current)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <EmptyState label="近 20 交易日未检测到显著拐点" hint="或历史数据不足" />
                  )}
                  <p className="mt-2 text-xs text-sf-ink-3">
                    共 {events.length} 个事件；触底反转 = 自 &lt;−2 回升越过 −1，触顶回落 = 自 &gt;+2 回落越过 +1。
                  </p>
                </Card>

                <Card title="单维度 z-score 轨迹（含拐点标注）">
                  <label className="block text-xs text-sf-ink-2 mb-3">
                    扫描维度
                    <select
                      className={SELECT_CLS}
                      value={dim}
                      onChange={(e) => setPicked(e.target.value)}
                    >
                      {dims.map((k) => (
                        <option key={k} value={k}>
                          {labels[k] ?? k}
                        </option>
                      ))}
                    </select>
                  </label>

                  {zq.isLoading && <Loading label="加载 z-score 轨迹…" />}
                  {zq.isError && (
                    <ErrorState
                      message={zq.error instanceof Error ? zq.error.message : 'z-score 轨迹加载失败'}
                    />
                  )}
                  {zq.data && !zq.data.available && (
                    <EmptyState label="该维度暂无 z-score 轨迹" hint={zq.data.reason ?? '历史数据不足'} />
                  )}
                  {zq.data?.available && zq.data.dates.length > 0 && (
                    <>
                      <EChart
                        option={zOption}
                        height={360}
                        ariaLabel="单维度 z-score 折线图，橙点为检测到的拐点，虚线为 ±1/±2 阈值"
                      />
                      <p className="mt-1 text-xs text-sf-ink-3">
                        近 {zq.data.window} 交易日{zq.data.truncated ? '（自全历史截取末段）' : ''}；
                        橙点 = 检测到的拐点，虚线 ±2 为极端阈值、±1 为反转确认阈值。
                        z-score 仅描述相对自身 60 日均值的偏离，非预测。
                      </p>
                    </>
                  )}
                  {zq.data?.available && zq.data.dates.length === 0 && (
                    <EmptyState label="该维度无足够历史生成 z-score 轨迹" />
                  )}
                </Card>
              </>
            )}
          </SectionState>

          <DataBoundary
            data={d}
            method="对维度计算 60 日滚动 z-score，检测「自极端(<−2 或 >+2)反转越过确认阈值(∓1)」形态；这是历史序列的形态描述，不构成方向预测或买卖建议。"
            extra="⚠️ 这些维度是市场宽度的动量/反转形态（涨跌家数、极限宽度），并非狭义「投资者情绪调查」类指标；连板梯队类情绪维度离线缺真值已剔除，故本页「情绪」实为「广度动能的极端反转」。"
          />
        </>
      )}
    </div>
  )
}
