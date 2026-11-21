import { useCallback, useEffect, useState } from 'react'
import { Outlet, Link, useNavigate, useRouterState } from '@tanstack/react-router'
import { applyPreferences, getZen, setZen } from '@/lib/preferences'
import { clearAuth } from '@/app/guards'
import { NAV } from '@/nav/nav'
import { MockBanner } from '@/mocks/MockBanner'
import { ThemeToggle } from '@/shared/ui/ThemeToggle'
import { StockSearchInput } from '@/shared/ui/StockSearchInput'
import { FeatureSearch } from '@/shared/ui/FeatureSearch'
import { ZenToggle } from '@/shared/ui/ZenToggle'
import { DecisionLoopAlarm } from './DecisionLoopAlarm'
import { PageErrorBoundary } from './PageErrorBoundary'
import { GlobalKLineOverlay } from '@/features/stock/charts/GlobalKLineOverlay'
import { openKLine } from '@/features/stock/charts/klineOverlayStore'
import { useXingchenRunning } from '@/features/xingchen/useXingchen'

/** 星辰 AI 入口：从 NAV 单一真理源派生，避免在此硬编码路由。 */
const XINGCHEN_PATH = NAV.flatMap((g) => g.items).find((it) => it.label === '星辰 AI 助手')?.to

/** 顶栏股票搜索：复用既有 StockSearchInput；命中后走全局 K 线浮层，不新增路由、不改地址栏。 */
function GlobalStockSearch() {
  const [code, setCode] = useState('')
  return (
    <div className="hidden w-40 md:block lg:w-48" aria-label="股票搜索">
      <StockSearchInput
        value={code}
        label=""
        placeholder="搜索股票…"
        onSelect={(next, item) => {
          setCode(next)
          openKLine(next, item?.name)
        }}
      />
    </div>
  )
}

/** 星辰 AI 运行中徽标：只读订阅 running 布尔值，点击回到星辰页；未运行不占位。 */
function XingchenRunningBadge() {
  const running = useXingchenRunning()
  const navigate = useNavigate()
  if (!running || !XINGCHEN_PATH) return null
  return (
    <button
      type="button"
      onClick={() => navigate({ to: XINGCHEN_PATH })}
      aria-label="星辰 AI 正在运行，点击查看"
      className="shrink-0 rounded-tile border border-sf-accent px-2 py-1 text-label text-sf-accent hover:bg-sf-surface-2"
    >
      <span className="md:hidden" aria-hidden="true">🌟</span>
      <span className="hidden md:inline">星辰 AI 正在运行</span>
    </button>
  )
}

/**
 * 轻量卡片流 · 鉴权后应用外壳（DESIGN.md §3）。
 *  - 导航激活态由 TanStack Router 自动写入 aria-current="page"，
 *    交给 tokens.css 的 `.nav-link[aria-current]` 画左侧细指示条（inset shadow，不占布局）；
 *  - 文字层级收敛到 L1/L2/L3 实色令牌，hover 用实色 surface-2 而非半透明叠色；
 *  - 窄屏（<768px）侧栏收为图标栏，标签由 CSS 隐藏，避免挤压内容区（DESIGN.md §4）。
 */
