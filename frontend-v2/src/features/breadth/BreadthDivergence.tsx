import { useState, type CSSProperties } from 'react'
import type { EChartsOption } from 'echarts'
import { useBreadthDivergence } from '@/lib/queriesBatchB'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 61 广度结构分化（v2 native /breadth-divergence）。
 *
 * 后端 GET /api/v2/read/breadth-divergence 直接封装 modules/breadth_divergence.py
 * 的三个纯函数（calendar / episodes / trend），页面只做诚实渲染：
 *  - 缺失值（null）显「—」，不补 0；
 *  - available=false 由 QueryState 如实呈现，不伪造热力矩阵或分化日；
 *  - 分化判据（红盘率阈值 + 跌停占比历史分位）明示在页面上，不隐藏口径。
 */
function fmt(v: number | null | undefined, digits = 1): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—'
}

const CELL_CLS = 'h-7 min-w-9 border border-sf-line text-center text-[11px] tabular-nums'

/** 红盘率越高越偏红（A 股语义）；null 用中性底 + 「—」，绝不按 0 上色。 */
function heatStyle(v: number | null): CSSProperties {
  if (typeof v !== 'number' || !Number.isFinite(v)) {
    return { backgroundColor: 'transparent', color: 'var(--sf-ink-3, #64748b)' }
  }
  const a = Math.max(0, Math.min(1, (v - 20) / 60))
  return { backgroundColor: `rgba(220, 38, 38, ${(0.12 + a * 0.68).toFixed(2)})`, color: '#fff' }
}

