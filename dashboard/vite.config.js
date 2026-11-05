import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: http://localhost:5173 (proxies /api to the FastAPI server on :8000)
// Prod: `npm run build` -> dist/, served by FastAPI at /dashboard
export default defineConfig({
  plugins: [react()],
  base: '/dashboard/',
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
