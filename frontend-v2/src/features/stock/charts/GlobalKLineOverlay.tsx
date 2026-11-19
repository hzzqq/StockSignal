import { KLineModal } from './KLineModal'
import { useKLineOverlayStore } from './klineOverlayStore'

/**
 * 全局 K 线浮层 · 薄桥接层（零额外逻辑）。
 *
 * 把全局 store 的状态直接转发给既有 KLineModal；不复制弹窗内部任何逻辑，
 * 也不硬编码涨跌颜色（交给 KLineModal / KLineChart 按 priceDomain 处理）。
 * 挂载点在 AppShell 根、PageErrorBoundary 之外，故任意页面调用 openKLine 都能弹出。
 */
export function GlobalKLineOverlay() {
  const open = useKLineOverlayStore((s) => s.open)
  const code = useKLineOverlayStore((s) => s.code)
  const name = useKLineOverlayStore((s) => s.name)
  const priceDomain = useKLineOverlayStore((s) => s.priceDomain)
  const closeKLine = useKLineOverlayStore((s) => s.closeKLine)

  return (
    <KLineModal
      open={open}
      onClose={closeKLine}
      code={code}
      name={name}
      priceDomain={priceDomain}
    />
  )
}
