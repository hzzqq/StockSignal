/**
 * 专注 / Zen 模式浮动开关（纯展示组件，状态由 AppShell 持有）。
 *
 * 行为：点击或快捷键 Z 在「进入/退出专注」间切换；AppShell 负责把状态落到
 * localStorage 并写入 html[data-zen]，CSS 据此隐藏侧栏与顶栏。组件本身只负责
 * 可访问的按钮与文案，不触碰任何颜色令牌（双主题恒等）。
 */
export function ZenToggle({ zen, onToggle }: { zen: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="zen-fab__btn"
      aria-pressed={zen}
      aria-label={zen ? '退出专注模式' : '进入专注模式'}
      title={zen ? '退出专注模式（快捷键 Z）' : '进入专注模式（快捷键 Z）'}
      onClick={onToggle}
    >
      <span aria-hidden="true">{zen ? '✕' : '⤢'}</span>
      <span>{zen ? '退出专注' : '专注'}</span>
    </button>
  )
}
