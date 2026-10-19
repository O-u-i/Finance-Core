import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  define: { __FC_API_URL__: JSON.stringify(process.env.FC_UI_API_TARGET || 'http://127.0.0.1:8788') },
  optimizeDeps: { entries: ['index.html'] },
  build: {
    outDir: 'dist/v3.10.0',
    emptyOutDir: false,
    modulePreload: false,
    rollupOptions: {
      output: { entryFileNames: 'assets/app.js', chunkFileNames: 'assets/[name].js', assetFileNames: 'assets/[name][extname]' },
    },
  },
  server: {
    host: '127.0.0.1',
    strictPort: true,
    fs: {
      strict: true,
      // Watching exclusions do not prevent HTTP reads. Serve UI inputs only.
      allow: ['demo/src', 'node_modules', 'public', 'index.html'].map(path => fileURLToPath(new URL(path, import.meta.url))),
      deny: [
        '.env', '.env.*', '*.{crt,pem,key}', '**/.git/**',
        '**/{.tmp,tmp,backend,test,private,personal,real-data,attachments,imports,exports}/**',
        '**/{.agents,.codex,.local-data,.local-acceptance}/**',
        '**/AGENTS*.md', '*.{sqlite,sqlite3,db,sqlite-wal,sqlite-shm,sqlite3-wal,sqlite3-shm,csv,tsv,xls,xlsx}',
      ],
    },
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
