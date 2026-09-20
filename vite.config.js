import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ['**/.venv/**', '**/node_modules/**', '**/.venv_pkgs/**', '**/dist/**', '**/dist-electron/**']
    }
  },
  build: {
    outDir: 'dist'
  }
})
