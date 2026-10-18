import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The API only allows requests from this exact origin (see CORS in api.py),
  // so fail loudly instead of silently moving to another port.
  server: { port: 5173, strictPort: true },
});
