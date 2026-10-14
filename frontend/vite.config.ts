import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.replace(/\\/g, "/").includes("/src/data/tkcnEvidence")) return "pilot-evidence";
        },
      },
    },
  },
  server: {
    // 5173–5240 处于部分 Windows 系统的端口排除范围，默认改用 6100
    port: 6100,
    host: "127.0.0.1",
    proxy: { "/api": "http://127.0.0.1:6400" },
  },
  preview: {
    // 4173 处于 4136–4235 排除段（EACCES），preview 默认改用 6200
    port: 6200,
    host: "127.0.0.1",
  },
});
