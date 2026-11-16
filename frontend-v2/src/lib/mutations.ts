import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'
import { apiMutate, type Parser, type WriteMethod } from '@/api/write'

/**
 * v2 统一 mutation 工厂（单一真理源）。
 *
 * 后端写端点都是「按当前用户隔离」的资源，成功后必须让相关读缓存失效，
 * 否则列表会停留在旧数据、看起来像「写成功了但没生效」——这类假成功必须避免。
 *
 * 设计：
 *  - mutationFn 固定走 apiMutate，禁止页面自己拼 fetch。
 *  - onSuccess 只做 invalidateQueries，不做乐观更新（服务端才是真理源）。
 *  - 失败不改缓存、不吞错；error 原样交给页面渲染。
 */
export interface WriteMutationSpec<TVars, TData> {
  /** 目标路径；可由变量拼出（如带 id 的 DELETE） */
  path: string | ((vars: TVars) => string)
  method: WriteMethod
  /** 请求体构造器；不传表示无 body */
  body?: (vars: TVars) => unknown
  /** 响应 data 的严格校验；null 表示端点无响应体，不解析 */
  schema?: Parser<TData> | null
  /** 写成功后需要失效的 queryKey 列表 */
  invalidateKeys: readonly (readonly unknown[])[]
}

export function useWriteMutation<TVars, TData = unknown>(
  spec: WriteMutationSpec<TVars, TData>,
): UseMutationResult<TData, Error, TVars> {
  const qc = useQueryClient()
  return useMutation<TData, Error, TVars>({
    mutationFn: (vars) =>
      apiMutate<TData>(
        typeof spec.path === 'function' ? spec.path(vars) : spec.path,
        spec.method,
        spec.body ? spec.body(vars) : undefined,
        spec.schema,
      ),
    onSuccess: () => {
      for (const key of spec.invalidateKeys) {
        void qc.invalidateQueries({ queryKey: [...key] })
      }
    },
  })
}
