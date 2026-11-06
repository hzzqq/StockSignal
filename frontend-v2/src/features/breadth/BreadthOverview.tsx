import type { DailySnapshot } from '@/api/schemas/read'
import type { EChartsOption } from 'echarts'
import { useDailySnapshot } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { ScenarioChart } from '@/shared/charts/ScenarioChart'
import { CHART } from '@/shared/charts/palette'
import {
  freshnessLevelFromAge,
  freshnessFromStatus,
  type FreshnessLevel,
} from '@/lib/freshness'
import { fmtNum } from '@/lib/format'

/**
 * W3 广度·温度首簇落地页（对应 IA-MIGRATION.md §4 W3）。
 * 全部数据来自 getDailySnapshot（12 只读端点之一），缺失字段诚实留空，不编造。
 */
export function BreadthOverview() {
  const { data, isLoading, isError, error } = useDailySnapshot()
  return (
    <QueryState isLoading={isLoading} isError={isError} error={error}>
      {data ? <BreadthBody snapshot={data} /> : null}
    </QueryState>
  )
}

function BreadthBody({ snapshot }: { snapshot: DailySnapshot }) {
  const ind = snapshot.indicators ?? {}
  const level: FreshnessLevel =
    typeof snapshot.data_age_days === 'number'
      ? freshnessLevelFromAge(snapshot.data_age_days)
      : freshnessFromStatus(snapshot.data_freshness?.status)

  const breadthOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 44, right: 16, top: 16, bottom: 28 },
    xAxis: {
      type: 'category',
      data: ['上涨', '下跌', '涨停', '跌停'],
      axisLabel: { color: CHART.txt },
      axisLine: { lineStyle: { color: CHART.border } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHART.txt },
      splitLine: { lineStyle: { color: CHART.grid } },
    },
    series: [
      {
        type: 'bar',
        barWidth: '52%',
        data: [
          { value: Number(ind.up_count ?? 0), itemStyle: { color: CHART.up } },
          { value: Number(ind.down_count ?? 0), itemStyle: { color: CHART.down } },
          { value: Number(ind.limit_up ?? 0), itemStyle: { color: CHART.up } },
          { value: Number(ind.limit_down ?? 0), itemStyle: { color: CHART.down } },
        ],
      },
    ],
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">市场广度·温度总览</h2>
        <FreshnessBadge level={level} />
        <span className="text-xs text-sf-txt/50">权威数据日 {snapshot.date}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="市场温度" value={fmtNum(snapshot.temperature)} sub={snapshot.cycle} />
        <Stat label="红盘比" value={fmtNum(ind.red_ratio)} />
        <Stat label="中位涨跌幅" value={fmtNum(ind.median_chg)} />
        <Stat label="成交额(亿)" value={fmtNum(ind.turnover_amt)} />
      </div>

      <Card title="涨跌家数分布">
        <EChart option={breadthOption} height={240} />
      </Card>

      {snapshot.scenario && snapshot.scenario.length > 0 && (
        <Card title="情景概率">
          <ScenarioChart items={snapshot.scenario} />
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card title="连板梯队">
          <div className="text-sm text-sf-txt/70">
            最高板 <span className="text-sf-txt font-semibold">{snapshot.ladder?.max_boards ?? '—'}</span>
            {' · '}连板总数{' '}
            <span className="text-sf-txt font-semibold">{snapshot.ladder?.total_connect ?? '—'}</span>
          </div>
          <div className="text-xs text-sf-txt/40 mt-1">
            连板明细需 shepherd_ladder 专属 read 端点（W3 后续波）
          </div>
        </Card>
        <Card title="事件因子">
          {snapshot.event_factor?.available ? (
            <div className="text-sm text-sf-txt/70">
              多头 {snapshot.event_factor.long_count ?? '—'} 只
              {snapshot.event_factor.adj != null && (
                <span className="ml-2">调节 {snapshot.event_factor.adj}</span>
              )}
            </div>
          ) : (
            <div className="text-sm text-sf-txt/40">事件因子不可用</div>
          )}
        </Card>
        <Card title="综合评分">
          <Stat label="评分" value={fmtNum(snapshot.score)} sub={`偏向 ${snapshot.bias ?? '—'}`} />
        </Card>
      </div>
    </div>
  )
}
