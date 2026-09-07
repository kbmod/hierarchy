import path from "node:path";
import { defineConfig } from "vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  root: path.resolve("apk-src"),
  base: "./",
  define: {
    "import.meta.env.VITE_APK": JSON.stringify("1"),
  },
  plugins: [tailwindcss(), viteReact()],
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve("src") },
      { find: /lib\/server\/proxy$/, replacement: path.resolve("apk-src/proxy-stub.ts") },
    ],
  },
  build: {
    outDir: path.resolve("android-web"),
    emptyOutDir: true,
    sourcemap: false,
  },
});
