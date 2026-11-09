/**
 * ECharts 按需注册的唯一入口（tree-shaking）。
 *
 * 历史：EChart.tsx 曾直接动态加载全量 echarts 主包，实测构建产物
 * echarts chunk 1,124 kB / gzip 374 kB，其中绝大多数图表类型本项目从未使用。
 * 改为 echarts/core + 具名图表/组件注册后，rollup 能摇掉未引用的实现；
 * EChart.tsx 仍通过动态 import('./echartsSetup') 保持「仅图表挂载时才加载」。
 *
 * ⚠️ 新增图表类型或 option 组件时必须同步下面 use([...]) 清单，
 * 否则该图表会**静默不渲染**（不抛错）。tests/unit/echarts-setup.test.ts
 * 全 src 真扫 `type: 'xxx'` 与 option 顶层组件键来兜底。
 */
import { init, use } from 'echarts/core'
import {
  BarChart,
  CandlestickChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  RadarChart,
  TreemapChart,
} from 'echarts/charts'
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  // 图表类型（对应全站 `type: '...'` 真扫结果）
  BarChart,
  CandlestickChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  RadarChart,
  TreemapChart,
  // 坐标系 / 交互 / 标注组件
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  RadarComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export { init }
