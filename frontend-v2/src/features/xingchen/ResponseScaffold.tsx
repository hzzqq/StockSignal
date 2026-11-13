import type { ChatMessage } from '@/api/schemas/chat'

type AnalysisMeta = NonNullable<ChatMessage['analysisMeta']>

/** 三阶段步骤定义（对标 FinPilot 进度步进器）。 */
const PHASES = ['问题解析', '多维研判', '结论生成'] as const

function StepDot({ state }: { state: 'done' | 'active' | 'pending' }) {
  if (state === 'done') {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-sf-accent text-[0.7rem] text-white">
        ✓
      </span>
    )
  }
  if (state === 'active') {
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full border border-sf-accent text-sf-accent">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sf-accent animate-pulse" />
      </span>
    )
  }
  return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full border border-sf-line text-sf-ink-3" />
  )
}

/**
 * 星辰 AI 回应全面化外壳（对标 FinPilot「深度研究」卡片）：
 * 标题卡（标的 · 风格）+ 三阶段进度步进器 + 多维研判维度卡网格。
 * 维度卡随流式 ratio 翻「分析中 → 已返回」，是分析透镜而非伪造数据（诚实红线）。
 */
export function ResponseScaffold({
  meta,
  streaming,
  completed,
  ratio,
}: {
  meta: AnalysisMeta
  /** 仍在生成中（轮询或客户端揭示）。 */
  streaming: boolean
  /** 已成功完成（status=done 且非生成中）。错误态为 false，维度卡保持「分析中」而非误导为「已返回」。 */
  completed: boolean
  /** 流式进度 0..1（done 时由调用方传 1）。 */
  ratio: number
}) {
  const phase = completed ? 2 : streaming ? (ratio > 0.02 ? 1 : 0) : 1
  const n = meta.dimensions.length || 1
  const title = meta.topic ? `${meta.topic} · ${meta.styleLabel}` : `综合研判 · ${meta.styleLabel}`

  return (
    <div className="rounded-tile border border-sf-line bg-sf-surface-2 p-3">
      {/* 标题卡 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-title font-medium text-sf-ink-2">
          <span aria-hidden="true">📊</span>
          <span className="truncate">{title}</span>
        </div>
        <span className="shrink-0 rounded-tile bg-brand-1/10 px-2 py-0.5 text-label text-sf-accent">
          {meta.styleLabel}
        </span>
      </div>

      {/* 三阶段进度步进器 */}
      <div className="mt-3 flex items-center">
        {PHASES.map((label, i) => {
          const state: 'done' | 'active' | 'pending' = i < phase ? 'done' : i === phase ? 'active' : 'pending'
          return (
            <div key={label} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <StepDot state={state} />
                <span
                  className={
                    'text-[0.65rem] ' +
                    (state === 'pending' ? 'text-sf-ink-3' : 'text-sf-ink-2')
                  }
                >
                  {label}
                </span>
              </div>
              {i < PHASES.length - 1 && (
                <span
                  aria-hidden="true"
                  className={
                    'mx-1 h-px flex-1 ' + (i < phase ? 'bg-sf-accent' : 'bg-sf-line')
                  }
                />
              )}
            </div>
          )
        })}
      </div>

      {/* 多维研判维度卡网格 */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {meta.dimensions.map((d, i) => {
          const done = completed && (!streaming || ratio >= (i + 1) / n)
          return (
            <div
              key={d.label}
              className="rounded-tile border border-sf-line bg-sf-surface p-2"
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-label text-sf-ink-2">{d.label}</span>
                <span
                  className={
                    'flex items-center gap-1 text-[0.65rem] ' +
                    (done ? 'text-sf-accent' : 'text-sf-warn')
                  }
                >
                  {done ? (
                    <>
                      <span aria-hidden="true">✓</span>已返回
                    </>
                  ) : (
                    <>
                      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-sf-warn animate-pulse" />
                      分析中
                    </>
                  )}
                </span>
              </div>
              <p className="mt-1 text-[0.65rem] leading-tight text-sf-ink-3">{d.desc}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
