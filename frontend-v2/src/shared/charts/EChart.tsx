import { useEffect, useRef } from 'react'
import type { ECharts, EChartsOption } from 'echarts'
import { remapChartColors, type ChartTheme } from './palette'

interface EChartProps {
  option: EChartsOption
  height?: number
  className?: string
  /** 无障碍：图表文本替代。canvas 内容读屏不可达，必须给出一句可理解的描述。 */
  ariaLabel?: string
}

/** 从根元素 data-theme 读当前生效主题（由 index.html FOUC 脚本 / applyTheme 写入）。 */
function readChartTheme(): ChartTheme {
  try {
    if (typeof document !== 'undefined' && document.documentElement?.dataset.theme === 'light') {
      return 'light'
    }
  } catch {
    /* SSR / 异常环境回落 dark */
  }
  return 'dark'
}

/**
 * 轻量 ECharts 封装：动态 import('echarts')，仅当图表挂载时才拉取 echarts 分包，
 * 主包不再静态依赖 echarts（满足 DESIGN.md §4 预算；vite.config 的 manualChunks 再将其独立成块）。
 * 纯展示组件：option 变化只调 setOption，不重建实例；卸载时 dispose 释放 canvas。
 *
 * 主题：初始 / 更新 setOption 均经 remapChartColors；订阅 ss-theme-change 自定义事件，
 * 主题切换时仅重映射 option 后 setOption(notMerge)，绝不 dispose / 重建实例（不依赖 React Context）。
 *
 * 无障碍（DESIGN.md §5）：容器 role=img + aria-label，并提供 sr-only 文本替代；
 * 图形不是唯一信息载体，同页 Stat / 脚注给出关键数值。
 */
export function EChart({ option, height = 220, className, ariaLabel }: EChartProps) {
  const elRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<ECharts | null>(null)
  const optionRef = useRef<EChartsOption>(option)
  optionRef.current = option

  useEffect(() => {
    let disposed = false
    let ro: ResizeObserver | undefined
    void (async () => {
      const echarts = await import('echarts')
      if (disposed || !elRef.current) return
      const chart = echarts.init(elRef.current)
      chartRef.current = chart
      chart.setOption(remapChartColors(optionRef.current, readChartTheme()) as EChartsOption)
      ro = new ResizeObserver(() => chart.resize())
      ro.observe(elRef.current)
    })()
    return () => {
      disposed = true
      ro?.disconnect()
      chartRef.current?.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(remapChartColors(option, readChartTheme()) as EChartsOption)
  }, [option])

  // 主题切换：只重映射当前 option 后 setOption，不 dispose / reinit。
  useEffect(() => {
    if (typeof window === 'undefined') return
    const onThemeChange = (e: Event) => {
      const chart = chartRef.current
      if (!chart) return
      const detail = (e as CustomEvent<ChartTheme>).detail
      const next: ChartTheme = detail === 'light' || detail === 'dark' ? detail : readChartTheme()
      chart.setOption(remapChartColors(optionRef.current, next) as EChartsOption, { notMerge: true })
    }
    window.addEventListener('ss-theme-change', onThemeChange)
    return () => window.removeEventListener('ss-theme-change', onThemeChange)
  }, [])

  const label = ariaLabel ?? '数据图表'
  return (
    <div className={className}>
      <div
        ref={elRef}
        role="img"
        aria-label={label}
        style={{ height, width: '100%' }}
      />
      <span className="sr-only">{label}（图形内容，关键数值见同页指标卡与脚注）</span>
    </div>
  )
}
