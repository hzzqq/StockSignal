import { useCallback, useEffect, useState } from 'react'
import { Outlet, Link, useNavigate } from '@tanstack/react-router'
import { applyPreferences, getZen, setZen } from '@/lib/preferences'
import { clearAuth } from '@/app/guards'
import { NAV } from '@/nav/nav'
import { MockBanner } from '@/mocks/MockBanner'
import { ThemeToggle } from '@/shared/ui/ThemeToggle'
import { ZenToggle } from '@/shared/ui/ZenToggle'

/**
 * 轻量卡片流 · 鉴权后应用外壳（DESIGN.md §3）。
 *  - 导航激活态由 TanStack Router 自动写入 aria-current="page"，
 *    交给 tokens.css 的 `.nav-link[aria-current]` 画左侧细指示条（inset shadow，不占布局）；
 *  - 文字层级收敛到 L1/L2/L3 实色令牌，hover 用实色 surface-2 而非半透明叠色；
 *  - 窄屏（<768px）侧栏收为图标栏，标签由 CSS 隐藏，避免挤压内容区（DESIGN.md §4）。
 */
export function AppShell() {
  const navigate = useNavigate()
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
    <div className="min-h-screen flex bg-sf-bg text-sf-ink">
      <aside className="app-sidebar w-14 md:w-56 shrink-0 flex flex-col border-r border-sf-line p-3 space-y-4 overflow-y-auto">
        <div className="px-2 py-2 text-title font-semibold text-sf-ink whitespace-nowrap">
          <span className="md:hidden">S2</span>
          <span className="nav-label hidden md:inline">StockSignal V2</span>
        </div>
        <nav className="space-y-4">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-label px-2 text-label text-sf-ink-3 uppercase tracking-wide hidden md:block">
                {g.group}
              </div>
              <div className="mt-1 space-y-0.5">
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
          ))}
        </nav>

        {/* 底部固定入口：不进 NAV 数组，避免影响导航分组/图标唯一守卫 */}
        <div className="mt-auto border-t border-sf-line pt-3 space-y-0.5">
          <Link
            to="/catalog"
            title="v1 功能全景"
            aria-label="v1 功能全景"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">▣</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">v1 功能全景</span>
          </Link>
          <Link
            to="/matrix"
            title="维度领先滞后矩阵"
            aria-label="维度领先滞后矩阵"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">⊹</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">领先滞后矩阵</span>
          </Link>
          <Link
            to="/guide"
            title="新手教程"
            aria-label="新手教程"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">◇</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">新手教程</span>
          </Link>
          <Link
            to="/settings"
            title="设置"
            aria-label="设置"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">⚒</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">设置</span>
          </Link>
          <Link
            to="/users"
            title="用户管理"
            aria-label="用户管理"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">👥</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">用户管理</span>
          </Link>
          <Link
            to="/financial-hunter"
            title="财报猎手"
            aria-label="财报猎手"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">📒</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">财报猎手</span>
          </Link>
          <Link
            to="/dashboard-custom"
            title="自定义看板"
            aria-label="自定义看板"
            className="nav-link flex items-center gap-2 px-2 py-1.5 rounded-tile text-body text-sf-ink-2 hover:bg-sf-surface-2 hover:text-sf-ink transition-colors"
          >
            <span aria-hidden="true" className="w-5 text-center text-sf-ink-3">🧩</span>
            <span className="nav-label hidden md:inline whitespace-nowrap">自定义看板</span>
          </Link>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="app-header h-12 shrink-0 border-b border-sf-line flex items-center justify-between px-4 md:px-6">
          <span className="text-label text-sf-ink-3">决策中枢 · 只读视图</span>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <button
              onClick={onLogout}
              className="text-label text-sf-ink-2 hover:text-sf-ink transition-colors"
            >
              退出登录
            </button>
          </div>
        </header>
        <main className="app-main flex-1 overflow-auto p-4 md:p-6">
          <MockBanner />
          <Outlet />
        </main>
      </div>

      {/* 专注模式浮动开关：常驻右下角，Zen 下仍可退出，且提供主题切换（顶栏隐藏时唯一入口）。 */}
      <div className="zen-fab">
        {zen && <ThemeToggle />}
        <ZenToggle zen={zen} onToggle={toggleZen} />
      </div>
    </div>
  )
}
