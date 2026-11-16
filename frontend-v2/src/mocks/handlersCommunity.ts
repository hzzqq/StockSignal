import { http, HttpResponse } from 'msw'
import { z } from 'zod'
import {
  writeOk,
  writeBadRequest,
  writeNotFound,
  MOCK_WRITE_TS,
} from './writeEnvelope'
import {
  CreatePostInputSchema,
  AddCommentInputSchema,
  SettingsInputSchema,
  AvatarInputSchema,
  RegisterInputSchema,
} from '@/api/schemas/community'
import {
  demoPosts,
  demoComments,
  demoCurrentUser,
  demoLoginHistory,
  demoTokenInfo,
  type DemoPost,
  type DemoComment,
} from './fixturesCommunity'

/**
 * 股吧社区 + 账户 MSW handlers（**演示态 Mock，非真实后端数据**）。
 *
 * ⚠️ 这是前端演示用的内存可变状态，绝不对外宣称是真实行情 / 真实账户数据。
 * 所有时间戳用固定常量 MOCK_WRITE_TS（确定性、可重现），禁止 new Date() 冒充数据日。
 *
 * 可变内存态实现真实交互链路（与真后端逐端点对齐）：
 *  发帖 → 列表出现；评论 → 详情出现；点赞 likes+1；删除消失；详情自增 views；
 *  空标题/空内容 → 400；非作者删除 → 400「只能删除自己的帖子」。
 * 登录历史 / token-info / me / settings / avatar / register 均返回真实字段形状。
 *
 * 校验复用 api/schemas/community.ts 的输入 schema（客户端与 Mock 同一份契约），
 * 拒绝信息即 schema 的 message，与真后端 ValidationError 文案一致。
 */

interface CommunityMockState {
  posts: DemoPost[]
  comments: DemoComment[]
  nextPostId: number
  nextCommentId: number
  currentUser: {
    id: number
    username: string
    role: 'user' | 'admin'
    created_at: string
    is_active: boolean
    avatar: string | null
    settings: Record<string, unknown>
  }
}

/** 模块作用域可变副本：必须在 communityHandlers 之前声明，handlers 内的闭包引用它。 */
const state: CommunityMockState = {
  posts: demoPosts.map((p) => ({ ...p })),
  comments: demoComments.map((c) => ({ ...c })),
  nextPostId: Math.max(0, ...demoPosts.map((p) => p.id)) + 1,
  nextCommentId: Math.max(0, ...demoComments.map((c) => c.id)) + 1,
  currentUser: { ...demoCurrentUser, settings: { ...demoCurrentUser.settings } },
}

/** 测试间复位，避免跨用例污染（发帖/评论/点赞/删除/设置/头像都在内存态累积）。 */
export function resetCommunityMock(): void {
  state.posts = demoPosts.map((p) => ({ ...p }))
  state.comments = demoComments.map((c) => ({ ...c }))
  state.nextPostId = Math.max(0, ...demoPosts.map((p) => p.id)) + 1
  state.nextCommentId = Math.max(0, ...demoComments.map((c) => c.id)) + 1
  state.currentUser = { ...demoCurrentUser, settings: { ...demoCurrentUser.settings } }
}

/** 取 Zod 首条校验失败的 message（与后端 ValidationError 文案同源）。 */
function firstMessage(error: z.ZodError): string {
  return error.issues[0]?.message ?? '参数不合法'
}

/** code='created' 的写响应（对齐后端 create_post / add_comment / register 的 code）。 */
function writeCreated(data: unknown, message: string, httpStatus = 200) {
  return HttpResponse.json({ status: 'ok', code: 'created', message, data }, { status: httpStatus })
}

/** DemoPost → 列表项（to_dict(with_content=false) + comment_count）。 */
function toListItem(p: DemoPost) {
  return {
    id: p.id,
    user_id: p.user_id,
    username: p.username,
    avatar: p.avatar,
    title: p.title,
    stock_code: p.stock_code,
    stock_name: p.stock_name,
    likes: p.likes,
    views: p.views,
    created_at: p.created_at,
    excerpt: p.content.slice(0, 80),
    comment_count: state.comments.filter((c) => c.post_id === p.id).length,
  }
}

/** DemoPost → 完整帖子（to_dict(with_content=true)，含 content）。 */
function toFullPost(p: DemoPost) {
  return { ...p }
}

