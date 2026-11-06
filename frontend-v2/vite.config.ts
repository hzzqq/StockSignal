import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// W0 骨架：Vite 8 + React 19 + Tailwind v4 + TanStack Router/Query。
// 通过 proxy 复用现有 Flask 后端(5050)，不重启原服务（PLAN.md §3.1）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5050',
        changeOrigin: true,
      },
    },
  },
  // 分包策略（manualChunks）推迟到 W2 图表库接入时再加，避免 W0 类型摩擦；
  // 届时按 DESIGN.md §4 预算用函数式 manualChunks 对 echarts/lightweight-charts 单独分包。
})
