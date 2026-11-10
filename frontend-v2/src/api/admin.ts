import { apiFetch } from './client'
import {
  AdminUserListSchema,
  AdminLogListSchema,
  PublicUserSchema,
  CreateUserInputSchema,
  UpdateUserInputSchema,
  type PublicUser,
  type AdminUserList,
  type AdminLogList,
  type CreateUserInput,
  type UpdateUserInput,
} from './schemas/admin'

/**
 * 管理端 API 客户端（对齐 backend/api/admin_routes.py）。
 *
 * 设计：每个函数先 `apiFetch<unknown>` 取信封 data（已由 client 解包），再用专用
 * Zod schema `parse` 严格校验；缺失/类型不符即抛错（不兜底），与 PLAN.md §4.3 红线一致。
 * 路径斜杠与查询参数按契约精确拼接，不整体 encodeURIComponent。
 */

export interface ListUsersParams {
  page?: number
  per_page?: number
  keyword?: string
}

/** GET /api/admin/users —— 用户列表（分页 + 关键词搜索） */
export async function listUsers(params: ListUsersParams = {}): Promise<AdminUserList> {
  const q = new URLSearchParams()
  if (params.page != null) q.set('page', String(params.page))
  if (params.per_page != null) q.set('per_page', String(params.per_page))
  if (params.keyword) q.set('keyword', params.keyword)
  const qs = q.toString()
  const data = qs ? await apiFetch<unknown>(`/admin/users?${qs}`) : await apiFetch<unknown>('/admin/users')
  return AdminUserListSchema.parse(data)
}

/** POST /api/admin/users —— 创建用户 */
export async function createUser(input: CreateUserInput): Promise<PublicUser> {
  const body = CreateUserInputSchema.parse(input)
  const data = await apiFetch<unknown>('/admin/users', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  return PublicUserSchema.parse(data)
}

/** PUT /api/admin/users/<id> —— 修改用户（role / is_active / password，均可选） */
export async function updateUser(id: number, input: UpdateUserInput): Promise<PublicUser> {
  const body = UpdateUserInputSchema.parse(input)
  const data = await apiFetch<unknown>(`/admin/users/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  return PublicUserSchema.parse(data)
}

/** DELETE /api/admin/users/<id> —— 删除用户 */
export async function deleteUser(id: number): Promise<void> {
  await apiFetch<unknown>(`/admin/users/${id}`, { method: 'DELETE' })
}

/** GET /api/admin/logs —— 操作日志（分页） */
export async function listLogs(params: { page?: number; per_page?: number } = {}): Promise<AdminLogList> {
  const q = new URLSearchParams()
  if (params.page != null) q.set('page', String(params.page))
  if (params.per_page != null) q.set('per_page', String(params.per_page))
  const qs = q.toString()
  const data = qs ? await apiFetch<unknown>(`/admin/logs?${qs}`) : await apiFetch<unknown>('/admin/logs')
  return AdminLogListSchema.parse(data)
}
