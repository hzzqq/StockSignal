// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { BreadthAnalytics } from '@/api/schemas/read'
import { breadthAnalytics } from '@/mocks/fixtures'
import { AnalyticsHeader, DataBoundary } from './shared'

const data = breadthAnalytics as unknown as BreadthAnalytics
const CAPTION = '用涨停家数 + 红盘占比的历史分位识别投机情绪相位（亢奋 / 活跃 / 偏冷 / 冰点 / 中性）。纯离线、描述性框架。'
const FULL_DATA_LINE =
  '数据截至 2026-08-21（离线健康镜像快照，非实时行情）。全部为历史统计描述，不预测收益、不构成买卖建议。'

describe('analytics/shared · 重点突出接入（文本一字不动，只加视觉）', () => {
  it('AnalyticsHeader 标题用 SectionTitle as=h2：brand-2 左条 + 1.08rem，不再用 text-lg', () => {
    const { container } = render(<AnalyticsHeader title="投机情绪周期时钟" caption={CAPTION} data={data} />)
    const h2 = container.querySelector('h2')!
    expect(h2.textContent).toBe('投机情绪周期时钟')
    expect(h2.style.borderColor).toContain('var(--color-brand-2)')
    expect(h2.className).toContain('border-l-[3px]')
    expect(h2.className).not.toContain('text-lg')
    expect(screen.getByText(CAPTION)).toBeTruthy()
  })

  it('数据截至整句 textContent 与原文逐字一致，仅把免责短语包进 brand-1 的 strong', () => {
    const { container } = render(<AnalyticsHeader title="标题" caption={CAPTION} data={data} />)
    const line = screen.getByText(/数据截至/)
    expect(line.textContent).toBe(FULL_DATA_LINE)
    const strong = container.querySelector('strong')!
    expect(strong.textContent).toBe('不预测收益、不构成买卖建议')
    expect(strong.className).toContain('font-bold')
    expect(strong.style.color).toContain('var(--color-brand-1)')
  })

  it('缺失数据日仍如实显「—」，免责短语同样带 brand-1 强调', () => {
    const { container } = render(<AnalyticsHeader title="标题" caption={CAPTION} />)
    expect(screen.getByText(/数据截至/).textContent).toBe(
      FULL_DATA_LINE.replace('2026-08-21', '—'),
    )
    expect(container.querySelector('strong')!.style.color).toContain('var(--color-brand-1)')
  })

  it('DataBoundary 摘要短语用 LeadText；方法学用 SectionTitle as=p 保留 mt-2 text-xs', () => {
    const { container } = render(<DataBoundary data={data} method="规则分位法" />)
    const summary = screen.getByText(/以下 10 个维度离线缺真值/)
    expect(summary.textContent).toBe('以下 10 个维度离线缺真值，一律剔除、不编造')
    const strong = summary.querySelector('strong')!
    expect(strong.textContent).toBe('一律剔除、不编造')
    expect(strong.style.color).toContain('var(--color-brand-1)')

    const method = screen.getByText(/方法学/)
    expect(method.tagName).toBe('P')
    expect(method.textContent).toBe('📐 方法学：规则分位法')
    expect(method.className).toContain('mt-2')
    expect(method.className).toContain('text-xs')
    // 字号唯一：不得再叠加 text-body（CSS 中 .text-body 后置会把 12px 顶成 13px）
    expect(method.className.match(/text-xs/g)?.length).toBe(1)
    expect(method.className).not.toContain('text-body')
    expect(method.style.borderColor).toContain('var(--color-brand-2)')
    expect(container.querySelector('strong[style]')).toBeTruthy()
  })
})
