import { render, screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThesisEvidenceView } from './ThesisEvidence'

vi.mock('@/api/read', () => ({ getThesisEvidence: vi.fn() }))
import { getThesisEvidence } from '@/api/read'
const mocked = vi.mocked(getThesisEvidence)

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const full = {
  findings: {
    core_innovation_cn: '决策闭环为创新主轴，三算法为诚实实验证据而非生产信号',
    decision_closure_anchor: { accuracy: 0.491, n: 3507, n_hit: 1722 },
    findings: {
      transformer_signal: {
        title: '#1 纯 Transformer 对照 GRUAttention', verdict: 'modest_positive',
        direction_hit: 0.5130, direction_hit_baseline: 0.5097,
        ic: 0.0465, icir: 0.3796, provenance: 'walk-forward 2022–2026',
      },
      gnn_factor: {
        title: '#2 GNN 板块-个股传导因子', verdict: 'negative',
        direction_hit: 0.4948, direction_hit_baseline: 0.5097,
        provenance: 'head-to-head n=1,583,338',
      },
      rl_position: {
        title: '#3 RL 仓位决策', verdict: 'negative',
        sharpe: -0.741, sharpe_baseline_tanh: 1.145, provenance: 'RL 对照',
      },
    },
    asymmetric_finding: {
      defensive_total_pp: 9.5, offensive_total_pp: -8.0, annualized_offensive_cost_pp: -0.5,
      note: '闭环是风险缩放器而非收益放大器', provenance: '§5.4.3',
    },
    honest_redline: '负向如实记录，不包装成碾压式领先',
  },
  ch6: {
    available: true,
    metrics: {
      snapshot_count: 41, snapshot_date_range: ['2026-08-31', '2026-11-23'],
      prediction_count: 41, prediction_scored: 24, prediction_hit_rate: 0.375,
      note: '样本量小时如实标注，不推断统计显著性',
    },
    note: null,
  },
  shap_attribution: {
    available: true, baseline: 50,
    adjustments: { '方向调节': 8, '周期调节': 5 }, adjustments_total: 13,
    final_running: 63, as_of: '2026-11-27', reason: null,
  },
  note: '三算法为对照实验证据而非生产信号；modest/负向如实记录。',
}

beforeEach(() => {
  mocked.mockReset()
  mocked.mockResolvedValue(full as never)
})

describe('ThesisEvidenceView · 毕设证据转向 v2', () => {
  it('四块内容齐全：闭环锚 49.1% / 三算法 / 第6章 / SHAP / 非对称', async () => {
    renderWithClient(<ThesisEvidenceView />)
    expect(await screen.findByText('49.1%')).toBeTruthy()
    expect(screen.getByText('1722/3507')).toBeTruthy()
    expect(screen.getByText('#1 纯 Transformer 对照 GRUAttention')).toBeTruthy()
    expect(screen.getByText('#2 GNN 板块-个股传导因子')).toBeTruthy()
    expect(screen.getByText('#3 RL 仓位决策')).toBeTruthy()
    expect(screen.getByText('41')).toBeTruthy()
    expect(screen.getByText('37.5%')).toBeTruthy()
    expect(screen.getByText('63')).toBeTruthy()  // SHAP final_running
    expect(screen.getByText('闭环是风险缩放器而非收益放大器')).toBeTruthy()
    expect(mocked).toHaveBeenCalledTimes(1)
  })

  it('负向结果如实标 negative：#2/#3 显示「负向」，不包装成突破', async () => {
    renderWithClient(<ThesisEvidenceView />)
    expect(await screen.findAllByText('负向')).toHaveLength(2)
    // 小幅占优也如实标注，不写成碾压
    expect(screen.getByText('小幅占优')).toBeTruthy()
  })

  it('口径声明原文展示（实验证据非生产信号）', async () => {
    renderWithClient(<ThesisEvidenceView />)
    expect(await screen.findByText(/三算法为对照实验证据而非生产信号/)).toBeTruthy()
    expect(screen.getByText(/负向如实记录，不包装成碾压式领先/)).toBeTruthy()
  })

  it('ch6 缺失：诚实空态，不编造 41 快照', async () => {
    mocked.mockResolvedValue({
      ...full,
      ch6: { available: false, metrics: null, note: '第6章评估文件缺失或不可解析，未做任何填充' },
      shap_attribution: { available: false, reason: '归因不可用：决策快照缺失', baseline: null, adjustments: {} },
    } as never)
    renderWithClient(<ThesisEvidenceView />)
    expect(await screen.findByText(/第6章评估文件缺失或不可解析，未做任何填充/)).toBeTruthy()
    expect(screen.getByText(/归因不可用：决策快照缺失/)).toBeTruthy()
    expect(document.body.textContent).not.toMatch(/NaN|undefined/)
  })

  it('error → 错误态可重试，不伪装成空数据', async () => {
    mocked.mockRejectedValue(new Error('证据加载失败'))
    renderWithClient(<ThesisEvidenceView />)
    expect(await screen.findByText('证据加载失败')).toBeTruthy()
    expect(screen.getByRole('button', { name: /重试/ })).toBeTruthy()
  })
})
