import { useState } from 'react'
import type { EChartsOption } from 'echarts'
import { DIM_KEYS, type DimKey, type SixDim } from '@/api/schemas/stock'
import { useSixDim } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState, EmptyState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'
import { fmtNum } from '@/lib/format'

/** 六维中文标签（顺序与 DIM_KEYS 一致）。 */
const DIM_LABELS: Record<DimKey, string> = {
  technical: '技术',
  capital: '资金',
  value: '价值',
  growth: '成长',
  fundamental: '基本面',
  cycle: '周期',
}

const CODE_RE = /^\d{6}$/

/**
 * W4-A · 个股六维评分页（/stock/six-dim）。
 * 数据源：getSixDim → /api/v2/read/six-dim?code=<6位>。
 *
 * 诚实红线：
 *  - dims 为 null 的维 = 取数失败，明细显示「缺失」、雷达数据以 null 不参与绘制，绝不补 0；
 *  - date 为 null 显示「暂无权威数据日」，禁止用今天日期兜底；
 *  - overall 为 null 显示「暂无综合分」；
 *  - note 为后端口径原文，原样展示，不改写、不包装成投资建议；
 *  - 强弱只用状态色（sf-warn / sf-accent / sf-ink），不借 A 股涨跌色表达。
 */
export function SixDimView() {
  const [input, setInput] = useState('600519')
  const valid = CODE_RE.test(input)
  // enabled 由 hook 内 /^\d{6}$/ 校验，非法输入不发起任何请求。
  const query = useSixDim(input)

  return (
    <div className="flow">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">个股六维评分</h2>
        <span className="text-label text-sf-ink-3">数据源 six-dim</span>
        <a
          href="/breadth"
          className="ml-auto text-label text-sf-accent hover:text-sf-ink underline underline-offset-4"
        >
          ← 返回广度总览
        </a>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="six-dim-code" className="text-label text-sf-ink-3">股票代码</label>
        <input
          id="six-dim-code"
          aria-label="股票代码"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          inputMode="numeric"
          maxLength={6}
          placeholder="600519"
          className="rounded-tile border border-sf-line bg-sf-surface px-3 py-1.5 text-body text-sf-ink tabular-nums"
        />
        {!valid && <span className="text-label text-sf-warn">请输入 6 位数字代码</span>}
      </div>

      {!valid ? (
        <EmptyState label="请输入 6 位数字股票代码" hint="当前输入不合法，未发起请求" />
      ) : (
        <QueryState
          isLoading={query.isLoading}
          isError={query.isError}
          error={query.error}
          isEmpty={!!query.data && query.data.coverage === 0}
          emptyLabel="该股六维数据均缺失"
          emptyHint="未取到任何有效维度，未做补零填充"
        >
          {query.data ? <SixDimBody data={query.data} /> : null}
        </QueryState>
      )}
    </div>
  )
}

function SixDimBody({ data }: { data: SixDim }) {
  // 雷达数据：缺失维以 null 放入 value 数组，ECharts 不绘制该点（不补 0）。
  const radarValues: (number | null)[] = DIM_KEYS.map((k) =>
    typeof data.dims[k] === 'number' ? data.dims[k] : null,
  )
  const radarOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    radar: {
      indicator: DIM_KEYS.map((k) => ({ name: DIM_LABELS[k], max: 100 })),
      axisName: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
      splitLine: { lineStyle: { color: CHART.line } },
      splitArea: { show: false },
    },
    series: [
      {
        type: 'radar',
        symbolSize: 5,
        data: [
          {
            value: radarValues,
            name: '六维评分',
            itemStyle: { color: CHART.accent },
            lineStyle: { color: CHART.accent, width: 1.5 },
            areaStyle: { color: CHART.accent, opacity: 0.15 },
          },
        ],
      },
    ],
  }

  return (
    <div className="flow">
      {/* 数据日条：date 为权威数据日；为 null 时如实显示，禁止今天日期兜底。 */}
      <div className="flex flex-wrap items-center gap-3 text-body">
        <span className="text-sf-ink-3">数据日</span>
        {data.date === null ? (
          <span role="status" className="text-sf-warn">暂无权威数据日</span>
        ) : (
          <span className="text-sf-ink tabular-nums">{`权威数据日：${data.date}`}</span>
        )}
        <span className="text-label text-sf-ink-3">{`代码 ${data.code}`}</span>
      </div>

      {/* 降权态：有效维度不足 6 时明确告知缺失，不掩饰。 */}
      {data.coverage < 6 && (
        <div
          role="status"
          className="flex items-start gap-2 rounded-tile border border-sf-line bg-sf-surface px-4 py-3 text-body text-sf-ink-2"
        >
          <span aria-hidden="true" className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-sf-warn" />
          <span>{`仅 ${data.coverage}/6 维有效，缺失维未取到数据`}</span>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="综合分"
          value={data.overall === null ? '暂无综合分' : fmtNum(data.overall)}
          sub="仅有效维参与平均"
        />
        <Stat label="有效维度" value={`${data.coverage}/6`} sub={`缺失 ${data.missing.length} 维`} />
        <Stat label="最新数据日" value={data.date === null ? '—' : data.date} />
        <Stat label="股票代码" value={data.code} />
      </div>

      <Card title="六维评分雷达图">
        <EChart
          option={radarOption}
          height={300}
          ariaLabel="个股六维评分雷达图：技术、资金、价值、成长、基本面、周期六个维度的评分，缺失维度不绘制数据点"
        />
        <p className="text-label text-sf-ink-3 mt-2">
          缺失维以空值呈现，雷达图不补 0 分；下方明细给出各维准确分数。
        </p>
      </Card>

      <Card title="六维明细">
        <ul className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {DIM_KEYS.map((k) => {
            const v = data.dims[k]
            return (
              <li
                key={k}
                className="flex items-center justify-between rounded-tile border border-sf-line bg-sf-surface-2 px-3.5 py-3"
              >
                <span className="text-label text-sf-ink-3">{DIM_LABELS[k]}</span>
                <span
                  data-testid={`dim-${k}`}
                  className={`text-kpi tabular-nums ${v === null ? 'text-sf-ink-3' : 'text-sf-ink'}`}
                >
                  {v === null ? '缺失' : fmtNum(v)}
                </span>
              </li>
            )
          })}
        </ul>
      </Card>

      <Card title="口径说明">
        {/* note 为后端原文，原样展示，不改写、不美化成投资建议。 */}
        <p className="text-body text-sf-ink-2">{data.note ?? '原始响应未提供口径说明'}</p>
      </Card>
    </div>
  )
}
