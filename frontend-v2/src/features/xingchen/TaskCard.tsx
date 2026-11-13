import type { AiConsultTask } from '@/api/schemas/chat'

const STATUS_LABEL: Record<string, string> = {
  pending: '排队中',
  running: '分析中',
  success: '已完成',
  error: '出错',
  cancelled: '已取消',
}

/** ai_consult 后台任务进度卡（对应轮询态 Task.to_dict）。 */
export function TaskCard({
  task,
  className = '',
}: {
  task: AiConsultTask
  className?: string
}) {
  const raw = task.progress == null ? 0 : task.progress
  const pct = Math.max(0, Math.min(100, Math.round(raw * 100)))
  const label = STATUS_LABEL[task.status] ?? task.status
  const tone =
    task.status === 'error'
      ? 'text-sf-danger'
      : task.status === 'success'
        ? 'text-sf-ok'
        : 'text-sf-accent'
  const icon =
    task.status === 'success' ? '✅' : task.status === 'error' ? '❌' : '⏳'
  return (
    <div
      className={`rounded-tile border border-sf-line bg-sf-surface-2 px-3 py-2 ${className}`}
    >
      <div className="flex items-center justify-between text-label">
        <span className={`flex items-center gap-1 ${tone}`}>
          <span aria-hidden="true">{icon}</span>
          {label}
        </span>
        <span className="text-sf-ink-3">{pct}%</span>
      </div>
      {task.stage && (
        <div className="mt-1 truncate text-label text-sf-ink-3">阶段：{task.stage}</div>
      )}
      <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-sf-line">
        <div
          className="h-full rounded-full bg-sf-accent transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      {task.logs && task.logs.length > 0 && (
        <div className="mt-1 truncate text-label text-sf-ink-3">
          {task.logs[task.logs.length - 1].message}
        </div>
      )}
    </div>
  )
}
