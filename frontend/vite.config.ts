import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Vendor chunk groups: each rarely changes between deploys, so isolating them
// from app code lets browsers keep cached copies across releases. Order matters
// — the first matching group wins. recharts and lightweight-charts are split
// because they update on independent cadences.
const VENDOR_CHUNKS: Record<string, RegExp> = {
  "vendor-recharts": /node_modules\/(recharts|d3-[^/]+|victory-vendor)/,
  "vendor-lightweight-charts": /node_modules\/lightweight-charts/,
  "vendor-react": /node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//,
  "vendor-query": /node_modules\/(@tanstack|zustand)/,
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // Vendor chunks are intentionally large for cache stability; warn at 600 KB
    // instead of the 500 KB default to suppress noise on chunks that are as
    // small as they can be.
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          for (const [name, pattern] of Object.entries(VENDOR_CHUNKS)) {
            if (pattern.test(id)) return name;
          }
          return undefined;
        },
      },
    },
  },
});
