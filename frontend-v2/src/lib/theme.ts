/**
 * 主题偏好纯函数层（DESIGN.md §2）：模块顶层零副作用，import 时不触碰 DOM。
 * 所有浏览器 API（localStorage / matchMedia / CustomEvent / document）均做存在性守卫
 * 或 try/catch，保证 SSR、jsdom、隐私模式等任何环境都不会抛错。
 */
export type ThemePref = 'dark' | 'light' | 'system'
export type Theme = 'dark' | 'light'

export const THEME_KEY = 'ss_theme'

/** 读偏好：非法值 / localStorage 不可用 → 'dark'。 */
export function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(THEME_KEY)
    if (v === 'dark' || v === 'light' || v === 'system') return v
  } catch {
    /* localStorage 不可用（SSR / 隐私模式）→ 回落 dark */
  }
  return 'dark'
}

/** 解析生效主题：'system' 跟随系统 prefers-color-scheme，jsdom 无 matchMedia 回落 dark。 */
export function resolve(pref: ThemePref): Theme {
  if (pref === 'dark') return 'dark'
  if (pref === 'light') return 'light'
  try {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    }
  } catch {
    /* matchMedia 守卫 */
  }
  return 'dark'
}

/** 应用主题到根元素，并广播 ss-theme-change 供图表等非 React 消费方重映射。 */
export function applyTheme(theme: Theme): void {
  try {
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.dataset.theme = theme
      document.documentElement.style.colorScheme = theme
    }
  } catch {
    /* DOM 不可用 */
  }
  try {
    if (typeof window !== 'undefined' && typeof CustomEvent !== 'undefined') {
      window.dispatchEvent(new CustomEvent('ss-theme-change', { detail: theme }))
    }
  } catch {
    /* CustomEvent 不存在 / dispatch 失败 */
  }
}

/** 持久化偏好 + resolve + applyTheme，返回实际生效主题。 */
export function setPref(pref: ThemePref): Theme {
  try {
    localStorage.setItem(THEME_KEY, pref)
  } catch {
    /* localStorage 不可用仍尽力应用主题 */
  }
  const theme = resolve(pref)
  applyTheme(theme)
  return theme
}
