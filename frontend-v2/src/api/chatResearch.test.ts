// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { submitAiResearch } from './chat'
import { apiFetch } from './client'
import {
  AiResearchSubmitSchema,
  AiConsultTaskSchema,
  TaskLogSchema,
} from './schemas/chat'

vi.mock('./client', () => ({ apiFetch: vi.fn() }))
const fetchMock = vi.mocked(apiFetch)

beforeEach(() => { fetchMock.mockReset() })

describe('submitAiResearch · 07 AI Copilot 深度研究接线', () => {
  it('payload 精确对齐后端 worker 契约（type=ai_research + 默认 max_steps=8/style=report）', async () => {
    fetchMock.mockResolvedValue({ task_id: 't-123' } as never)
    const id = await submitAiResearch({ question: '分析茅台风险' })
    expect(id).toBe('t-123')
    expect(fetchMock).toHaveBeenCalledWith('/tasks/', {
      method: 'POST',
      body: JSON.stringify({
        type: 'ai_research',
        payload: { question: '分析茅台风险', max_steps: 8, style: 'report' },
      }),
    })
  })

  it('history 超过 8 条 → Zod 拒绝，零请求（防上下文膨胀打爆后端）', async () => {
    await expect(submitAiResearch({
      question: 'q',
      history: Array.from({ length: 9 }, () => ({ role: 'user', content: 'x' })),
    })).rejects.toThrow()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('max_steps 超过 8 → Zod 拒绝（与 worker 上限一致）', () => {
    expect(() => AiResearchSubmitSchema.parse({ question: 'q', max_steps: 9 })).toThrow()
  })

  it('非法 style → Zod 拒绝（不接受 debate/teach，research 合成只认 quick/report）', () => {
    expect(() => AiResearchSubmitSchema.parse({ question: 'q', style: 'debate' })).toThrow()
  })

  // 以下两例锁定「提交 → 轮询 → 正文回填」闭环：submit 用新 schema，但轮询仍走
  // ai_consult 的 AiConsultTaskSchema。若后端 research 返回结构或 progress_bus
  // 规范化变化，这里先红，避免用户看到「提交成功但正文空白 / 轮询失败」。
  it('research 成功任务态可被轮询 schema 解析，answer 正文不丢', () => {
    // 真值：modules/research_agent.py:_envelope 的 8 个键
    const task = AiConsultTaskSchema.parse({
      task_id: 't-research-1',
      task_type: 'ai_research',
      status: 'success',
      result: {
        question: '分析茅台风险',
        status: 'ok',
        steps: [],
        answer: '## 结论\n研究正文',
        citations: [],
        limitations: [],
        generated_at: '2026-11-17 12:00:00',
        elapsed_s: 1.2,
      },
    })
    expect((task.result as { answer?: string } | null)?.answer).toContain('研究正文')
  })

  it('research 结构化进度事件可被日志 schema 解析（progress_bus dict 规范化）', () => {
    // 真值：backend/tasks/progress_bus.py report() 对 dict 产出 stage/message/event
    const log = TaskLogSchema.parse({
      stage: 'research',
      message: '▶ [1/8] 调 fin_data…',
      ts: 1763304000, // 真值：worker.py reporter 追加日志时补 time.time()
      event: {
        type: 'tool_start', tool: 'fin_data', idx: 1, total: 8,
        _fmt: '▶ [1/8] 调 fin_data…',
      },
    })
    expect(log.stage).toBe('research')
    expect(log.message).toBe('▶ [1/8] 调 fin_data…')
  })
})