export const communityHandlers = [
  /* ─────────────── forum ─────────────── */

  // GET /api/forum/posts —— 列表（按 stock_code 过滤 + 分页，按 created_at desc / id desc）
  http.get('/api/forum/posts', ({ request }) => {
    const url = new URL(request.url)
    const stockCode = (url.searchParams.get('stock_code') ?? '').trim()
    const rawLimit = Number(url.searchParams.get('limit') ?? '50')
    const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.min(200, Math.floor(rawLimit)) : 50
    const rawOffset = Number(url.searchParams.get('offset') ?? '0')
    const offset = Number.isFinite(rawOffset) && rawOffset >= 0 ? Math.floor(rawOffset) : 0
    const filtered = stockCode
      ? state.posts.filter((p) => p.stock_code === stockCode)
      : state.posts.slice()
    filtered.sort((a, b) => {
      const ca = a.created_at ?? ''
      const cb = b.created_at ?? ''
      if (ca !== cb) return ca < cb ? 1 : -1
      return b.id - a.id
    })
    return writeOk(filtered.slice(offset, offset + limit).map(toListItem))
  }),

  // POST /api/forum/posts —— 发帖（空标题/空内容 → 400；code='created'）
  http.post('/api/forum/posts', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const parsed = CreatePostInputSchema.safeParse(body)
    if (!parsed.success) return writeBadRequest(firstMessage(parsed.error))
    const p: DemoPost = {
      id: state.nextPostId++,
      user_id: state.currentUser.id,
      username: state.currentUser.username,
      avatar: state.currentUser.avatar ?? '',
      title: parsed.data.title,
      content: parsed.data.content,
      stock_code: parsed.data.stock_code ?? '',
      stock_name: parsed.data.stock_name ?? '',
      likes: 0,
      views: 0,
      created_at: MOCK_WRITE_TS,
    }
    state.posts.push(p)
    return writeCreated(toFullPost(p), '发布成功')
  }),

  // GET /api/forum/posts/:id —— 详情 + 评论，自增 views
  http.get('/api/forum/posts/:id', ({ params }) => {
    const id = Number(params.id)
    const p = state.posts.find((x) => x.id === id)
    if (!p) return writeNotFound(`帖子 ${id}`)
    p.views = p.views + 1
    const comments = state.comments.filter((c) => c.post_id === id).map((c) => ({ ...c }))
    return writeOk({ ...toFullPost(p), comments })
  }),

  // DELETE /api/forum/posts/:id —— 仅作者或管理员（仅 message）
  http.delete('/api/forum/posts/:id', ({ params }) => {
    const id = Number(params.id)
    const p = state.posts.find((x) => x.id === id)
    if (!p) return writeNotFound(`帖子 ${id}`)
    if (p.user_id !== state.currentUser.id && state.currentUser.role !== 'admin') {
      return writeBadRequest('只能删除自己的帖子')
    }
    state.posts = state.posts.filter((x) => x.id !== id)
    state.comments = state.comments.filter((c) => c.post_id !== id)
    return writeOk(null, '已删除')
  }),

  // POST /api/forum/posts/:id/like —— 点赞 likes+1
  http.post('/api/forum/posts/:id/like', ({ params }) => {
    const id = Number(params.id)
    const p = state.posts.find((x) => x.id === id)
    if (!p) return writeNotFound(`帖子 ${id}`)
    p.likes = p.likes + 1
    return writeOk({ likes: p.likes }, '点赞成功')
  }),

  // POST /api/forum/posts/:id/comments —— 发表评论（空内容 → 400；code='created'）
  http.post('/api/forum/posts/:id/comments', async ({ params, request }) => {
    const id = Number(params.id)
    const p = state.posts.find((x) => x.id === id)
    if (!p) return writeNotFound(`帖子 ${id}`)
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const parsed = AddCommentInputSchema.safeParse({ content: body.content })
    if (!parsed.success) return writeBadRequest(firstMessage(parsed.error))
    const c: DemoComment = {
      id: state.nextCommentId++,
      post_id: id,
      user_id: state.currentUser.id,
      username: state.currentUser.username,
      avatar: state.currentUser.avatar ?? '',
      content: parsed.data.content,
      created_at: MOCK_WRITE_TS,
    }
    state.comments.push(c)
    return writeCreated({ ...c }, '评论成功')
  }),

  /* ─────────────── auth / 账户 ─────────────── */

  // GET /api/auth/me —— 当前用户公开对象
  http.get('/api/auth/me', () => writeOk({ ...state.currentUser })),

  // GET /api/auth/token-info —— 非敏感声明（iat/exp 为 Unix 秒）
  http.get('/api/auth/token-info', () => writeOk({ ...demoTokenInfo })),

  // GET /api/auth/logins —— 登录历史（action=login）
  http.get('/api/auth/logins', ({ request }) => {
    const url = new URL(request.url)
    const raw = Number(url.searchParams.get('limit') ?? '20')
    const limit = Number.isFinite(raw) && raw > 0 ? Math.min(50, Math.floor(raw)) : 20
    return writeOk(demoLoginHistory.slice(0, limit).map((l) => ({ ...l })), 'success')
  }),

  // POST /api/auth/logout —— 仅 message（客户端据此丢弃 token）
  http.post('/api/auth/logout', () => writeOk(null, '已登出')),

  // POST /api/auth/settings —— settings 必须是对象（非对象 → 400；体积 ≤10000 字符）
  http.post('/api/auth/settings', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    if (typeof body.settings !== 'object' || body.settings === null || Array.isArray(body.settings)) {
      return writeBadRequest('settings 必须是对象')
    }
    const parsed = SettingsInputSchema.safeParse({ settings: body.settings })
    if (!parsed.success) return writeBadRequest(firstMessage(parsed.error))
    state.currentUser.settings = parsed.data.settings
    return writeOk({ ...state.currentUser }, '设置已保存')
  }),

  // POST /api/auth/avatar —— 必须 data:image/ 前缀且 ≤4MB
  http.post('/api/auth/avatar', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const parsed = AvatarInputSchema.safeParse({ avatar: body.avatar })
    if (!parsed.success) return writeBadRequest(firstMessage(parsed.error))
    state.currentUser.avatar = parsed.data.avatar
    return writeOk({ ...state.currentUser }, '头像已保存')
  }),

  // POST /api/auth/register —— 开放注册（角色固定 user；201 + code='created'）
  http.post('/api/auth/register', async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>
    const parsed = RegisterInputSchema.safeParse({
      username: body.username,
      password: body.password,
      confirm: body.confirm,
    })
    if (!parsed.success) return writeBadRequest(firstMessage(parsed.error))
    if (parsed.data.password !== parsed.data.confirm) return writeBadRequest('两次密码不一致')
    const user = {
      id: state.nextPostId + 1000,
      username: parsed.data.username,
      role: 'user',
      created_at: MOCK_WRITE_TS,
      is_active: true,
      avatar: null,
      settings: {},
    }
    return writeCreated(user, '注册成功', 201)
  }),
]
