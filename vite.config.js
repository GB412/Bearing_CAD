import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const demoStep = resolve(process.cwd(), 'outputs', 'bearing_assembly.step');

export default defineConfig({
  base: './',
  plugins: [{
    name: 'copy-fixed-demo-step',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'outputs/bearing_assembly.step',
        source: readFileSync(demoStep),
      });
    },
  }],
  server: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: false,
  },
  build: {
    target: 'es2020',
    outDir: 'dist',
    emptyOutDir: true,
  },
});
