import { useState } from 'react'
import { P1Signals } from './P1Signals'
import { ConstructionDiagnostics } from './ConstructionDiagnostics'
import { PageTabs } from '@/shared/ui/PageTabs'

/** /p1 页面双 tab：量化信号（主）+ 组合构建诊断。
 *
 *  2026-11-22 侧栏减臃肿：原独立页 /p1-construction 并入本页 tab，
 *  旧路径 redirect 到 /p1；tab 选择在会话内记忆（sessionStorage），
 *  刷新/回跳不丢视图。 */
const TAB_KEY = 'ss_p1_tab'

const TABS = [
  { key: 'signals', label: '量化信号' },
  { key: 'construction', label: '组合构建诊断' },
] as const

export function P1Tabbed() {
  const [tab, setTab] = useState<string>(() => {
    try {
      const v = sessionStorage.getItem(TAB_KEY)
      return v === 'construction' ? 'construction' : 'signals'
    } catch {
      // ui_audit_exempt: 已知静默降级 — sessionStorage 不可用时回默认 tab，不影响功能
      return 'signals'
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
      <PageTabs tabs={TABS} active={tab} onChange={pick} ariaLabel="P1 视图切换" />
      {tab === 'construction' ? <ConstructionDiagnostics /> : <P1Signals />}
    </div>
  )
}
