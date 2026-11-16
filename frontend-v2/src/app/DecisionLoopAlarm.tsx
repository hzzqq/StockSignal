import { useDecisionLoopHealth } from '@/lib/queries'

/**
 * 决策闭环停摆告警（v1 54 页横幅的 v2 生产前端等价能力）。
 *
 * 挂在 AppShell <main> 顶部，Zen 专注模式折叠顶栏/侧栏时依然可见。
 * 真值源是后端 modules.decision.assess_decision_loop_health()：
 *  - ok 不渲染（不打扰正常浏览）；
 *  - warn/stale 橙、dead/unknown 红；
 *  - 取数失败/无数据显示「不可得」，绝不假装正常。
 * 缺失的时间/滞后如实显示「时间不可得」/「—」，不补 0、不编造。
 */
export function DecisionLoopAlarm() {
  const q = useDecisionLoopHealth()
  const h = q.data

  // 首次加载且无既有数据：不闪横幅；已有数据时继续显示旧状态（不伪装正常）。
  if (q.isLoading && !h) return null

  const tone = (danger: boolean) =>
    danger
      ? 'border-sf-danger bg-sf-danger-soft text-sf-danger'
      : 'border-sf-warn bg-sf-warn-soft text-sf-warn'

  const retry = (
    <button
      type="button"
      onClick={() => void q.refetch()}
      className="shrink-0 rounded-tile border border-current px-2 py-1 text-label hover:opacity-80"
    >
      重新检测
    </button>
  )

  if (q.isError || !h) {
    const why = q.error instanceof Error ? q.error.message : '接口未返回健康状态'
    return (
      <div role="alert" className={`mb-3 flex flex-wrap items-center gap-2 rounded-tile border px-3 py-2 text-body ${tone(true)}`}>
        <strong className="font-semibold">决策闭环健康状态不可得</strong>
        <span className="text-label">{why}</span>
        <span className="ml-auto">{retry}</span>
      </div>
    )
  }

  if (h.status === 'ok') return null

  const danger = h.status === 'dead' || h.status === 'unknown'
  return (
    <div role="alert" className={`mb-3 flex flex-wrap items-center gap-2 rounded-tile border px-3 py-2 text-body ${tone(danger)}`}>
      <strong className="font-semibold">{danger ? '⛔ 决策闭环告警' : '⚠️ 决策闭环提示'}</strong>
      <span>{h.message}</span>
      <span className="text-label">
        最后生成：{h.generated_at ?? '时间不可得'} · 滞后：{h.gen_lag_hours ?? '—'} 小时
      </span>
      <span className="ml-auto">{retry}</span>
    </div>
  )
}
