import { describe, it, expect } from 'vitest'
import { classifyIntent } from './intent'

describe('classifyIntent（规则引擎）', () => {
  it('研判类：带代码 → analyze + 追问 chips', () => {
    const r = classifyIntent('茅台 600519 怎么样？')
    expect(r.kind).toBe('analyze')
    expect(r.needsParam).toBe(false)
    expect(r.suggestionChips.length).toBeGreaterThan(0)
  })

  it('对比类：含「对比」→ compare', () => {
    expect(classifyIntent('宁德时代和比亚迪对比').kind).toBe('compare')
  })

  it('解释类：含「为什么」→ explain', () => {
    expect(classifyIntent('为什么今天大跌？').kind).toBe('explain')
  })

  it('多空类：含「看多」→ debate', () => {
    expect(classifyIntent('新能源后市看多还是看空？').kind).toBe('debate')
  })

  it('数据类：含「估值」→ data', () => {
    expect(classifyIntent('茅台的估值和毛利率如何？').kind).toBe('data')
  })

  it('缺分析标的 → needsParam 为真，并给出追问项', () => {
    const r = classifyIntent('你好')
    expect(r.needsParam).toBe(true)
    expect(r.paramPrompts.length).toBeGreaterThan(0)
    expect(r.suggestionChips).toHaveLength(0)
  })

  it('纯泛泛提问且无标的 → general，置信压低', () => {
    const r = classifyIntent('随便聊聊')
    expect(r.kind).toBe('general')
    expect(r.confidence).toBeLessThan(0.6)
  })
})
