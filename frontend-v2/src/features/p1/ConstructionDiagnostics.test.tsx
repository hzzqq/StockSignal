// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { Providers } from '@/app/providers'
import { ConstructionDiagnostics } from './ConstructionDiagnostics'
import { ConstructionDiagSchema } from './constructionDiag'
import raw from './data/constructionDiag.json'

/**
 * /p1-construction（P1 组合构建诊断）三态 + 诚实红线。
 * 数据来源：本地随包 JSON（constructionDiag.json），经 Zod 严格校验，零网络、零写入；
 * 故 ok 态直接喂解析后的真实快照，loading/error/empty 用可控 state 驱动。
 * ECharts 在 jsdom 无 canvas，按全站约定用轻量替身。
 */
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ height, ariaLabel }: { height?: number; ariaLabel?: string }) => (
    <div data-testid="echart" aria-label={ariaLabel} style={{ height }} />
  ),
}))

const data = ConstructionDiagSchema.parse(raw as unknown)

let diagState: {
  isLoading: boolean
  isError: boolean
  data: typeof data | undefined
  error: unknown
} = { isLoading: false, isError: false, data: undefined, error: undefined }

vi.mock('./constructionDiag', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('./constructionDiag')
  return { ...actual, useConstructionDiag: () => diagState }
})

function renderWithClient(ui: ReactElement) {
  return render(<Providers>{ui}</Providers>)
}

afterEach(() => {
  cleanup()
  diagState = { isLoading: false, isError: false, data: undefined, error: undefined }
})

describe('ConstructionDiagnostics 三态 + 诚实红线', () => {
  it('loading 显示加载占位（诚实：不编造内容）', () => {
    diagState = { isLoading: true, isError: false, data: undefined, error: undefined }
    renderWithClient(<ConstructionDiagnostics />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态（role=alert，带出原因）', () => {
    diagState = {
      isLoading: false,
      isError: true,
      data: undefined,
      error: new Error('组合构建诊断加载失败'),
    }
    renderWithClient(<ConstructionDiagnostics />)
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByText('组合构建诊断加载失败')).toBeTruthy()
  })

  it('empty（无数据）显示诚实空态，不补零', () => {
    diagState = { isLoading: false, isError: false, data: undefined, error: undefined }
    renderWithClient(<ConstructionDiagnostics />)
    expect(screen.getByText('暂无组合构建诊断数据')).toBeTruthy()
  })

  it('ok 渲染标题 + 诊断结论 + 诚实边界 + KPI', () => {
    diagState = { isLoading: false, isError: false, data, error: undefined }
    renderWithClient(<ConstructionDiagnostics />)
    // 标题恒显（QueryState 之外）
    expect(screen.getByText('组合构建诊断')).toBeTruthy()
    // 诊断结论卡片
    expect(screen.getByText('诊断结论（结论先行）')).toBeTruthy()
    // 诚实边界卡片
    expect(screen.getByText('诚实边界')).toBeTruthy()
    // KPI：纯多头 2026 净收益（真实数值，非编造）
    expect(screen.getByText('纯多头 2026 净收益')).toBeTruthy()
  })
})
