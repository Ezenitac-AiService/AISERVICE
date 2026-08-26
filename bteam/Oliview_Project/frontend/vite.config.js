import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/bteam/oliview/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    cors: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || (process.env.NODE_ENV === 'production' || process.env.DOCKER_CONTAINER ? 'http://oliview_backend:5050' : 'http://localhost:5050'),
        changeOrigin: true,
      }
    }
  }
})
