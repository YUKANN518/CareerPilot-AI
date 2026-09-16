import { fileURLToPath, URL } from "node:url"
import { join } from "node:path"
import { tmpdir } from "node:os"

import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [vue()],
  cacheDir:
    process.env.VITE_CACHE_DIR ?? join(tmpdir(), "careerpilot-vite-cache"),
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  optimizeDeps: {
    include: [
      "echarts/charts",
      "echarts/components",
      "echarts/core",
      "echarts/renderers",
    ],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/unit/setup.ts"],
    include: ["./tests/unit/**/*.spec.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/api/**/*.ts", "src/stores/**/*.ts", "src/router/**/*.ts"],
    },
  },
})
