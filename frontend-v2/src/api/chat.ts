import { z } from 'zod'
import { apiFetch, ApiError } from './client'
import { apiMutate } from './write'
import {
  AiConsultSubmitSchema,
  AiResearchSubmitSchema,
  TaskSubmitResultSchema,
  AiConsultTaskSchema,
  type AiConsultTask,
  ConversationListSchema,
  type ConversationList,
  ConversationSchema,
  type Conversation,
  ConversationMessagesSchema,
  type ConversationMessages,
  ConversationExportJsonSchema,
  type ConversationExportJson,
  ChatHistorySchema,
  type ChatHistory,
  WireMessageSchema,
  type WireMessage,
} from './schemas/chat'

const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'

/**
 * 星辰 AI API 客户端（对齐 modules/background_tasks.py + backend/tasks/worker.py）。
 *
 * 设计：每个函数先 `apiFetch<unknown>` 取信封 data（已由 client 解包），再用专用
 * Zod schema `parse` 严格校验；缺失/类型不符即抛错（不兜底），与 admin.ts 同红线。
 * 路径斜杠与查询参数按契约精确拼接，不整体 encodeURIComponent。
 */

/** POST /api/tasks/ —— 提交 ai_consult 后台任务，返回 task_id */
export async function submitAiConsult(input: z.input<typeof AiConsultSubmitSchema>): Promise<string> {
  const body = AiConsultSubmitSchema.parse(input)
  const data = await apiFetch<unknown>('/tasks/', {
    method: 'POST',
    body: JSON.stringify({ type: 'ai_consult', payload: body }),
  })
  const parsed = TaskSubmitResultSchema.parse(data)
  return parsed.task_id
}

/** POST /api/tasks/ —— 提交 ai_research 深度研究任务（多步工具调用 + 引用溯源）。
 *  后端已允许该类型（task_routes._ALLOWED_TASK_TYPES），payload 仅需为对象。 */
export async function submitAiResearch(input: z.input<typeof AiResearchSubmitSchema>): Promise<string> {
  const body = AiResearchSubmitSchema.parse(input)
  // 新增写操作必须走统一写层，不搭 chat.ts 历史遗留豁免的便车
  const parsed = await apiMutate(
    '/tasks/',
    'POST',
    { type: 'ai_research', payload: body },
    TaskSubmitResultSchema,
  )
  return parsed.task_id
}

/** GET /api/tasks/<id> —— 轮询 ai_consult 任务态 */
export async function getAiConsultTask(taskId: string): Promise<AiConsultTask> {
  const data = await apiFetch<unknown>(`/tasks/${taskId}`)
  return AiConsultTaskSchema.parse(data)
}

/** DELETE /api/tasks/<id> —— 取消 ai_consult 任务（后端仅标记 CANCELLED，文案如实「已停止等待」） */
export async function cancelAiConsult(taskId: string): Promise<void> {
  await apiFetch<unknown>(`/tasks/${taskId}`, { method: 'DELETE' })
}

/** GET /api/chat/conversations —— 会话列表；404/错误由调用方回退旧单记录模式 */
export async function listConversations(): Promise<ConversationList> {
  const data = await apiFetch<unknown>('/chat/conversations')
  return ConversationListSchema.parse(data)
}

/** POST /api/chat/conversations —— 新建会话（title 空则后端兜底「新对话」） */
export async function createConversation(title = '新对话'): Promise<Conversation> {
  const data = await apiFetch<unknown>('/chat/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title || '新对话' }),
  })
  return ConversationSchema.parse(data)
}

/** GET /api/chat/conversations/<id> —— 读取会话消息（容忍字段缺失） */
export async function getConversationMessages(convId: number): Promise<ConversationMessages> {
  const data = await apiFetch<unknown>(`/chat/conversations/${convId}`)
  return ConversationMessagesSchema.parse(data)
}

/**
 * POST /api/chat/conversations/<id> —— 覆盖保存会话消息。
 * 落库归一化：仅持久化 user/assistant（tool 意图卡不落库，每次会话客户端重建）；
 * 入参按 WireMessageSchema 严格校验，非法项直接抛错（不静默丢弃）。
 */
export async function saveConversationMessages(convId: number, messages: WireMessage[]): Promise<void> {
  const clean = z.array(WireMessageSchema).parse(messages)
  const payload = clean
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role, content: m.content }))
  await apiFetch<unknown>(`/chat/conversations/${convId}`, {
    method: 'POST',
    body: JSON.stringify({ messages: payload }),
  })
}

/**
 * PATCH /api/chat/conversations/<id> —— 重命名会话标题。
 *
 * 后端统一 ok 信封解包后，data 顶层含 {id, title}（额外键如 ok/count 由 Zod 剥离）。
 * 说明：此处直接用 apiFetch 而非统一写层 apiMutate —— 后者 WriteMethod 仅含
 * POST/PUT/DELETE，且本批次前端改动范围不含 write.ts，故沿用 chat.ts 既有的
 * apiFetch 直连写惯例；鉴权/401 单飞刷新/失败抛 ApiError 完全一致。
 */
const RenameConversationResultSchema = z.object({
  id: z.number().int(),
  title: z.string(),
})
export type RenameConversationResult = z.infer<typeof RenameConversationResultSchema>

export async function renameConversation(
  cid: number,
  title: string,
): Promise<RenameConversationResult> {
  const data = await apiFetch<unknown>(`/chat/conversations/${cid}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })
  return RenameConversationResultSchema.parse(data)
}

/** DELETE /api/chat/conversations/<id> —— 删除会话 */
export async function deleteConversation(convId: number): Promise<void> {
  await apiFetch<unknown>(`/chat/conversations/${convId}`, { method: 'DELETE' })
}

/** GET /api/chat/conversations/<id>/export?format=json —— 导出为结构化 JSON */
export async function exportConversationJson(convId: number): Promise<ConversationExportJson> {
  const data = await apiFetch<unknown>(`/chat/conversations/${convId}/export?format=json`)
  return ConversationExportJsonSchema.parse(data)
}

/**
 * GET /api/chat/conversations/<id>/export?format=markdown —— 导出为 markdown 原文。
 * 后端返回 text/markdown 原始字节（非 JSON 信封），故走 raw fetch：复用 Bearer 头，
 * 但不接 401 自动刷新（导出为非核心路径，失败直接提示重新登录更清晰）。
 */
export async function exportConversationMarkdown(convId: number): Promise<string> {
  const token =
    typeof localStorage !== 'undefined' ? localStorage.getItem('ss_token') : null
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`${BASE}/chat/conversations/${convId}/export?format=markdown`, {
    method: 'GET',
    credentials: 'include',
    headers,
  })
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      throw new ApiError('unauthorized', '登录已过期，请重新登录')
    }
    if (res.status === 404) {
      throw new ApiError('not_found', '会话不存在或已删除')
    }
    throw new ApiError('export_failed', `导出失败（HTTP ${res.status}）`)
  }
  return await res.text()
}

/**
 * GET /api/chat/history —— 旧单记录模式兜底。
 * 仅在 listConversations 返回 404（后端未迁移多会话接口）时由 store 回退调用，
 * 拉取单条历史记录转为本地会话，避免白屏（诚实降级，非错误）。
 */
export async function getChatHistory(): Promise<ChatHistory> {
  const data = await apiFetch<unknown>('/chat/history')
  return ChatHistorySchema.parse(data)
}
