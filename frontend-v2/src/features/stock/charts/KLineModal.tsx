import { useEffect } from 'react'
import { useStockKline, useIndexKline } from '@/lib/queries'
import { KLineChart } from './KLineChart'
import { QueryState } from '@/shared/ui/States'
import type { PriceDomain } from './common'

/**
 * 可复用 K 线弹窗（FinPilot MarketSyncPage 的「点击卡片 → 弹 K 线详情」形态）。
 *
 * 设计（无 antd，自建轻量弹窗）：
 *  - open + 选中 code/name 即弹出，close 即回收；可被任意页面随时调用（首页指数卡片、个股页等）。
 *  - 按 code 形态自动选数据源：6 位纯数字 → getStockKline（个股）；sh/sz+6 位 → getIndexKline（指数）。
 *    两个 hook 始终调用（enabled 自行拦截非法 code），不破坏 hooks 顺序。
 *  - 渐变主图 + 成交量/MACD 副图由 KLineChart 统一绘制；涨跌色按 priceDomain 注入。
 *  - 关闭：右上角按钮 / 点遮罩 / Esc；role=dialog + aria-modal 保证读屏可达。
 *
 * 诚实红线：取数失败 → error 态；rows 空 → 空态（KLineChart 内部 EmptyState）；note 原文展示。
 */
export interface KLineModalProps {
  open: boolean
  onClose: () => void
  /** 选中标的代码（6 位个股 / sh|sz+6 位指数）；null 时不渲染。 */
  code: string | null
  /** 标的名称（卡片名 / 个股名），用于弹窗标题。 */
  name?: string
  /** 价格域：market=交易屏红涨绿跌；report=报告体绿涨红跌。 */
  priceDomain: PriceDomain
}

export function KLineModal({ open, onClose, code, name, priceDomain }: KLineModalProps) {
  const stockQ = useStockKline(code ?? '')
  const indexQ = useIndexKline(code ?? '')
  const isIndex = !!code && /^(sh|sz)\d{6}$/.test(code)
  const q = isIndex ? indexQ : stockQ
  const rows = (q.data?.rows ?? []) as Record<string, unknown>[]

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !code) return null

  const title = name ?? code

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(8,8,18,0.6)' }}
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${title} K 线详情`}
        className="w-full max-w-[960px] max-h-[90vh] overflow-auto rounded-card border border-sf-line bg-sf-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-title font-semibold text-sf-ink">
            {title}
            <span className="text-label text-sf-ink-3 font-normal"> · K 线详情</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭 K 线弹窗"
            className="rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-ink"
          >
            ✕ 关闭
          </button>
        </div>

        <QueryState
          isLoading={q.isLoading}
          isError={q.isError}
          error={q.error}
          isEmpty={!q.isLoading && !q.isError && rows.length === 0}
          emptyLabel="暂无 K 线数据"
          emptyHint="该标的取数失败或暂无日线"
        >
          <KLineChart rows={rows} priceDomain={priceDomain} height={460} />
        </QueryState>

        {q.data && q.data.note !== null && (
          <p className="text-body text-sf-ink-2 mt-3">{q.data.note}</p>
        )}
      </div>
    </div>
  )
}
