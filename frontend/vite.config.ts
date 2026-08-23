import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, './env', 'VITE_')
  const apiTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:5000'

  return {
    base: '/',
    envDir: './env',
    envPrefix: ['VITE_'],
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5173,
      proxy: {
        // 业务接口统一 /api/* → 后端（不要代理 /api-docs，那是前端页面路由）
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
        },
        '/docs': { target: apiTarget, changeOrigin: true },
        '/assets': { target: apiTarget, changeOrigin: true },
        '/health': { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      sourcemap: false,
      outDir: 'dist',
      assetsDir: 'static',
      chunkSizeWarningLimit: 1024,
    },
  }
})
