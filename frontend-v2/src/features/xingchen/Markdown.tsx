import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * Markdown 渲染（react-markdown + remark-gfm）。
 * - 表格 / 列表 / 行内码 / 引用块 走语义令牌，跟随 data-theme。
 * - `[S1]` 引用徽标：预处理为 `#xc-src-1` 锚点，由 a 渲染器识别为带
 *   cursor:help 的 S# 徽标（标题提示「引用来源 S1」），不破坏 markdown 结构。
 *
 * 设计红线：不引入 FinPilot 的 antd 样式，仅复用其「react-markdown + remark-gfm」
 * 选型思路（见 V2-XINGCHEN-AI-DESIGN.md §8.9）。
 */

function preprocess(src: string): string {
  return (src || '').replace(/\[S(\d+)\]/g, '[S$1](#xc-src-$1)')
}

const components: Components = {
  a({ href, children }) {
    if (href && href.startsWith('#xc-src-')) {
      const n = href.replace('#xc-src-', '')
      return (
        <span
          className="mx-0.5 inline-flex cursor-help items-center rounded bg-sf-surface-2 px-1 align-middle text-label text-sf-accent"
          title={`引用来源 S${n}`}
          aria-label={`引用来源 S${n}`}
        >
          S{n}
        </span>
      )
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-sf-accent underline">
        {children}
      </a>
    )
  },
  table({ children }) {
    return <table className="my-3 w-full border-collapse text-body">{children}</table>
  },
  th({ children }) {
    return (
      <th className="border border-sf-line bg-sf-surface-2 px-2 py-1 text-left font-medium text-sf-ink-2">
        {children}
      </th>
    )
  },
  td({ children }) {
    return <td className="border border-sf-line px-2 py-1 text-sf-ink-2">{children}</td>
  },
  h1({ children }) {
    return <h1 className="mb-1 mt-3 text-[1.2rem] font-semibold text-sf-ink">{children}</h1>
  },
  h2({ children }) {
    return <h2 className="mb-1 mt-3 text-[1.08rem] font-semibold text-sf-ink">{children}</h2>
  },
  h3({ children }) {
    return <h3 className="mb-1 mt-2 text-[1rem] font-semibold text-sf-ink">{children}</h3>
  },
  p({ children }) {
    return <p className="my-1.5 leading-relaxed text-sf-ink-2">{children}</p>
  },
  ul({ children }) {
    return <ul className="my-1.5 list-disc space-y-1 pl-5 text-sf-ink-2">{children}</ul>
  },
  ol({ children }) {
    return <ol className="my-1.5 list-decimal space-y-1 pl-5 text-sf-ink-2">{children}</ol>
  },
  blockquote({ children }) {
    return <blockquote className="my-2 border-l-2 border-sf-line pl-3 text-sf-ink-3">{children}</blockquote>
  },
  hr() {
    return <hr className="my-3 border-sf-line" />
  },
  strong({ children }) {
    return <strong className="font-semibold text-sf-ink">{children}</strong>
  },
  code({ className, children }) {
    const isBlock = /language-/.test(className || '')
    if (isBlock) {
      return <code className="font-mono text-sf-ink">{children}</code>
    }
    return (
      <code className="rounded bg-sf-surface-2 px-1 py-0.5 text-[0.88em] text-sf-accent">{children}</code>
    )
  },
  pre({ children }) {
    return (
      <pre className="my-3 overflow-auto rounded-tile border border-sf-line bg-sf-surface-2 p-3 text-body">
        {children}
      </pre>
    )
  },
}

export function Markdown({ content }: { content: string }) {
  return (
    <div className="xc-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {preprocess(content)}
      </ReactMarkdown>
    </div>
  )
}
