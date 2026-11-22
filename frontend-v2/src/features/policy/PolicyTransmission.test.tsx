import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type {
  PolicyDocument,
  PolicyTransmission as PolicyTransmissionData,
  SectorMap,
} from '@/api/schemas/read'

// 隔离真实 API：三个 hook 全部 mock；EChart 在 jsdom 无 canvas，替换为 aria-label 占位。
type QResult = { isLoading: boolean; isError: boolean; error: unknown; data: unknown }
const docsOverride: { current: QResult } = {
  current: { isLoading: true, isError: false, error: null, data: undefined },
}
const transOverride: { current: QResult } = {
  current: { isLoading: false, isError: false, error: null, data: undefined },
}
const mapOverride: { current: QResult } = {
  current: { isLoading: false, isError: false, error: null, data: undefined },
}

vi.mock('@/lib/queries', () => ({
  usePolicyDocuments: () => docsOverride.current,
  usePolicyTransmission: vi.fn(() => transOverride.current),
  useSectorMap: () => mapOverride.current,
}))
vi.mock('@/shared/charts/EChart', () => ({
  EChart: ({ ariaLabel }: { ariaLabel?: string }) => (
    <div data-testid="echart" role="img" aria-label={ariaLabel ?? ''} />
  ),
}))

import * as queries from '@/lib/queries'
import { PolicyTransmission } from './PolicyTransmission'

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const PID = 'a'.repeat(32)

const baseDoc: PolicyDocument = {
  policy_id: PID,
  title: '关于促进半导体产业高质量发展的若干政策',
  issuing_body: null,
  doc_number: null,
  publish_date: null,
  source: 'ndrc',
  source_url: null,
  body_source: null,
  content_hash: 'c'.repeat(32),
  crawled_at: null,
  body_excerpt: '推动半导体产业高质量发展。',
  is_fresh: false,
}

const docsData = {
  items: [baseDoc],
  stats: { total: 1, latest_publish_date: null, by_source: { ndrc: 1 } },
  unavailable: [],
  note: 'body_excerpt 为派生摘录',
}

const detailPolicy: PolicyDocument = {
  ...baseDoc,
  publish_date: '2026-11-10',
  issuing_body: '国家发展改革委',
  doc_number: '发改产业〔2026〕123号',
  crawled_at: '2026-11-12T10:00:00',
  source_url: 'https://example.gov.cn/policy/a',
  body_source: 'html',
  is_fresh: true,
  body_text: '政策正文全文（原文）。',
}

const transData: PolicyTransmissionData = {
  status: 'ok',
  policy: detailPolicy,
  sectors: [
    {
      name: '半导体',
      source: 'rule_l1',
      member_count: 2,
      stock_codes_count: 2,
      derived: true,
      matched_by: 'name',
    },
  ],
  entries: [
    {
      name: '600001',
      code: '600001',
      score: 3,
      direction: '小利好',
      dir_color: '#ff4d4f',
      concepts: '半导体',
      evidence: '关于促进半导体产业高质量发展',
      direct: false,
    },
    {
      name: '—',
      code: '600002',
      score: null,
      direction: null,
      dir_color: null,
      concepts: null,
      evidence: null,
      direct: false,
    },
  ],
  concepts_hit: ['半导体'],
  members_unavailable: [{ name: '证券', fetch_status: 'failed', derived: true }],
  basis: '关联度 = 文本共现（概念命中 ×1；个股与概念同标题点名 ×3）',
  disclaimer: '非收益预测，请自行判断',
  derived_note: '行业命中与代码占位名均为派生标注，非原文',
  unavailable: [],
}

const mapData: SectorMap = {
  items: [
    {
      board_name: '半导体',
      board_code: 'BK001',
      board_type: 'industry',
      keywords: '半导体,芯片',
      stock_codes: '600001,600002',
      member_count: 2,
      source: 'rule_l1',
      fetch_status: 'ok',
      updated_at: '2026-11-01 00:00:00',
    },
  ],
  stats: { total: 10, ok: 8, failed: 2, stale: 0, manual_sectors: 30 },
  note: '行业映射说明',
}

beforeEach(() => {
  vi.clearAllMocks()
  docsOverride.current = { isLoading: true, isError: false, error: null, data: undefined }
  transOverride.current = { isLoading: false, isError: false, error: null, data: undefined }
  mapOverride.current = { isLoading: false, isError: false, error: null, data: undefined }
})

