import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    strictPort: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.FEA_API_PORT ?? "8000"}`,
        // Preserve the browser authority for the API's same-origin write check.
        changeOrigin: false,
      },
    },
  },
  test: { include: ["apps/web/src/**/*.test.ts"], environment: "node" },
});
