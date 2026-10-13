import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    strictPort: true,
    proxy: {
      "/api": `http://127.0.0.1:${process.env.FEA_API_PORT ?? "8000"}`,
    },
  },
  test: { include: ["apps/web/src/**/*.test.ts"], environment: "node" },
});
