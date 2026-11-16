import { useMutation, useQuery, useQueryClient, type UseQueryResult, type UseMutationResult } from '@tanstack/react-query'
import { clearAuth } from '@/app/guards'
import {
  listPosts,
  getPost,
  getMe,
  getTokenInfo,
  getLoginHistory,
  logout as logoutApi,
} from '@/api/community'
import { useWriteMutation } from '@/lib/mutations'
import { PublicUserSchema } from '@/api/schemas/admin'
import {
  ForumPostSchema,
  ForumCommentSchema,
  LikeResultSchema,
  type ForumPost,
  type ForumPostDetail,
  type ForumComment,
  type LikeResult,
  type TokenInfo,
  type OperationLog,
  type CreatePostInput,
  type SettingsInput,
  type AvatarInput,
  type RegisterInput,
  type PublicUser,
} from '@/api/schemas/community'

/**
 * 股吧社区 + 账户的 TanStack Query hooks（v1→v2 parity 批次）。
 *
 * 读：统一 key 前缀 ['community', ...]，取数失败（Zod / 网络 / 401）进入 error 态由页面渲染，
 *     绝不兜底。
 * 写：统一走 useWriteMutation（mutations.ts 工厂，mutationFn 固定 apiMutate），成功后
 *     只做 invalidateQueries，服务端才是真理源，不做乐观更新、不吞错。
 *
 * 例外说明：logout 需要在「真实成功后」额外丢弃本地 token（工厂的 onSuccess 固定只做
 * invalidateQueries，无法表达该副作用），因此用本地 useMutation 定制；它仍然调用
 * community.logout() → apiMutate（统一写层），且只在 onSuccess 里 clearAuth，失败绝不碰
 * token、绝不伪造成功。
 */

/* ───────────────────────── 读 ───────────────────────── */

export function useForumPosts(stockCode = ''): UseQueryResult<ForumPost[]> {
  return useQuery({
    queryKey: ['community', 'posts', stockCode],
    queryFn: () => listPosts({ stock_code: stockCode || undefined }),
  })
}

export function useForumPost(id: number | null): UseQueryResult<ForumPostDetail> {
  return useQuery({
    queryKey: ['community', 'post', id],
    queryFn: () => getPost(id as number),
    enabled: id !== null,
  })
}

export function useMe(): UseQueryResult<PublicUser> {
  return useQuery({ queryKey: ['community', 'me'], queryFn: getMe })
}

export function useTokenInfo(): UseQueryResult<TokenInfo> {
  return useQuery({ queryKey: ['community', 'token-info'], queryFn: getTokenInfo })
}

export function useLoginHistory(): UseQueryResult<OperationLog[]> {
  return useQuery({ queryKey: ['community', 'logins'], queryFn: () => getLoginHistory() })
}

/* ───────────────────────── 写（useWriteMutation 工厂） ───────────────────────── */

export function useCreatePost(): UseMutationResult<ForumPost, Error, CreatePostInput> {
  return useWriteMutation<CreatePostInput, ForumPost>({
    path: '/forum/posts',
    method: 'POST',
    body: (v) => ({
      title: v.title,
      content: v.content,
      stock_code: v.stock_code,
      stock_name: v.stock_name,
    }),
    schema: ForumPostSchema,
    invalidateKeys: [['community', 'posts']],
  })
}

export function useDeletePost(): UseMutationResult<void, Error, number> {
  return useWriteMutation<number, void>({
    path: (id) => `/forum/posts/${id}`,
    method: 'DELETE',
    schema: null,
    invalidateKeys: [['community', 'posts']],
  })
}

export function useLikePost(): UseMutationResult<LikeResult, Error, number> {
  return useWriteMutation<number, LikeResult>({
    path: (id) => `/forum/posts/${id}/like`,
    method: 'POST',
    schema: LikeResultSchema,
    invalidateKeys: [['community', 'post'], ['community', 'posts']],
  })
}

export interface AddCommentVars {
  postId: number
  content: string
}

export function useAddComment(): UseMutationResult<ForumComment, Error, AddCommentVars> {
  return useWriteMutation<AddCommentVars, ForumComment>({
    path: (v) => `/forum/posts/${v.postId}/comments`,
    method: 'POST',
    body: (v) => ({ content: v.content }),
    schema: ForumCommentSchema,
    invalidateKeys: [['community', 'post'], ['community', 'posts']],
  })
}

export function useSaveSettings(): UseMutationResult<PublicUser, Error, SettingsInput> {
  return useWriteMutation<SettingsInput, PublicUser>({
    path: '/auth/settings',
    method: 'POST',
    body: (v) => ({ settings: v.settings }),
    schema: PublicUserSchema,
    invalidateKeys: [['community', 'me']],
  })
}

export function useSaveAvatar(): UseMutationResult<PublicUser, Error, AvatarInput> {
  return useWriteMutation<AvatarInput, PublicUser>({
    path: '/auth/avatar',
    method: 'POST',
    body: (v) => ({ avatar: v.avatar }),
    schema: PublicUserSchema,
    invalidateKeys: [['community', 'me']],
  })
}

export function useRegister(): UseMutationResult<PublicUser, Error, RegisterInput> {
  return useWriteMutation<RegisterInput, PublicUser>({
    path: '/auth/register',
    method: 'POST',
    body: (v) => ({ username: v.username, password: v.password, confirm: v.confirm }),
    schema: PublicUserSchema,
    invalidateKeys: [['community']],
  })
}

/**
 * 登出：mutationFn 仍走统一写层（community.logout → apiMutate）。
 * 仅在真实成功（后端 status=ok）后 clearAuth() 丢弃 token / refresh / 缓存用户，
 * 并使 ['community'] 缓存失效；失败绝不改缓存、绝不碰 token、绝不伪造成功。
 * 组件可在 onDone 里补跳 /login（同样只在成功回调里触发）。
 */
export function useLogout(): UseMutationResult<void, Error, void> & {
  logout: (onDone?: () => void) => void
} {
  const qc = useQueryClient()
  const mutation = useMutation<void, Error, void>({
    mutationFn: () => logoutApi(),
    onSuccess: () => {
      clearAuth()
      void qc.invalidateQueries({ queryKey: ['community'] })
    },
  })
  return {
    ...mutation,
    logout: (onDone?: () => void) =>
      mutation.mutate(undefined, {
        onSuccess: () => {
          onDone?.()
        },
      }),
  }
}
