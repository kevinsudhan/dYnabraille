import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, the Python server (python -m dynabraille) runs on :8000 and Vite proxies to it.
const server = process.env.DYNABRAILLE_SERVER ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // The ElevenLabs SDK (WebRTC) is most of the bundle; keep it in its own cacheable chunk.
        manualChunks: { elevenlabs: ['@elevenlabs/react'], react: ['react', 'react-dom'] },
      },
    },
  },
  server: {
    host: true,
    proxy: {
      '/api': server,
      '/ca.crt': server,
      '/ws': { target: server.replace(/^http/, 'ws'), ws: true },
    },
  },
})
