import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { crx } from '@crxjs/vite-plugin';
import { fileURLToPath } from 'node:url';
import manifest from './manifest.json';

export default defineConfig({
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  plugins: [
    react(),
    crx({ manifest }),
  ],
});
