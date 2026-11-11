/**
 * 演示数据横幅：仅在开发模式且未显式关闭 MSW 时显示，
 * 明确告知用户当前为 Mock 数据（非真实行情），严守诚实红线。
 *
 * 用设计令牌（sf-warn / sf-warn-soft）做主题自适应：暗色为浅琥珀文字 + 深琥珀底，
 * 亮色为深琥珀文字 + 浅琥珀底，两主题均高对比可读，避免旧版 amber-* 静态色在亮色下
 * 低对比、文字发虚像「重叠/截断」的问题。
 */
export function MockBanner() {
  const env = import.meta.env as Record<string, unknown>
  const mockOn = import.meta.env.DEV && env['VITE_ENABLE_MOCKS'] !== 'false'
  if (!mockOn) return null
  return (
    <div className="mb-3 flex items-center gap-2 rounded-lg border border-sf-warn/30 bg-sf-warn-soft px-3 py-1.5 text-xs text-sf-warn">
      <span aria-hidden>⚠️</span>
      <span>演示数据（Mock）· 非真实行情，仅用于前端联调</span>
    </div>
  )
}
