import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import viteCompression from 'vite-plugin-compression';
import path from 'path';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// 開發與預覽伺服器都套用：禁止頁面被其他來源以 iframe 嵌入（點擊劫持），
// 圖片只允許同源與本機產生的 data:／blob:，模型回答中的外部圖片不會被自動載入
const SECURITY_HEADERS = {
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "frame-ancestors 'none'; img-src 'self' data: blob:",
};
const LOOPBACK_ADDRESSES = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
// Vite 內建的 /__open-in-editor 會在主機上啟動編輯器程序，只允許本機回送位址呼叫
function restrictOpenInEditor() {
  return {
    name: 'askmiao-restrict-open-in-editor',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/__open-in-editor', (req, res, next) => {
        if (LOOPBACK_ADDRESSES.has(req.socket.remoteAddress)) {
          next();
          return;
        }
        res.statusCode = 403;
        res.end();
      });
    },
  };
}
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '');
  return {
    plugins: [
      react(),
      restrictOpenInEditor(),
      viteCompression({
        apply: 'build',
      }),
    ],
    server: {
      port: parseInt(env.PORT) || 3000,
      // 開發伺服器只供本機使用；需要讓區網裝置連線時請改用建置產物與正式的網頁伺服器
      host: 'localhost',
      open: false,
      headers: SECURITY_HEADERS,
      proxy: {
        '/api': {
          target: env.VITE_API_BASE || 'http://127.0.0.1:8001',
          changeOrigin: true,
          secure: false,
          ws: true,
        },
      },
    },
    preview: {
      port: 3000,
      host: 'localhost',
      headers: SECURITY_HEADERS,
    },
    build: {
      outDir: 'build',
      sourcemap: env.GENERATE_SOURCEMAP !== 'false',
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom')) {
                return 'vendor';
              }
            }
          },
        },
      },
      chunkSizeWarningLimit: 1000,
    },
    resolve: {
      extensions: ['.mjs', '.js', '.jsx', '.ts', '.tsx', '.json'],
      alias: {
        '@': path.resolve(__dirname, './src'),
        '@components': path.resolve(__dirname, './src/components'),
        '@pages': path.resolve(__dirname, './src/pages'),
        '@services': path.resolve(__dirname, './src/services'),
        '@utils': path.resolve(__dirname, './src/utils'),
        '@contexts': path.resolve(__dirname, './src/contexts'),
      },
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode),
    },
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'react-router-dom',
        'axios'
      ],
    },
  };
});
