/**
 * 共享「重点突出」排版原语：把星辰 AI Markdown 渲染器认可的分节标题 / 重点词
 * 排版推广到全局共享骨架（仅视觉，不承载任何数据语义）。
 *
 * 令牌来源：--color-brand-1 / --color-brand-2 定义于 styles/tokens.css，
 * 暗 / 亮主题恒等；正文色沿用 sf-ink 语义令牌。品牌色属于产品识别色，
 * 与价格涨跌 / 数据状态语义完全无关，本组件不借用那两类配色。
 */
import type { ReactNode } from 'react'

export function SectionTitle({
  children,
  as = 'h3',
  className = '',
}: {
  children: ReactNode
  as?: 'h2' | 'h3' | 'p'
  className?: string
}) {
  const size = as === 'h2' ? 'text-[1.08rem]' : as === 'h3' ? 'text-[1rem]' : 'text-xs'
  const cls = `border-l-[3px] pl-2 font-semibold ${size} text-sf-ink ${className}`.trim()
  const style = { borderColor: 'var(--color-brand-2)' }
  if (as === 'h2') {
    return <h2 className={cls} style={style}>{children}</h2>
  }
  if (as === 'p') {
    return <p className={cls} style={style}>{children}</p>
  }
  return <h3 className={cls} style={style}>{children}</h3>
}

export function LeadText({ children }: { children: ReactNode }) {
  return (
    <strong className="font-bold" style={{ color: 'var(--color-brand-1)' }}>
      {children}
    </strong>
  )
}
