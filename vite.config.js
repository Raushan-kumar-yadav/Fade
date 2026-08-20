import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    strictPort: true    // fail fast if 5173 is taken — don't silently drift
  },
  build: {
    outDir: 'dist'
  }
})
