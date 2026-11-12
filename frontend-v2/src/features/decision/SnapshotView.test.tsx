import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SnapshotView } from './SnapshotView'
import type { DailySnapshot } from '@/api/schemas/read'

// PositionGauge / ScenarioChart 内部用 EChart（jsdom 无 canvas）→ 桩掉。
// 注意：只桩 EChart 本体，PositionGauge 空态、ScenarioChart 缺失提示都是纯 DOM，仍会真实渲染。
vi.mock('@/shared/charts/EChart', () => ({ EChart: () => null }))

/**
 * 最小快照：只带权威数据日，其余字段全部缺失。
 * 这正是诚实红线要锁的状态——「无数据」不得被渲染成「数值为 0 / 空仓 / 新鲜」。
 */
const minimal = { date: '2026-03-01' } as DailySnapshot

function full(): DailySnapshot {
  return {
    date: '2026-03-01',
    as_of: '2026-03-01 15:00',
    data_age_days: 2,
    temperature: 55.5,
    cycle: '复苏',
    score: 62,
    bias: '偏多',
    confidence: 0.72,
    promo_overall: 3.2,
    position: { pct: 65, band: '中性偏多', color: '#009e60', reasons: ['广度回暖', '情绪修复'] },
    event_factor: { available: true, long_count: 12, adj: 1.5, as_of: '2026-02-28' },
    data_freshness: {
      status: 'ok',
      sources: {
        akshare: { lag_days: 1, status: 'ok' },
        p1: { lag_days: 2, status: 'ok' },
      },
    },
    indicators: { up_count: 3000, down_count: 1800, limit_up: 45, red_ratio: 0.62 },
    ladder: { max_boards: 7, total_connect: 20 },
    scenario: [
      { name: '震荡', prob: 55 },
      { name: '上行', prob: 30 },
    ],
  } as DailySnapshot
}

/** 盘面指标 tile 的值节点：SnapshotView 用 className="text-base font-medium" 渲染 12 项。 */
function indicatorValues(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.text-base.font-medium')).map(
    (el) => el.textContent ?? '',
  )
}

