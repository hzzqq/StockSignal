import { useState } from 'react'
import { useMarketSentiment } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Loading, EmptyState, ErrorState } from '@/shared/ui/States'

/** 迷你走势：把近 40 日序列画成折线；含 null 时按有效点缩放，全 null 显「—」。 */
function Spark({ values }: { values: Array<number | null> }) {
  const pts = values.map((v, i) => ({ v, i })).filter((x) => x.v != null) as { v: number; i: number }[]
  if (pts.length < 2) return <span className="text-label text-sf-ink-3">—</span>
  const xs = pts.map((p) => p.i)
  const ys = pts.map((p) => p.v)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const W = 96
  const H = 24
  const sx = (x: number) => ((x - minX) / (maxX - minX || 1)) * W
  const sy = (y: number) => H - ((y - minY) / (maxY - minY || 1)) * H
  const d = pts.map((p) => `${sx(p.i).toFixed(1)},${sy(p.v).toFixed(1)}`).join(' ')
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="overflow-visible" aria-hidden="true">
      <polyline points={d} fill="none" stroke="var(--sf-accent, #2b8aef)" strokeWidth={1.5} />
    </svg>
  )
}

/** 50 市场情绪·广度与情绪温度计（v2 native /market-sentiment）：实时市场驱动力（21 指标）。
 *  诚实红线：单源失败优雅降级、网络全失败回落 SQLite 缓存；综合温度样本不足返回 null（不补零）；
 *  缺值（value/heat 为 null）显「—」，不编造。days 可选（默认 180，上限 1200）。 */
export function MarketSentiment() {
  const [days, setDays] = useState(180)
  const q = useMarketSentiment(days)
  const data = q.data

  const temp = data?.temperature ?? null
  const level = data?.level ?? null

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">市场情绪 · 温度计</h2>
      <p className="text-xs text-sf-ink-3">
        综合市场温度由可用指标近期分位多空加权得出（高=热：ADR/涨停/PE/北向/融资净买；高=冷：VIX/PCR/股息率）。
        温度计为风险/健康语义，与价格涨跌红绿无关。
      </p>

      <Card>
        <label className="text-xs text-sf-ink-2">
          回溯天数
          <select
            className="mt-1 w-40 bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {[90, 180, 250, 500, 750, 1200].map((d) => (
              <option key={d} value={d}>
                {d} 日
              </option>
            ))}
          </select>
        </label>
      </Card>

      {q.isLoading && <Loading label="加载市场情绪…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '市场情绪加载失败'} />
      )}

      {data && !data.available && (
        <EmptyState label="市场情绪数据暂时取不到" hint={data.reason ?? data.note} />
      )}

      {data && data.available && (
        <>
          {/* 温度计 */}
          <Card title="综合市场温度">
            <div className="flex items-center gap-4">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-full text-lg font-semibold"
                style={{
                  backgroundColor: level?.color ?? '#e5e7eb',
                  color: '#fff',
                }}
              >
                {temp != null ? temp.toFixed(1) : '—'}
              </div>
              <div>
                <div className="text-title font-medium text-sf-ink">
                  {level ? `${level.emoji} ${level.label}` : '温度样本不足'}
                </div>
                <div className="text-label text-sf-ink-3">
                  数据截至：{data.data_as_of ?? '—'}
                </div>
              </div>
            </div>
          </Card>

          {/* 各维度指标 */}
          {Object.entries(data.dims).map(([group, items]) => (
            <Card key={group} title={group}>
              {items.length === 0 ? (
                <div className="text-label text-sf-ink-3">该维度暂无可用指标</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                        <th className="py-2 pr-3">指标</th>
                        <th className="py-2 pr-3 text-right">最新值</th>
                        <th className="py-2 pr-3 text-right">单位</th>
                        <th className="py-2 pr-3 text-right">热度</th>
                        <th className="py-2 pr-3 text-right">近 40 日</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((it) => (
                        <tr key={it.key} className="border-b border-sf-line/60">
                          <td className="py-1.5 pr-3 text-sf-ink">{it.name}</td>
                          <td className="py-1.5 pr-3 text-right text-sf-ink">
                            {it.value != null ? it.value.toFixed(2) : '—'}
                          </td>
                          <td className="py-1.5 pr-3 text-right text-sf-ink-2">{it.unit || '—'}</td>
                          <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                            {it.heat != null ? it.heat.toFixed(1) : '—'}
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            <Spark values={it.spark} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          ))}

          {/* 不可用指标 */}
          {data.unavailable.length > 0 && (
            <Card title="不可用指标（诚实降级）">
              <div className="flex flex-wrap gap-2 text-xs">
                {data.unavailable.map((u, i) => (
                  <span key={`${u.dim}-${u.key}-${i}`} className="rounded bg-sf-surface-2 px-2 py-1 text-sf-ink-2">
                    {u.key}：{u.reason}
                  </span>
                ))}
              </div>
            </Card>
          )}

          {data.note && <p className="text-xs text-sf-ink-3">{data.note}</p>}
        </>
      )}
    </div>
  )
}
