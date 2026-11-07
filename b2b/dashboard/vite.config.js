import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: http://localhost:5174 (proxies /api to the B2B FastAPI server on :8001)
// Prod: `npm run build` -> dist/, served by b2b/api.py at /
export default defineConfig({
  plugins: [react()],
  base: '/',
  server: { port: 5174, proxy: { '/api': 'http://127.0.0.1:8001' } },
})
