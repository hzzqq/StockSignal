import { useState } from 'react'
import { useIndexQuotes } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { QueryState } from '@/shared/ui/States'
import { KLineModal } from '../charts/KLineModal'
import type { IndexQuote } from '@/api/schemas/stock'
import type { PriceDomain } from '../charts/common'

/**
 * 主要指数组件（FinPilot MarketSyncPage 的「指数卡片 → 点击显示详细 K 线」形态）。
 *
 * 外部视角：卡片网格展示指数名称 / 现价 / 涨跌额·涨跌幅（红涨绿跌，交易屏语义）。
 * 交互：点击任一卡片 → 打开 KLineModal 显示该指数详细日线 K 线。
 * 数据缺失（current===null）→ 显示「—」；涨跌方向按 change 符号着色，缺失用中性色。
 *
 * 诚实红线：指数报价离线/取数失败 → null（前端「—」）；点击弹窗 K 线为空 → KLineChart 空态；
 * 绝不补 0 / 不编造涨跌幅。
 */
export function IndexQuotes() {
  const { data, isLoading, isError, error } = useIndexQuotes()
  const [active, setActive] = useState<IndexQuote | null>(null)
  // 指数 = 交易屏语义：涨红跌绿（--ss-up / --ss-down）。
  const priceDomain: PriceDomain = 'market'

  return (
    <Card title="主要指数">
      <QueryState
        isLoading={isLoading}
        isError={isError}
        error={error}
        isEmpty={!!data && data.items.length === 0}
        emptyLabel="暂无指数数据"
        emptyHint="指数报价取数失败"
      >
        {data ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {data.items.map((it) => {
              const up = (it.change ?? 0) >= 0
              const color =
                it.change === null
                  ? 'var(--color-sf-ink-2)'
                  : up
                    ? 'var(--color-ss-up)'
                    : 'var(--color-ss-down)'
              return (
                <button
                  key={it.code}
                  type="button"
                  onClick={() => setActive(it)}
                  aria-label={`${it.name} 查看 K 线详情`}
                  className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-3 text-left hover:border-sf-accent transition-colors"
                >
                  <div className="text-label text-sf-ink-3">{it.name}</div>
                  <div className="text-[1.3rem] font-bold tabular-nums" style={{ color }}>
                    {it.current === null ? '—' : it.current.toFixed(2)}
                  </div>
                  <div className="text-label tabular-nums" style={{ color }}>
                    {it.change === null
                      ? '—'
                      : `${up ? '+' : ''}${it.change.toFixed(2)}（${it.change_pct === null ? '—' : `${it.change_pct.toFixed(2)}%`}）`}
                  </div>
                </button>
              )
            })}
          </div>
        ) : null}
      </QueryState>

      {data && data.note !== null && (
        <p className="text-body text-sf-ink-2 mt-3">{data.note}</p>
      )}

      <KLineModal
        open={active !== null}
        onClose={() => setActive(null)}
        code={active?.code ?? null}
        name={active?.name}
        priceDomain={priceDomain}
      />
    </Card>
  )
}
