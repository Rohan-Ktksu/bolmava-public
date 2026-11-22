import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser only calls same-origin /api; Vite forwards it to the local FastAPI server.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
