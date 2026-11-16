import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

/**
 * 页面级错误边界：任一懒加载页面组件抛错时，显示可解释的错误卡而不是整页空白。
 *
 * 2026-11-16 星辰 AI 空白页反馈暴露：整棵路由树没有 ErrorBoundary，
 * 懒 chunk 失败 / 单个气泡组件抛错都会让 <Outlet /> 什么都不渲染。
 * 这里只拦渲染异常，不吞后端错误、不伪造数据、不把失败显示成成功。
 */
export class PageErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('[PageErrorBoundary] 页面渲染失败', error, info.componentStack)
  }

  render(): ReactNode {
    const e = this.state.error
    if (!e) return this.props.children
    return (
      <div
        role="alert"
        className="flow rounded-card border border-sf-danger bg-sf-danger-soft px-4 py-3 text-body text-sf-danger"
      >
        <strong className="text-title font-semibold">页面渲染失败</strong>
        <p>该页面组件抛出异常，已阻止整页空白。原始错误：{e.message || '未知错误'}</p>
        <p className="text-label text-sf-ink-3">
          数据未被改写；可重试渲染，或重新加载页面恢复完整状态。
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="rounded-tile border border-current px-2.5 py-1 text-label hover:opacity-80"
          >
            重试渲染
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-tile border border-current px-2.5 py-1 text-label hover:opacity-80"
          >
            重新加载页面
          </button>
        </div>
      </div>
    )
  }
}
