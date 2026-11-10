/**
 * 本地偏好单一真理源（localStorage）。
 *
 * 诚实口径：这些是**真实生效**的浏览器本地设置，不写后端、不假装同步到账号；
 * 设置页展示的当前值均由此读出，修改后立即作用于 DOM。
 */

const KEY_DENSITY = 'ss_density'
const KEY_V1_BASE = 'ss_v1_base'
const KEY_ZEN = 'ss_zen'
const DEFAULT_V1_BASE = 'http://127.0.0.1:8501'

export type Density = 'comfortable' | 'compact'

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 隐私模式 / 禁用存储：设置仍在本会话内通过 DOM 生效，不谎报已持久化
  }
}

export function getDensity(): Density {
  return safeGet(KEY_DENSITY) === 'compact' ? 'compact' : 'comfortable'
}

export function setDensity(value: Density): void {
  safeSet(KEY_DENSITY, value)
  applyPreferences()
}

/** 专注 / Zen 模式：隐藏侧栏与顶栏，主内容占满视口（单页深度阅读 / 看盘聚焦）。
 *  localStorage 持久化、不写后端；真实生效，作用于 html[data-zen]。 */
export function getZen(): boolean {
  return safeGet(KEY_ZEN) === 'on'
}

export function setZen(value: boolean): void {
  safeSet(KEY_ZEN, value ? 'on' : 'off')
  applyPreferences()
}

/** v1 Streamlit 服务地址；用于「仅 v1」功能的直达链接，可由设置页修改。 */
export function getV1Base(): string {
  const raw = safeGet(KEY_V1_BASE)
  return raw && /^https?:\/\//.test(raw) ? raw.replace(/\/+$/, '') : DEFAULT_V1_BASE
}

export function setV1Base(value: string): void {
  const v = value.trim().replace(/\/+$/, '')
  if (/^https?:\/\//.test(v)) safeSet(KEY_V1_BASE, v)
}

/** 拼出 v1 多页 URL（中文页名需编码）。 */
export function v1PageUrl(v1Path: string): string {
  return getV1Base() + v1Path.split('/').map(encodeURIComponent).join('/')
}

/** 启动时把已存偏好应用到文档根节点。 */
export function applyPreferences(): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.density = getDensity()
  document.documentElement.dataset.zen = getZen() ? 'on' : 'off'
}
