import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { V1_PAGES, type V1Page } from './v1Pages.generated'
import {
  mappingOf,
  statusCounts,
  NATIVE_TARGETS,
  NATIVE_FILES,
  PINNED_FILES,
} from './v2Mapping'

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

/** AppPath 是类型，运行时从 nav.ts 源码真扫（与 nav.test.ts 同范式）。 */
const APP_PATHS: string[] = [...read('../../nav/nav.ts').matchAll(/\| '(\/[^']*)'/g)].map(
  (m) => m[1],
)

/** 映射表源码分区：文本断言用（防止「只改注释、没改数据」的伪修正）。 */
const SRC = read('./v2Mapping.ts')
const NATIVE_BLOCK = SRC.slice(SRC.indexOf('const NATIVE'), SRC.indexOf('const DATA'))
const PINNED_BLOCK = SRC.slice(
  SRC.indexOf('const PINNED'),
  SRC.indexOf('export function mappingOf'),
)

/** 取磁盘上真实存在的 v1 页对象（顺带断言清单未丢页）。 */
function mustPage(file: string): V1Page {
  const p = V1_PAGES.find((x) => x.file === file)
  if (!p) throw new Error(`v1 清单缺少页：${file}`)
  return p
}

/**
 * 2026-11-16 v1/v2 parity 双向失真防复发守卫。
 *
 * 历史缺陷：v2Mapping.ts 曾同时「低估」（53/52 已实现却标 pinned）与
 * 「高估」（44 真实下单标 native→/alerts、42 零写操作标 native 且零说明、
 * 63 模块错配仍标 native→/backtest）。本守卫把审计结论固化为回归网。
 */
