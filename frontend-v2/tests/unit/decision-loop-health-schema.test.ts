import { describe, it, expect } from 'vitest'
import { DecisionLoopHealthSchema } from '@/api/schemas/read'

const base = {
  status: 'ok',
  rank: 0,
  generated_at: '2026-11-16T09:00:00',
  as_of: '2026-11-15',
  gen_lag_hours: 1.2,
  data_lag_days: 1,
  message: '✅ 决策闭环正常',
}

describe('DecisionLoopHealthSchema · 严格契约（AC3）', () => {
  it('schema 已定义（防 undefined 假绿）', () => {
    expect(DecisionLoopHealthSchema).toBeDefined()
    expect(typeof DecisionLoopHealthSchema.safeParse).toBe('function')
  })

  it.each(['ok', 'warn', 'stale', 'dead', 'unknown'])('接受合法 status=%s', (s) => {
    expect(DecisionLoopHealthSchema.parse({ ...base, status: s }).status).toBe(s)
  })

  it('未知 status 必须抛错（前端进 error 态，绝不假绿）', () => {
    expect(DecisionLoopHealthSchema.safeParse({ ...base, status: 'green' }).success).toBe(false)
  })

  it('rank 越界 / 非整数必须抛错', () => {
    expect(DecisionLoopHealthSchema.safeParse({ ...base, rank: 9 }).success).toBe(false)
    expect(DecisionLoopHealthSchema.safeParse({ ...base, rank: 1.5 }).success).toBe(false)
  })

  it('时间/滞后字段允许 null（缺失如实透出，不补 0）', () => {
    const r = DecisionLoopHealthSchema.parse({
      status: 'dead', rank: 3, generated_at: null, as_of: null,
      gen_lag_hours: null, data_lag_days: null, message: '快照不存在',
    })
    expect(r.generated_at).toBeNull()
    expect(r.gen_lag_hours).toBeNull()
  })

  it('缺 message / 缺 rank 必须抛错', () => {
    const { message: _m, ...noMsg } = base
    expect(DecisionLoopHealthSchema.safeParse(noMsg).success).toBe(false)
    const { rank: _r, ...noRank } = base
    expect(DecisionLoopHealthSchema.safeParse(noRank).success).toBe(false)
  })
})
