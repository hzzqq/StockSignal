/**
 * 数据检测类模块的统一「重新检测」按钮。
 * 截图 2 反馈：行情/诊断类页面缺一个能主动触发重取的入口。
 * 按钮只负责触发与如实呈现状态，不改写数据、不把失败显示成成功。
 */
export interface RetestButtonProps {
  onRetest: () => void | Promise<void>
  loading?: boolean
  label?: string
  /** 上一次检测时间（字符串由调用方格式化），没有就不显示 */
  lastAt?: string | null
  /** 附加说明，例如本次降级原因 */
  hint?: string | null
  disabled?: boolean
}

export function RetestButton({
  onRetest,
  loading = false,
  label = '重新检测',
  lastAt = null,
  hint = null,
  disabled = false,
}: RetestButtonProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => void onRetest()}
        disabled={loading || disabled}
        aria-label={label}
        className="rounded-tile border border-sf-line px-2.5 py-1 text-label text-sf-ink-2 hover:border-sf-accent hover:text-sf-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? '检测中…' : label}
      </button>
      {lastAt && <span className="text-[11px] text-sf-ink-3">上次检测：{lastAt}</span>}
      {hint && <span className="text-[11px] text-sf-ink-3">{hint}</span>}
    </div>
  )
}
