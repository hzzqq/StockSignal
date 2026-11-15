// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { NlScreen } from '@/api/schemas/read'
import { Screener } from './Screener'

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    Link: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <a className={className}>{children}</a>
    ),
  }
})

vi.mock('@/api/read', () => ({ getNlScreen: vi.fn() }))
import { getNlScreen } from '@/api/read'
const mocked = vi.mocked(getNlScreen)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const parsed: NlScreen = {
  status: 'ok',
  query: '创业板 市盈率<30 且 营收增长>20% 剔除ST 前10',
  spec: {
    boards: ['cyb'],
    filters: [
      { field: 'pe', op: 'lt', value: 30, unit: 'ratio', raw: '市盈率<30' },
      { field: 'rev_growth', op: 'gt', value: 20, unit: 'pct', raw: '营收增长>20%' },
    ],
    sort: null,
    sort_dir: 'desc',
    limit: 10,
    concepts: [],
    exclude_boards: [],
    exclude_concepts: ['ST'],
    unparsed: [],
    errors: [],
  },
  note: 'v2 仅承接语义解析层，不返回候选标的。',
  unavailable: [],
}

beforeEach(() => {
  mocked.mockReset()
})

describe('Screener · 选股框架（诚实落地）', () => {
  it('真实 v2 入口全部在，顶部如实声明「列出 ≠ 已实现」', () => {
    renderWithClient(<Screener />)
    expect(screen.getByRole('heading', { name: '选股框架' })).toBeTruthy()
    for (const label of ['每日荐股', '六维评分', '个股研究', '基本面分析', '个股对比', '因子分析', '星辰 AI 助手']) {
      // 「每日荐股」等词也会出现在 v1 状态说明里，故用 AllBy 变体校验存在性
      expect(screen.getAllByText(new RegExp(label)).length).toBeGreaterThan(0)
    }
    // 7 个真实入口 Link（另有 31/33/81 的 v1/v2 直达链接，故用下界）
    expect(document.querySelectorAll('a').length).toBeGreaterThanOrEqual(7)
    expect(screen.getByText(/列出 ≠ 已实现/)).toBeTruthy()
    expect(screen.getByText(/不编造候选池/)).toBeTruthy()
  })

  it('未提交查询时不臆造解析结果', () => {
    renderWithClient(<Screener />)
    expect(screen.getByText(/尚未提交查询/)).toBeTruthy()
    expect(screen.queryByText(/筛选条件（/)).toBeNull()
    expect(mocked).not.toHaveBeenCalled()
  })

  it('提交后透明展示「听懂了什么」，且明确不含候选标的', async () => {
    mocked.mockResolvedValue(parsed)
    renderWithClient(<Screener />)
    fireEvent.change(screen.getByRole('textbox', { name: '自然语言选股条件' }), {
      target: { value: parsed.query },
    })
    fireEvent.click(screen.getByRole('button', { name: '解析' }))
    expect(await screen.findByText(/筛选条件（2）/)).toBeTruthy()
    expect(screen.getByText('cyb')).toBeTruthy()
    expect(screen.getByText('10')).toBeTruthy()
    expect(screen.getByText('ST')).toBeTruthy()
    expect(screen.getByText(/不是筛选结果、也不含任何候选标的/)).toBeTruthy()
    // 未识别的排序字段如实显示「—」，不编造
    expect(screen.getByText('排序字段')).toBeTruthy()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('后端解析失败 → 诚实错误态，不编造条件表', async () => {
    mocked.mockRejectedValue(new Error('语义解析失败（compute_error）'))
    renderWithClient(<Screener />)
    fireEvent.change(screen.getByRole('textbox', { name: '自然语言选股条件' }), {
      target: { value: '随便一句' },
    })
    fireEvent.click(screen.getByRole('button', { name: '解析' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText(/语义解析失败/)).toBeTruthy()
    expect(screen.queryByText(/筛选条件（/)).toBeNull()
  })

  it('v1 三页状态来自单一真理源：31 已承接，33/81 不做假入口', () => {
    renderWithClient(<Screener />)
    expect(screen.getByText('已由 v2 承接')).toBeTruthy()
    expect(screen.getAllByText('v1 保留（v2 不做等价实现）')).toHaveLength(2)
    expect(screen.getAllByText('打开 v2 →')).toHaveLength(1)
    expect(screen.getAllByText('在 v1 打开 ↗')).toHaveLength(2)
    expect(screen.getByText(/不提供假入口/)).toBeTruthy()
  })
})
