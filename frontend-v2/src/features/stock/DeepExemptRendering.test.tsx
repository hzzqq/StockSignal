// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { DeepBody } from './ResearchView'
import type { ResearchDeep } from '@/api/schemas/stock'

/**
 * 「深度分析」tab 诚实红线守卫。
 *
 * deep_analysis_available=false 只表示「旧版 56 键 analysis_engine 异步分析未接入」，
 * 不得借此把后端已如实返回的轻量同步技术字段（price/pe_ttm/market_cap/ma5/...）
 * 全部藏掉。正确行为：真实字段表照常在前，诚实说明追加在后；缺源 null 显示「—」不补 0。
 */
const EXEMPT_NOTE = '56 键深度分析（旧版 analysis_engine 异步任务）V2 暂未接入，可走 /legacy 查看旧版'

/** 真后端 research-deep(600519) 的形态：有技术字段 + 诚实标注未接入 + 两处 null。 */
const dataWithTech: ResearchDeep = {
  code: '600519',
  name: '贵州茅台',
  date: '2026-11-06',
  deep_analysis_available: false,
  price: 1523,
  pe_ttm: 28.1,
  ma5: 1508,
  ma20: 1476,
  amplitude: 2.21,
  pb: null,
  turnover: null,
  note: '轻量同步技术面已返回',
}

function fieldRow(key: string): HTMLElement {
  const th = screen.getByText(key)
  const row = th.closest('tr')
  if (!row) throw new Error(`field row ${key} not found`)
  return row
}

describe('DeepBody · 未接入态不得藏起真实技术字段（诚实红线）', () => {
  it('⚠️ deep_analysis_available=false 且含 price/ma5/ma20 → 字段行必须渲染', () => {
    // mutation 反证：若仍按旧逻辑短路只显示豁免卡，则查不到 table / price 行，本例红。
    render(<DeepBody data={dataWithTech} />)

    expect(screen.getByRole('table')).toBeTruthy()
    for (const k of ['price', 'ma5', 'ma20', 'amplitude']) {
      expect(fieldRow(k), `字段 ${k} 应渲染`).toBeTruthy()
    }
    expect(within(fieldRow('price')).getByText('1523')).toBeTruthy()
    expect(within(fieldRow('ma5')).getByText('1508')).toBeTruthy()
  })

  it('⚠️ 同一情形仍显示诚实说明文案（不因展示数据而丢掉「未接入」标注）', () => {
    render(<DeepBody data={dataWithTech} />)

    expect(screen.getByText(EXEMPT_NOTE)).toBeTruthy()
    expect(screen.getByText('已预选 code：600519')).toBeTruthy()
    // 说明在字段表下方（DOM 顺序：table 先、说明段落后）。
    const table = screen.getByRole('table')
    const note = screen.getByText(EXEMPT_NOTE)
    expect(table.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('deep_analysis_available 缺失且无任何技术字段 → 只显示诚实说明/空态，不伪造数据', () => {
    const data: ResearchDeep = { code: '600519', name: '贵州茅台', date: null, note: null }
    render(<DeepBody data={data} />)

    expect(screen.getByText(EXEMPT_NOTE)).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('cell')).toBeNull()
    expect(screen.queryByText('—')).toBeNull()
  })

  it('pb:null / turnover:null → 渲染为「—」，不显示 0、不编造', () => {
    render(<DeepBody data={dataWithTech} />)

    const pbRow = fieldRow('pb')
    const turnoverRow = fieldRow('turnover')
    expect(within(pbRow).getByText('—')).toBeTruthy()
    expect(within(turnoverRow).getByText('—')).toBeTruthy()
    expect(within(pbRow).queryByText('0')).toBeNull()
    expect(within(turnoverRow).queryByText('0')).toBeNull()
  })
})
