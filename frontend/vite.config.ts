import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;
const isDocker = process.env.DOCKER_ENV === 'true' || process.env.NODE_ENV === 'production';
// Determinar o target da API com base no ambiente
// Para Windows -> WSL2, usar IP do WSL2 (bridge network)
const apiTarget = process.env.VITE_API_URL || 'http://127.0.0.1:17234';

// Configuração do proxy comum para todos os ambientes
const proxyConfig = {
  '/api': {
    target: apiTarget,
    changeOrigin: true,
    secure: false,
    ws: true,
    configure: (proxy, _options) => {
      proxy.on('error', (err, _req, _res) => {
        console.log('proxy error', err);
      });
      proxy.on('proxyReq', (proxyReq, req, _res) => {
        console.log('Sending Request to the Target:', req.method, req.url);
      });
      proxy.on('proxyRes', (proxyRes, req, _res) => {
        console.log('Received Response from the Target:', proxyRes.statusCode, req.url);
      });
    },
  },
  '/health': {
    target: apiTarget,
    changeOrigin: true,
    secure: false,
  },
  '/ws': {
    target: apiTarget,
    ws: true,
    changeOrigin: true,
  },
};

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent vite from obscuring rust errors
  clearScreen: false,
  // 2. Configure port based on environment
  server: {
    port: isDocker ? 3000 : (host ? 3000 : 5173),
    strictPort: !isDocker,
    host: isDocker ? '0.0.0.0' : (host || false),
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 3001,
        }
      : isDocker 
        ? {
            protocol: "ws",
            host: 'localhost',
            port: 3000,
          }
        : undefined,
    watch: {
      // 3. tell vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
      usePolling: isDocker, // Use polling for Docker environments
      interval: 300,
    },
    cors: true,
    // Usar a mesma configuração de proxy em todos os ambientes
    proxy: proxyConfig,
  },
  
  // Configure proxy for API calls  
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(process.env.VITE_API_URL || 'http://127.0.0.1:17234'),
  },
});
