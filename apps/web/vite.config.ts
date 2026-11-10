// Vite = the dev server + bundler for the React app.
// In dev, calls to /api are forwarded ("proxied") to the FastAPI server on port 8000.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } } },
});
