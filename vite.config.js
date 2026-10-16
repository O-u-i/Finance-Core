import { defineConfig } from 'vite';

export default defineConfig({
  optimizeDeps: { entries: ['index.html'] },
  build: {
    outDir: 'dist/v3.7.1',
    emptyOutDir: false,
    modulePreload: false,
    rollupOptions: {
      output: { entryFileNames: 'assets/app.js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
  server: {
    watch: {
      // Backend, local data and accumulated test/build outputs are not UI inputs.
      ignored: [
        '**/.tmp/**', '**/backend/**', '**/dist/**', '**/test/**',
        '**/tmp/**', '**/.pytest_cache/**', '**/demo/tests/**', '**/tools/**',
        '**/docs/**', '**/plugins/**', '**/.agents/**', '**/.codex/**',
        '**/.local-data/**', '**/.local-acceptance/**', '**/imports/**', '**/exports/**',
        '**/private/**', '**/personal/**', '**/real-data/**', '**/attachments/**',
      ],
    },
    proxy: {
      '/api': process.env.FC_UI_API_TARGET || 'http://127.0.0.1:8788',
    },
  },
});
