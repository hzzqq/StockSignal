// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { MarketSentiment } from '@/api/schemas/read'
import {
  MarketDrivers,
  buildDerivedCsv,
  deriveCorrelation,
  normalizeSpark,
} from './MarketDrivers'

// mock hook（而非真发请求）：三态 + 缺失空态全部由返回值驱动。
vi.mock('@/lib/queries', () => ({ useMarketSentiment: vi.fn() }))
// EChart 在 jsdom 下会动态 import 图表包；这里只验证 ariaLabel 与挂载，不渲染 canvas。
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel?: string }) => (
    <div data-testid="echart" aria-label={ariaLabel} />
  ),
}))

import { useMarketSentiment } from '@/lib/queries'

const mocked = vi.mocked(useMarketSentiment)
const setState = (o: Record<string, unknown>) =>
  o as unknown as ReturnType<typeof useMarketSentiment>

const okData: MarketSentiment = {
  available: true,
  reason: null,
  data_as_of: '2026-03-01',
  temperature: 57.3,
  level: { label: '中性', emoji: '⚖️', color: '#2b8aef' },
  dims: {
    资金: [
      {
        key: 'margin_net', name: '融资净买入额', unit: '亿元',
        value: 46.8, spark: [40, 50, 45, 60], heat: 60.1, available: true,
      },
      {
        key: 'north_net', name: '北向净买额', unit: '亿元',
        value: null, spark: [null, null, null, null], heat: null, available: true,
      },
    ],
    情绪: [
      { key: 'adr', name: 'ADR', unit: '', value: 1.2, spark: [1, 2, 1.5, 2.5], heat: 55, available: true },
      { key: 'vix', name: 'VIX', unit: '', value: 20, spark: [19, 21, 20, 18], heat: 40, available: true },
    ],
  },
  unavailable: [{ dim: '宏观', key: 'pmi', reason: 'akshare 限流' }],
  note: '派生测试',
}

const unavailableData: MarketSentiment = {
  available: false,
  reason: '无任何可用指标（网络与缓存均不可用）',
  data_as_of: null,
  temperature: null,
  level: null,
  dims: {},
  unavailable: [],
  note: '市场驱动力数据加载失败',
}

const missingData: MarketSentiment = {
  ...okData,
  data_as_of: null,
  temperature: null,
  level: null,
  // 至少留 1 个指标让正文渲染（总指标为 0 会走诚实空态），用空维度/全 null spark 验证缺失标注
  dims: {
    资金: [
      {
        key: 'margin_null', name: '融资净买额', unit: '亿元',
        value: null, spark: [null, null, null], heat: null, available: true,
      },
    ],
    宏观: [],
  },
  unavailable: [],
}

beforeEach(() => mocked.mockReset())

