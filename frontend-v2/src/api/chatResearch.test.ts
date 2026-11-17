// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { submitAiResearch } from './chat'
import { apiFetch } from './client'
import { AiResearchSubmitSchema } from './schemas/chat'

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
})
