import type { EChartsOption } from 'echarts'
import type { FundFlow as FundFlowData, FundFlowNorthbound, FundFlowIndustryRow, FundFlowMarketRow, FundFlowMarginRow } from '@/api/schemas/read'
import { useFundFlow } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 35 页「资金流向」V2 化落地（对应 IA-MIGRATION.md Tier1）。
 * 数据来源：useFundFlow → GET /api/v2/read/fund-flow（后端复用 modules.fundflow /
 * margin_trading 网络数据层，东方财富/同花顺接口）。
 *
 * 四块（北向 / 行业 / 大盘主力 / 融资融券）各自独立 available，离线或接口受限时
 * 该块诚实降级（显示「数据暂不可用」而非编造数值），不整页失败、不补 0。
 * 金额单位均为亿元（后端已折算），百分比保留原始百分数；缺值显示「—」。
 *
 * ⚠️ A 股语义：资金净流入=红（up）、净流出=绿（down），与红涨绿跌一致。
 */
function yi(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(2)}亿` : '—'
}
function pct(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(2)}%` : '—'
}
function flowColor(v: unknown): string | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? (v >= 0 ? CHART.up : CHART.down) : undefined
}
function num(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
}
function DeltaTag({ text, dir }: { text: string; dir: 'up' | 'down' | 'flat' }) {
  const color = dir === 'up' ? CHART.up : dir === 'down' ? CHART.down : CHART.ink2
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '·'
  return (
    <span className="tabular-nums" style={{ color }}>
      {arrow} {text}
    </span>
  )
}

export function FundFlow() {
  const q = useFundFlow()
  const d = q.data

  const nb = d?.northbound
  const ind = d?.industry
  const mk = d?.market
  const mg = d?.margin
  const allUnavailable =
    !!d && !nb?.available && !ind?.available && !mk?.available && !mg?.available

  return (
    <div className="flow">
      <h2 className="text-lg font-semibold">资金流向</h2>
      <div className="text-xs text-sf-ink-3">
        北向资金 · 行业板块 · 大盘主力净流入 · 融资融券；红=净流入、绿=净流出（与红涨绿跌一致）。
        数据来自东方财富/同花顺网络接口，离线或接口受限时逐块诚实降级，非实时、非投资建议。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={allUnavailable}
        emptyLabel="资金流向数据暂不可用"
        emptyHint="北向 / 行业 / 大盘主力 / 融资融券取数均失败（离线或接口受限）；后端已逐块诚实降级"
      >
        {d ? (
          <div className="space-y-6">
            <NorthboundBlock nb={nb} />
            <IndustryBlock rows={ind?.rows ?? []} available={!!ind?.available} />
            <MarketBlock rows={mk?.rows ?? []} available={!!mk?.available} />
            <MarginBlock rows={mg?.rows ?? []} latest={mg?.latest ?? null} available={!!mg?.available} />
            {d.note && <div className="text-xs text-sf-ink-3">{d.note}</div>}
          </div>
        ) : null}
      </QueryState>
    </div>
  )
}

function HonestUnavailable({ label }: { label: string }) {
  return (
    <Card title={label}>
      <div className="text-xs text-sf-ink-3">
        数据暂不可用（离线或接口受限），后端已诚实降级，未编造数值。
      </div>
    </Card>
  )
}

