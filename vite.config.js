import { defineConfig } from 'vite';

export default defineConfig({
  root: 'html',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
  }
});
