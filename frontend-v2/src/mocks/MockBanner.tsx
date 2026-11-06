/**
 * 演示数据横幅：仅在开发模式且未显式关闭 MSW 时显示，
 * 明确告知用户当前为 Mock 数据（非真实行情），严守诚实红线。
 */
export function MockBanner() {
  const env = import.meta.env as Record<string, unknown>
  const mockOn = import.meta.env.DEV && env['VITE_ENABLE_MOCKS'] !== 'false'
  if (!mockOn) return null
  return (
    <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-300">
      演示数据（Mock）· 非真实行情，仅用于前端联调
    </div>
  )
}