function NorthboundBlock({ nb }: { nb?: FundFlowNorthbound }) {
  if (!nb || !nb.available) return <HonestUnavailable label="北向资金（沪股通 / 深股通）" />
  const avail = !!nb.northbound_net_available
  const boards = nb.boards ?? []

  return (
    <Card title="北向资金（沪股通 / 深股通）">
      {avail ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="北向净流入(实时)" value={yi(nb.total_inflow)} color={flowColor(nb.total_inflow)} />
          <Stat label="沪股通(实时)" value={yi(nb.sh_inflow)} color={flowColor(nb.sh_inflow)} />
          <Stat label="深股通(实时)" value={yi(nb.sz_inflow)} color={flowColor(nb.sz_inflow)} />
          <Stat label="交易日" value={nb.trade_date ?? '—'} />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs text-sf-ink-3">
            北向资金实时净买额已停披露（交易所自 2024-08-16 起不再实时公布），下方为「最近一次真实披露」与「历史累计净买入」兜底。
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="北向净流入(最近真实披露)" value={yi(nb.last_net_buy)} sub={nb.last_net_buy_date ? `披露日 ${nb.last_net_buy_date}` : undefined} />
            <Stat label="历史累计净买入" value={yi(nb.cumulative)} sub={nb.cumulative_date ? `截至 ${nb.cumulative_date}` : undefined} />
            <Stat label="交易日" value={nb.trade_date ?? '—'} />
            <Stat label="实时净额" value="停披露" />
          </div>
        </div>
      )}

      {boards.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs text-sf-ink">
            <thead>
              <tr className="text-sf-ink-3 border-b border-sf-line">
                <th className="text-left py-1.5 pr-3">板块</th>
                <th className="text-left py-1.5 pr-3">资金方向</th>
                <th className="text-right py-1.5 pr-3">成交净买额</th>
                <th className="text-right py-1.5 pr-3">资金净流入</th>
                <th className="text-right py-1.5 pr-3">上涨数</th>
                <th className="text-right py-1.5 pr-3">下跌数</th>
                <th className="text-right py-1.5">指数涨跌幅</th>
              </tr>
            </thead>
            <tbody>
              {boards.map((b, i) => (
                <tr key={`${b.board}-${i}`} className="border-b border-sf-line/60">
                  <td className="py-1.5 pr-3">{b.board ?? '—'}</td>
                  <td className="py-1.5 pr-3">{b.direction ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-right" style={{ color: flowColor(b.trade_net) }}>{yi(b.trade_net)}</td>
                  <td className="py-1.5 pr-3 text-right" style={{ color: flowColor(b.net_inflow) }}>{yi(b.net_inflow)}</td>
                  <td className="py-1.5 pr-3 text-right">{b.up_count ?? '—'}</td>
                  <td className="py-1.5 pr-3 text-right">{b.down_count ?? '—'}</td>
                  <td className="py-1.5 text-right">{pct(b.index_chg_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function IndustryBlock({ rows, available }: { rows: FundFlowIndustryRow[]; available: boolean }) {
  if (!available) return <HonestUnavailable label="行业板块资金流向" />
  const valid = rows.filter((r) => typeof r.net === 'number' && Number.isFinite(r.net))
  const sorted = [...valid].sort((a, b) => (b.net as number) - (a.net as number))
  const topIn = sorted[0]
  const topOut = sorted[sorted.length - 1]

  const top = sorted.slice(0, 15).reverse()
  const barOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 64, right: 24, top: 16, bottom: 64 },
    xAxis: { type: 'category', data: top.map((r) => r.industry ?? ''), axisLabel: { color: CHART.ink2, rotate: 45, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}亿' }, splitLine: { lineStyle: { color: CHART.line } } },
    series: [{
      type: 'bar',
      data: top.map((r) => {
        const v = typeof r.net === 'number' && Number.isFinite(r.net) ? r.net : null
        return {
          value: v,
          itemStyle: v == null ? undefined : { color: v >= 0 ? CHART.up : CHART.down },
        }
      }),
    }],
  }

  return (
    <Card title="行业板块资金流向">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="最强净流入" value={topIn?.industry ?? '—'} sub={topIn ? <DeltaTag text={`${(topIn.net as number) >= 0 ? '+' : ''}${(topIn.net as number).toFixed(2)}亿`} dir={(topIn.net as number) >= 0 ? 'up' : 'down'} /> : undefined} />
        <Stat label="最强净流出" value={topOut?.industry ?? '—'} sub={topOut ? <DeltaTag text={`${(topOut.net as number) >= 0 ? '+' : ''}${(topOut.net as number).toFixed(2)}亿`} dir={(topOut.net as number) >= 0 ? 'up' : 'down'} /> : undefined} />
        <Stat label="净流入行业" value={valid.filter((r) => (r.net as number) > 0).length} />
        <Stat label="净流出行业" value={valid.filter((r) => (r.net as number) < 0).length} />
      </div>

      {sorted.length > 0 && (
        <div className="mt-3">
          <EChart option={barOption} height={Math.max(200, top.length * 28)} ariaLabel="行业净流入 TOP15 条形图（亿元）" />
        </div>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">行业</th>
              <th className="text-right py-1.5 pr-3">涨跌幅%</th>
              <th className="text-right py-1.5 pr-3">流入(亿)</th>
              <th className="text-right py-1.5 pr-3">流出(亿)</th>
              <th className="text-right py-1.5 pr-3">净额(亿)</th>
              <th className="text-left py-1.5 pr-3">领涨股</th>
              <th className="text-right py-1.5">领涨股涨跌幅%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.industry}-${i}`} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{r.industry ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right">{pct(r.chg_pct)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.inflow)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.outflow)}</td>
                <td className="py-1.5 pr-3 text-right" style={{ color: flowColor(r.net) }}>{yi(r.net)}</td>
                <td className="py-1.5 pr-3">{r.leader ?? '—'}</td>
                <td className="py-1.5 text-right">{pct(r.leader_chg_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function MarketBlock({ rows, available }: { rows: FundFlowMarketRow[]; available: boolean }) {
  if (!available) return <HonestUnavailable label="大盘主力资金净流入（近 30 日）" />
  const last = rows[rows.length - 1]
  const dates = rows.map((r) => r.date ?? '')
  const netVals = rows.map((r) => (typeof r.main_net === 'number' && Number.isFinite(r.main_net) ? r.main_net : null))
  const idxVals = rows.map((r) => (typeof r.index_chg_pct === 'number' && Number.isFinite(r.index_chg_pct) ? r.index_chg_pct : null))

  const barOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['主力净流入', '上证涨跌幅%'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 56, right: 24, top: 28, bottom: 40 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: CHART.ink2, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    yAxis: [
      { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}亿' }, splitLine: { lineStyle: { color: CHART.line } } },
      { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}%' }, splitLine: { show: false } },
    ],
    series: [
      { name: '主力净流入', type: 'bar', data: netVals.map((v) => ({ value: v, itemStyle: v == null ? undefined : { color: v >= 0 ? CHART.up : CHART.down } })) },
      { name: '上证涨跌幅%', type: 'line', yAxisIndex: 1, smooth: true, showSymbol: false, data: idxVals, itemStyle: { color: '#f5a623' }, lineStyle: { color: '#f5a623', width: 1.5 } },
    ],
  }

  return (
    <Card title="大盘主力资金净流入（近 30 日）">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="最新主力净流入" value={yi(last?.main_net)} color={flowColor(last?.main_net)} />
        <Stat label="最新上证涨跌幅" value={pct(last?.index_chg_pct)} color={flowColor(last?.index_chg_pct)} />
        <Stat label="最新超大单净流入" value={yi(last?.super_net)} color={flowColor(last?.super_net)} />
        <Stat label="最新大单净流入" value={yi(last?.big_net)} color={flowColor(last?.big_net)} />
      </div>

      {rows.length > 0 && (
        <div className="mt-3">
          <EChart option={barOption} height={300} ariaLabel="大盘主力净流入与上证涨跌幅图" />
        </div>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">日期</th>
              <th className="text-right py-1.5 pr-3">上证涨跌幅%</th>
              <th className="text-right py-1.5 pr-3">主力净流入(亿)</th>
              <th className="text-right py-1.5 pr-3">超大单(亿)</th>
              <th className="text-right py-1.5 pr-3">大单(亿)</th>
              <th className="text-right py-1.5">中单(亿)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.date}-${i}`} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{r.date ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right">{pct(r.index_chg_pct)}</td>
                <td className="py-1.5 pr-3 text-right" style={{ color: flowColor(r.main_net) }}>{yi(r.main_net)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.super_net)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.big_net)}</td>
                <td className="py-1.5 text-right">{yi(r.mid_net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function MarginBlock({ rows, latest, available }: { rows: FundFlowMarginRow[]; latest: FundFlowData['margin']['latest']; available: boolean }) {
  if (!available) return <HonestUnavailable label="融资融券趋势（融资买入额 & 融资余额）" />
  const dates = rows.map((r) => r.date ?? '')
  const rzmrVals = rows.map((r) => (typeof r.total_rzmr_yi === 'number' && Number.isFinite(r.total_rzmr_yi) ? r.total_rzmr_yi : null))

  const lineOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['融资买入额(合计)'], textStyle: { color: CHART.ink2 }, top: 0 },
    grid: { left: 56, right: 24, top: 28, bottom: 40 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: CHART.ink2, hideOverlap: true }, axisLine: { lineStyle: { color: CHART.line } } },
    yAxis: { type: 'value', axisLabel: { color: CHART.ink2, formatter: '{value}亿' }, splitLine: { lineStyle: { color: CHART.line } } },
    series: [{ name: '融资买入额(合计)', type: 'line', smooth: true, showSymbol: false, data: rzmrVals, itemStyle: { color: CHART.up }, lineStyle: { color: CHART.up, width: 1.5 } }],
  }

  return (
    <Card title="融资融券趋势（融资买入额 & 融资余额）">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="融资买入额(最新)" value={yi(latest?.total_rzmr_yi)} sub={latest?.rzmr_change_yi != null ? <DeltaTag text={`${latest.rzmr_change_yi >= 0 ? '+' : ''}${num(latest.rzmr_change_yi)}亿`} dir={latest.rzmr_change_yi >= 0 ? 'up' : 'down'} /> : undefined} />
        <Stat label="融资余额(最新)" value={yi(latest?.total_rzye_yi)} sub={latest?.rzye_change_yi != null ? <DeltaTag text={`${latest.rzye_change_yi >= 0 ? '+' : ''}${num(latest.rzye_change_yi)}亿`} dir={latest.rzye_change_yi >= 0 ? 'up' : 'down'} /> : undefined} />
        <Stat label="沪市买入额" value={yi(latest?.sh_rzmr_yi)} />
        <Stat label="深市买入额" value={yi(latest?.sz_rzmr_yi)} />
      </div>

      {rows.length > 0 && (
        <div className="mt-3">
          <EChart option={lineOption} height={300} ariaLabel="融资买入额趋势图（亿元）" />
        </div>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">日期</th>
              <th className="text-right py-1.5 pr-3">沪融资买入(亿)</th>
              <th className="text-right py-1.5 pr-3">深融资买入(亿)</th>
              <th className="text-right py-1.5 pr-3">合计买入(亿)</th>
              <th className="text-right py-1.5 pr-3">沪融资余额(亿)</th>
              <th className="text-right py-1.5 pr-3">深融资余额(亿)</th>
              <th className="text-right py-1.5">合计余额(亿)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.date}-${i}`} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{r.date ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.sh_rzmr_yi)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.sz_rzmr_yi)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.total_rzmr_yi)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.sh_rzye_yi)}</td>
                <td className="py-1.5 pr-3 text-right">{yi(r.sz_rzye_yi)}</td>
                <td className="py-1.5 text-right">{yi(r.total_rzye_yi)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-xs text-sf-ink-3">
        数据来源：东方财富融资融券（沪+深），北交所无公开宏观融资融券序列，故合计未含 BJ。金额单位均为亿元。
      </div>
    </Card>
  )
}
