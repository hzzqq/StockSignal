import { useState } from 'react'
import { usePaperTrades } from '@/lib/queries'
import { QueryState } from '@/shared/ui/States'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'

const INPUT_CLS =
  'mt-1 bg-sf-bg border border-sf-line text-sf-ink rounded px-2 py-1.5 outline-none focus:border-sf-accent'

/** 42 模拟交易：按用户拉取 paper_<user>.json 账本（持仓 / 成交 / 权益曲线点）。 */
export function PaperTrades() {
  const [user, setUser] = useState('admin')
  const q = usePaperTrades(user)
  const p = q.data

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">模拟交易账本</h2>
      <Card>
        <label className="text-xs text-sf-ink-2">用户</label>
        <input
          className={`${INPUT_CLS} ml-2 w-48`}
          value={user}
          onChange={(e) => setUser(e.target.value)}
          placeholder="用户名"
        />
      </Card>

      <QueryState isLoading={q.isLoading} isError={q.isError} error={q.error} isEmpty={!p}>
        {p && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Stat
                label="初始资金"
                value={p.init_cash != null ? p.init_cash.toLocaleString() : '—'}
              />
              <Stat
                label="可用现金"
                value={p.cash != null ? p.cash.toLocaleString() : '—'}
              />
              <Stat
                label="持仓数"
                value={p.positions ? Object.keys(p.positions).length : '—'}
              />
            </div>

            {p.positions && Object.keys(p.positions).length > 0 && (
              <Card title="持仓">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-sf-ink-3 text-left">
                      <th className="py-1">代码</th>
                      <th className="py-1">名称</th>
                      <th className="py-1">数量</th>
                      <th className="py-1">成本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(p.positions).map(([code, pos]) => (
                      <tr key={code} className="border-t border-sf-line">
                        <td>{code}</td>
                        <td>{pos.name ?? '—'}</td>
                        <td>{pos.qty ?? '—'}</td>
                        <td>{pos.avg_cost != null ? pos.avg_cost : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}

            {p.trades && p.trades.length > 0 && (
              <Card title={`成交记录（${p.trades.length}）`}>
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-sf-ink-3 text-left">
                        <th className="py-1">时间</th>
                        <th className="py-1">代码</th>
                        <th className="py-1">名称</th>
                        <th className="py-1">方向</th>
                        <th className="py-1">价</th>
                        <th className="py-1">量</th>
                        <th className="py-1">额</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.trades.map((t, i) => (
                        <tr key={i} className="border-t border-sf-line">
                          <td>{t.time ?? '—'}</td>
                          <td>{t.code ?? '—'}</td>
                          <td>{t.name ?? '—'}</td>
                          <td
                            style={{
                              color:
                                t.side === '买'
                                  ? 'var(--color-ss-up)'
                                  : 'var(--color-ss-down)',
                            }}
                          >
                            {t.side ?? '—'}
                          </td>
                          <td>{t.price ?? '—'}</td>
                          <td>{t.qty ?? '—'}</td>
                          <td>{t.amount ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        )}
      </QueryState>
    </div>
  )
}
