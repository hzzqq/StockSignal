import type { EChartsOption } from 'echarts'
import type { EventPool } from '@/api/schemas/read'
import { useEventPool } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/**
 * W3 后续簇 · 事件因子池页（/events）。
 * 数据源：getEventPool → /api/v2/read/event-pool → data/event_pool_brief.json。
 *
 * 诚实红线：原始文件的 note 是「统计意义上的超额收益概率排序，非买卖指令」，
 * 必须原样带出；本页只展示既有排序结果，不产生买卖指令、不补目标价、不包装成荐股。
 * 字段缺失一律 fmtNum → '—'，禁止 `?? 0` 兜底。
 */
export function EventPoolView() {
  const pool = useEventPool()
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">事件因子池</h2>
        <span className="text-label text-sf-ink-3">数据源 event_pool_brief</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <QueryState
        isLoading={pool.isLoading}
        isError={pool.isError}
        error={pool.error}
        isEmpty={!pool.data?.pool?.length}
        emptyLabel="事件池为空"
        emptyHint="数据文件缺失或池内无标的，未做任何填充"
      >
        {pool.data ? <EventPoolBody data={pool.data} /> : null}
      </QueryState>
    </div>
  )
}

function EventPoolBody({ data }: { data: EventPool }) {
  const rows = data.pool ?? []
  const top = rows.slice(0, 12)

  // 评分是 0~100 的既有量纲，固定刻度不属于「补零兜底」；
  // 单条 score 缺失仍传 null（图上留空），不补 0。
  const scoreOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 92, right: 32, top: 10, bottom: 24 },
    xAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { color: CHART.ink2 },
      splitLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: {
      type: 'category',
      data: top.map((r) => r.symbol).reverse(),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        data: top.map((r) => (typeof r.score === 'number' ? r.score : null)).reverse(),
        itemStyle: { color: CHART.accent },
        label: { show: true, position: 'right', color: CHART.ink2 },
      },
    ],
  }

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="数据日" value={data.date} />
        <Stat label="模型" value={data.model ?? '—'} />
        <Stat label="池内标的" value={fmtNum(data.count ?? rows.length)} />
        <Stat label="来源" value={data.source ?? '—'} sub="P1 量化因子" />
      </div>

      <Card title="口径与免责">
        <p className="text-body text-sf-ink-2">{data.note ?? '原始文件未提供口径说明'}</p>
        <p className="text-label text-sf-ink-3 mt-2">
          本页仅展示既有排序结果，不构成投资建议；评分是相对排序量，不代表预期收益率。
        </p>
      </Card>

      <Card title="评分分布（前 12 名）">
        <EChart option={scoreOption} height={260} ariaLabel="事件因子池前 12 名标的的评分分布条形图" />
      </Card>

      <Card title="池内标的明细">
        <div className="overflow-x-auto">
          <table className="w-full text-body border-collapse">
            <caption className="sr-only">
              事件因子池标的排序明细，含排名、代码、评分、原始排名、原始预测值、信号与数据来源
            </caption>
            <thead>
              <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                <th scope="col" className="text-left py-2 pr-3 font-normal">排名</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">代码</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">评分</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">原始排名</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">原始预测</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">信号</th>
                <th scope="col" className="text-left py-2 font-normal">来源</th>
              </tr>
            </thead>
            <tbody className="text-sf-ink-2">
              {rows.map((r) => (
                <tr key={`${r.rank}-${r.symbol}`} className="border-b border-sf-line last:border-0">
                  <td className="py-1.5 pr-3 tabular-nums">{fmtNum(r.rank)}</td>
                  <td className="py-1.5 pr-3 font-mono">{r.symbol}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.score)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.raw_rank)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.raw_pred)}</td>
                  <td className="py-1.5 pr-3">{r.signal ?? '—'}</td>
                  <td className="py-1.5 text-label text-sf-ink-3">{r.source ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-label text-sf-ink-3 mt-2">
          共 {rows.length} 条；数据来自 data/event_pool_brief.json，未做去重或重排。
        </p>
      </Card>
    </div>
  )
}
