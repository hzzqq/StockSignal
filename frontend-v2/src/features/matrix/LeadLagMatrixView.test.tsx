import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LeadLagMatrixView } from './LeadLagMatrixView'

vi.mock('@/api/read', () => ({
  getBreadthHistory: vi.fn(),
}))
import { getBreadthHistory } from '@/api/read'
const mocked = vi.mocked(getBreadthHistory)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  mocked.mockReset()
})

describe('LeadLagMatrixView 三态 + 诚实空态', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<LeadLagMatrixView />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('广度历史加载失败'))
    renderWithClient(<LeadLagMatrixView />)
    await expect(screen.findByText('广度历史加载失败')).resolves.toBeTruthy()
  })

  it('空数据 → 诚实空态「有效样本不足，未计算矩阵」（不补零/不编造）', async () => {
    mocked.mockResolvedValue([])
    renderWithClient(<LeadLagMatrixView />)
    await expect(screen.findByText('有效样本不足，未计算矩阵')).resolves.toBeTruthy()
  })

  it('口径与结论重点词用品牌色加粗强调（文案原样，仅视觉分层）', () => {
    const src = readFileSync(
      resolve(process.cwd(), 'src/features/matrix/LeadLagMatrixView.tsx'),
      'utf8',
    )
    for (const phrase of [
      '有序对',
      '互相关只描述协同/错位，非因果、非预测',
      '不代表能预测次日涨跌',
    ]) {
      const close = `>${phrase}</strong>`
      const idx = src.indexOf(close)
      expect(idx, `未找到重点词：${phrase}`).toBeGreaterThan(-1)
      const open = src.lastIndexOf('<strong', idx)
      const tag = src.slice(open, idx + 1)
      expect(tag, `${phrase} 应使用品牌色强调`).toContain('var(--color-brand-1)')
    }
  })
})
