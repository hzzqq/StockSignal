import { getCurrentUser } from '@/lib/auth'
import { useUserDashboard } from '@/lib/queries'
import { Card } from '@/shared/ui/Card'
import { Loading, ErrorState } from '@/shared/ui/States'

const WIDGET_LABELS: Record<string, string> = {
  snapshot: '今日决策快照',
  recommendation: '每日荐股',
  breadth: '广度温度',
  event: '事件因子池',
  backtest: '回测运行记录',
}

/**
 * 91 我的（v2 native /me）：展示登录身份 + 自定义看板偏好种子。
 * 复用 /user-dashboard（data/user_dashboard.json，73 页自定义看板的默认组件种子）。
 * 诚实红线：看板偏好缺失即如实显默认组件列表或「暂无」；身份缺失显「请重新登录」，不编造角色。
 */
export function Me() {
  const user = getCurrentUser()
  const dashQ = useUserDashboard()

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">我的</h2>
      <p className="text-xs text-sf-ink-3">登录身份与自定义看板偏好（只读视图，无写能力）。</p>

      <Card title="账户">
        {user ? (
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-sf-ink-2">用户名</span>
              <span className="text-sf-ink">{user.username}</span>
              <span
                className={`rounded px-1.5 py-0.5 text-xs ${
                  user.role === 'admin' ? 'bg-sf-accent text-white' : 'bg-sf-surface-2 text-sf-ink-2'
                }`}
              >
                {user.role === 'admin' ? '管理员' : '普通用户'}
              </span>
            </div>
            <div className="text-sf-ink-3 text-xs">
              账号 ID：{user.id} · 创建于 {user.created_at ?? '—'}
            </div>
          </div>
        ) : (
          <p className="text-xs text-sf-ink-3">未读取到登录信息（请重新登录）。</p>
        )}
      </Card>

      <Card title="自定义看板偏好">
        {dashQ.isLoading && <Loading label="加载看板偏好…" />}
        {dashQ.isError && (
          <ErrorState message={dashQ.error instanceof Error ? dashQ.error.message : '看板偏好加载失败'} />
        )}
        {dashQ.data && (
          <div className="space-y-2 text-sm">
            <div className="text-sf-ink-2">默认组件：</div>
            <div className="flex flex-wrap gap-2">
              {dashQ.data.default_widgets.length === 0 && (
                <span className="text-xs text-sf-ink-3">暂无默认组件</span>
              )}
              {dashQ.data.default_widgets.map((w) => (
                <span key={w} className="rounded bg-sf-surface-2 px-2 py-1 text-xs text-sf-ink">
                  {WIDGET_LABELS[w] ?? w}
                </span>
              ))}
            </div>
            {dashQ.data.note && <p className="text-xs text-sf-ink-3">{dashQ.data.note}</p>}
            {dashQ.data.updated_at && (
              <p className="text-xs text-sf-ink-3">更新于 {dashQ.data.updated_at}</p>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
