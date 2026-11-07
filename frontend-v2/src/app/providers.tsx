import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  applyTheme,
  readPref,
  resolve,
  setPref as persistPref,
  type Theme,
  type ThemePref,
} from '@/lib/theme'

interface ThemeContextValue {
  pref: ThemePref
  theme: Theme
  setPref: (pref: ThemePref) => void
}

/** 从根元素 dataset 读当前生效主题（index.html 的 FOUC 脚本已写入），不重复 resolve。 */
function themeFromDom(): Theme {
  try {
    if (typeof document !== 'undefined' && document.documentElement?.dataset.theme === 'light') {
      return 'light'
    }
  } catch {
    /* SSR / 异常环境回落 dark */
  }
  return 'dark'
}

const noop = () => {}

/** 默认 context value：无 Provider 的渲染（如 renderToStaticMarkup）也不会因 useTheme 崩溃。 */
const defaultThemeContext: ThemeContextValue = {
  pref: 'dark',
  theme: themeFromDom(),
  setPref: noop,
}

export const ThemeContext = createContext<ThemeContextValue>(defaultThemeContext)

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(() => readPref())
  const [theme, setTheme] = useState<Theme>(() => themeFromDom())

  // 用户切换：落库 + resolve + applyTheme + 广播，返回生效主题回填 state。
  const setPref = useCallback((next: ThemePref) => {
    setPrefState(next)
    setTheme(persistPref(next))
  }, [])

  // 'system' 模式跟随系统偏好变化；无 matchMedia 的环境不注册监听。
  useEffect(() => {
    if (pref !== 'system') return
    try {
      if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
      const mq = window.matchMedia('(prefers-color-scheme: light)')
      const onChange = () => {
        const next = resolve('system')
        applyTheme(next)
        setTheme(next)
      }
      if (typeof mq.addEventListener === 'function') {
        mq.addEventListener('change', onChange)
        return () => mq.removeEventListener('change', onChange)
      }
      if (typeof mq.addListener === 'function') {
        mq.addListener(onChange)
        return () => mq.removeListener(onChange)
      }
    } catch {
      /* matchMedia 守卫 */
    }
  }, [pref])

  const value = useMemo<ThemeContextValue>(() => ({ pref, theme, setPref }), [pref, theme, setPref])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

/** 全局 Providers：主题上下文包住 TanStack Query 客户端（原有配置不变）。 */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  )

  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ThemeProvider>
  )
}
