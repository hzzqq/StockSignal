import { z } from 'zod'

/**
 * 管理端接口契约（对齐 backend/api/admin_routes.py）。
 *
 * 严格解析、禁止 `??` 兜底：字段缺失/类型不符即抛错，由页面渲染错误态（红线）。
 * User.to_public() / OperationLog.to_dict() 的真实字段形状见 backend/models.py。
 */

/** 对外用户对象（User.to_public()） */
export const PublicUserSchema = z.object({
  id: z.number().int(),
  username: z.string(),
  role: z.enum(['user', 'admin']),
  created_at: z.string(),
  is_active: z.boolean(),
  avatar: z.string().nullable().optional(),
  settings: z.record(z.string(), z.unknown()).optional(),
})
export type PublicUser = z.infer<typeof PublicUserSchema>

/** GET /api/admin/users 响应 */
export const AdminUserListSchema = z.object({
  items: z.array(PublicUserSchema),
  total: z.number().int(),
  page: z.number().int(),
  per_page: z.number().int(),
  pages: z.number().int(),
})
export type AdminUserList = z.infer<typeof AdminUserListSchema>

/** 操作日志（OperationLog.to_dict()） */
export const AdminLogSchema = z.object({
  id: z.number().int(),
  user_id: z.number().int(),
  username: z.string(),
  action: z.string(),
  target: z.string(),
  detail: z.string(),
  created_at: z.string(),
})
export type AdminLog = z.infer<typeof AdminLogSchema>

/** GET /api/admin/logs 响应 */
export const AdminLogListSchema = z.object({
  items: z.array(AdminLogSchema),
  total: z.number().int(),
  page: z.number().int(),
  per_page: z.number().int(),
  pages: z.number().int(),
})
export type AdminLogList = z.infer<typeof AdminLogListSchema>

/** 创建用户入参（POST /api/admin/users） */
export const CreateUserInputSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
  role: z.enum(['user', 'admin']),
})
export type CreateUserInput = z.infer<typeof CreateUserInputSchema>

/** 修改用户入参（PUT /api/admin/users/<id>，字段均可选） */
export const UpdateUserInputSchema = z.object({
  role: z.enum(['user', 'admin']).optional(),
  is_active: z.boolean().optional(),
  password: z.string().min(1).optional(),
})
export type UpdateUserInput = z.infer<typeof UpdateUserInputSchema>
