import { useState } from 'react'
import { MarketSentiment } from './MarketSentiment'
import { MarketDrivers } from './MarketDrivers'
import { PageTabs } from '@/shared/ui/PageTabs'

/** /market-sentiment 页面双 tab：情绪温度计（主）+ 市场驱动力五维。
 *
 *  2026-11-22 侧栏减臃肿：原独立页 /market-drivers 并入本页 tab（两者本就
 *  复用同一端点 /api/v2/read/market-sentiment 的 21 指标数据），旧路径
 *  redirect 到 /market-sentiment；tab 选择会话内记忆（sessionStorage）。 */
const TAB_KEY = 'ss_market_tab'

const TABS = [
  { key: 'sentiment', label: '情绪温度计' },
  { key: 'drivers', label: '市场驱动力' },
] as const

export function MarketSentimentTabbed() {
  const [tab, setTab] = useState<string>(() => {
    try {
      const v = sessionStorage.getItem(TAB_KEY)
      return v === 'drivers' ? 'drivers' : 'sentiment'
    } catch {
      // ui_audit_exempt: 已知静默降级 — sessionStorage 不可用时回默认 tab，不影响功能
      return 'sentiment'
    }
  })

  const pick = (k: string) => {
    setTab(k)
    try {
      sessionStorage.setItem(TAB_KEY, k)
    } catch {
      // ui_audit_exempt: 已知静默降级 — 存储失败仅失去会话记忆，切换仍生效
    }
  }

  return (
    <div>
      <PageTabs tabs={TABS} active={tab} onChange={pick} ariaLabel="市场情绪视图切换" />
      {tab === 'drivers' ? <MarketDrivers /> : <MarketSentiment />}
    </div>
  )
}