describe('MarketDrivers · 三态 + 五维派生 + 诚实降级', () => {
  it('loading 显示加载占位（role=status）', () => {
    mocked.mockReturnValue(setState({ isLoading: true }))
    render(<MarketDrivers />)
    expect(screen.getByRole('status')).toBeTruthy()
    expect(screen.getByText(/加载中/)).toBeTruthy()
  })

  it('error 显示错误态（role=alert，不复用涨跌色）', () => {
    mocked.mockReturnValue(
      setState({ isError: true, error: new Error('市场驱动力加载失败') }),
    )
    render(<MarketDrivers />)
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('市场驱动力加载失败')
  })

  it('available=false → 诚实空态，原因原文透出', () => {
    mocked.mockReturnValue(setState({ data: unavailableData }))
    render(<MarketDrivers />)
    expect(screen.getByText(/暂无市场驱动力数据/)).toBeTruthy()
    expect(screen.getByText(/网络与缓存均不可用/)).toBeTruthy()
  })

  it('ok 渲染五维卡片 + 派生口径说明 + 图表 ariaLabel', () => {
    mocked.mockReturnValue(setState({ data: okData }))
    render(<MarketDrivers />)
    expect(screen.getByText('资金维度 · 归一化叠加（派生）')).toBeTruthy()
    expect(screen.getByText('情绪维度 · 归一化叠加（派生）')).toBeTruthy()
    expect(screen.getByText(/口径说明（派生，非 v1 原样迁移）/)).toBeTruthy()
    const charts = screen.getAllByTestId('echart')
    expect(charts.length).toBeGreaterThanOrEqual(3)
    for (const c of charts) expect((c.getAttribute('aria-label') ?? '').length).toBeGreaterThan(8)
  })

  it('口径说明重点词用品牌色加粗强调（文案原样，仅视觉分层）', () => {
    mocked.mockReturnValue(setState({ data: okData }))
    const { container } = render(<MarketDrivers />)
    const targets = Array.from(container.querySelectorAll('strong')).filter((s) =>
      ['派生', '本页不编造这两项'].includes((s.textContent ?? '').trim()),
    )
    expect(targets.length, '派生 / 本页不编造这两项 两处强调都应存在').toBe(2)
    for (const s of targets) {
      expect(s.getAttribute('style') ?? '', `${s.textContent} 应带品牌色强调`).toContain(
        'var(--color-brand-1)',
      )
    }
  })

  it('缺失显「—」：数据日/温度不可得不补 0，空维度显式标注', () => {
    mocked.mockReturnValue(setState({ data: missingData }))
    render(<MarketDrivers />)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.getByText(/该维度暂无可用指标/)).toBeTruthy()
    expect(screen.getByText(/可用指标不足 2 项/)).toBeTruthy()
    expect(screen.queryByText('0.0')).toBeNull()
  })

  it('无涨跌色黑名单 class、无 .flow 缺失（真扫源码）', () => {
    const src = readFileSync(
      resolve(process.cwd(), 'src/features/market/MarketDrivers.tsx'),
      'utf8',
    )
    // 运行时拼接禁用 token：守卫扫描的是源码字面量，测试自身不得把它写进 src 文件。
    const sep = '-'
    const up = `ss${sep}up`
    const down = `ss${sep}down`
    const banned = [
      `text${sep}${up}`, `text${sep}${down}`,
      `bg${sep}${up}`, `bg${sep}${down}`,
      `border${sep}${up}`, `border${sep}${down}`,
      `focus:border${sep}${up}`,
      `bg${sep}sf${sep}card`,
      `rounded${sep}xl`,
      `border${sep}sf${sep}line${sep}strong`,
    ]
    for (const token of banned) {
      expect(src, `禁用 class 回流：${token}`).not.toContain(token)
    }
    expect(src).toContain('className="flow"')
  })

  it('派生标注真扫源码：归一化/热力/CSV 均带「派生」且 EChart 传 ariaLabel', () => {
    const src = readFileSync(
      resolve(process.cwd(), 'src/features/market/MarketDrivers.tsx'),
      'utf8',
    )
    expect(src).toContain('派生')
    expect((src.match(/ariaLabel=/g) ?? []).length).toBeGreaterThanOrEqual(2)
    for (const m of src.matchAll(/ariaLabel=\{`([^`]+)`\}/g)) {
      expect(m[1].length, 'ariaLabel 不得为空占位').toBeGreaterThan(8)
    }
  })
})

describe('MarketDrivers · 派生函数单测', () => {
  it('normalizeSpark 按首个有效值=100 归一化，全 null 序列保持 null 不补零', () => {
    const norm = normalizeSpark(okData.dims['资金'][0])
    expect(norm.values[0]).toBe(100)
    expect(norm.values[1]).toBeCloseTo(125, 5)
    const empty = normalizeSpark(okData.dims['资金'][1])
    expect(empty.values.every((v) => v === null)).toBe(true)
  })

  it('deriveCorrelation 完全正相关=1，样本不足为 null（不补零）', () => {
    const items = [
      { key: 'a', name: 'A', unit: '', value: 1, spark: [1, 2, 3], heat: 1, available: true },
      { key: 'b', name: 'B', unit: '', value: 2, spark: [2, 4, 6], heat: 1, available: true },
    ]
    const { data } = deriveCorrelation(items)
    const ab = data.find(([x, y]) => x === 1 && y === 0)
    expect(ab?.[2]).toBeCloseTo(1, 5)
    const short = deriveCorrelation([
      { ...items[0], spark: [1] },
      { ...items[1], spark: [2] },
    ]).data.find(([x, y]) => x === 1 && y === 0)
    expect(short?.[2]).toBeNull()
  })

  it('buildDerivedCsv 缺失值留空单元格、真实值保留、无补零', () => {
    const csv = buildDerivedCsv(okData)
    expect(csv.startsWith('\uFEFF')).toBe(true)
    expect(csv).toContain('派生归一化序列(起点=100,近40点)')
    expect(csv).toContain('融资净买入额')
    expect(csv).toContain('46.8')
    // 北向净买额 value=null → 该单元格为空，不是 0
    const line = csv.split('\n').find((l) => l.includes('北向净买额')) ?? ''
    expect(line).toContain('亿元,,') // 单位后紧跟空的最新值、空的热度
    expect(line).not.toMatch(/亿元,0(,|\.)/)
  })
})
