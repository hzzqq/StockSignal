import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from '@tanstack/react-router'
import { Providers } from '@/app/providers'
import { applyPreferences } from '@/lib/preferences'
import { router } from '@/app/router'
import '@/styles/tokens.css'

const rootEl = document.getElementById('root')
if (!rootEl) throw new Error('root element not found')

/**
 * 启动引导：开发模式下默认启用 MSW（VITE_ENABLE_MOCKS=false 可关），
 * 先等 worker 就绪再渲染，确保首个请求即被拦截。生产构建不含 mocks。
 */
async function bootstrap() {
  if (!rootEl) return
  // 密度与主题同在挂载前落定：登录页不在 AppShell 下，否则会回落标准密度。
  applyPreferences()
  const env = import.meta.env as Record<string, unknown>
  const enableMocks = import.meta.env.DEV && env['VITE_ENABLE_MOCKS'] !== 'false'
  if (enableMocks) {
    const mod = await import('@/mocks/browser')
    await mod.startMockWorker()
  }

  createRoot(rootEl).render(
    <StrictMode>
      <Providers>
        <RouterProvider router={router} />
      </Providers>
    </StrictMode>,
  )
}

void bootstrap()
