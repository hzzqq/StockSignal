/**
 * 后端写端点 → v2 覆盖率守卫（2026-11-16 v1/v2 parity 批次）。
 *
 * 真实缺陷：双向审计实测发现后端早已注册自选股 / 价格预警 / 市场告警 / 股吧 /
 * 账户设置等一整套写端点，而 v2 全站 `useMutation` 零命中、一个都没接；
 * 功能全景页却把对应 v1 页标成 `native`，形成「标签说已实现、实际只有只读壳」。
 *
 * 本守卫从**后端 Python 源码真扫** `@bp.post/put/delete` 装饰器 + Blueprint 的
 * url_prefix，得到实际写端点路径；再断言每个端点要么在 v2 `src/api/` 里出现，
 * 要么显式列入 HONEST_PENDING 白名单。白名单即「尚未做到」的诚实清单，
 * 新增后端写端点而 v2 忘记接时会立刻 fail，不允许靠改标签蒙混过去。
 *
 * 与 v2Mapping.test.ts 的分工：那边守「标签不撒谎」，这边守「端点不悬空」。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'

const ROOT = resolve(process.cwd(), '..')

function walk(dir: string, exts: readonly string[]): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...walk(p, exts))
    else if (exts.some((e) => name.endsWith(e))) out.push(p)
  }
  return out
}

/** 从后端源码真扫写端点。返回去掉 /api 前缀后的 v2 相对路径前缀。 */
function backendWriteEndpoints(): string[] {
  const pyFiles = [
    ...walk(join(ROOT, 'backend/api'), ['.py']),
    join(ROOT, 'backend/auth/routes.py'),
  ]
  const found = new Set<string>()
  for (const file of pyFiles) {
    const src = readFileSync(file, 'utf8')
    const prefixMatch = src.match(/Blueprint\(\s*["'][^"']+["']\s*,\s*__name__\s*,\s*url_prefix\s*=\s*["']([^"']+)["']/)
    const prefix = prefixMatch ? prefixMatch[1] : ''
    // 只认本文件自己定义的 bp；跳过 read_routes 等纯 GET 文件自然无匹配
    for (const m of src.matchAll(/@bp\.(?:post|put|delete)\(\s*["']([^"']*)["']/g)) {
      const full = `${prefix}${m[1]}`
      const rel = full.startsWith('/api') ? full.slice(4) : full
      // 动态段：<int:id> → 取它之前的静态前缀（v2 模板字符串会在这里拼接变量）
      const segs = rel.split('/')
      const dyn = segs.findIndex((s) => s.includes('<'))
      const staticPath = dyn === -1 ? rel : segs.slice(0, dyn).join('/') + '/'
      found.add(staticPath || '/')
    }
  }
  return [...found].sort()
}

const v2ApiSrc = walk(join(ROOT, 'frontend-v2/src/api'), ['.ts'])
  .map((f) => readFileSync(f, 'utf8'))
  .join('\n')

/**
 * 后端有写端点、但 v2 本批**明确尚未承接**的路径前缀。
 * 每条都必须在文档 docs/frontend-v2/V1-V2-PARITY.md 里能找到对应说明。
 * ⚠️ 禁止为了过守卫随便往这里加条目——加一条等于承认一处「未做到」。
 */
const HONEST_PENDING: Record<string, string> = {
  '/cond-orders': 'C 类实盘红线：条件单/自动扫描真实下单，v2 明确不做',
  '/trade/': 'C 类实盘红线：真实券商下单与账户写入，v2 明确不做',
  '/admin/config': 'B 类：站点配置 CRUD 需后端权限模型对齐，下一批',
  '/recommendations/generate': 'B 类：荐股生成任务触发，v2 仅有只读结果展示',
  '/research-runs/run': 'B 类：异步研报任务触发，v2 仅有只读运行记录',
}

/** v2 已接（或本批接入）的端点，必须真实出现在 src/api/ 源码里。 */
const REQUIRED_COVERED = [
  '/watchlist',
  '/junk-stocks',
  '/user-scores',
  '/price-alerts',
  '/market-alerts',
  '/forum/posts',
  '/auth/settings',
  '/auth/avatar',
  '/auth/logout',
  '/auth/register',
]

describe('后端写端点 ↔ v2 API 层覆盖率', () => {
  it('能从后端源码真扫出写端点（守卫自身不空转）', () => {
    const eps = backendWriteEndpoints()
    expect(eps.length).toBeGreaterThanOrEqual(20)
    expect(eps).toContain('/watchlist')
    expect(eps).toContain('/price-alerts')
    expect(eps).toContain('/forum/posts')
    expect(eps).toContain('/cond-orders')
  })

  it('本批目标写端点全部已在 v2 src/api/ 接线（不是只写在 MSW 或注释里）', () => {
    for (const path of REQUIRED_COVERED) {
      expect(v2ApiSrc, `${path} 未出现在 v2 API 层`).toContain(path)
    }
  })

  it('所有后端写端点要么已接线、要么在诚实白名单里（不静默漏接）', () => {
    const eps = backendWriteEndpoints()
    const uncovered: string[] = []
    for (const ep of eps) {
      if (v2ApiSrc.includes(ep)) continue
      if (Object.keys(HONEST_PENDING).some((k) => ep.startsWith(k))) continue
      uncovered.push(ep)
    }
    expect(uncovered, `以下写端点既未接线也未诚实登记：${uncovered.join(', ')}`).toEqual([])
  })

  it('实盘红线端点绝不出现在 v2 API 层', () => {
    expect(v2ApiSrc).not.toContain('/cond-orders')
    expect(v2ApiSrc).not.toContain('/trade/orders')
    expect(v2ApiSrc).not.toMatch(/action\s*[:=]\s*['"]buy['"]/)
  })

  it('所有写请求都走统一写层 apiMutate（防三套分裂回潮）', () => {
    const apiFiles = walk(join(ROOT, 'frontend-v2/src/api'), ['.ts'])
    // 历史遗留：endpoints.ts(login) / client.ts(refresh 递归) / admin.ts / chat.ts
    // 在本批之前已有裸 apiFetch 写操作；本批新增的写模块必须走 apiMutate。
    const LEGACY = new Set(['endpoints.ts', 'client.ts', 'admin.ts', 'chat.ts', 'write.ts', 'schema.ts', 'read.ts', 'diagnostics.ts', 'stock.ts', 'stockSearch.ts'])
    const offenders: string[] = []
    for (const f of apiFiles) {
      const base = f.split(/[\\/]/).pop() ?? ''
      if (LEGACY.has(base)) continue
      const src = readFileSync(f, 'utf8')
      if (/method:\s*['"](?:POST|PUT|DELETE)['"]/.test(src) && !src.includes('apiMutate')) {
        offenders.push(base)
      }
    }
    expect(offenders, `以下新增写模块绕过统一写层：${offenders.join(', ')}`).toEqual([])
  })
})
