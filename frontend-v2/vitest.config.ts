import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 测试专用配置：复用生产别名的 '@'，jsdom 环境跑 RTL；不加载 tailwindcss 插件
// （组件仅使用 className 字符串，测试不处理真实 CSS，避免插件副作用）。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // 注意：tests/ 下为 e2e-fix 契约测试与 w4 各阶段 e2e/单元回归，
    // 必须显式纳入，否则默认 `vitest run` 收不到（此前仅含 src/** 导致 tests/ 全被排除）。
    include: ['src/**/*.{test,spec}.{ts,tsx}', 'tests/**/*.{test,spec}.{ts,tsx}'],
  },
})
