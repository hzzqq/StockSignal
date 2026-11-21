import { apiMutate } from './write'
import {
  PortfolioPositionInputSchema,
  PortfolioSellInputSchema,
  PortfolioPositionAddedSchema,
  PortfolioPositionDeletedSchema,
  PortfolioSellRecordedSchema,
  type PortfolioPositionInput,
  type PortfolioSellInput,
} from './schemas/portfolioWrite'

/**
 * 40/41/45 组合写操作（v2 统一写层，本地模拟账本，非实盘）。
 * 所有写请求经 apiMutate：Bearer + 401 单飞刷新 + 信封解包 + Zod 严格解析。
 */
export function addPortfolioPosition(input: PortfolioPositionInput) {
  const body = PortfolioPositionInputSchema.parse(input)
  return apiMutate('/v2/portfolio/positions', 'POST', body, PortfolioPositionAddedSchema)
}

/** index 为 GET /api/v2/read/portfolio 返回 positions 数组的零基行号。 */
export function deletePortfolioPosition(index: number) {
  return apiMutate(
    `/v2/portfolio/positions/${index}`,
    'DELETE',
    undefined,
    PortfolioPositionDeletedSchema,
  )
}

export function recordPortfolioSell(input: PortfolioSellInput) {
  const body = PortfolioSellInputSchema.parse(input)
  return apiMutate('/v2/portfolio/sell', 'POST', body, PortfolioSellRecordedSchema)
}
