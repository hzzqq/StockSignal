import { z } from 'zod'

/**
 * 星辰 AI（53_星辰AI）前端契约（对齐后端实测，非推测）。
 *
 * 严格解析、禁止 `??` 兜底：字段缺失/类型不符即抛错，由页面渲染错误态（红线）。
 * 真实来源：
 *  - ai_consult 任务结果 = modules/ai_engine.py:714 ai_answer 返回 {answer, independent, specialist?}
 *  - 任务轮询态      = backend/tasks/worker.py Task.to_dict
 *  - 对话持久化      = modules/background_tasks.py（灵活 dict，保存归一化为 {role, content}）
 */

/** ai_consult 后台任务状态（backend/tasks/worker.py TaskStatus） */
export const TaskStatusSchema = z.enum(['pending', 'running', 'success', 'error', 'cancelled'])
export type TaskStatus = z.infer<typeof TaskStatusSchema>

/** ai_consult 单个进度日志条目（Task.to_dict.logs[i]） */
export const TaskLogSchema = z.object({
  stage: z.string(),
  message: z.string(),
  ts: z.number(),
})
export type TaskLog = z.infer<typeof TaskLogSchema>

/**
 * ai_consult 后台任务对象（GET /api/tasks/<id> 解包后的 data）。
 * success 时 result = AiConsultResultSchema。
 */
export const AiConsultTaskSchema = z.object({
  task_id: z.string(),
  task_type: z.string(),
  status: TaskStatusSchema,
  progress: z.number().optional(),
  stage: z.string().optional(),
  logs: z.array(TaskLogSchema).optional(),
  result: z.unknown().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at: z.number().optional(),
  updated_at: z.number().optional(),
})
export type AiConsultTask = z.infer<typeof AiConsultTaskSchema>

/** ai_answer 真实返回（modules/ai_engine.py:714-873）—— 后端不产出结构化分析卡 */
export const AiConsultResultSchema = z.object({
  answer: z.string(),
  independent: z.boolean(),
  specialist: z.string().optional(),
})
export type AiConsultResult = z.infer<typeof AiConsultResultSchema>

/** 提交 ai_consult 的入参（下发至 backend/tasks/worker.py:_handle_ai_consult） */
export const AiConsultSubmitSchema = z.object({
  question: z.string().min(1, '问题不能为空'),
  context: z.record(z.string(), z.unknown()).optional(),
  style: z.enum(['quick', 'report', 'debate', 'teach']).default('quick'),
  model: z.string().optional(),
})
export type AiConsultSubmit = z.infer<typeof AiConsultSubmitSchema>

/** 提交任务返回（POST /api/tasks/ 解包后的 data） */
export const TaskSubmitResultSchema = z.object({
  task_id: z.string(),
})
export type TaskSubmitResult = z.infer<typeof TaskSubmitResultSchema>

/** 会话列表项（GET /api/chat/conversations 的 data.conversations[i]） */
export const ConversationSchema = z.object({
  id: z.number().int(),
  title: z.string(),
  updated_at: z.string().optional(),
  created_at: z.string().optional(),
  message_count: z.number().int().optional(),
})
export type Conversation = z.infer<typeof ConversationSchema>

export const ConversationListSchema = z.object({
  conversations: z.array(ConversationSchema),
})
export type ConversationList = z.infer<typeof ConversationListSchema>

/**
 * 线上消息格式（v1 pages/53_星辰AI.py 实测落库字段，灵活）。
 * 保存时归一化为 {role, content}（仅 user/assistant 持久化）；读取容忍 ts/chips 缺失。
 */
export const WireMessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'tool', 'research']),
  content: z.string(),
  ts: z.number().optional(),
  chips: z.array(z.string()).optional(),
  tool: z.string().optional(),
  payload: z.unknown().optional(),
})
export type WireMessage = z.infer<typeof WireMessageSchema>

/** 会话消息列表响应（GET /api/chat/conversations/<id> 解包后的 data） */
export const ConversationMessagesSchema = z.object({
  id: z.number().int(),
  title: z.string().optional(),
  messages: z.array(WireMessageSchema),
})
export type ConversationMessages = z.infer<typeof ConversationMessagesSchema>

/** 导出 json 格式（GET .../export?format=json 解包后的 data） */
export const ConversationExportJsonSchema = z.object({
  id: z.number().int().optional(),
  title: z.string().optional(),
  messages: z.array(WireMessageSchema).optional(),
  markdown: z.string().optional(),
})
export type ConversationExportJson = z.infer<typeof ConversationExportJsonSchema>

/**
 * 旧单记录模式（GET /api/chat/history 解包后的 data）——仅作 404 回退路径。
 * 真后端若未迁移多会话接口，前端回退到此单条历史记录，避免白屏（诚实降级，非错误）。
 */
export const ChatHistorySchema = z.object({
  messages: z.array(
    z.object({
      role: z.string(),
      content: z.string(),
      ts: z.number().optional(),
    }),
  ),
})
export type ChatHistory = z.infer<typeof ChatHistorySchema>

// ---------------------------------------------------------------------------
// v2 内部判别消息模型（前端态，不落库；kind 决定渲染分支）
// ---------------------------------------------------------------------------
export const ChatMessageKindSchema = z.enum(['user', 'assistant', 'tool', 'param-prompt'])
export type ChatMessageKind = z.infer<typeof ChatMessageKindSchema>

export const ChatMessageStatusSchema = z.enum(['streaming', 'done', 'error'])
export type ChatMessageStatus = z.infer<typeof ChatMessageStatusSchema>

export const ChatMessageSchema = z.object({
  id: z.string(),
  kind: ChatMessageKindSchema,
  role: z.string(),
  content: z.string(),
  status: ChatMessageStatusSchema.optional(),
  ts: z.number().optional(),
  process: z.array(z.string()).optional(), // kind=tool：客户端意图分析步骤（intent.ts 生成，非后端）
  toolCall: z.unknown().optional(), // kind=tool/assistant：ai_consult 任务轮询进度（AiConsultTask）
  paramPrompt: z.array(z.string()).optional(), // kind=param-prompt：缺参时向用户追问项
  chips: z.array(z.string()).optional(), // assistant 追问建议（点击直接发送）
  model: z.string().optional(), // assistant 该轮模型（未配置显「规则引擎模式」）
  errors: z.array(z.string()).optional(), // 诚实态降级/错误明细
  fresh: z.boolean().optional(), // 前端态：本轮刚生成、待组件层做流式揭示（不落库语义）
  analysisMeta: z
    .object({
      topic: z.string().optional(), // 抽出的标的主题（代码/实体），无则 omit
      styleLabel: z.string(), // 回应风格文案（STYLE_LABELS）
      dimensions: z.array(z.object({ label: z.string(), desc: z.string() })), // 研判维度框架
    })
    .optional(), // 前端态：全面化外壳元数据（对标 FinPilot 标题卡+维度卡），不落库
})
export type ChatMessage = z.infer<typeof ChatMessageSchema>
