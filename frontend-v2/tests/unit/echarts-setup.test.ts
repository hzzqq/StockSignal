/**
 * ECharts 按需注册守卫。
 *
 * 真实风险：改成 echarts/core 后，新增图表类型 / option 组件若忘了在
 * echartsSetup.ts 的 use([...]) 里注册，图表会**静默不渲染**（不抛异常），
 * 而 typecheck / 现有测试全绿。本守卫全 src 真扫实际用到的类型与组件键，
 * 逐项要求注册清单覆盖，并用反例自测确保扫描器自己没失效。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const SRC = resolve(process.cwd(), 'src')
const SETUP_REL = 'shared/charts/echartsSetup.ts'
const ECHART_REL = 'shared/charts/EChart.tsx'
const read = (p: string) => readFileSync(resolve(SRC, p), 'utf-8')

/** 剥注释：注释里写 type / 注册名不能喂饱守卫。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function allSource(dir = SRC): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...allSource(full))
    else if ((name.endsWith('.ts') || name.endsWith('.tsx')) && !name.endsWith('.d.ts')) {
      out.push(stripComments(readFileSync(full, 'utf-8')))
    }
  }
  return out
}

/** 只认已知 ECharts 图表类型；lineStyle.type:'dashed' 之类不算。 */
const CHART_MODULES: Record<string, string> = {
  bar: 'BarChart', line: 'LineChart', candlestick: 'CandlestickChart',
  radar: 'RadarChart', gauge: 'GaugeChart', pie: 'PieChart',
  scatter: 'ScatterChart', heatmap: 'HeatmapChart', graph: 'GraphChart',
  sunburst: 'SunburstChart', treemap: 'TreemapChart', funnel: 'FunnelChart',
  sankey: 'SankeyChart', boxplot: 'BoxplotChart', custom: 'CustomChart',
}

const COMPONENT_MODULES: Record<string, string> = {
  grid: 'GridComponent', xAxis: 'GridComponent', yAxis: 'GridComponent',
  tooltip: 'TooltipComponent', legend: 'LegendComponent', title: 'TitleComponent',
  dataZoom: 'DataZoomComponent', axisPointer: 'AxisPointerComponent',
  markLine: 'MarkLineComponent', markPoint: 'MarkPointComponent',
  radar: 'RadarComponent', visualMap: 'VisualMapComponent',
  dataset: 'DatasetComponent', toolbox: 'ToolboxComponent',
  graphic: 'GraphicComponent', polar: 'PolarComponent',
}

function scanChartTypes(code: string): Set<string> {
  const out = new Set<string>()
  // scanner 自身就剥注释：注释里的 `type: 'pie'` 不得喂饱守卫
  for (const m of stripComments(code).matchAll(/\btype:\s*'([A-Za-z]+)'/g)) {
    if (m[1] in CHART_MODULES) out.add(m[1])
  }
  return out
}

function scanComponentKeys(code: string): Set<string> {
  const out = new Set<string>()
  for (const m of stripComments(code).matchAll(/\b([A-Za-z]+)\s*:/g)) {
    if (m[1] in COMPONENT_MODULES) out.add(m[1])
  }
  return out
}

function registeredFrom(setupSrc: string): Set<string> {
  const block = stripComments(setupSrc).match(/\buse\(\[([\s\S]*?)\]\)/)
  if (!block) return new Set()
  return new Set(block[1].match(/\b[A-Z][A-Za-z]*(?:Chart|Component|Renderer)\b/g) ?? [])
}

function missingModules(setupSrc: string, types: Set<string>, keys: Set<string>): string[] {
  const registered = registeredFrom(setupSrc)
  const expected = new Set<string>([
    ...[...types].map((t) => CHART_MODULES[t]),
    ...[...keys].map((k) => COMPONENT_MODULES[k]),
  ])
  return [...expected].filter((m) => !registered.has(m)).sort()
}

const allCode = allSource()
const usedTypes = new Set<string>()
const usedKeys = new Set<string>()
for (const code of allCode) {
  for (const t of scanChartTypes(code)) usedTypes.add(t)
  for (const k of scanComponentKeys(code)) usedKeys.add(k)
}
const setupSrc = read(SETUP_REL)

describe('ECharts 按需注册覆盖全站真实用法', () => {
  it('扫描器真扫到足够多的源码 / 图表类型 / 组件键（防空集恒真）', () => {
    expect(allCode.length).toBeGreaterThanOrEqual(60)
    expect(usedTypes.size).toBeGreaterThanOrEqual(5)
    expect(usedKeys.size).toBeGreaterThanOrEqual(8)
    expect([...usedTypes]).toEqual(expect.arrayContaining(['bar', 'line', 'candlestick']))
  })

  it('use([...]) 清单覆盖所有实际用到的图表类型与组件', () => {
    expect(registeredFrom(setupSrc).size).toBeGreaterThanOrEqual(14)
    expect(missingModules(setupSrc, usedTypes, usedKeys)).toEqual([])
  })

  it('EChart.tsx 保持懒加载且不再拉全量 echarts 主包', () => {
    const src = stripComments(read(ECHART_REL))
    expect(src).toContain("import('./echartsSetup')")
    expect(src).not.toMatch(/import\(\s*['"]echarts['"]\s*\)/)
  })
})

describe('扫描器反例自测', () => {
  it('能抓到真实 type 写法、忽略 lineStyle 与注释里的假信号', () => {
    expect([...scanChartTypes("const s = { type: 'candlestick' }")]).toContain('candlestick')
    expect([...scanChartTypes("const s = { type: 'line' as const }")]).toContain('line')
    expect(scanChartTypes("lineStyle: { type: 'dashed' }").size).toBe(0)
    expect(scanChartTypes("// type: 'pie'\nconst a = 1").size).toBe(0)
    expect([...scanComponentKeys('const o = { tooltip: {}, dataZoom: [] }')])
      .toEqual(expect.arrayContaining(['tooltip', 'dataZoom']))
  })

  it('删掉一个注册项或掏空清单必须被抓出来（守卫不自静音）', () => {
    // 必须删 use([...]) 注册块里的那一项，删 import 块不影响注册清单
    const at = setupSrc.search(/^use\(\[/m)
    expect(at).toBeGreaterThan(0)
    const head = setupSrc.slice(0, at)
    const tail = setupSrc.slice(at).replace('CandlestickChart,', '')
    const reduced = head + tail
    expect(reduced).not.toBe(setupSrc)
    expect(missingModules(reduced, usedTypes, usedKeys)).toContain('CandlestickChart')
    expect(missingModules('export const nothing = 1', usedTypes, usedKeys).length)
      .toBeGreaterThanOrEqual(5)
  })
})
