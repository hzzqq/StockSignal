import type { TradingAccount as TradingAccountData, TradingAccountPosition, TradingAccountOrder } from '@/api/schemas/read'
import { useTradingAccount } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Stat } from '@/shared/ui/Stat'
import { QueryState } from '@/shared/ui/States'
import { CHART } from '@/shared/charts/palette'

/**
 * 交易账户（只读概览）—— 对应 v1「实盘交易」页的只读镜像，**非 实盘交易实现**。
 *
 * ⚠️ 红线：V2 此处只做只读聚合（后端读本地模拟账本 data/paper_<user>.json），
 * 不暴露任何写接口；实时下单 / 真实券商（QMT / 同花顺）写能力仅在 v1 实盘交易页
 * /api/trade/* 提供（本页不接、不渲染下单表单）。真实交易能力永久留在 v1，符合
 * 「实盘交易不放在 v2」的红线。
 *
 * 三块：账户(account) / 持仓(positions) / 订单流水(orders)。缺账本 → 诚实空态，不编造。
 * 金额单位「元」（本地账本原始值），前端以 ¥ 千分位展示；缺值显示「—」，绝不补 0。
 *
 * A 股语义：买入=红(CHART.up)、卖出=绿(CHART.down)，与红涨绿跌一致。
 */
function yuan(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v)
    ? `¥${v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
    : '—'
}
function num(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v)
    ? v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
    : '—'
}
function sideColor(side: unknown): string | undefined {
  if (side === '买') return CHART.up
  if (side === '卖') return CHART.down
  return undefined
}

export function TradingAccount() {
  const q = useTradingAccount()
  const d = q.data

  const acc = d?.account
  const positions = d?.positions ?? []
  const orders = d?.orders ?? []
  const isEmpty =
    !!d &&
    acc?.available !== true &&
    positions.length === 0 &&
    orders.length === 0

  return (
    <div className="trade">
      <h2 className="text-lg font-semibold">交易账户（只读概览）</h2>
      <div className="text-xs text-sf-ink-3">
        V2 此处仅只读聚合本地模拟账本（账户 / 持仓 / 订单流水），<span className="text-sf-ink">不提供实时下单</span>；
        真实券商（QMT / 同花顺）下单能力在 v1 实盘交易页。数据仅供参考，非投资建议。
      </div>

      <QueryState
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        isEmpty={isEmpty}
        emptyLabel="暂无本地模拟账本"
        emptyHint="未找到 data/paper_<user>.json（无模拟交易记录）；V2 只读概览不创建账本"
      >
        {d ? (
          <div className="space-y-6">
            <AccountBlock acc={acc} />
            <PositionBlock rows={positions} />
            <OrderBlock rows={orders} />
            {d.note && (
              <div className="text-xs text-sf-ink-3 border-l-2 border-sf-line pl-3">
                {d.note}
              </div>
            )}
          </div>
        ) : null}
      </QueryState>
    </div>
  )
}

function AccountBlock({ acc }: { acc?: TradingAccountData['account'] }) {
  if (!acc) return null
  return (
    <Card title="账户概览">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="券商通道" value={acc.broker_type === 'sim' ? '模拟账本' : (acc.broker_type ?? '—')} />
        <Stat label="当前模式" value={acc.mode ?? '—'} />
        <Stat label="可用资金" value={yuan(acc.cash)} />
        <Stat label="持仓成本合计" value={yuan(acc.position_cost)} />
        <Stat label="总资产" value={yuan(acc.total_assets)} />
      </div>
    </Card>
  )
}

function PositionBlock({ rows }: { rows: TradingAccountPosition[] }) {
  if (rows.length === 0) {
    return (
      <Card title="当前持仓">
        <div className="text-xs text-sf-ink-3">暂无持仓（本地模拟账本无持仓记录）。</div>
      </Card>
    )
  }
  return (
    <Card title={`当前持仓（${rows.length}）`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">代码</th>
              <th className="text-left py-1.5 pr-3">名称</th>
              <th className="text-right py-1.5 pr-3">持股数</th>
              <th className="text-right py-1.5 pr-3">成本价</th>
              <th className="text-right py-1.5">持仓成本</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.code}-${i}`} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{r.code ?? '—'}</td>
                <td className="py-1.5 pr-3">{r.name ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right">{num(r.qty)}</td>
                <td className="py-1.5 pr-3 text-right">{yuan(r.avg_cost)}</td>
                <td className="py-1.5 text-right">{yuan(r.cost_basis)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-xs text-sf-ink-3">
        持仓成本 = 持股数 × 成本价（本地模拟账本无实时价，故不展示实时市值 / 浮动盈亏）。
      </div>
    </Card>
  )
}

function OrderBlock({ rows }: { rows: TradingAccountOrder[] }) {
  if (rows.length === 0) {
    return (
      <Card title="订单流水">
        <div className="text-xs text-sf-ink-3">暂无订单（本地模拟账本无交易记录）。</div>
      </Card>
    )
  }
  return (
    <Card title={`订单流水（${rows.length}）`}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-sf-ink">
          <thead>
            <tr className="text-sf-ink-3 border-b border-sf-line">
              <th className="text-left py-1.5 pr-3">时间</th>
              <th className="text-left py-1.5 pr-3">代码</th>
              <th className="text-left py-1.5 pr-3">名称</th>
              <th className="text-left py-1.5 pr-3">方向</th>
              <th className="text-right py-1.5 pr-3">价格</th>
              <th className="text-right py-1.5 pr-3">数量</th>
              <th className="text-right py-1.5">金额</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o, i) => (
              <tr key={`${o.time}-${o.code}-${i}`} className="border-b border-sf-line/60">
                <td className="py-1.5 pr-3">{o.time ?? '—'}</td>
                <td className="py-1.5 pr-3">{o.code ?? '—'}</td>
                <td className="py-1.5 pr-3">{o.name ?? '—'}</td>
                <td className="py-1.5 pr-3" style={{ color: sideColor(o.side) }}>
                  {o.side === '买' ? '买入 ▲' : o.side === '卖' ? '卖出 ▼' : (o.side ?? '—')}
                </td>
                <td className="py-1.5 pr-3 text-right">{yuan(o.price)}</td>
                <td className="py-1.5 pr-3 text-right">{num(o.qty)}</td>
                <td className="py-1.5 text-right">{yuan(o.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
