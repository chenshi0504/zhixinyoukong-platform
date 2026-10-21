import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  base: process.env.GITHUB_PAGES === 'true' ? '/zhixinyoukong-cloud/' : '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ['echarts'],
          'element-plus': ['element-plus'],
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api/cloud': {
        target: 'http://localhost:9000',
        changeOrigin: true
      }
    }
  }
})
