import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProjectIntro } from './ProjectIntro'

/**
 * ProjectIntro 是 v1 Hero 的 1:1 静态移植，不含任何动态数字（文案与 v1 完全一致）。
 * 因此只做渲染冒烟 + 关键静态文案断言，不存在「照抄旧数 / 取不到补 0」类缺陷需要锁。
 */
describe('ProjectIntro · v1 Hero 静态移植 · 渲染冒烟', () => {
  it('渲染主标题 + 三枚痛点卡 + 三色能力卡，且不含任何动态数值', () => {
    render(<ProjectIntro />)
    // 主标题（含品牌强调）
    expect(screen.getByRole('heading', { level: 1, name: /凭感觉/ })).toBeTruthy()
    // 三枚痛点卡标题
    expect(screen.getByText('当初为什么买？')).toBeTruthy()
    expect(screen.getByText('赚了，是判断对还是运气？')).toBeTruthy()
    expect(screen.getByText('亏了，错在哪一步？')).toBeTruthy()
    // 三色能力卡标题
    expect(screen.getByText('情绪温度计')).toBeTruthy()
    expect(screen.getByText('事件驱动信号')).toBeTruthy()
    expect(screen.getByText('决策闭环回测')).toBeTruthy()
    // 静态文案：无任何动态数值（如 KPI、日期、百分比）——hero 内不应出现「%」或「评分」
    const body = document.body.textContent ?? ''
    expect(body).not.toMatch(/\d+%/)
    expect(body).not.toContain('综合评分')
  })
})
