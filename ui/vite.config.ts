import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

// Check if SSL certs exist (for dev server only, not needed for build)
const hasSSLCerts = fs.existsSync('./localhost+2-key.pem') && fs.existsSync('./localhost+2.pem');
const httpsConfig = hasSSLCerts ? {
  key: fs.readFileSync('./localhost+2-key.pem'),
  cert: fs.readFileSync('./localhost+2.pem'),
} : undefined;

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@market-swarm/core': path.resolve(__dirname, '../packages/core/src'),
      '@market-swarm/api-client': path.resolve(__dirname, '../packages/api-client/src'),
    },
  },
  server: {
    https: httpsConfig,
    proxy: {
      // Copilot direct routes (bypass SSE Gateway, match nginx config)
      '/api/mel': {
        target: 'http://localhost:8095',
        changeOrigin: true,
        secure: false,
      },
      '/api/adi': {
        target: 'http://localhost:8095',
        changeOrigin: true,
        secure: false,
      },
      '/api/commentary': {
        target: 'http://localhost:8095',
        changeOrigin: true,
        secure: false,
      },
      // Copilot WebSocket
      '/ws': {
        target: 'http://localhost:8095',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      // Vexy AI service (must be before general /api)
      '/api/vexy': {
        target: 'http://localhost:3005',
        changeOrigin: true,
        secure: false,
      },
      // Proxy API and SSE requests to the SSE Gateway
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        secure: false,
      },
      '/sse': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Connection', 'keep-alive');
          });
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['Cache-Control'] = 'no-cache';
            proxyRes.headers['Connection'] = 'keep-alive';
          });
        },
      },
    },
  },
})
