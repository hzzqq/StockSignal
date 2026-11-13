// @vitest-environment jsdom
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { handlers, resetChatMock } from '@/mocks/handlers'
import {
  submitAiConsult,
  getAiConsultTask,
  cancelAiConsult,
  listConversations,
  createConversation,
  getConversationMessages,
  saveConversationMessages,
  deleteConversation,
  exportConversationJson,
  exportConversationMarkdown,
} from '@/api/chat'

/**
 * 星辰 AI API 层 × MSW 契约测试（§10 第 2-3 步落地验证）。
 *
 * 不渲染组件：纯校验 apiFetch + Zod 严格校验 + MSW 任务轮询态 / 多会话 CRUD / 导出
 * 的真实链路。覆盖：
 *  - ai_consult 提交 → 轮询（首次 running、二次 success 带样例结果）
 *  - 多会话 列表/新建/读取/保存（仅 user/assistant 落库）/删除
 *  - 导出 json（信封 data）/ markdown（原始文本，非 JSON 信封）
 *  - 缺会话导出 404 → 抛错
 */
const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  server.resetHandlers()
  resetChatMock()
  localStorage.clear()
})
afterAll(() => server.close())

beforeAll(() => {
  // 模拟已登录态（Bearer 头；Mock 不校验，仅满足 client.ts tokenStore 读取）
  localStorage.setItem('ss_token', 'mock-access-token')
})

describe('chat API · ai_consult 任务流转', () => {
  it('提交 → 首次轮询 running、二次轮询 success 带样例研判', async () => {
    const taskId = await submitAiConsult({ question: '分析一下贵州茅台' })
    expect(typeof taskId).toBe('string')
    expect(taskId.startsWith('mock-ai-consult-')).toBe(true)

    const first = await getAiConsultTask(taskId)
    expect(first.status).toBe('running')

    const second = await getAiConsultTask(taskId)
    expect(second.status).toBe('success')
    expect(second.result).toBeTypeOf('object')
    const result = second.result as { answer: string; independent: boolean }
    expect(result.independent).toBe(true)
    expect(result.answer).toContain('贵州茅台')
    // 引用徽标 [S#] 透传（供前端 Markdown 渲染测试）
    expect(result.answer).toContain('[S1]')
  })

  it('取消任务返回 ok（无异常）', async () => {
    const taskId = await submitAiConsult({ question: 'hello' })
    await expect(cancelAiConsult(taskId)).resolves.toBeUndefined()
  })
})

describe('chat API · 多会话 CRUD', () => {
  it('列表含种子会话；新建后出现在列表；读取消息；保存仅落库 user/assistant', async () => {
    const list0 = await listConversations()
    expect(list0.conversations.length).toBeGreaterThanOrEqual(1)
    expect(list0.conversations.some((c) => c.id === 1)).toBe(true)

    const created = await createConversation('测试会话')
    expect(created.id).toBeGreaterThan(1)

    const list1 = await listConversations()
    expect(list1.conversations.some((c) => c.id === created.id)).toBe(true)

    // 读取种子会话消息（2 条：user + assistant）
    const msgs = await getConversationMessages(1)
    expect(msgs.messages.length).toBe(2)
    expect(msgs.messages[0].role).toBe('user')

    // 保存：tool 角色不落库，仅 user/assistant 保留
    await saveConversationMessages(created.id, [
      { role: 'user', content: 'q1', ts: 1 },
      { role: 'assistant', content: 'a1', ts: 2 },
      { role: 'tool', content: 'intent', ts: 3 },
    ])
    const saved = await getConversationMessages(created.id)
    expect(saved.messages.length).toBe(2)
    expect(saved.messages.map((m) => m.role).sort()).toEqual(['assistant', 'user'])
  })

  it('删除会话后列表不再包含', async () => {
    const created = await createConversation('待删除')
    await deleteConversation(created.id)
    const list = await listConversations()
    expect(list.conversations.some((c) => c.id === created.id)).toBe(false)
  })
})

describe('chat API · 导出', () => {
  it('json 导出返回信封 data（messages 数组）', async () => {
    const data = await exportConversationJson(1)
    expect(data.id).toBe(1)
    expect(Array.isArray(data.messages)).toBe(true)
  })

  it('markdown 导出返回原始文本（含标题与引用徽标）', async () => {
    const md = await exportConversationMarkdown(1)
    expect(typeof md).toBe('string')
    expect(md).toContain('# 贵州茅台 研判')
    expect(md).toContain('[S1]')
  })

  it('导出不存在会话 → 抛错（404）', async () => {
    await expect(exportConversationMarkdown(99999)).rejects.toThrow()
    await expect(exportConversationJson(99999)).rejects.toThrow()
  })
})
