import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// El build se sirve desde FastAPI (finanzas/web). En desarrollo, /api va al backend en :8000.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss()],
  build: { outDir: '../finanzas/web', emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
})