describe('v2Mapping · v1→v2 双向失真防复发守卫', () => {
  it('纠正「低估」：53 星辰 AI / 52 股吧 为 native 且目标正确，PINNED 表不得再出现', () => {
    const xc = mappingOf(mustPage('53_星辰AI.py'))
    expect(xc.status).toBe('native')
    expect(xc.to).toBe('/xingchen')

    const forum = mappingOf(mustPage('52_股吧.py'))
    expect(forum.status).toBe('native')
    expect(forum.to).toBe('/forum')

    expect(PINNED_BLOCK).not.toContain('53_星辰AI.py')
    expect(PINNED_BLOCK).not.toContain('52_股吧.py')
  })

  it('纠正「高估」：44 智能条件单 / 43 实盘交易 为 v1-pinned 且 note 含实盘/券商红线', () => {
    for (const f of ['44_智能条件单.py', '43_实盘交易.py']) {
      const m = mappingOf(mustPage(f))
      expect(m.status, `${f} 应为 v1-pinned`).toBe('v1-pinned')
      expect(m.note, `${f} 缺红线说明`).toMatch(/实盘|券商/)
    }
    // 全表任何 NATIVE 项都不许指向条件单/下单端点，也不许出现下单动作字样
    for (const banned of [
      /\/cond-orders/,
      /action=buy/,
      /cond-orders\/scan/,
      /\/api\/trade\/orders/,
      /live_mode/,
    ]) {
      expect(NATIVE_BLOCK, `NATIVE 段不该出现 ${banned}`).not.toMatch(banned)
    }
    expect(NATIVE_TARGETS.some((t) => /cond-orders|trade\/orders/.test(t))).toBe(false)
  })

  it('已知能力缩水页：mappingOf 必带非空 note（杜绝「标 native 却零说明」）', () => {
    const shrinkPages = [
      '11_股票选取.py',
      '14_智能盯盘.py',
      '20_个股分析.py',
      '40_仓位管理.py',
      '41_组合收益.py',
      '45_持仓中心.py',
      '46_自选股监控.py',
    ]
    for (const f of shrinkPages) {
      const m = mappingOf(mustPage(f))
      expect(m.note, `${f} 缺诚实 note`).toBeTruthy()
      expect(m.note!.trim().length, `${f} note 为空`).toBeGreaterThan(0)
    }
    // 42 模拟账本写已在 parity C 真承接、95 多格式导出已在 parity D 真承接
    // （见下条 parity D 测试），均不再属于缩水页
  })

  it('parity D：77 业绩预告扫描 / 81 NL 执行 / 95 多格式导出已真承接为 native', () => {
    const fh = mappingOf(mustPage('77_财报猎手.py'))
    expect(fh.status).toBe('native')
    expect(fh.to).toBe('/financial-hunter')
    expect(fh.note).toMatch(/earnings-hunter/)
    const nl = mappingOf(mustPage('81_自然语言选股.py'))
    expect(nl.status).toBe('native')
    expect(nl.to).toBe('/stock/screener')
    expect(nl.note).toMatch(/nl-screen\/execute/)
    const exp = mappingOf(mustPage('95_数据导出.py'))
    expect(exp.status).toBe('native')
    expect(exp.to).toBe('/export')
    expect(exp.note).toMatch(/export-bundle/)
  })

  it('parity C：31 形态扫描 / 42 模拟账本写已真承接为 native', () => {
    const pat = mappingOf(mustPage('31_形态选股.py'))
    expect(pat.status).toBe('native')
    expect(pat.to).toBe('/pattern-scan')
    const paper = mappingOf(mustPage('42_模拟交易.py'))
    expect(paper.status).toBe('native')
    expect(paper.note).toMatch(/模拟账本写/)
  })

  it('parity B：61 广度分化 / 63 温度回测已真承接为 native（不再是缩水页 / v1-only）', () => {
    const div = mappingOf(mustPage('61_广度分化.py'))
    expect(div.status).toBe('native')
    expect(div.to).toBe('/breadth-divergence')
    const temp = mappingOf(mustPage('63_温度回测.py'))
    expect(temp.status).toBe('native')
    expect(temp.to).toBe('/temperature-backtest')
    // 63 绝不能回退到策略回测 /backtest（模块错配）
    expect(temp.to).not.toBe('/backtest')
    expect(statusCounts()['v1-only']).toBe(0)
  })

  it('所有 native 的 to 必须是 nav.ts AppPath 真实路径（/forum 为本批唯一待接线项）', () => {
    // /forum 由 team-lead 本批统一接入 AppPath / router / NAV；接线前作为唯一已知待接线项豁免。
    // 接线后它进入 APP_PATHS，pending 自动清空，守卫收紧为「零孤儿」。
    const pending = APP_PATHS.includes('/forum') ? [] : ['/forum']
    const valid = new Set([...APP_PATHS, ...pending])
    for (const t of NATIVE_TARGETS) {
      expect(valid.has(t), `native 目标 ${t} 不在 AppPath`).toBe(true)
    }
    // 精确锁定豁免：除 /forum 外不得夹带任何其它「不在 AppPath」的孤儿目标
    const orphan = NATIVE_TARGETS.filter((t) => !APP_PATHS.includes(t))
    expect([...orphan].sort()).toEqual([...pending].sort())
  })

  it('statusCounts 四档之和 = V1_PAGES.length，且各档为非负整数', () => {
    const counts = statusCounts()
    // CI 日志留痕：四档分布随 v2Mapping.ts 实时变化，禁止写死到文档
    console.log('[v2Mapping] statusCounts =', JSON.stringify(counts))
    for (const [k, v] of Object.entries(counts)) {
      expect(Number.isInteger(v) && v >= 0, `${k} 档计数异常：${v}`).toBe(true)
    }
    expect(Object.keys(counts).sort()).toEqual(
      ['data', 'native', 'v1-only', 'v1-pinned'].sort(),
    )
    expect(Object.values(counts).reduce((a, b) => a + b, 0)).toBe(V1_PAGES.length)
  })

  it('登记表 key 均为磁盘真实页、且 NATIVE/PINNED 无跨档重复（防漏项/多项）', () => {
    const real = new Set(V1_PAGES.map((p) => p.file))
    for (const f of [...NATIVE_FILES, ...PINNED_FILES]) {
      expect(real.has(f), `登记表出现磁盘不存在的页：${f}`).toBe(true)
    }
    for (const f of NATIVE_FILES) {
      expect(PINNED_FILES, `${f} 同时登记在 NATIVE 与 PINNED`).not.toContain(f)
    }
  })
})
