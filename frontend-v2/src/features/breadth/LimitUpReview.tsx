import { useState } from 'react'
import { useLimitUpReview } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Loading, EmptyState, ErrorState } from '@/shared/ui/States'

const DATE_RE = /^\d{8}$/

/** 70 涨停复盘 × 龙头识别（v2 native /limit-up-review）：实时涨停池（东财，10 分钟缓存）。
 *  诚实红线：联网不可用时 pool.available=false + reason，前端显诚实降级，不展示陈旧/编造数据；
 *  缺值（如某行 seal 为 null）显「—」，不补零。date 可选（YYYYMMDD），缺省自动选最近有数据交易日。 */
export function LimitUpReview() {
  const [draft, setDraft] = useState('')
  const [date, setDate] = useState<string | undefined>(undefined)
  const q = useLimitUpReview(date)
  const data = q.data

  const submit = () => {
    const v = draft.trim()
    if (v === '') {
      setDate(undefined)
      return
    }
    if (!DATE_RE.test(v)) return // 畸形不提交，避免把脏参数喂给后端
    setDate(v)
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">涨停复盘 × 龙头识别</h2>
      <p className="text-xs text-sf-ink-3">
        数据源：东方财富涨停池（10 分钟缓存，非实时行情）。龙头评分为启发式加权，不构成投资建议。
      </p>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-sf-ink-2">
            交易日（YYYYMMDD，留空=最近交易日）
            <input
              className="mt-1 w-44 bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent"
              value={draft}
              placeholder="例如 20261106"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit()
              }}
            />
          </label>
          <button
            className="rounded-tile bg-sf-accent px-3 py-1.5 text-sm text-white"
            onClick={submit}
          >
            查询
          </button>
          <button
            className="rounded-tile border border-sf-line px-3 py-1.5 text-sm text-sf-ink-2"
            onClick={() => {
              setDraft('')
              setDate(undefined)
            }}
          >
            重置
          </button>
          {data?.date && (
            <span className="text-xs text-sf-ink-3">当前数据日：{data.date}</span>
          )}
        </div>
      </Card>

      {q.isLoading && <Loading label="加载涨停复盘…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '涨停复盘加载失败'} />
      )}

      {data && (
        <>
          {/* 涨停池 */}
          {data.pool.available ? (
            <Card
              title={`涨停池（${data.pool.count} 只 · 首板 ${data.pool.first_boards} · 连板 ${data.pool.connect_boards} · 最高 ${data.pool.max_boards} 板 · 炸板 ${data.pool.broken_count}）`}
            >
              <div className="mb-3 flex flex-wrap gap-2 text-xs">
                {Object.entries(data.pool.bands).map(([k, v]) => (
                  <span key={k} className="rounded bg-sf-surface-2 px-2 py-1 text-sf-ink-2">
                    {k}：{v}
                  </span>
                ))}
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                      <th className="py-2 pr-3">名称</th>
                      <th className="py-2 pr-3">代码</th>
                      <th className="py-2 pr-3">行业</th>
                      <th className="py-2 pr-3 text-right">板数</th>
                      <th className="py-2 pr-3 text-right">封单(万)</th>
                      <th className="py-2 pr-3 text-right">成交额(万)</th>
                      <th className="py-2 pr-3">首次封板</th>
                      <th className="py-2 pr-3 text-center">炸板</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pool.rows.map((r) => (
                      <tr key={r.code} className="border-b border-sf-line/60">
                        <td className="py-1.5 pr-3 text-sf-ink">{r.name}</td>
                        <td className="py-1.5 pr-3 text-sf-ink-2">{r.code}</td>
                        <td className="py-1.5 pr-3 text-sf-ink-2">{r.industry}</td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink">{r.boards}</td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {r.seal != null ? r.seal.toFixed(0) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {r.amount != null ? r.amount.toFixed(0) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-sf-ink-2">{r.first_seal_band}</td>
                        <td className="py-1.5 pr-3 text-center text-sf-ink-2">
                          {r.broken ? '是' : '否'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* 龙头评分榜 */}
              <h4 className="mt-5 mb-2 text-sm font-medium text-sf-ink-2">龙头评分榜</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                      <th className="py-2 pr-3">名称</th>
                      <th className="py-2 pr-3">代码</th>
                      <th className="py-2 pr-3 text-right">板数</th>
                      <th className="py-2 pr-3 text-right">综合</th>
                      <th className="py-2 pr-3 text-right">高度</th>
                      <th className="py-2 pr-3 text-right">封单</th>
                      <th className="py-2 pr-3 text-right">板块</th>
                      <th className="py-2 pr-3 text-right">成交额</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.pool.leaderboard.map((l) => (
                      <tr key={l.code} className="border-b border-sf-line/60">
                        <td className="py-1.5 pr-3 text-sf-ink">{l.name}</td>
                        <td className="py-1.5 pr-3 text-sf-ink-2">{l.code}</td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink">{l.boards}</td>
                        <td className="py-1.5 pr-3 text-right font-medium text-sf-ink">
                          {l.score != null ? l.score.toFixed(1) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {l.s_height != null ? l.s_height.toFixed(1) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {l.s_seal != null ? l.s_seal.toFixed(1) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {l.s_ind != null ? l.s_ind.toFixed(1) : '—'}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-sf-ink-2">
                          {l.s_amt != null ? l.s_amt.toFixed(1) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {data.pool.themes.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {data.pool.themes.map((t) => (
                    <span key={t.industry} className="rounded bg-sf-surface-2 px-2 py-1 text-sf-ink-2">
                      {t.industry}：{t.count}
                    </span>
                  ))}
                </div>
              )}
            </Card>
          ) : (
            <EmptyState label="涨停池暂时取不到（联网不可用）" hint={data.pool.reason ?? '东财涨停池数据源不可达'} />
          )}

          {/* 连板梯队 */}
          <Card title="连板梯队">
            {data.ladder.available ? (
              <>
                <div className="mb-3 flex flex-wrap gap-2 text-xs text-sf-ink-2">
                  <span>最高 {data.ladder.max_boards} 板</span>
                  <span>连板合计 {data.ladder.total_connect}</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {data.ladder.distribution.map(([b, c]) => (
                    <span key={b} className="rounded bg-sf-surface-2 px-2 py-1 text-sf-ink-2">
                      {b} 板：{c} 只
                    </span>
                  ))}
                </div>
                {data.ladder.gaps.length > 0 && (
                  <p className="mt-3 text-xs text-sf-warn">
                    梯队断层（缺失板数）：{data.ladder.gaps.join(' / ')} 板
                  </p>
                )}
              </>
            ) : (
              <EmptyState label="连板梯队暂时取不到" hint={data.ladder.reason} />
            )}
          </Card>

          {/* 上下文（状态机 / 温度 / 牧羊人） */}
          {data.context.available && (
            <Card title="市场上下文">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                <div>
                  <div className="text-label text-sf-ink-3">涨停失败率</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.fail_ratio != null ? `${data.context.fail_ratio.toFixed(1)}%` : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-label text-sf-ink-3">涨停家数</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.limit_up_cnt != null ? data.context.limit_up_cnt : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-label text-sf-ink-3">市场周期</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.cycle ?? '—'}
                  </div>
                </div>
                <div>
                  <div className="text-label text-sf-ink-3">市场温度</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.temperature != null ? data.context.temperature : '—'}
                  </div>
                </div>
                <div>
                  <div className="text-label text-sf-ink-3">状态机</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.state ?? '—'}
                  </div>
                </div>
                <div>
                  <div className="text-label text-sf-ink-3">置信度</div>
                  <div className="text-lg font-semibold text-sf-ink">
                    {data.context.confidence != null ? data.context.confidence.toFixed(2) : '—'}
                  </div>
                </div>
              </div>
            </Card>
          )}

          {data.note && <p className="text-xs text-sf-ink-3">{data.note}</p>}
        </>
      )}
    </div>
  )
}
