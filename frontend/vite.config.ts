import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Env vars are read from the repository root .env (shared with the backend); only VITE_* reach the browser.
export default defineConfig({
  plugins: [react()],
  envDir: '..',
  server: {
    port: 5173,
    // Dev only: forward API calls to Django so the browser stays same-origin.
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: {
    // MapLibre (~1 MB) is a separate, long-cached vendor chunk so app changes don't invalidate it.
    chunkSizeWarningLimit: 1100,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: 'maplibre', test: /node_modules[\\/]maplibre-gl/ }],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
    unstubGlobals: true,
  },
})
