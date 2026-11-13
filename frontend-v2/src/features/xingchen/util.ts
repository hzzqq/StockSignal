/** 复制文本到剪贴板；失败静默（jsdom / 无 clipboard 环境不抛）。 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
    if (typeof document !== 'undefined') {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand?.('copy')
      document.body.removeChild(ta)
      return !!ok
    }
  } catch {
    // 复制是辅助动作，静默失败不阻塞
  }
  return false
}
