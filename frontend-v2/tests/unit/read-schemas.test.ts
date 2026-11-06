import { describe, it, expect } from 'vitest'
import {
  DailySnapshotSchema,
  P1SignalSchema,
  WebAppSchema,
  PaperTradeSchema,
} from '@/api/schemas/read'

const snap = {
  date: '2026-11-06',
  position: { pct: 29, band: '偏空', color: '#00d486', reasons: ['x'] },
  indicators: { red_ratio: 0.42 },
  scenario: [],
}

describe('DailySnapshotSchema', () => {
  it('接受真实形状快照', () => {
    const r = DailySnapshotSchema.parse(snap)
    expect(r.date).toBe('2026-11-06')
    expect(r.position?.pct).toBe(29)
  })
  it('缺 date 即抛错（红线：不兜底）', () => {
    expect(() => DailySnapshotSchema.parse({ position: {} })).toThrow()
  })
})

describe('P1SignalSchema', () => {
  it('接受 signal 形状', () => {
    const r = P1SignalSchema.parse({
      latest_date: '2026-10-21',
      top_long: [{ symbol: 'sh600000', pred: 0.01, rank: 1 }],
    })
    expect(r.latest_date).toBe('2026-10-21')
  })
})

describe('WebAppSchema', () => {
  it('title 必填', () => {
    expect(() => WebAppSchema.parse({ dir: 'x', entry: 'i.html' })).toThrow()
    const r = WebAppSchema.parse({ dir: 'x', title: 'T', entry: 'i.html' })
    expect(r.title).toBe('T')
  })
})

describe('PaperTradeSchema', () => {
  it('接受 paper 账本形状', () => {
    const r = PaperTradeSchema.parse({
      init_cash: 1000000,
      cash: 870944,
      positions: { '600519': { name: '贵州茅台', qty: 100, avg_cost: 1290.56 } },
      trades: [{ time: 't', code: '600519', side: '买', price: 1, qty: 1, amount: 1 }],
    })
    expect(r.positions?.['600519'].name).toBe('贵州茅台')
  })
})
