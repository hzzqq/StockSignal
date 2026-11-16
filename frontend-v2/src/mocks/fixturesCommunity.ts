import { z } from 'zod'
import {
  ForumPostSchema,
  ForumPostDetailSchema,
  ForumCommentSchema,
  OperationLogSchema,
  TokenInfoSchema,
  PublicUserSchema,
  LikeResultSchema,
} from '@/api/schemas/community'

/**
 * 股吧社区 + 账户演示夹具（Mock 演示态，非真实后端数据）。
 *
 * ⚠️ 全部为固定演示值（时间戳用常量 MOCK_WRITE_TS，绝不 new Date() 冒充数据日），
 * 形状逐字段对齐真后端 to_dict()/to_public()；仅用于 MSW 演示与契约漂移校验，
 * 不得对外宣称是真实行情 / 真实账户数据。
 *
 * 列表态 / 详情态 / 空态变体都在此备齐，供 communityFixturePairs 锁定「可空」契约。
 */

/** 演示态固定时间戳（与 writeEnvelope.MOCK_WRITE_TS 同源口径，确定性、可重现）。 */
const T = '2026-01-01T08:00:00Z'
const T2 = '2026-01-02T09:30:00Z'
const T3 = '2026-01-03T10:00:00Z'

/** handler 内部完整帖子记录（含 content，列表/详情都由它派生，模拟数据库行）。 */
export interface DemoPost {
  id: number
  user_id: number
  username: string
  avatar: string
  title: string
  content: string
  stock_code: string
  stock_name: string
  likes: number
  views: number
  created_at: string | null
}

/** handler 内部评论记录。 */
export interface DemoComment {
  id: number
  post_id: number
  user_id: number
  username: string
  avatar: string
  content: string
  created_at: string | null
}

/** 当前演示登录用户：id=1 / demo / 普通用户（非作者删除将命中 400「只能删除自己的帖子」）。 */
export const demoCurrentUser = {
  id: 1,
  username: 'demo',
  role: 'user' as const,
  created_at: T,
  is_active: true,
  avatar: null as string | null,
  settings: { theme_mode: 'dark' } as Record<string, unknown>,
}

export const demoPosts: DemoPost[] = [
  {
    id: 1, user_id: 1, username: 'demo', avatar: '',
    title: '贵州茅台年报解读',
    content: '茅台 2025 年报营收稳健增长，重点关注直销渠道占比与批价走势。',
    stock_code: '600519', stock_name: '贵州茅台',
    likes: 5, views: 120, created_at: T,
  },
  {
    id: 2, user_id: 2, username: 'another', avatar: '',
    title: '平安银行估值讨论',
    content: '银行板块估值处于历史低位，讨论后续修复空间与息差压力。',
    stock_code: '000001', stock_name: '平安银行',
    likes: 2, views: 40, created_at: T2,
  },
  {
    id: 3, user_id: 1, username: 'demo', avatar: '',
    title: '今日盘面随笔',
    content: '两市成交额温和放量，题材轮动较快，注意控制仓位。',
    stock_code: '', stock_name: '',
    likes: 0, views: 7, created_at: T3,
  },
]

export const demoComments: DemoComment[] = [
  { id: 1, post_id: 1, user_id: 2, username: 'another', avatar: '', content: '直销渠道确实是看点', created_at: T },
  { id: 2, post_id: 1, user_id: 1, username: 'demo', avatar: '', content: '同意，还要看批价', created_at: T2 },
]

/** GET /api/auth/logins 演示数据（action=login 的 OperationLog.to_dict()）。 */
export const demoLoginHistory = [
  { id: 12, user_id: 1, username: 'demo', action: 'login', target: 'demo', detail: 'ip=127.0.0.1', created_at: T3 },
  { id: 9, user_id: 1, username: 'demo', action: 'login', target: 'demo', detail: 'ip=10.0.0.5', created_at: T2 },
]

