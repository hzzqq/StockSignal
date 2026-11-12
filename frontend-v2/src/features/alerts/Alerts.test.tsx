import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Alerts } from './Alerts'

vi.mock('@/api/read', () => ({
  getAlertRules: vi.fn(),
  getAlertLog: vi.fn(),
}))
import { getAlertRules, getAlertLog } from '@/api/read'
const mockedRules = vi.mocked(getAlertRules)
const mockedLog = vi.mocked(getAlertLog)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mockedRules.mockReset()
  mockedLog.mockReset()
  // 默认日志查询成功，避免多「加载中…」冲突
  mockedLog.mockResolvedValue('some log line')
})

describe('Alerts 四态 + 诚实空态', () => {
  it('loading（仅规则挂起）显示加载占位', async () => {
    mockedRules.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<Alerts />)
    // 规则挂起时，日志查询也尚未完成 → 两个「加载中…」，用 findAllByText
    expect(await screen.findAllByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mockedRules.mockRejectedValue(new Error('规则加载失败'))
    renderWithClient(<Alerts />)
    await expect(screen.findByText('规则加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染规则与日志', async () => {
    mockedRules.mockResolvedValue({ rule1: 'threshold', rule2: 'price' })
    renderWithClient(<Alerts />)
    // 标题「告警引擎」始终存在，改用数据态才出现的规则内容作为加载完成信号
    expect(await screen.findByText(/rule1/)).toBeTruthy()
    expect(screen.getByText('告警引擎')).toBeTruthy()
    expect(screen.getByText(/rule1/)).toBeTruthy()
    expect(screen.getByText('告警日志（alerts.log）')).toBeTruthy()
    expect(screen.getByText('some log line')).toBeTruthy()
  })

  it('规则缺失 → 暂无告警规则（诚实空态）', async () => {
    // React Query 不接受 undefined 作为成功结果，须用 null 触发空态
    mockedRules.mockResolvedValue(null as unknown as Record<string, unknown>)
    renderWithClient(<Alerts />)
    await expect(screen.findByText('暂无告警规则')).resolves.toBeTruthy()
    expect(screen.getByText(/alert_rules.json 当前缺失/)).toBeTruthy()
  })

  it('日志缺失 → 暂无告警日志', async () => {
    mockedRules.mockResolvedValue({})
    mockedLog.mockResolvedValue(null as unknown as string)
    renderWithClient(<Alerts />)
    await expect(screen.findByText('暂无告警日志')).resolves.toBeTruthy()
  })
})
