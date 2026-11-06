import { Outlet, Link, useNavigate } from '@tanstack/react-router'
import { clearAuth } from '@/app/guards'
import { NAV } from '@/nav/nav'
import { MockBanner } from '@/mocks/MockBanner'

/** 鉴权后的应用外壳：左侧分组导航 + 顶栏 + 内容区（Outlet）。 */
export function AppShell() {
  const navigate = useNavigate()

  function onLogout() {
    clearAuth()
    navigate({ to: '/login', search: { from: '/' } })
  }

  return (
    <div className="min-h-screen flex bg-sf-bg text-sf-txt">
      <aside className="w-56 shrink-0 border-r border-sf-border p-3 space-y-4">
        <div className="px-2 py-2 text-base font-semibold">StockSignal V2</div>
        <nav className="space-y-4">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="px-2 text-xs text-sf-txt/40 uppercase tracking-wide">
                {g.group}
              </div>
              <div className="mt-1 space-y-0.5">
                {g.items.map((it) => (
                  <Link
                    key={it.to}
                    to={it.to}
                    className="flex items-center gap-2 px-2 py-1.5 rounded text-sm text-sf-txt/75 hover:bg-sf-bg/60"
                    activeProps={{ className: 'bg-sf-bg/70 text-sf-txt font-medium' }}
                  >
                    <span className="text-sf-txt/40">{it.icon}</span>
                    {it.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-12 border-b border-sf-border flex items-center justify-between px-4">
          <span className="text-sm text-sf-txt/60">决策中枢 · 只读视图</span>
          <button
            onClick={onLogout}
            className="text-sm text-sf-txt/60 hover:text-ss-down"
          >
            退出登录
          </button>
        </header>
        <main className="flex-1 overflow-auto p-4">
          <MockBanner />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