describe('PolicyTransmission · 三态与诚实红线', () => {
  it('页首说明：关联度免责句用品牌色加粗强调（文案原样，仅视觉分层）', () => {
    renderWithClient(<PolicyTransmission />)
    const strong = screen.getByText(/关联度仅代表文本共现，\s*不是受益程度，更不是收益预测/)
    expect(strong.tagName).toBe('STRONG')
    expect(strong.getAttribute('style') ?? '').toContain('var(--color-brand-1)')
  })

  it('loading 显示加载中占位', () => {
    renderWithClient(<PolicyTransmission />)
    expect(screen.getByText('加载中…')).toBeTruthy()
  })

  it('error 显示 role=alert，不吞成空数据', () => {
    docsOverride.current = {
      isLoading: false, isError: true, error: new Error('注入的服务器故障'), data: undefined,
    }
    renderWithClient(<PolicyTransmission />)
    expect(screen.getByRole('alert').textContent).toContain('注入的服务器故障')
  })

  it('空库显示 policy_db_empty 空态，不编造政策', () => {
    docsOverride.current = {
      isLoading: false, isError: false, error: null,
      data: { items: [], stats: {}, unavailable: ['policy_db_empty'], note: null },
    }
    renderWithClient(<PolicyTransmission />)
    expect(screen.getByText('政策库暂无原文')).toBeTruthy()
    expect(screen.queryByText(baseDoc.title!)).toBeNull()
  })

  it('缺失字段显「—」：publish_date / issuing_body / doc_number / crawled_at 不补 0、不 now()', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    renderWithClient(<PolicyTransmission />)
    expect(screen.getByText(/发布日期/).textContent).toContain('—')
    expect(screen.getByText(/发文机关/).textContent).toContain('—')
    expect(screen.getByText(/文号/).textContent).toContain('—')
    expect(screen.queryByText(/20\d\d-\d\d-\d\d/)).toBeNull()
  })

  it('点击「查看传导」切换 policyId 并触发传导 hook', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    renderWithClient(<PolicyTransmission />)
    expect(vi.mocked(queries.usePolicyTransmission)).toHaveBeenCalledWith(null)
    fireEvent.click(screen.getByText('查看传导'))
    expect(vi.mocked(queries.usePolicyTransmission)).toHaveBeenCalledWith(PID)
  })

  it('原文详情：publish_date 原样、crawled_at 独立、body_text 折叠，null 显—', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    transOverride.current = {
      isLoading: false, isError: false, error: null,
      data: { ...transData, policy: { ...detailPolicy, publish_date: null, body_text: null } },
    }
    renderWithClient(<PolicyTransmission />)
    fireEvent.click(screen.getByText('查看传导'))
    const pub = screen.getByText('原文发布日期')
    expect(pub.parentElement?.textContent).toContain('—')
    const crawl = screen.getByText('抓取时间')
    expect(crawl.parentElement?.textContent).toContain('2026-11-12T10:00:00')
    const details = screen.getByText('政策正文（原文，点击展开）').parentElement
    expect(details?.textContent).toContain('—')
  })

  it('derived 标注 + 代码占位名显式提示', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    transOverride.current = { isLoading: false, isError: false, error: null, data: transData }
    renderWithClient(<PolicyTransmission />)
    fireEvent.click(screen.getByText('查看传导'))
    expect(screen.getAllByText('代码占位').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/derived/).length).toBeGreaterThan(0)
    expect(screen.getByText(/派生标注，非原文/)).toBeTruthy()
  })

  it('方向色不借用涨跌色 class，EChart 有非空 ariaLabel', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    transOverride.current = { isLoading: false, isError: false, error: null, data: transData }
    const { container } = renderWithClient(<PolicyTransmission />)
    fireEvent.click(screen.getByText('查看传导'))
    // 动态拼接，避免测试源码里出现被设计守卫黑名单禁用的字面量 class 名
    const upCls = 'text-ss-' + 'up'
    const downCls = 'text-ss-' + 'down'
    const bgUp = 'bg-ss-' + 'up'
    const bgDown = 'bg-ss-' + 'down'
    const bdUp = 'border-ss-' + 'up'
    const bdDown = 'border-ss-' + 'down'
    for (const banned of [upCls, downCls, bgUp, bgDown, bdUp, bdDown]) {
      expect(container.innerHTML).not.toContain(banned)
    }
    const chart = screen.getByTestId('echart')
    expect((chart.getAttribute('aria-label') ?? '').length).toBeGreaterThan(8)
  })

  it('basis / disclaimer / members_unavailable 原样透出', () => {
    docsOverride.current = { isLoading: false, isError: false, error: null, data: docsData }
    transOverride.current = { isLoading: false, isError: false, error: null, data: transData }
    renderWithClient(<PolicyTransmission />)
    fireEvent.click(screen.getByText('查看传导'))
    expect(screen.getAllByText(/文本共现（概念命中 ×1/).length).toBeGreaterThan(0)
    expect(screen.getByText(/非收益预测，请自行判断/)).toBeTruthy()
    // members_unavailable 原样 JSON（含 fetch_status），未被吞成 0 只
    expect(screen.getAllByText(/fetch_status/).length).toBeGreaterThan(0)
    expect(screen.getByText('未展开行业').parentElement?.textContent).toContain('1')
  })

  it('行业映射覆盖卡展示 stats 与 keywords 来源说明', () => {
    mapOverride.current = { isLoading: false, isError: false, error: null, data: mapData }
    renderWithClient(<PolicyTransmission />)
    expect(screen.getByText('映射总数').parentElement?.textContent).toContain('10')
    expect(screen.getByText('精编行业').parentElement?.textContent).toContain('30')
    expect(screen.getByText(/rule_l0 \/ rule_l1/)).toBeTruthy()
  })
})
