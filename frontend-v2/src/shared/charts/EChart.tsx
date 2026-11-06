import { useEffect, useRef } from 'react'
import type { ECharts, EChartsOption } from 'echarts'

interface EChartProps {
  option: EChartsOption
  height?: number
  className?: string
}

/**
 * 轻量 ECharts 封装：动态 import('echarts')，仅当图表挂载时才拉取 echarts 分包，
 * 主包不再静态依赖 echarts（满足 DESIGN.md §4 预算；vite.config 的 manualChunks 再将其独立成块）。
 * 纯展示组件：option 变化只调 setOption，不重建实例；卸载时 dispose 释放 canvas。
 */
export function EChart({ option, height = 220, className }: EChartProps) {
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
      chart.setOption(optionRef.current)
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
    chartRef.current?.setOption(option)
  }, [option])

  return <div ref={elRef} style={{ height, width: '100%' }} className={className} />
}
