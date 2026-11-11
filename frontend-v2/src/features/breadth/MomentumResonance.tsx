import { useMomentumBreadth } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Loading, EmptyState, ErrorState } from '@/shared/ui/States'

/** 62 动量×广度共振矩阵（v2 native /momentum-resonance）：离线广度统计真页面。
 *  纯离线：数据来自 modules.market_regime.load_breadth_history（red_ratio / zt_prev_ret）。
 *  矩阵 = 广度五档（红盘率）× 动量五档（涨停前日收益代理）的联合分布共现天数。
 *  诚实红线：离线历史不足 → 后端 available=false + reason，前端显诚实空态，不编造矩阵；
 *  缺值（red_ratio / zt_prev_ret 为 null）显「—」，不补零。 */
export function MomentumResonance() {
  const q = useMomentumBreadth()
  const data = q.data

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">动量 × 广度共振</h2>
      <p className="text-xs text-sf-ink-3">
        离线广度统计（红盘率 × 涨停前日收益代理的联合分布）。仅描述历史结构，非收益预测。只读视图，无写能力。
      </p>

      {q.isLoading && <Loading label="加载共振矩阵…" />}
      {q.isError && (
        <ErrorState message={q.error instanceof Error ? q.error.message : '共振矩阵加载失败'} />
      )}

      {data && !data.available && (
        <EmptyState label="暂无可用的广度历史" hint={data.reason ?? data.note} />
      )}

      {data && data.available && (
        <>
          {/* 概要 */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Card title="样本天数">
              <div className="text-2xl font-semibold text-sf-ink">{data.n_days}</div>
            </Card>
            <Card title="当前红盘率">
              <div className="text-2xl font-semibold text-sf-ink">
                {data.current.red_ratio != null ? `${data.current.red_ratio.toFixed(2)}%` : '—'}
              </div>
              <div className="mt-1 text-label text-sf-ink-3">
                {data.current.rr_label ?? '—'} · {data.current.mom_label ?? '—'}
              </div>
            </Card>
            <Card title="共振高热占比">
              <div className="text-2xl font-semibold text-sf-ink">
                {data.stats.co_hot != null ? `${data.stats.co_hot.toFixed(1)}%` : '—'}
              </div>
            </Card>
            <Card title="共振偏冷占比">
              <div className="text-2xl font-semibold text-sf-ink">
                {data.stats.co_cold != null ? `${data.stats.co_cold.toFixed(1)}%` : '—'}
              </div>
            </Card>
          </div>

          {/* 共振矩阵 */}
          <Card title="共振矩阵（共现天数）">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                    <th className="py-2 pr-3">红盘率＼动量</th>
                    {data.mom_labels.map((m, j) => (
                      <th key={j} className="py-2 pr-3 text-right">
                        {m}
                      </th>
                    ))}
                    <th className="py-2 pr-3 text-right">合计</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rr_labels.map((r, i) => {
                    const row = data.matrix[i] ?? []
                    const isCurrent =
                      data.current.rr_band === i
                    return (
                      <tr
                        key={i}
                        className={`border-b border-sf-line/60 ${isCurrent ? 'bg-sf-surface-2' : ''}`}
                      >
                        <td className="py-2 pr-3 text-sf-ink-2">{r}</td>
                        {row.map((v, j) => (
                          <td key={j} className="py-2 pr-3 text-right text-sf-ink">
                            {v}
                          </td>
                        ))}
                        <td className="py-2 pr-3 text-right font-medium text-sf-ink">
                          {data.totals_col[i] ?? '—'}
                        </td>
                      </tr>
                    )
                  })}
                  <tr className="border-t border-sf-line">
                    <td className="py-2 pr-3 text-sf-ink-2 font-medium">合计</td>
                    {data.totals_row.map((v, j) => (
                      <td key={j} className="py-2 pr-3 text-right font-medium text-sf-ink">
                        {v}
                      </td>
                    ))}
                    <td className="py-2 pr-3 text-right text-sf-ink-3">—</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-sf-ink-3">
              行 = 广度（红盘率）五档，列 = 动量（涨停前日收益代理）五档；单元格为历史共现天数。
              {data.current.rr_band != null && data.current.mom_band != null
                ? ` 当前格高亮（${data.current.rr_label} / ${data.current.mom_label}）。`
                : ''}
            </p>
          </Card>

          {/* 共振轨迹 */}
          <Card title="共振轨迹（近期）">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-sf-line text-left text-xs font-medium text-sf-ink-3">
                    <th className="py-2 pr-3">日期</th>
                    <th className="py-2 pr-3 text-right">红盘率档</th>
                    <th className="py-2 pr-3 text-right">动量档</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trajectory.dates.map((d, i) => (
                    <tr key={d} className="border-b border-sf-line/60">
                      <td className="py-1.5 pr-3 text-sf-ink-2">{d}</td>
                      <td className="py-1.5 pr-3 text-right text-sf-ink">
                        {data.trajectory.rr_band[i] ?? '—'}
                      </td>
                      <td className="py-1.5 pr-3 text-right text-sf-ink">
                        {data.trajectory.mom_band[i] ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.note && <p className="mt-3 text-xs text-sf-ink-3">{data.note}</p>}
          </Card>
        </>
      )}
    </div>
  )
}
