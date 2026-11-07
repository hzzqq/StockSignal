import { apiFetch } from './client'
import { SixDimSchema, type SixDim } from './schemas/stock'

/**
 * W4-A · 个股六维评分（GET /api/v2/read/six-dim?code=<6位>）。
 *
 * 6 位代码校验通过后才发请求；信封已由 apiFetch 解包（并对非 ok 状态抛 ApiError），
 * data 再经 SixDimSchema 严格校验，任何类型不符即抛错（不兜底、不补默认值）。
 */
export async function getSixDim(code: string): Promise<SixDim> {
  if (!/^\d{6}$/.test(code)) {
    throw new Error('股票代码须为 6 位数字')
  }
  const data = await apiFetch<unknown>(`/v2/read/six-dim?code=${encodeURIComponent(code)}`)
  return SixDimSchema.parse(data)
}
