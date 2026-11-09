import type { EChartsOption } from 'echarts'
import type { MacroIndicator, MacroRegime } from '@/api/schemas/read'
import { useMacroData } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { EChart } from '@/shared/charts/EChart'
import { CHART } from '@/shared/charts/palette'

/**
 * 84 页「宏观数据」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useMacroData → GET /api/v2/read/macro-data（后端复用 modules.macro_data）。
 *
 * 各指标**独立降级**：取不到→null，前端显示「—」，绝不补 0。
 * 数值字段后端已把 NaN/Inf 清洗为 null。
 */
const REGIME_LABELS: Record<string, string> = {
  dxy: '美元指数',
  us_treasury_10y: '美债10Y',
  us_cpi: '美国CPI',
  usd_cny: '美元兑人民币',
  yield_curve: '收益率曲线',
  cn_us_spread: '中美利差',
}

function fmtVal(v: unknown, unit?: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const s = v.toFixed(2)
    return `${s}${typeof unit === 'string' ? unit : ''}`
  }
  return '—'
}

function dirColor(dir: 'up' | 'down' | 'flat'): string {
  return dir === 'up' ? CHART.up : dir === 'down' ? CHART.down : CHART.ink2
}
function dirArrow(dir: 'up' | 'down' | 'flat'): string {
  return dir === 'up' ? '▲' : dir === 'down' ? '▼' : '·'
}

function scoreColor(score: number): string {
  // 评分越高 = 全球流动性越宽松 / 风险偏好越高 → 利好 A 股（红）；越低 → 压制（绿）。
  if (score >= 60) return CHART.up
  if (score >= 40) return CHART.ink2
  return CHART.down
}
function scoreBand(score: number): string {
  if (score >= 60) return '宽松 · 利好风险资产'
  if (score >= 40) return '中性'
  return '收紧 · 压制风险资产'
}

export function MacroData() {
  const q = useMacroData()
  const d = q.data

  const indicators = d?.indicators ?? {}
  const all = Object.entries(indicators) as [string, MacroIndicator | null][]
  const domestic = all.filter(
    (e): e is [string, MacroIndicator] => {
      const v = e[1]
      return !!v && v.region === '国内'
    },
  )
  const global = all.filter(
    (e): e is [string, MacroIndicator] => {
      const v = e[1]
      return !!v && v.region === '全球'
    },
  )
  const regime = d?.regime ?? null

  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')

  const isEmpty = !!d && domestic.length === 0 && global.length === 0 && !regime

  return (
    <div className="macro">
      <h2 className="text-lg font-semibold">宏观数据</h2>
      <div className="text-xs text-sf-ink-3">
        国内 + 全球关键宏观指标（PMI / CPI / M2 / 美债 / 美元 / 美股等）与全球流动性风险评分；
        数据来自国家统计局 / 央行 / 东方财富 / 新浪等公开源，离线或接口受限时逐指标诚实降级（取不到显示「—」），非实时、非投资建议。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="宏观数据暂不可用"
        emptyHint="全部指标取数失败（离线或接口受限）；后端已逐指标诚实降级，未编造数值"
      >
        {d ? (
          <div className="space-y-6">
            {regime && <RegimeBlock regime={regime} />}
            <RegionBlock title="国内指标" rows={domestic} />
            <RegionBlock title="全球指标" rows={global} />
            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下指标本次取不到（已诚实降级）：{unavailable.join('、')}
              </div>
            )}
            {d.note && <div className="text-xs text-sf-ink-3">{d.note}</div>}
          </div>
        ) : null}
      </QueryState>
    </div>
  )
}