/** GET /api/auth/token-info 演示数据（iat/exp 为 Unix 秒，固定常量非运行时时间）。 */
export const demoTokenInfo = {
  sub: 'demo',
  uid: 1,
  role: 'user',
  iat: 1767225600,
  exp: 1767229200,
}

/* ─────────────────── 真后端响应形状样本（供契约漂移校验） ─────────────────── */

/** 列表态：to_dict(with_content=false) + comment_count */
export const forumPostListSample = {
  id: 1, user_id: 1, username: 'demo', avatar: '',
  title: '贵州茅台年报解读', stock_code: '600519', stock_name: '贵州茅台',
  likes: 5, views: 120, created_at: T,
  excerpt: '茅台 2025 年报营收稳健增长，重点关注直销渠道占比与批价走势。',
  comment_count: 2,
}

/** 列表态诚实空值变体：created_at=null、content/excerpt/comment_count 均可空 */
export const forumPostListNullVariant = {
  id: 3, user_id: 1, username: 'demo', avatar: '',
  title: '今日盘面随笔', stock_code: '', stock_name: '',
  likes: 0, views: 7, created_at: null,
  content: null, excerpt: null, comment_count: null,
}

/** 详情态：完整 post（content）+ comments */
export const forumPostDetailSample = {
  id: 1, user_id: 1, username: 'demo', avatar: '',
  title: '贵州茅台年报解读', stock_code: '600519', stock_name: '贵州茅台',
  likes: 5, views: 121, created_at: T,
  content: '茅台 2025 年报营收稳健增长，重点关注直销渠道占比与批价走势。',
  comments: [
    { id: 1, post_id: 1, user_id: 2, username: 'another', avatar: '', content: '直销渠道确实是看点', created_at: T },
    { id: 2, post_id: 1, user_id: 1, username: 'demo', avatar: '', content: '同意，还要看批价', created_at: T2 },
  ],
}

/** 详情态空评论变体：created_at=null、comments=[] */
export const forumPostDetailEmptyVariant = {
  id: 3, user_id: 1, username: 'demo', avatar: '',
  title: '今日盘面随笔', stock_code: '', stock_name: '',
  likes: 0, views: 8, created_at: null,
  content: '两市成交额温和放量，题材轮动较快，注意控制仓位。',
  comments: [],
}

export const forumCommentSample = {
  id: 1, post_id: 1, user_id: 2, username: 'another', avatar: '',
  content: '直销渠道确实是看点', created_at: T,
}

export const forumCommentNullVariant = {
  id: 2, post_id: 1, user_id: 1, username: 'demo', avatar: '',
  content: '同意，还要看批价', created_at: null,
}

export const likeResultSample = { likes: 6 }

/** 契约漂移校验对：{name, schema, samples[]}，与 tests/unit/contract-drift.test.ts 同协议。 */
export const communityFixturePairs: Array<{ name: string; schema: z.ZodTypeAny; samples: unknown[] }> = [
  {
    name: 'forum-post-list',
    schema: z.array(ForumPostSchema),
    samples: [[forumPostListSample], [forumPostListSample, forumPostListNullVariant]],
  },
  {
    name: 'forum-post-detail',
    schema: ForumPostDetailSchema,
    samples: [forumPostDetailSample, forumPostDetailEmptyVariant],
  },
  {
    name: 'forum-comment',
    schema: ForumCommentSchema,
    samples: [forumCommentSample, forumCommentNullVariant],
  },
  { name: 'operation-log', schema: OperationLogSchema, samples: demoLoginHistory },
  { name: 'token-info', schema: TokenInfoSchema, samples: [demoTokenInfo] },
  {
    name: 'public-user',
    schema: PublicUserSchema,
    samples: [demoCurrentUser, { ...demoCurrentUser, avatar: 'data:image/png;base64,AAAA' }],
  },
  { name: 'like-result', schema: LikeResultSchema, samples: [likeResultSample] },
]
