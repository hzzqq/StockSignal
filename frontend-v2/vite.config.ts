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
    // 端口被占用时必须直接失败：静默漂移到 5174 会让 active_ports_v2.json、
    // _stop_services.bat、启动脚本与浏览器全部指向错误端口。
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:5050',
        changeOrigin: true,
      },
      // 网页作品集静态资源（86 页）由 Flask 在 /webapps 下托管，开发期一并代理
      '/webapps': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:5050',
        changeOrigin: true,
      },
    },
  },
  // 分包策略（manualChunks）：W2 图表库接入后落地。
  // 按 DESIGN.md §4 预算，用函数式 manualChunks 对 echarts(+zrender) / tanstack 单独成块；
  // EChart 组件本身已动态 import('echarts')，故 echarts 仅随图表挂载按需加载。
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) return 'echarts'
          if (id.includes('node_modules/@tanstack')) return 'tanstack'
          return undefined
        },
      },
    },
  },
})
