/// <reference types="vitest" />
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { resolve } from "path"

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src")
    }
  },
  server: {
    proxy: {
      "/healthz": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: "dist"
  }
})
