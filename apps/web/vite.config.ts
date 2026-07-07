import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Dev-only convenience: talk to the FastAPI backend (run separately,
      // e.g. `uvicorn graph_explorer_api.main:app --port 8000`) without CORS
      // friction. Production deploys serve web + api behind the same origin
      // or set VITE_API_BASE_URL instead.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
