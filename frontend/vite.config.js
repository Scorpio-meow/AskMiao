import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import viteCompression from 'vite-plugin-compression';
import path from 'path';
import { createHash } from 'crypto';
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
// 只在建置時讀取專案自己的 index.html，不用來過濾不可信的 HTML；仍比照瀏覽器的寬鬆規則：
// 標籤名稱與屬性名稱不分大小寫，結束標籤可以帶空白或屬性（例如 </script >）
const INLINE_ELEMENT_PATTERNS = {
  script: /<script([^>]*)>([\s\S]*?)<\/script[^>]*>/gi,
  style: /<style([^>]*)>([\s\S]*?)<\/style[^>]*>/gi,
};
// index.html 中內嵌的腳本或樣式（反框架守衛、主題初始化）以內容雜湊列入 CSP，其他內嵌程式碼都不會執行
function inlineHashes(html, element) {
  return [...html.matchAll(INLINE_ELEMENT_PATTERNS[element])]
    .filter(([, attributes, content]) => !/\ssrc\s*=/i.test(attributes) && content.trim())
    .map(([, , content]) => `'sha256-${createHash('sha256').update(content).digest('base64')}'`);
}
// API 為絕對網址（前端與後端不同來源）時 connect-src 需要允許該來源；
// 讀取的變數與 DevTunnels 去除連接埠的規則都與 src/services/api.ts 相同
function apiOrigins(env) {
  return [env.VITE_API_BASE, env.VITE_API_URL]
    .filter((value) => typeof value === 'string' && /^https?:\/\//.test(value))
    .map((value) => new URL(value))
    .map((url) => (url.hostname.includes('devtunnels.ms') ? `${url.protocol}//${url.hostname}` : url.origin));
}
// 正式環境由 nginx 等網頁伺服器提供建置產物，伺服器不一定設定 CSP；建置時把 CSP 以 <meta> 寫進 index.html，
// 頁面只執行建置產生的腳本，模型回答等內容即使被注入 HTML 也無法執行腳本或載入外部資源。
// 開發伺服器需要內嵌的 HMR 腳本，因此只在建置時套用；<meta> 不支援 frame-ancestors，反框架仍靠網頁伺服器的標頭
function contentSecurityPolicy(env) {
  return {
    name: 'askmiao-content-security-policy',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler(html) {
        const policy = [
          "default-src 'self'",
          ["script-src 'self'", ...inlineHashes(html, 'script')].join(' '),
          ["style-src 'self'", ...inlineHashes(html, 'style')].join(' '),
          "img-src 'self' data: blob:",
          ["connect-src 'self'", ...apiOrigins(env)].join(' '),
          "object-src 'none'",
          "base-uri 'none'",
          "form-action 'self'",
        ].join('; ');
        // 放在 <meta charset> 之後（編碼宣告須位於前 1024 位元組）、所有內嵌腳本之前，CSP 才會套用到它們
        const charset = html.match(/<meta charset=[^>]*>/i);
        if (!charset) {
          throw new Error('index.html 缺少 <meta charset>，無法決定 CSP <meta> 的位置');
        }
        return html.replace(charset[0], `${charset[0]}\n  <meta http-equiv="Content-Security-Policy" content="${policy}" />`);
      },
    },
  };
}
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '');
  return {
    plugins: [
      react(),
      restrictOpenInEditor(),
      contentSecurityPolicy(env),
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
