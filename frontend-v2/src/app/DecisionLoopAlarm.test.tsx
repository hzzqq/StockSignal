import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DecisionLoopAlarm } from './DecisionLoopAlarm'
import { HEALTH_REFETCH_INTERVAL_MS } from '@/lib/health'
import { useDecisionLoopHealth } from '@/lib/queries'
import { ApiError } from '@/api/client'

vi.mock('@/lib/queries', () => ({ useDecisionLoopHealth: vi.fn() }))
const mHook = vi.mocked(useDecisionLoopHealth)

const health = (over: Record<string, unknown> = {}) => ({
  status: 'ok',
  rank: 0,
  generated_at: '2026-11-16T09:00:00',
  as_of: '2026-11-15',
  gen_lag_hours: 1.2,
  data_lag_days: 1,
  message: '✅ 决策闭环正常，最后更新 2026-11-16T09:00:00。',
  ...over,
})

function query(over: Record<string, unknown>) {
  mHook.mockReturnValue({
    data: undefined, isLoading: false, isError: false, error: null,
    isFetching: false, refetch: vi.fn(), ...over,
  } as never)
}

beforeEach(() => mHook.mockReset())

describe('DecisionLoopAlarm · 决策闭环停摆告警（AC4–AC7）', () => {
  it('ok 不渲染横幅（不打扰正常浏览）', () => {
    query({ data: health() })
    const { container } = render(<DecisionLoopAlarm />)
    expect(container.firstChild).toBeNull()
  })

  it('warn → 橙色提示 + 后端 message 原文 + 真实时间', () => {
    query({ data: health({ status: 'warn', rank: 1, message: '数据偏旧：截至 2026-11-12（滞后 4 天）。' }) })
    render(<DecisionLoopAlarm />)
    const alert = screen.getByRole('alert')
    expect(alert.className).toContain('sf-warn')
    expect(alert.textContent).toContain('数据偏旧：截至 2026-11-12（滞后 4 天）。')
    expect(alert.textContent).toContain('2026-11-16T09:00:00')
  })

  it('stale → 橙色提示', () => {
    query({ data: health({ status: 'stale', rank: 2, message: '决策快照超过一个交易日未更新' }) })
    render(<DecisionLoopAlarm />)
    expect(screen.getByRole('alert').className).toContain('sf-warn')
    expect(screen.getByText(/决策快照超过一个交易日未更新/)).toBeTruthy()
  })

  it('dead → 红色告警，不得显示为正常', () => {
    query({ data: health({ status: 'dead', rank: 3, message: '⛔ 决策闭环疑似停摆：调度可能已死' }) })
    render(<DecisionLoopAlarm />)
    const alert = screen.getByRole('alert')
    expect(alert.className).toContain('sf-danger')
    expect(alert.textContent).toContain('决策闭环疑似停摆')
    expect(screen.queryByText(/决策闭环正常/)).toBeNull()
  })

  it('unknown → 红色告警（评估失败也算不可信）', () => {
    query({ data: health({ status: 'unknown', rank: 3, message: '健康评估失败：ValueError' }) })
    render(<DecisionLoopAlarm />)
    expect(screen.getByRole('alert').className).toContain('sf-danger')
  })

  it('请求失败 → 显示「不可得」，绝不假装正常', () => {
    query({ isError: true, error: new Error('boom') })
    render(<DecisionLoopAlarm />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('健康状态不可得')
    expect(screen.queryByText(/决策闭环正常/)).toBeNull()
  })

  it('缺失时间与滞后 → 显示「时间不可得」与「—」，不补 0', () => {
    query({ data: health({ status: 'dead', generated_at: null, gen_lag_hours: null, message: '快照不存在' }) })
    render(<DecisionLoopAlarm />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('时间不可得')
    expect(alert.textContent).toContain('—')
    expect(alert.textContent).not.toContain('0 小时')
  })

  it('「重新检测」按钮触发真实 refetch', () => {
    const refetch = vi.fn()
    query({ data: health({ status: 'dead' }), refetch })
    render(<DecisionLoopAlarm />)
    fireEvent.click(screen.getByRole('button', { name: /重新检测/ }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('404 not_found → 明确提示端点缺失 / 服务未重启，不误判为调度停摆', () => {
    query({ isError: true, error: new ApiError('not_found', '资源不存在') })
    render(<DecisionLoopAlarm />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('后端未提供该端点')
    expect(alert.textContent).toContain('服务可能未重启')
    expect(screen.getByRole('link', { name: /去检测/ })).toBeTruthy()
  })

  it('自动轮询间隔为 60s（AC7）', () => {
    expect(HEALTH_REFETCH_INTERVAL_MS).toBe(60_000)
  })
})
