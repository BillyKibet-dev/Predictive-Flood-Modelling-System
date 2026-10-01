import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Vite config for NairobiFloodWatch dashboard
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
})