export function BreadthDivergence() {
  const [redThresh, setRedThresh] = useState('50')
  const [quantile, setQuantile] = useState('0.90')
  const [windowDays, setWindowDays] = useState('750')

  const red = Number(redThresh)
  const q = Number(quantile)
  const wd = Number(windowDays)
  const paramsValid =
    Number.isFinite(red) && red >= 0 && red <= 100 &&
    Number.isFinite(q) && q >= 0.01 && q <= 0.99 &&
    Number.isFinite(wd) && wd >= 1 && wd <= 5000

  const query = useBreadthDivergence(
    paramsValid ? { red_thresh: red, ld_quantile: q, window_days: wd } : undefined,
  )

  const trendOption: EChartsOption | null = query.data?.trend?.available
    ? {
        tooltip: { trigger: 'axis' },
        legend: { data: ['红盘率', '跌停家数'] },
        grid: { left: 48, right: 48, top: 36, bottom: 28 },
        xAxis: { type: 'category', data: query.data.trend.dates },
        yAxis: [
          { type: 'value', name: '红盘率 %' },
          { type: 'value', name: '跌停家数' },
        ],
        series: [
          {
            name: '红盘率',
            type: 'line',
            yAxisIndex: 0,
            showSymbol: false,
            data: query.data.trend.red_ratio,
          },
          {
            name: '跌停家数',
            type: 'line',
            yAxisIndex: 1,
            showSymbol: false,
            data: query.data.trend.limit_down,
          },
        ],
      }
    : null

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">广度结构分化</h2>
      <p className="text-xs text-sf-ink-3">
        判据：红盘率 ≥ 阈值 且 跌停占比 ≥ 历史分位 → 判为「涨多但杀跌」的结构分化。
        仅用离线广度序列（shepherd_history），不含任何实时行情或预测收益。
      </p>

      <Card title="参数">
        <div className="flex flex-wrap items-end gap-3 text-label">
          <label className="text-sf-ink-3">
            红盘率阈值（%）
            <input
              type="number"
              value={redThresh}
              onChange={(e) => setRedThresh(e.target.value)}
              className="mt-1 block w-28 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sf-ink"
            />
          </label>
          <label className="text-sf-ink-3">
            跌停占比分位
            <input
              type="number"
              step="0.01"
              value={quantile}
              onChange={(e) => setQuantile(e.target.value)}
              className="mt-1 block w-28 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sf-ink"
            />
          </label>
          <label className="text-sf-ink-3">
            趋势窗口（交易日）
            <select
              value={windowDays}
              onChange={(e) => setWindowDays(e.target.value)}
              className="mt-1 block w-32 rounded-tile border border-sf-line bg-sf-surface px-2 py-1 text-sf-ink"
            >
              <option value="250">近 1 年</option>
              <option value="750">近 3 年</option>
              <option value="1250">近 5 年</option>
              <option value="2500">近 10 年</option>
              <option value="5000">全历史</option>
            </select>
          </label>
          {!paramsValid && (
            <span className="text-sf-danger">参数超出合法范围，未发起请求</span>
          )}
        </div>
      </Card>

      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        isEmpty={!paramsValid || !query.data?.available}
        emptyLabel={!paramsValid ? '参数不合法' : '广度历史不可用'}
        emptyHint={query.data?.divergence?.available === false ? '数据源缺失，不伪造分化结果' : undefined}
      >
        {query.data?.available ? (
          <>
            <div className="grid gap-3 sm:grid-cols-4">
              <Card title="最新红盘率">
                <div className="text-xl font-semibold tabular-nums">
                  {fmt(query.data.divergence.current?.red_ratio)}%
                </div>
              </Card>
              <Card title="最新跌停家数">
                <div className="text-xl font-semibold tabular-nums">
                  {query.data.divergence.current?.limit_down === null ||
                  query.data.divergence.current?.limit_down === undefined
                    ? '—'
                    : query.data.divergence.current.limit_down}
                </div>
              </Card>
              <Card title="当前结构">
                <div
                  className="text-xl font-semibold"
                  style={{
                    color: query.data.divergence.current?.is_divergent
                      ? CHART.up
                      : CHART.ink2,
                  }}
                >
                  {query.data.divergence.current?.is_divergent ? '分化' : '未分化'}
                </div>
              </Card>
              <Card title="历史分化日">
                <div className="text-xl font-semibold tabular-nums">
                  {query.data.divergence.n_episodes}
                </div>
              </Card>
            </div>

            <Card title="历史分化日（最近 15 条）">
              {query.data.divergence.episodes.length === 0 ? (
                <p className="text-xs text-sf-ink-3">该阈值下无分化日，不伪造样本。</p>
              ) : (
                <table className="w-full text-label tabular-nums">
                  <thead>
                    <tr className="text-sf-ink-3">
                      <th className="text-left py-1">日期</th>
                      <th className="text-right py-1">红盘率</th>
                      <th className="text-right py-1">跌停家数</th>
                      <th className="text-right py-1">跌停占比</th>
                      <th className="text-right py-1">涨停次日收益</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.divergence.episodes
                      .slice(-15)
                      .reverse()
                      .map((e) => (
                        <tr key={e.date} className="border-t border-sf-line">
                          <td className="py-1">{e.date}</td>
                          <td className="text-right py-1">{fmt(e.red_ratio)}%</td>
                          <td className="text-right py-1">
                            {e.limit_down === null ? '—' : e.limit_down}
                          </td>
                          <td className="text-right py-1">{fmt(e.limit_down_ratio, 2)}%</td>
                          <td className="text-right py-1">{fmt(e.zt_prev_ret, 4)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )}
            </Card>

            <Card title="广度日历热力（年 × 月，月均红盘率）">
              {query.data.calendar.available ? (
                <div className="overflow-auto">
                  <table className="border-collapse text-[11px]">
                    <thead>
                      <tr>
                        <th className="px-1 text-sf-ink-3">年</th>
                        {query.data.calendar.months.map((m) => (
                          <th key={m} className="px-1 text-sf-ink-3">{m}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {query.data.calendar.years.map((year, i) => (
                        <tr key={year}>
                          <td className="px-1 text-sf-ink-3">{year}</td>
                          {query.data.calendar.z[i]?.map((v, j) => (
                            <td key={j} className={CELL_CLS} style={heatStyle(v)}>
                              {v === null ? '—' : v.toFixed(0)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-sf-ink-3">日历数据不可用。</p>
              )}
            </Card>

            <Card title="红盘率 vs 跌停家数趋势">
              {trendOption ? (
                <EChart option={trendOption} height={320} />
              ) : (
                <p className="text-xs text-sf-ink-3">趋势数据不可用。</p>
              )}
            </Card>
          </>
        ) : null}
      </QueryState>
    </div>
  )
}