export function AppShell() {
  const navigate = useNavigate()
  // 订阅真实路由：从 A 组跳到 B 组页面时，侧栏自动展开 B 组（不会停在旧组）。
  const pathname = useRouterState({ select: (st) => st.location.pathname })
  const activeGroup = NAV.find((g) => g.items.some((it) => it.to === pathname))?.group ?? ''
  const [allOpen, setAllOpen] = useState(false)
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})
  const isOpen = (group: string): boolean => {
    if (allOpen) return true
    const own = overrides[group]
    return own === undefined ? group === activeGroup : own
  }
  useEffect(() => applyPreferences(), [])

  // 专注 / Zen 模式：状态由 localStorage 单一真理源驱动，写入 html[data-zen]。
  const [zen, setZenState] = useState<boolean>(() => getZen())
  const toggleZen = useCallback(() => {
    const next = !zen
    setZenState(next)
    setZen(next)
  }, [zen])

  // 快捷键 Z 进入/退出专注（输入框/可编辑区/带修饰键时屏蔽，避免劫持打字）。
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'z' && e.key !== 'Z') return
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      const t = e.target as HTMLElement | null
      if (
        t &&
        (t.tagName === 'INPUT' ||
          t.tagName === 'TEXTAREA' ||
          t.tagName === 'SELECT' ||
          t.isContentEditable)
      )
        return
      e.preventDefault()
      toggleZen()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleZen])

  function onLogout() {
    clearAuth()
    navigate({ to: '/login', search: { from: '/' } })
  }

  return (
    <div className="h-screen flex bg-sf-bg text-sf-ink">
      <aside className="app-sidebar w-14 md:w-56 shrink-0 flex flex-col border-r border-sf-line p-3 space-y-4 overflow-y-auto">
        <div className="px-2 py-2 text-title font-semibold text-sf-ink whitespace-nowrap">
          <span className="md:hidden">S2</span>
          <span className="nav-label hidden md:inline">StockSignal V2</span>
        </div>
        <div className="flex items-center justify-between gap-2 px-2">
          <span className="nav-label hidden md:inline text-label text-sf-ink-3">
            {NAV.length} 类 · {NAV.reduce((n, g) => n + g.items.length, 0)} 个功能
          </span>
          <button
            type="button"
            onClick={() => setAllOpen((v) => !v)}
            aria-expanded={allOpen}
            className="shrink-0 rounded-tile border border-sf-line px-2 py-0.5 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent"
          >
            <span className="nav-label hidden md:inline">{allOpen ? '折叠全部' : '展开全部'}</span>
            <span className="md:hidden" aria-hidden="true">{allOpen ? '−' : '+'}</span>
          </button>
        </div>
        <nav className="space-y-2">
          {NAV.map((g, gi) => {
            const open = isOpen(g.group)
            const listId = `nav-group-${gi}`
            return (
              <div key={g.group}>
                <button
                  type="button"
                  onClick={() => setOverrides((o) => ({ ...o, [g.group]: !open }))}
                  aria-expanded={open}
                  aria-controls={listId}
                  className="flex w-full items-center gap-1.5 rounded-tile px-2 py-1 text-left text-label text-sf-ink-3 hover:bg-sf-surface-2 hover:text-sf-ink"
                >
                  <span aria-hidden="true" className="w-3 shrink-0 text-center">{open ? '▾' : '▸'}</span>
                  <span className="nav-label hidden md:inline uppercase tracking-wide">{g.group}</span>
                  <span className="nav-label hidden md:inline ml-auto tabular-nums">{g.items.length}</span>
                  <span className="md:hidden" aria-hidden="true">•••</span>
                </button>
                {/* 收起时 md:hidden：窄屏(<768px)图标栏始终可见，避免折叠后整条侧栏无法导航。
                    jsdom 不加载 Tailwind，DOM 内链接始终存在，a11y 守卫不受影响。 */}
                <div id={listId} className={open ? 'mt-1 space-y-0.5' : 'mt-1 space-y-0.5 md:hidden'}>
                  {g.items.map((it) => (
                    <Link
                      key={it.to}
                      to={it.to}
                      title={it.label}
                      aria-label={it.label}
                      className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
                    >
                      <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">{it.icon}</span>
                      <span className="nav-label hidden md:inline whitespace-nowrap">{it.label}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )
          })}
        </nav>

        {/* 底部只留说明，不再手抄 20 条平铺入口：路径唯一真理源是 nav.ts 的 NAV。 */}
        <div className="mt-auto border-t border-sf-line pt-3">
          <p className="nav-label hidden md:block text-label text-sf-ink-3">
            点击分组名可折叠 / 展开
          </p>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <header className="app-header h-12 shrink-0 border-b border-sf-line flex items-center justify-between px-4 md:px-6">
          <span className="text-label text-sf-ink-3">决策中枢 · 只读视图</span>
          <div className="flex items-center gap-3">
            <FeatureSearch />
            <GlobalStockSearch />
            <XingchenRunningBadge />
            <ThemeToggle />
            <button
              onClick={onLogout}
              className="text-label text-sf-ink-2 hover:text-sf-ink transition-colors"
            >
              退出登录
            </button>
          </div>
        </header>
        <main className="app-main flex-1 min-h-0 overflow-auto p-4 md:p-6">
          <MockBanner />
          {/* 决策闭环停摆告警：安全信息，Zen 折叠顶栏/侧栏时仍随 <main> 可见 */}
          <DecisionLoopAlarm />
          {/* 任一懒加载页面抛错时显示可解释错误卡，而不是整页空白（2026-11-16 星辰 AI 反馈） */}
          <PageErrorBoundary>
            <Outlet />
          </PageErrorBoundary>
        </main>
      </div>

      {/* 全局 K 线浮层：挂在 PageErrorBoundary 之外，任意页面一行 openKLine() 即可弹出。 */}
      <GlobalKLineOverlay />

      {/* 专注模式浮动开关：常驻右下角，Zen 下仍可退出，且提供主题切换（顶栏隐藏时唯一入口）。 */}
      <div className="zen-fab">
        {zen && <ThemeToggle />}
        <ZenToggle zen={zen} onToggle={toggleZen} />
      </div>
    </div>
  )
}
