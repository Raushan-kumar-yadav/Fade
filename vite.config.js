import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: [
        '**/.venv/**', '**/node_modules/**', '**/.venv_pkgs/**', '**/dist/**', '**/dist-electron/**',
        // The backend rewrites .env when settings are saved. Vite treats that as a
        // config change, restarts and reloads the UI — which kills a running AI task.
        '**/.env', '**/.env.*',
        // Not frontend code: no need to watch (and never a reason to reload).
        '**/backend/**', '**/AIModels/**', '**/renderer/**', '**/exports/**',
        '**/dist-app/**', '**/pyinstaller-build/**', '**/pyinstaller-dist/**',
      ]
    }
  },
  build: {
    outDir: 'dist'
  }
})
