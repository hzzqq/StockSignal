import { z } from 'zod'
import { apiFetch } from './client'
import { apiMutate } from './write'
import { PublicUserSchema } from './schemas/admin'
import {
  ForumPostSchema,
  ForumPostDetailSchema,
  ForumCommentSchema,
  LikeResultSchema,
  TokenInfoSchema,
  OperationLogSchema,
  CreatePostInputSchema,
  AddCommentInputSchema,
  SettingsInputSchema,
  AvatarInputSchema,
  RegisterInputSchema,
  type ForumPost,
  type ForumPostDetail,
  type ForumComment,
  type LikeResult,
  type TokenInfo,
  type OperationLog,
  type CreatePostInput,
  type AddCommentInput,
  type SettingsInput,
  type AvatarInput,
  type RegisterInput,
  type PublicUser,
} from './schemas/community'

/**
 * 股吧社区 + 账户 API 客户端（对齐 backend/api/forum_routes.py 与 backend/auth/routes.py）。
 *
 * 分层：
 *  - 所有写请求统一走 apiMutate（write.ts 单一真理源：Bearer + 401 单飞刷新 + 信封解包）；
 *  - 所有读请求走 apiFetch + 专用 Zod schema.parse 严格校验；
 *  - 请求体在发出前用输入 schema 校验，响应 data 用输出 schema 校验；
 *  - 无响应体端点（DELETE / logout）用 schema=null 显式表示「不解析」，不是静默成功；
 *  - 失败原样抛 ApiError，绝不把 error 洗成成功。
 *
 * 端点覆盖（13 个）：
 *  forum: GET/POST posts、GET/DELETE posts/:id、POST posts/:id/like、POST posts/:id/comments
 *  auth : GET me、GET token-info、GET logins、POST logout、POST settings、POST avatar、POST register
 */

/* ───────────────────────── 读（apiFetch + schema.parse） ───────────────────────── */

export interface ListPostsParams {
  stock_code?: string
  limit?: number
  offset?: number
}

/** GET /api/forum/posts —— 帖子列表（可按股票代码过滤、分页） */
export async function listPosts(params: ListPostsParams = {}): Promise<ForumPost[]> {
  const q = new URLSearchParams()
  if (params.stock_code) q.set('stock_code', params.stock_code)
  if (params.limit != null) q.set('limit', String(params.limit))
  if (params.offset != null) q.set('offset', String(params.offset))
  const qs = q.toString()
  const data = qs
    ? await apiFetch<unknown>(`/forum/posts?${qs}`)
    : await apiFetch<unknown>('/forum/posts')
  return z.array(ForumPostSchema).parse(data)
}

/** GET /api/forum/posts/:id —— 详情 + 评论（后端自增浏览量） */
export async function getPost(id: number): Promise<ForumPostDetail> {
  const data = await apiFetch<unknown>(`/forum/posts/${id}`)
  return ForumPostDetailSchema.parse(data)
}

/** GET /api/auth/me —— 当前用户公开对象 */
export async function getMe(): Promise<PublicUser> {
  const data = await apiFetch<unknown>('/auth/me')
  return PublicUserSchema.parse(data)
}

/** GET /api/auth/token-info —— 非敏感声明（iat/exp 为 Unix 秒） */
export async function getTokenInfo(): Promise<TokenInfo> {
  const data = await apiFetch<unknown>('/auth/token-info')
  return TokenInfoSchema.parse(data)
}

/** GET /api/auth/logins —— 当前用户登录历史（OperationLog action=login） */
export async function getLoginHistory(limit = 20): Promise<OperationLog[]> {
  const data = await apiFetch<unknown>(`/auth/logins?limit=${limit}`)
  return z.array(OperationLogSchema).parse(data)
}

/* ───────────────────────── 写（统一走 apiMutate） ───────────────────────── */

/** POST /api/forum/posts —— 发帖（code='created'） */
export async function createPost(input: CreatePostInput): Promise<ForumPost> {
  const body = CreatePostInputSchema.parse(input)
  return apiMutate<ForumPost>('/forum/posts', 'POST', body, ForumPostSchema)
}

/** DELETE /api/forum/posts/:id —— 删帖（仅作者或管理员；仅 message） */
export async function deletePost(id: number): Promise<void> {
  await apiMutate<void>(`/forum/posts/${id}`, 'DELETE', undefined, null)
}

/** POST /api/forum/posts/:id/like —— 点赞，返回 {likes} */
export async function likePost(id: number): Promise<LikeResult> {
  return apiMutate<LikeResult>(`/forum/posts/${id}/like`, 'POST', undefined, LikeResultSchema)
}

/** POST /api/forum/posts/:id/comments —— 发表评论（code='created'） */
export async function addComment(id: number, input: AddCommentInput): Promise<ForumComment> {
  const body = AddCommentInputSchema.parse(input)
  return apiMutate<ForumComment>(`/forum/posts/${id}/comments`, 'POST', body, ForumCommentSchema)
}

/** POST /api/auth/logout —— 无状态 JWT，服务端仅建议客户端丢弃 token（仅 message） */
export async function logout(): Promise<void> {
  await apiMutate<void>('/auth/logout', 'POST', undefined, null)
}

/** POST /api/auth/settings —— 保存偏好，返回当前用户公开对象 */
export async function saveSettings(input: SettingsInput): Promise<PublicUser> {
  const body = SettingsInputSchema.parse(input)
  return apiMutate<PublicUser>('/auth/settings', 'POST', body, PublicUserSchema)
}

/** POST /api/auth/avatar —— 保存头像 data URL，返回当前用户公开对象 */
export async function saveAvatar(input: AvatarInput): Promise<PublicUser> {
  const body = AvatarInputSchema.parse(input)
  return apiMutate<PublicUser>('/auth/avatar', 'POST', body, PublicUserSchema)
}

/** POST /api/auth/register —— 开放注册（角色固定 user；限流 429 由后端处理） */
export async function register(input: RegisterInput): Promise<PublicUser> {
  const body = RegisterInputSchema.parse(input)
  return apiMutate<PublicUser>('/auth/register', 'POST', body, PublicUserSchema)
}
