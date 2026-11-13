import { useEffect, useRef, useState } from 'react'
import type { ChatMessage, AiConsultTask } from '@/api/schemas/chat'
import { Markdown } from './Markdown'
import { ProcessCard } from './ProcessCard'
import { TaskCard } from './TaskCard'
import { ParamPromptCard } from './ParamPromptCard'
import { SuggestionChips } from './SuggestionChips'
import { ResponseScaffold } from './ResponseScaffold'
import { copyText } from './util'
import { useXingchenStore } from './useXingchen'

function fmtTs(ts?: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleString('zh-CN', { hour12: false })
}

// rAF 在 jsdom/无头环境可能缺失，做降级
const raf: (cb: (t: number) => void) => number =
  typeof requestAnimationFrame === 'function'
    ? (cb) => requestAnimationFrame((t) => cb(t))
    : (cb) => setTimeout(() => cb(Date.now()), 16) as unknown as number
const caf: (h: number) => void =
  typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : clearTimeout

/** 按 msg.kind 判别渲染（借鉴 FinPilot MessageBubble + 全面化外壳）。 */
export function MessageBubble({
  msg,
  onPickChip,
  onPickParam,
}: {
  msg: ChatMessage
  onPickChip?: (c: string) => void
  onPickParam?: (p: string) => void
}) {
  // 用户：右对齐气泡
  if (msg.kind === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-tile bg-brand-1 px-3 py-2 text-body text-white">
          <p className="whitespace-pre-wrap break-words">{msg.content}</p>
          {msg.ts && (
            <div className="mt-1 text-right text-[0.7rem] text-white/70">{fmtTs(msg.ts)}</div>
          )}
        </div>
      </div>
    )
  }

  // 缺参追问卡片
  if (msg.kind === 'param-prompt') {
    return (
      <div className="flex justify-start">
        <div className="max-w-[90%]">
          <ParamPromptCard prompts={msg.paramPrompt ?? []} onPick={onPickParam} />
        </div>
      </div>
    )
  }

  // ---- assistant（含 tool 态：toolCall/process 均为前端态）----
  const fresh = !!msg.fresh
  const total = msg.content.length
  const [revealDone, setRevealDone] = useState(!fresh)
  const [revealed, setRevealed] = useState(fresh ? 0 : total)
  const ratioRef = useRef(0)
  const [elapsedMs, setElapsedMs] = useState(0)
  const startRef = useRef(Date.now())

  // 客户端流式揭示：fresh 消息一次性拿到全量 content，本地逐段展开「一点一点生成」
  useEffect(() => {
    if (!fresh) return
    const start = startRef.current
    const DURATION = Math.min(4000, Math.max(1200, total * 12))
    let handle = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION)
      ratioRef.current = t
      setRevealed(Math.floor(t * total))
      if (t < 1) {
        handle = raf(tick)
      } else {
        setRevealDone(true)
        setRevealed(total)
        useXingchenStore.getState().markRevealed(msg.id)
      }
    }
    handle = raf(tick)
    return () => caf(handle)
  }, [fresh, total, msg.id])

  const polling = msg.status === 'streaming' && !fresh
  const revealing = fresh && !revealDone
  const generating = polling || revealing

  // 流式期计时（已用秒）
  useEffect(() => {
    if (!generating) return
    const id = setInterval(() => setElapsedMs(Date.now() - startRef.current), 400)
    return () => clearInterval(id)
  }, [generating])

  const meta = msg.analysisMeta
  const task = msg.toolCall as AiConsultTask | undefined
  const isStreaming = msg.status === 'streaming'
  const shown = msg.content.slice(0, revealed)
  const ratio = generating ? (polling ? 0 : ratioRef.current) : 1

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] rounded-tile border border-sf-line bg-sf-surface px-3 py-2 text-body text-sf-ink-2">
        {/* 全面化外壳：标题卡 + 三阶段步进器 + 多维研判维度卡 */}
        {meta && (
          <ResponseScaffold
            meta={meta}
            streaming={generating}
            completed={msg.status === 'done' && !generating}
            ratio={ratio}
          />
        )}

        {/* 规则引擎问题分析卡（问题解析细节，生成期中展开） */}
        {msg.process && msg.process.length > 0 && (
          <div className={meta ? 'mt-2' : ''}>
            <ProcessCard steps={msg.process} defaultOpen={generating} />
          </div>
        )}

        {/* 生成中状态行（轮询真实进度 / 客户端揭示） */}
        {generating && (
          <div className="mt-2 flex items-center gap-2 text-label text-sf-warn">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sf-warn animate-pulse" />
            {polling ? '正在分析（后台任务执行中）…' : '正在生成结论…'}
            <span className="text-sf-ink-3">已用 {(elapsedMs / 1000).toFixed(0)}s</span>
          </div>
        )}

        {/* 后台任务真实进度（仅轮询期） */}
        {isStreaming && task && <TaskCard task={task} className="mt-2" />}
        {isStreaming && !msg.content && !task && (
          <div className="mt-1 flex items-center gap-2 text-label text-sf-ink-3">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sf-accent animate-pulse" />
            思考中…
          </div>
        )}

        {msg.status === 'error' ? (
          <div role="alert" className="mt-1 flex items-start gap-2 text-sf-danger">
            <span aria-hidden="true">⚠️</span>
            <span>{(msg.errors && msg.errors[0]) || '生成失败'}</span>
          </div>
        ) : shown ? (
          <div className="mt-1">
            <Markdown content={shown} />
          </div>
        ) : null}

        {msg.chips && msg.chips.length > 0 && !generating && msg.status !== 'error' && (
          <SuggestionChips chips={msg.chips} onPick={onPickChip} />
        )}

        {shown && msg.status !== 'error' && !generating && (
          <div className="mt-1 flex items-center justify-between text-[0.7rem] text-sf-ink-3">
            <span>{fmtTs(msg.ts)}</span>
            <button
              type="button"
              onClick={() => copyText(msg.content)}
              className="hover:text-sf-accent"
            >
              ⧉ 复制
            </button>
          </div>
        )}

        {revealDone && !generating && msg.status === 'done' && (
          <div className="mt-1 flex items-center gap-1 text-[0.7rem] text-sf-accent">
            <span aria-hidden="true">✓</span>分析完成
          </div>
        )}
      </div>
    </div>
  )
}
