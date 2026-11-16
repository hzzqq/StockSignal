import { z } from 'zod'
import { AdminLogSchema } from './admin'

/**
 * 股吧社区 + 账户接口契约（逐行核对 backend/api/forum_routes.py、backend/auth/routes.py、
 * backend/models.py 的 ForumPost.to_dict / ForumComment.to_dict / OperationLog.to_dict /
 * User.to_public）。
 *
 * 红线（与全站一致）：严格解析、nullable 显式、禁止 default 补零；字段缺失/类型不符即抛错，
 * 由页面渲染错误态，绝不 `?? 0` / `|| 0` 兜底。
 */

// PublicUserSchema 已在 admin.ts 定义并导出（User.to_public 同形），这里直接复用不重定义。
export { PublicUserSchema } from './admin'
export type { PublicUser } from './admin'

/**
 * 登录历史条目（OperationLog.to_dict()，action='login'）。
 * 字段与 admin.ts 的 AdminLogSchema 完全一致（同为 OperationLog.to_dict），别名复用。
 */
export const OperationLogSchema = AdminLogSchema
export type OperationLog = z.infer<typeof OperationLogSchema>

/**
 * 帖子（列表态 with_content=false + comment_count，详情态 with_content=true）。
 * 两态共用一个 schema：content / excerpt / comment_count 均可空（各自只在一态出现），
 * 缺字段不补零、不臆造，交由页面按态如实展示。
 */
export const ForumPostSchema = z.object({
  id: z.number().int(),
  user_id: z.number().int(),
  username: z.string(),
  avatar: z.string(),
  title: z.string(),
  stock_code: z.string(),
  stock_name: z.string(),
  likes: z.number().int(),
  views: z.number().int(),
  created_at: z.string().nullable(),
  content: z.string().nullable().optional(),
  excerpt: z.string().nullable().optional(),
  comment_count: z.number().int().nullable().optional(),
})
export type ForumPost = z.infer<typeof ForumPostSchema>

/** 评论（ForumComment.to_dict()） */
export const ForumCommentSchema = z.object({
  id: z.number().int(),
  post_id: z.number().int(),
  user_id: z.number().int(),
  username: z.string(),
  avatar: z.string(),
  content: z.string(),
  created_at: z.string().nullable(),
})
export type ForumComment = z.infer<typeof ForumCommentSchema>

/** GET /api/forum/posts/:id —— 完整帖子 + 评论列表（详情态必有 content 与 comments） */
export const ForumPostDetailSchema = ForumPostSchema.extend({
  content: z.string(),
  comments: z.array(ForumCommentSchema),
})
export type ForumPostDetail = z.infer<typeof ForumPostDetailSchema>

/** POST /api/forum/posts/:id/like 响应 data */
export const LikeResultSchema = z.object({ likes: z.number().int() })
export type LikeResult = z.infer<typeof LikeResultSchema>

/** GET /api/auth/token-info —— 非敏感声明；iat / exp 为 Unix 秒级时间戳 */
export const TokenInfoSchema = z.object({
  sub: z.string(),
  uid: z.number().int(),
  role: z.string(),
  iat: z.number().int(),
  exp: z.number().int(),
})
export type TokenInfo = z.infer<typeof TokenInfoSchema>

/* ───────────────────────── 输入 schema（请求体严格校验） ───────────────────────── */

/** POST /api/forum/posts —— title ≤200 非空、content ≤20000 非空、关联股票可选 */
export const CreatePostInputSchema = z.object({
  title: z.string().min(1, '标题不能为空').max(200, '标题过长（≤200 字）'),
  content: z.string().min(1, '内容不能为空').max(20000, '内容过长'),
  stock_code: z.string().max(20).optional(),
  stock_name: z.string().max(50).optional(),
})
export type CreatePostInput = z.infer<typeof CreatePostInputSchema>

/** POST /api/forum/posts/:id/comments —— content 非空 */
export const AddCommentInputSchema = z.object({
  content: z.string().min(1, '评论内容不能为空').max(20000, '内容过长'),
})
export type AddCommentInput = z.infer<typeof AddCommentInputSchema>

/** POST /api/auth/settings —— settings 必须是对象（≤10000 字符） */
export const SettingsInputSchema = z
  .object({
    settings: z.record(z.string(), z.unknown()),
  })
  .refine(({ settings }) => JSON.stringify(settings).length <= 10_000, {
    message: '设置数据过大',
  })
export type SettingsInput = z.infer<typeof SettingsInputSchema>

/** POST /api/auth/avatar —— 必须是 data:image/ 前缀，且体积 ≤4MB（对齐后端 4_000_000 字符） */
export const AvatarInputSchema = z.object({
  avatar: z
    .string()
    .refine((v) => v.startsWith('data:image/'), {
      message: '头像必须是 data:image/ 开头的 base64 图片',
    })
    .refine((v) => v.length <= 4_000_000, {
      message: '头像数据过大，请压缩到 3MB 以内',
    }),
})
export type AvatarInput = z.infer<typeof AvatarInputSchema>

/** POST /api/auth/register —— 开放注册（角色固定 user，限流 429 由后端处理） */
export const RegisterInputSchema = z.object({
  username: z.string().min(1, '用户名不能为空'),
  password: z.string().min(1, '密码不能为空'),
  confirm: z.string().min(1, '确认密码不能为空'),
})
export type RegisterInput = z.infer<typeof RegisterInputSchema>
