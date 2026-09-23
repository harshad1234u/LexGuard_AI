import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The browser never talks to the model provider. All AI traffic goes
    // through the backend, which holds the NVIDIA key server-side.
    proxy: {
      '/api': {
        // Overridable so the browser-test runner can point the dev server at
        // its own stub backend on a private port, instead of whatever happens
        // to be listening on the development default.
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
