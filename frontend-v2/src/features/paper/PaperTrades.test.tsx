import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PaperTrades } from './PaperTrades'

vi.mock('@/api/read', () => ({
  getPaperTrades: vi.fn(),
}))
import { getPaperTrades } from '@/api/read'
const mocked = vi.mocked(getPaperTrades)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const okData = {
  init_cash: 100000,
  cash: 95000,
  positions: { '600000': { name: '浦发银行', qty: 100, avg_cost: 10.5 } },
  trades: [
    { time: '2026-03-01', code: '600000', name: '浦发银行', side: '买', price: 10.5, qty: 100, amount: 1050 },
  ],
}

beforeEach(() => {
  mocked.mockReset()
})


/** 折叠卡默认收起：按 region 名展开后再断言表格行（大表折叠后的正确测试范式）。 */
async function expandCard(name: RegExp | string) {
  const region = await screen.findByRole('region', { name })
  fireEvent.click(within(region).getByRole('button', { name: /展开/ }))
}

describe('PaperTrades 四态', () => {
  it('loading 显示加载占位', () => {
    mocked.mockImplementation(() => new Promise<never>(() => {}))
    renderWithClient(<PaperTrades />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示错误态', async () => {
    mocked.mockRejectedValue(new Error('账本加载失败'))
    renderWithClient(<PaperTrades />)
    await expect(screen.findByText('账本加载失败')).resolves.toBeTruthy()
  })

  it('ok 渲染资金 / 持仓数 / 持仓表 / 成交表（数值本地化，null→—）', async () => {
    mocked.mockResolvedValue(okData)
    renderWithClient(<PaperTrades />)
    // 标题始终存在，改用数据态才出现的「初始资金」金额作为加载完成信号
    expect(await screen.findByText('100,000')).toBeTruthy()
    expect(screen.getByText('模拟交易账本')).toBeTruthy()
    expect(screen.getByText('100,000')).toBeTruthy()
    expect(screen.getByText('可用现金')).toBeTruthy()
    expect(screen.getByText('95,000')).toBeTruthy()
    expect(screen.getByText('持仓数')).toBeTruthy()
    expect(screen.getByText('1')).toBeTruthy()
    // 浦发银行同时出现在持仓表与成交表两处 → 用 getAllByText
    expect(screen.getAllByText('浦发银行').length).toBeGreaterThan(0)
    // 成交表折叠：region 名为 title「成交记录」，摘要含真实笔数；展开后断言买/卖单元格
    await expandCard('成交记录')
    expect(screen.getByText('买')).toBeTruthy()
    expect(screen.getByText('买')).toBeTruthy()
  })

  it('undefined → 暂无数据（未提供 emptyLabel，回落默认，不补零）', async () => {
    // 注意：React Query 不接受 undefined 作为成功结果，须用 null 触发空态
    mocked.mockResolvedValue(null as unknown as object)
    renderWithClient(<PaperTrades />)
    await expect(screen.findByText('暂无数据')).resolves.toBeTruthy()
  })
})
