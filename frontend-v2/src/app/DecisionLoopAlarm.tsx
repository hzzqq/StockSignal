import { useDecisionLoopHealth } from '@/lib/queries'
import { ApiError } from '@/api/client'

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
    const raw = q.error instanceof Error ? q.error.message : '接口未返回健康状态'
    const code = q.error instanceof ApiError ? q.error.code : ''
    // 真实部署曾显示「资源不存在」：旧后端进程没有 /decision-loop-health 端点。
    // 这是版本 / 部署问题，不是调度停摆；必须区分，否则运维会误判决策闭环已死。
    const endpointMissing = code === 'not_found' || /\b404\b/.test(raw)
    // 502/503/504 = 网关拿不到后端（Flask 未启动/已退出），与「端点不存在」是两回事：
    // 前者拉起服务即可恢复，后者是版本问题。误判会让老板去查错方向。
    const gatewayDown = /\b(502|503|504)\b/.test(raw)
    const why = endpointMissing
      ? '后端未提供该端点（服务可能未重启 / 版本过旧）；请在「数据源与接口检测」确认'
      : gatewayDown
        ? '后端服务未启动或已退出（网关 5xx）；请用 start_frontend_v2.bat 拉起 5050 后点「重新检测」'
        : raw
    return (
      <div role="alert" className={`mb-3 flex flex-wrap items-center gap-2 rounded-tile border px-3 py-2 text-body ${tone(true)}`}>
        <strong className="font-semibold">决策闭环健康状态不可得</strong>
        <span className="text-label">{why}</span>
        {endpointMissing && (
          <a href="/diagnostics" className="text-label underline underline-offset-2">去检测 →</a>
        )}
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