function RegimeBlock({ regime }: { regime: MacroRegime }) {
  const score = typeof regime.score === 'number' && Number.isFinite(regime.score) ? regime.score : null
  const sub = regime.sub ?? {}
  const subEntries = Object.entries(sub).filter(
    (e): e is [string, number] => typeof e[1] === 'number' && Number.isFinite(e[1]),
  )

  const barOption: EChartsOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 96, right: 24, top: 16, bottom: 24 },
    xAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: CHART.ink2 }, splitLine: { lineStyle: { color: CHART.line } } },
    yAxis: {
      type: 'category',
      data: subEntries.map(([k]) => REGIME_LABELS[k] ?? k),
      axisLabel: { color: CHART.ink2 },
      axisLine: { lineStyle: { color: CHART.line } },
    },
    series: [
      {
        type: 'bar',
        data: subEntries.map(([, v]) => ({
          value: v,
          itemStyle: { color: scoreColor(v) },
        })),
      },
    ],
  }

  return (
    <Card title="全球宏观风险偏好 / 流动性评分（0-100）">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat
          label="综合评分"
          value={score == null ? '—' : String(score)}
          color={score == null ? undefined : scoreColor(score)}
          sub={score == null ? undefined : scoreBand(score)}
        />
        <Stat
          label="美债10Y-2Y 斜率"
          value={fmtVal(regime.yield_curve, '%')}
          color={regime.yield_curve == null ? undefined : regime.yield_curve < 0 ? CHART.down : CHART.up}
          sub={regime.yield_curve == null ? undefined : regime.yield_curve < 0 ? '倒挂 ▼' : '陡峭 ▲'}
        />
        <Stat
          label="中美10Y利差"
          value={fmtVal(regime.cn_us_spread, '%')}
          color={regime.cn_us_spread == null ? undefined : regime.cn_us_spread < 0 ? CHART.down : CHART.up}
          sub={regime.cn_us_spread == null ? undefined : regime.cn_us_spread < 0 ? '倒挂 ▼' : '走阔 ▲'}
        />
      </div>

      {subEntries.length > 0 && (
        <div className="mt-3">
          <EChart option={barOption} height={Math.max(160, subEntries.length * 36)} ariaLabel="全球风险评分分项条形图（0-100）" />
        </div>
      )}

      <div className="mt-2 text-xs text-sf-ink-3">
        评分为规则化合成（弱美元 / 低美债收益率 / 低美国通胀 / 人民币偏强 → 高分），非模型预测；取不到的分项不计入，全部取不到则无评分。
      </div>
    </Card>
  )
}

function RegionBlock({ title, rows }: { title: string; rows: [string, MacroIndicator][] }) {
  if (rows.length === 0) {
    return (
      <Card title={title}>
        <div className="text-xs text-sf-ink-3">本组指标本次取不到（离线或接口受限），已诚实降级。</div>
      </Card>
    )
  }
  return (
    <Card title={`${title}（${rows.length}）`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">指标</th>
              <th className="text-right py-1.5 pr-3">最新值</th>
              <th className="text-right py-1.5 pr-3">较上期</th>
              <th className="text-left py-1.5 pr-3">数据日期</th>
              <th className="text-left py-1.5 pr-3">频率</th>
              <th className="text-left py-1.5">来源</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, ind]) => {
              const chg = fmtChange(ind.change, ind.unit)
              return (
                <tr key={key} className="border-b border-sf-line/60">
                  <td className="py-1.5 pr-3">
                    <div>{ind.name ?? key}</div>
                    {ind.desc && <div className="text-sf-ink-3 text-[11px]">{ind.desc}</div>}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-medium">{fmtVal(ind.value, ind.unit)}</td>
                  <td className="py-1.5 pr-3 text-right" style={chg ? { color: dirColor(chg.dir) } : undefined}>
                    {chg ? `${dirArrow(chg.dir)} ${chg.text}` : '—'}
                  </td>
                  <td className="py-1.5 pr-3">{ind.date ?? '—'}</td>
                  <td className="py-1.5 pr-3">{ind.freq ?? '—'}</td>
                  <td className="py-1.5">{ind.source ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function fmtChange(v: unknown, unit?: unknown): { text: string; dir: 'up' | 'down' | 'flat' } | null {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : v < 0 ? '' : ''
    const text = `${sign}${v.toFixed(2)}${typeof unit === 'string' ? unit : ''}`
    return { text, dir: v > 0 ? 'up' : v < 0 ? 'down' : 'flat' }
  }
  return null
}
