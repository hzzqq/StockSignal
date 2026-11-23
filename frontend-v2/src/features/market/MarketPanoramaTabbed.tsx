import { useState } from 'react'
import { MarketPanorama } from './MarketPanorama'
import { MarketRegime } from './MarketRegime'
import { PageTabs } from '@/shared/ui/PageTabs'

/** /panorama 页面双 tab：市场全景 + 市场状态机。
 *
 *  2026-11-23 合并取证：两页均走 useMarketPanorama → 同一后端
 *  /market-panorama（modules.market_regime），同 k 参数、同状态分布图、
 *  同历史相似日卡——仅独有「红盘率趋势/广度快照」与「转移热力图/置信度」，
 *  合并为 tab 不丢任何视图，旧 /regime 路径 redirect。 */
const TAB_KEY = 'ss_panorama_tab'

const TABS = [
  { key: 'panorama', label: '市场全景' },
  { key: 'regime', label: '市场状态机' },
] as const

export function MarketPanoramaTabbed() {
  const [tab, setTab] = useState<string>(() => {
    try {
      return sessionStorage.getItem(TAB_KEY) === 'regime' ? 'regime' : 'panorama'
    } catch {
      // ui_audit_exempt: 已知静默降级 — sessionStorage 不可用时回默认 tab
      return 'panorama'
    }
  })

  const pick = (k: string) => {
    setTab(k)
    try {
      sessionStorage.setItem(TAB_KEY, k)
    } catch {
      // ui_audit_exempt: 已知静默降级 — 存储失败仅失去会话记忆
    }
  }

  return (
    <div>
      <PageTabs tabs={TABS} active={tab} onChange={pick} ariaLabel="市场视图切换" />
      {tab === 'regime' ? <MarketRegime /> : <MarketPanorama />}
    </div>
  )
}
