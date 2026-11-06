import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { FreshnessBadge } from '@/shared/ui/FreshnessBadge'
import { Stat } from '@/shared/ui/Stat'
import { Card } from '@/shared/ui/Card'
import { EmptyState, ErrorState, Loading } from '@/shared/ui/States'

describe('纯展示组件（renderToStaticMarkup）', () => {
  it('FreshnessBadge stale 显示「数据陈旧」', () => {
    const html = renderToStaticMarkup(<FreshnessBadge level="stale" />)
    expect(html).toContain('数据陈旧')
  })
  it('FreshnessBadge ok 显示「数据新鲜」', () => {
    expect(renderToStaticMarkup(<FreshnessBadge level="ok" />)).toContain('数据新鲜')
  })
  it('Stat 渲染标签与数值', () => {
    const html = renderToStaticMarkup(<Stat label="评分" value={47.9} sub="中性" />)
    expect(html).toContain('评分')
    expect(html).toContain('47.9')
    expect(html).toContain('中性')
  })
  it('Card 渲染标题与子内容', () => {
    const html = renderToStaticMarkup(
      <Card title="测试">
        <span>内容</span>
      </Card>,
    )
    expect(html).toContain('测试')
    expect(html).toContain('内容')
  })
  it('EmptyState / ErrorState / Loading 文案', () => {
    expect(renderToStaticMarkup(<EmptyState label="暂无数据" />)).toContain('暂无数据')
    expect(renderToStaticMarkup(<ErrorState message="加载失败" />)).toContain('加载失败')
    expect(renderToStaticMarkup(<Loading />)).toContain('加载中')
  })
})