describe('SnapshotView · 决策闭环展示核心 · 诚实红线专项守卫', () => {
  it('position 缺失 → 仓位是「—」空态，绝不伪造「建议空仓 0%」', () => {
    render(<SnapshotView snapshot={minimal} />)
    expect(screen.getByLabelText('暂无仓位建议数据')).toBeTruthy()
    expect(screen.queryByText('0%')).toBeNull()
    expect(screen.queryByText(/建议空仓/)).toBeNull()
  })

  it('12 个盘面指标全部缺失 → 全显「—」，无一补零', () => {
    const { container } = render(<SnapshotView snapshot={minimal} />)
    const values = indicatorValues(container)
    expect(values).toHaveLength(12)
    expect(values.every((v) => v === '—')).toBe(true)
    expect(values.some((v) => v === '0' || v === '0.00')).toBe(false)
  })

  it('数值字段 / bias / 连板梯队 缺失 → 全部占位「—」，无补零', () => {
    render(<SnapshotView snapshot={minimal} />)
    // 3 个 Stat（市场温度 / 综合评分 / 信心）值 + bias 副文 + 最高板 / 连板总数
    expect(screen.getByText('偏向 —')).toBeTruthy()
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(12)
    expect(screen.queryByText('0.00')).toBeNull()
  })

  it('诚区分「真 0」与「缺失」：up_count=0 原样显示，down_count=null 显「—」', () => {
    const snapshot = {
      date: '2026-03-01',
      indicators: { up_count: 0, down_count: null },
    } as unknown as DailySnapshot
    const { container } = render(<SnapshotView snapshot={snapshot} />)
    const values = indicatorValues(container)
    expect(values[0]).toBe('0') // 真值 0 不吞
    expect(values[1]).toBe('—') // 缺失不补零
    expect(screen.getByText('0')).toBeTruthy()
  })

  it('event_factor 缺失 / available=false → 「事件因子不可用」，不编造多头数', () => {
    const { rerender } = render(<SnapshotView snapshot={minimal} />)
    expect(screen.getByText('事件因子不可用')).toBeTruthy()
    expect(screen.queryByText(/多头/)).toBeNull()

    const explicit = { date: '2026-03-01', event_factor: { available: false, long_count: 99 } } as DailySnapshot
    rerender(<SnapshotView snapshot={explicit} />)
    expect(screen.getByText('事件因子不可用')).toBeTruthy()
    expect(screen.queryByText('99')).toBeNull()
  })

  it('新鲜度信息全缺 → 「新鲜度未知」+「无新鲜度明细」，不乐观兜底成「数据新鲜」', () => {
    render(<SnapshotView snapshot={minimal} />)
    expect(screen.getByLabelText('数据新鲜度：新鲜度未知')).toBeTruthy()
    expect(screen.getByText('无新鲜度明细')).toBeTruthy()
    expect(screen.queryByText('数据新鲜')).toBeNull()
  })

  it('data_age_days 缺失但 status=stale → 仍判「数据陈旧」（不被兜底成 ok）', () => {
    const snapshot = {
      date: '2026-03-01',
      data_freshness: { status: 'stale' },
    } as DailySnapshot
    render(<SnapshotView snapshot={snapshot} />)
    expect(screen.getByLabelText('数据新鲜度：数据陈旧')).toBeTruthy()
  })

  it.each([
    [10, '数据陈旧'],
    [6, '数据偏旧'],
    [2, '数据新鲜'],
  ])('data_age_days=%s → 「%s」', (age, label) => {
    const snapshot = { date: '2026-03-01', data_age_days: age } as DailySnapshot
    render(<SnapshotView snapshot={snapshot} />)
    expect(screen.getByLabelText(`数据新鲜度：${label}`)).toBeTruthy()
  })

  it('全字段齐全 → 正向渲染对照（温度/评分/偏向/调节/多头/梯队/指标/新鲜度）', () => {
    const { container } = render(<SnapshotView snapshot={full()} />)
    expect(screen.getByText('权威数据日')).toBeTruthy()
    expect(screen.getByText('2026-03-01')).toBeTruthy()
    expect(screen.getByText('55.50')).toBeTruthy() // temperature 浮点两位
    expect(screen.getByText('62')).toBeTruthy() // score 整数原样
    expect(screen.getByText('偏向 偏多')).toBeTruthy()
    expect(screen.getByText(/CYCLE_ADJ 3\.20/)).toBeTruthy()
    expect(screen.getByText(/多头 12 只/)).toBeTruthy()
    expect(screen.getByText('7')).toBeTruthy() // 最高板
    expect(screen.getByText('20')).toBeTruthy() // 连板总数
    expect(screen.getByText('3000')).toBeTruthy() // up_count
    expect(screen.getByLabelText('数据新鲜度：数据新鲜')).toBeTruthy()
    expect(screen.getByText('中性偏多')).toBeTruthy() // position.band
    expect(screen.getByText('广度回暖')).toBeTruthy() // position.reasons
    expect(indicatorValues(container)[0]).toBe('3000')
  })

  it('scenario 含 prob 缺失 → 诚实提示「不按 0% 计算」，不补零', () => {
    const snapshot = {
      date: '2026-03-01',
      scenario: [
        { name: '震荡', prob: 55 },
        { name: '上行' }, // prob 缺失
      ],
    } as DailySnapshot
    render(<SnapshotView snapshot={snapshot} />)
    expect(screen.getByText(/1 个情景未提供概率值，已留空/)).toBeTruthy()
    expect(screen.getByText(/不按 0% 计算/)).toBeTruthy()
  })

  it('数据源 lag_days / status 缺失 → 显「—」而非补零', () => {
    const snapshot = {
      date: '2026-03-01',
      data_freshness: { status: 'ok', sources: { akshare: {} } },
    } as DailySnapshot
    render(<SnapshotView snapshot={snapshot} />)
    expect(screen.getByText(/— · —/)).toBeTruthy()
    expect(screen.queryByText(/0天/)).toBeNull()
  })
})
