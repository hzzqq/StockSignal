import { apiFetch } from './client'

/**
 * v2 统一写层（单一真理源，2026-11-16 v1/v2 parity 批次引入）。
 *
 * 背景：双向审计实测发现 v2 全站 `useMutation` 零命中、写操作散落在
 * admin.ts / chat.ts / endpoints.ts 三处各写一套 apiFetch，而后端早已注册
 * 自选股 / 价格预警 / 市场告警 / 股吧 / 账户设置等一整套写端点却一个都没接。
 *
 * 红线：
 *  - 所有写请求必须经此函数，统一走 apiFetch（Bearer + 401 单飞刷新 + 信封解包）。
 *  - data 缺失 / 类型不符一律由传入的 Zod schema 抛错，绝不 `?? 0` / 兜底。
 *  - 无响应体的端点（DELETE 等）传 schema=null 显式表示「不解析」，不是静默成功。
 *  - 失败原样抛 ApiError，页面必须如实显示，禁止把 error 洗成成功。
 *
 * schema 用结构类型而非 z.ZodType，避免 Zod 4 泛型签名差异导致 TS 报错；
 * 任何具备 parse(raw): T 的对象（含全部 Zod schema）都可实现该接口。
 */
export interface Parser<T> {
  parse: (raw: unknown) => T
}

export type WriteMethod = 'POST' | 'PUT' | 'DELETE'

/** 统一写请求：信封解包 → 可选严格解析 → 返回 data。 */
export async function apiMutate<T = unknown>(
  path: string,
  method: WriteMethod,
  body?: unknown,
  schema?: Parser<T> | null,
): Promise<T> {
  const init: RequestInit = { method }
  if (body !== undefined) init.body = JSON.stringify(body)
  const data = await apiFetch<unknown>(path, init)
  if (schema === null) return data as T
  if (schema) return schema.parse(data)
  return data as T
}
