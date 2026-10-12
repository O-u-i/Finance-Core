import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    outDir: 'dist/v3.5.0',
    emptyOutDir: false,
    modulePreload: false,
    rollupOptions: {
      output: { entryFileNames: 'assets/app.js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
  server: {
    proxy: {
      '/api': process.env.FC_UI_API_TARGET || 'http://127.0.0.1:8788',
    },
  },
});
