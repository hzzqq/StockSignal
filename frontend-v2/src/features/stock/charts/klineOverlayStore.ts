import { create } from 'zustand'
import type { PriceDomain } from './common'

/**
 * 全局 K 线浮层状态 · 全站单一真理源。
 *
 * 目的：把 KLineModal 从「IndexQuotes 专属」升级为「任意页面一行调用」的能力。
 * 任意页面 `import { openKLine } from '.../klineOverlayStore'` 后调用
 * `openKLine(code, name?, priceDomain?)` 即可弹出；AppShell 挂载的
 * GlobalKLineOverlay 订阅本 store 并转发给 KLineModal。
 *
 * 诚实红线：code 为空时不打开（无标的不弹窗）；不造假的 code/name；
 * 颜色语义默认 'market'（交易屏红涨绿跌），不在此处硬编码红绿。
 */
export interface KLineOverlayState {
  open: boolean
  code: string | null
  name?: string
  priceDomain: PriceDomain
  /** 打开浮层；空 code 为 no-op。 */
  openKLine: (code: string, name?: string, priceDomain?: PriceDomain) => void
  /** 关闭浮层并回填安全值（不残留上一次的标的）。 */
  closeKLine: () => void
}

export const useKLineOverlayStore = create<KLineOverlayState>((set) => ({
  open: false,
  code: null,
  name: undefined,
  priceDomain: 'market',
  openKLine: (code, name, priceDomain = 'market') => {
    if (!code) return
    set({ open: true, code, name, priceDomain })
  },
  closeKLine: () => set({ open: false, code: null, name: undefined, priceDomain: 'market' }),
}))

/** 顶层便捷函数：任意页面无需碰 store Hook，一行调用即可打开 K 线弹窗。 */
export const openKLine = (code: string, name?: string, priceDomain?: PriceDomain): void => {
  useKLineOverlayStore.getState().openKLine(code, name, priceDomain)
}
