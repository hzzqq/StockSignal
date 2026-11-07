import type { EChartsOption } from 'echarts'
import type { PredictionLogRow } from '@/api/schemas/read'
import { usePredictionLog } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/**
 * W3 后续簇 · 预测校准日志页（/predictions）。
 * 数据源：getPredictionLog → /api/v2/read/prediction-log → data/prediction_log.json。
 *
 * 诚实红线：hit / realized 为 null 表示「尚未兑现」，既不是「未命中」也不是 0。
 * 命中率分母只统计 hit 为 boolean 的已兑现样本；无可统计样本时显示「—」，不补 0%。
 * 本页是决策闭环的历史自评记录，不是未来预测。
 */
export function PredictionLogView() {
  const log = usePredictionLog()
  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">预测校准日志</h2>
        <span className="text-label text-sf-ink-3">数据源 prediction_log</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <QueryState
        isLoading={log.isLoading}
        isError={log.isError}
        error={log.error}
        isEmpty={!log.data?.length}
        emptyLabel="暂无预测记录"
        emptyHint="数据文件缺失或日志为空，未做任何填充"
      >
        {log.data ? <PredictionBody rows={log.data} /> : null}
      </QueryState>
    </div>
  )
}

function PredictionBody({ rows }: { rows: PredictionLogRow[] }) {
  // 只把 hit 为布尔值的样本计入分母；未兑现（null/undefined）不参与统计。
  const settled = rows.filter((r) => typeof r.hit === 'boolean')
  const hits = settled.filter((r) => r.hit === true).length
  const rate = settled.length > 0 ? (hits / settled.length) * 100 : null
  const latest = rows[rows.length - 1]

  const trendOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['市场温度', '建议仓位%'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 40, right: 44, top: 28, bottom: 48 },
    xAxis: {
      type: 'category',
      data: rows.map((r) => r.date),
      axisLabel: { color: CHART.ink2, hideOverlap: true },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    yAxis: [
      {
        type: 'value',
        name: '温度',
        nameTextStyle: { color: CHART.ink3 },
        axisLabel: { color: CHART.ink2 },
        splitLine: { lineStyle: { color: CHART.line } },
      },
      {
        type: 'value',
        name: '仓位%',
        nameTextStyle: { color: CHART.ink3 },
        axisLabel: { color: CHART.ink2 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '市场温度',
        type: 'line',
        smooth: true,
        showSymbol: false,
        data: rows.map((r) => (typeof r.temp === 'number' ? r.temp : null)),
        itemStyle: { color: CHART.accent },
        lineStyle: { color: CHART.accent, width: 1.5 },
      },
      {
        name: '建议仓位%',
        type: 'bar',
        yAxisIndex: 1,
        data: rows.map((r) => (typeof r.pct === 'number' ? r.pct : null)),
        itemStyle: { color: CHART.ink3 },
      },
    ],
  }

  const recent = [...rows].slice(-12).reverse()

  return (
    <div className="flow">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="日志条数" value={fmtNum(rows.length)} sub="交易日" />
        <Stat label="已兑现" value={fmtNum(settled.length)} />
        <Stat label="命中" value={fmtNum(hits)} />
        <Stat
          label="命中率"
          value={rate === null ? '—' : `${rate.toFixed(1)}%`}
          sub={rate === null ? '无可统计样本' : `分母 ${settled.length} 条`}
        />
      </div>

      <Card title="口径说明">
        <p className="text-body text-sf-ink-2">
          命中率仅统计 hit 字段为布尔值的已兑现样本；尚未兑现的预测 hit / realized 为空，
          既不计入分子也不计入分母，不按「未命中」处理、不补零。
        </p>
        <p className="text-label text-sf-ink-3 mt-2">
          最新一条：{latest?.date ?? '—'} · 温度 {fmtNum(latest?.temp)} · 倾向 {latest?.bias ?? '—'}。
          本页是决策闭环的历史自评记录，不构成未来预测。
        </p>
      </Card>

      <Card title="温度与建议仓位时序">
        <EChart option={trendOption} height={260} ariaLabel="预测校准日志的市场温度与建议仓位逐日时序图" />
      </Card>

      <Card title="最近 12 条校准记录">
        <div className="overflow-x-auto">
          <table className="w-full text-body border-collapse">
            <caption className="sr-only">
              预测校准日志最近记录，含日期、市场温度、周期、倾向、建议仓位、事件调整、实际涨跌与兑现结果
            </caption>
            <thead>
              <tr className="text-label text-sf-ink-3 border-b border-sf-line">
                <th scope="col" className="text-left py-2 pr-3 font-normal">日期</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">温度</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">周期</th>
                <th scope="col" className="text-left py-2 pr-3 font-normal">倾向</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">仓位%</th>
                <th scope="col" className="text-right py-2 pr-3 font-normal">实际涨跌</th>
                <th scope="col" className="text-left py-2 font-normal">兑现</th>
              </tr>
            </thead>
            <tbody className="text-sf-ink-2">
              {recent.map((r) => (
                <tr key={r.date} className="border-b border-sf-line last:border-0">
                  <td className="py-1.5 pr-3 tabular-nums">{r.date}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.temp)}</td>
                  <td className="py-1.5 pr-3">{r.cycle ?? '—'}</td>
                  <td className="py-1.5 pr-3">{r.bias ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.pct)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(r.realized)}</td>
                  <td className="py-1.5">
                    {typeof r.hit !== 'boolean' ? (
                      <span className="text-sf-ink-3">未兑现</span>
                    ) : r.hit ? (
                      <span className="text-sf-ok">命中</span>
                    ) : (
                      <span className="text-sf-warn">未命中</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-label text-sf-ink-3 mt-2">
          显示最近 {recent.length} 条（共 {rows.length} 条）；「未兑现」表示次日结果尚未落盘，不是判断错误。
        </p>
      </Card>
    </div>
  )
}
