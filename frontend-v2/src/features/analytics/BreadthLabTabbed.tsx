import { useState } from 'react'
import { SentimentClock } from '@/features/analytics/SentimentClock'
import { RegimeDuration } from '@/features/analytics/RegimeDuration'
import { SimilarDays } from '@/features/analytics/SimilarDays'
import { InflectionScan } from '@/features/analytics/InflectionScan'
import { MomentumResonance } from '@/features/breadth/MomentumResonance'
import { PageTabs } from '@/shared/ui/PageTabs'

/** /sentiment-clock 页面五 tab：广度情绪衍生视图聚合。
 *
 *  2026-11-23 合并取证：情绪时钟/温度持续期/历史相似日/拐点扫描四页均走
 *  useBreadthAnalytics → 同一 /breadth-analytics 端点（仅取不同段），动量共振
 *  走同族 useMomentumBreadth；五页均属「广度·温度与情绪」语义簇，合并为
 *  一个页面的 5 个 tab，旧四个路径 redirect（深链兼容），视图零丢失。 */
const TAB_KEY = 'ss_breadth_lab_tab'

const TABS = [
  { key: 'clock', label: '情绪时钟' },
  { key: 'duration', label: '温度持续期' },
  { key: 'similar', label: '历史相似日' },
  { key: 'inflection', label: '拐点扫描' },
  { key: 'momentum', label: '动量共振' },
] as const

const VIEWS: Record<string, () => React.JSX.Element> = {
  clock: SentimentClock,
  duration: RegimeDuration,
  similar: SimilarDays,
  inflection: InflectionScan,
  momentum: MomentumResonance,
}

export function BreadthLabTabbed() {
  const [tab, setTab] = useState<string>(() => {
    try {
      const v = sessionStorage.getItem(TAB_KEY)
      return v && v in VIEWS ? v : 'clock'
    } catch {
      // ui_audit_exempt: 已知静默降级 — sessionStorage 不可用时回默认 tab
      return 'clock'
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

  const View = VIEWS[tab] ?? SentimentClock
  return (
    <div>
      <PageTabs tabs={TABS} active={tab} onChange={pick} ariaLabel="广度情绪视图切换" wide />
      <View />
    </div>
  )
}
