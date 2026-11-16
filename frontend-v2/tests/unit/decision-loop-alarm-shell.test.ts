import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '../../..')
const shell = () => readFileSync(resolve(ROOT, 'frontend-v2/src/app/AppShell.tsx'), 'utf8')
const queries = () => readFileSync(resolve(ROOT, 'frontend-v2/src/lib/queries.ts'), 'utf8')

describe('AppShell · 决策闭环告警全局挂载（AC4/AC7 静态契约）', () => {
  it('导入并渲染 DecisionLoopAlarm', () => {
    const s = shell()
    expect(s).toContain("import { DecisionLoopAlarm }")
    expect(s).toContain('<DecisionLoopAlarm />')
  })

  it('横幅位于 <main> 内且早于 <Outlet />（Zen 折叠顶栏/侧栏时仍可见）', () => {
    const s = shell()
    const main = s.indexOf('<main')
    const end = s.indexOf('</main>', main)
    const alarm = s.indexOf('<DecisionLoopAlarm />')
    const outlet = s.indexOf('<Outlet />')
    expect(main).toBeGreaterThan(-1)
    expect(end).toBeGreaterThan(main)
    expect(alarm).toBeGreaterThan(main)
    expect(alarm).toBeLessThan(end)
    expect(alarm).toBeLessThan(outlet)
  })

  // AC7 防「守卫空转」：只断言常量等于 60_000 并不能证明 hook 真的用了它。
  // 若有人把 refetchInterval 写死成另一个数字或直接删掉，组件测试仍会绿 → 静默失去自动探测。
  it('useDecisionLoopHealth 真的使用共享常量轮询，不得写死/删除', () => {
    const s = queries()
    expect(s).toContain("import { HEALTH_REFETCH_INTERVAL_MS } from '@/lib/health'")
    const start = s.indexOf('export function useDecisionLoopHealth')
    expect(start).toBeGreaterThan(-1)
    const body = s.slice(start, start + 500)
    expect(body).toContain('refetchInterval: HEALTH_REFETCH_INTERVAL_MS')
    expect(body).not.toMatch(/refetchInterval:\s*\d/)
  })
})
