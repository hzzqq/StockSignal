import type { Watch, WatchlistItem, WatchAlert, SectorItem } from '@/api/schemas/read'
import { useWatch } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { CHART } from '@/shared/charts/palette'

/**
 * 14 页「智能盯盘」V2 化（对应 V2-STATUS-PLAN Tier2）。
 * 数据来源：useWatch → GET /api/v2/read/watch（后端只读聚合）。
 *
 * 三块内容：
 *  - 自选股盯盘：逐只主力资金流（真实优先 / 量价估算兜底），红涨绿跌。
 *  - 板块资金异动：行业资金流 TOP 净流入 / TOP 涨跌。
 *  - 资金流预警：基于主力净流入占比阈值（强 ≥+3% / 弱 ≤-3%），非价格。
 *
 * 红线：
 *  - 后端已诚实降级：资金流缺失→null，前端显示「—」，绝不补 0（避开 ?? 0 / || 0 / new Date()）。
 *  - 实时现价 / 涨跌幅未在只读端点聚合（Flask 上下文不可用 Streamlit 实时行情单例），
 *    页面如实标注；看实时价请用个股分时/行情端点或 v1 盯盘页。
 *  - 红涨绿跌（A 股交易屏语义）。
 */
// 仅供图表坐标 / 文本占位：非数→0，不编数据（避开诚实红线 ?? 0 / || 0 / new Date()）
function nz(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function fmtYi(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)} 亿`
  }
  return '—'
}
function fmtPct(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    const sign = v > 0 ? '+' : ''
    return `${sign}${v.toFixed(2)}%`
  }
  return '—'
}
function chgColor(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) {
    return v > 0 ? CHART.up : v < 0 ? CHART.down : CHART.ink2
  }
  return CHART.ink2
}
function levelColor(level: unknown): string {
  if (level === '强') return CHART.up
  if (level === '弱') return CHART.down
  return CHART.ink2
}
function sourceLabel(source: unknown): string {
  if (source === 'akshare') return '真实'
  if (source === 'estimate') return '估算'
  return '缺失'
}

// 板块异动内联条：宽度按 |净额| 相对最大值的比例。
function sectorBarWidth(net: unknown, maxAbs: number): number {
  const v = Math.abs(nz(net))
  if (maxAbs <= 0) return 0
  return Math.min(100, (v / maxAbs) * 100)
}

export function Watch() {
  const q = useWatch()
  const d = q.data
  const watchlist = (d?.watchlist ?? []).filter((w): w is WatchlistItem => !!w)
  const sectorItems = (d?.sector_items ?? []).filter((s): s is SectorItem => !!s && !!s.name)
  const alerts = (d?.alerts ?? []).filter((a): a is WatchAlert => !!a)
  const unavailable = (d?.unavailable ?? []).filter((k): k is string => typeof k === 'string')
  const summary = d?.summary

  const isEmpty = !!d && watchlist.length === 0 && sectorItems.length === 0

  const secMaxAbs = sectorItems.reduce((m, s) => Math.max(m, Math.abs(nz(s.net))), 0)
  const secTopNet = [...sectorItems].filter((s) => Number.isFinite(nz(s.net))).sort((a, b) => nz(b.net) - nz(a.net)).slice(0, 8)
  const secTopChg = [...sectorItems].filter((s) => Number.isFinite(nz(s.chg_pct))).sort((a, b) => nz(b.chg_pct) - nz(a.chg_pct)).slice(0, 8)

  return (
    <div className="watch">
      <h2 className="text-lg font-semibold">智能盯盘</h2>
      <div className="text-xs text-sf-ink-3">
        红涨绿跌；聚合自选股主力资金流、板块资金异动与资金流阈值预警。实时现价 / 涨跌幅未在此只读端点聚合
        （实时行情取数依赖 Streamlit 单例，Flask 上下文不可用），看实时价请用个股分时 / 行情端点或 v1 盯盘页。
        数据为加载时点快照，非实时，非投资建议。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="暂无盯盘数据"
        emptyHint="未查询到自选股与板块资金流（可能离线 / 接口受限 / 当前账号无自选股）；后端已诚实降级"
      >
        {d ? (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="盯盘数量" value={String(nz(summary?.watch_count))} sub="自选股只数" />
              <Stat label="有资金流" value={String(nz(summary?.with_fund))} sub="已拿到主力资金流" />
              <Stat label="强预警" value={String(nz(summary?.strong_count))} sub="主力净流入占比≥+3%" />
              <Stat label="弱预警" value={String(nz(summary?.weak_count))} sub="主力净流入占比≤-3%" />
            </div>

            {unavailable.length > 0 && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                以下情况本次发生（已诚实标注）：{unavailable.join('、')}
              </div>
            )}

            {/* 自选股盯盘 */}
            <Card title="👁️ 自选股盯盘（逐只主力资金流）">
              {watchlist.length === 0 ? (
                <div className="text-xs text-sf-ink-3">
                  当前账号暂无自选股。请在 v1 实时盯盘页或自选管理添加后，再回到此处查看逐只资金流异动。
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="text-sf-ink-3 border-b border-sf-line">
                        <th className="text-left py-1 pr-2 font-medium">代码</th>
                        <th className="text-left py-1 pr-2 font-medium">名称</th>
                        <th className="text-right py-1 pr-2 font-medium">主力净流入</th>
                        <th className="text-right py-1 pr-2 font-medium">主力占比</th>
                        <th className="text-right py-1 pr-2 font-medium">大单</th>
                        <th className="text-right py-1 pr-2 font-medium">超大单</th>
                        <th className="text-left py-1 pr-2 font-medium">来源</th>
                        <th className="text-left py-1 pr-2 font-medium">预警</th>
                      </tr>
                    </thead>
                    <tbody>
                      {watchlist.map((w) => {
                        const f = w.fund ?? {}
                        const code = w.code ?? '—'
                        return (
                          <tr key={code} className="border-b border-sf-line/60">
                            <td className="py-1 pr-2 font-mono">{code}</td>
                            <td className="py-1 pr-2">{w.name ?? '—'}</td>
                            <td className="py-1 pr-2 text-right" style={{ color: chgColor(f.main_net) }}>{fmtYi(f.main_net)}</td>
                            <td className="py-1 pr-2 text-right" style={{ color: chgColor(f.main_net_pct) }}>{fmtPct(f.main_net_pct)}</td>
                            <td className="py-1 pr-2 text-right">{fmtYi(f.big_net)}</td>
                            <td className="py-1 pr-2 text-right">{fmtYi(f.super_net)}</td>
                            <td className="py-1 pr-2">{sourceLabel(f.source)}</td>
                            <td className="py-1 pr-2">
                              {(() => {
                                const a = alerts.find((x) => (x.code ?? '') === code)
                                return a ? (
                                  <span
                                    className="inline-block rounded px-1.5 py-0.5 text-[11px]"
                                    style={{ color: levelColor(a.level), border: `1px solid ${levelColor(a.level)}` }}
                                  >
                                    {a.level}
                                  </span>
                                ) : (
                                  <span className="text-sf-ink-3">—</span>
                                )
                              })()}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="mt-2 text-[11px] opacity-70">
                金额单位：亿元（后端已折算）；「—」= 该字段缺失（来源不可用 / 非交易时段），不补 0；红涨绿跌。
              </div>
            </Card>

            {/* 板块资金异动 */}
            <Card title="🔥 板块资金异动（行业资金流 TOP）">
              {sectorItems.length === 0 ? (
                <div className="text-xs text-sf-ink-3">板块资金流本次未取到（离线 / 接口受限），已诚实标注，未编造板块列表。</div>
              ) : (
                <div className="grid md:grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs font-semibold mb-2">💰 主力净流入 TOP8</div>
                    {secTopNet.map((s) => (
                      <div key={`n-${s.name}`} className="mb-1">
                        <div className="flex justify-between text-xs">
                          <span>{s.name ?? '—'}</span>
                          <span style={{ color: chgColor(s.net) }}>{fmtYi(s.net)}</span>
                        </div>
                        <div className="h-1.5 rounded bg-sf-line/40 overflow-hidden">
                          <div className="h-full" style={{ width: `${sectorBarWidth(s.net, secMaxAbs)}%`, background: chgColor(s.net) }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="text-xs font-semibold mb-2">📈 涨跌幅 TOP8</div>
                    {secTopChg.map((s) => (
                      <div key={`c-${s.name}`} className="flex justify-between text-xs mb-1">
                        <span>{s.name ?? '—'}</span>
                        <span style={{ color: chgColor(s.chg_pct) }}>{fmtPct(s.chg_pct)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            {/* 资金流预警 */}
            <Card title="🚨 资金流预警（主力净流入占比阈值）">
              {alerts.length === 0 ? (
                <div className="text-xs text-sf-ink-3">暂无预警（当前无自选股或资金流数据）。</div>
              ) : (
                <div className="space-y-1">
                  {alerts.map((a) => (
                    <div key={a.code ?? a.name ?? 'x'} className="flex items-center gap-2 text-xs">
                      <span
                        className="inline-block w-10 text-center rounded px-1 py-0.5 text-[11px]"
                        style={{ color: levelColor(a.level), border: `1px solid ${levelColor(a.level)}` }}
                      >
                        {a.level}
                      </span>
                      <span className="font-mono">{a.code ?? '—'}</span>
                      <span>{a.name ?? '—'}</span>
                      <span className="text-sf-ink-3">{a.reason ?? ''}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-2 text-[11px] opacity-70">
                预警基于主力净流入占比：强 ≥ +3% / 弱 ≤ -3% / 其余中性；基于资金流而非价格。实时价变预警未在此聚合。
              </div>
            </Card>
          </div>
        ) : null}
      </QueryState>

      <div className="mt-8">
        <div className="text-xs text-sf-ink-3">
          ⚠️ 说明：本页为自选股与板块资金流异动的快照监控，非预测模型，不构成投资建议；
          资金流为页面加载时点数据，盘中读数可能有延迟。实时现价需在个股分时 / 行情端点查看。
        </div>
      </div>
    </div>
  )
}
