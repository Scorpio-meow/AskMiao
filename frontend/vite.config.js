import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import viteCompression from 'vite-plugin-compression';
import path from 'path';
import { createHash } from 'crypto';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SECURITY_HEADERS = {
  'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "frame-ancestors 'none'; img-src 'self' data: blob:",
};
const LOOPBACK_ADDRESSES = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);
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
const INLINE_ELEMENT_PATTERNS = {
  script: /<script([^>]*)>([\s\S]*?)<\/script[^>]*>/gi,
  style: /<style([^>]*)>([\s\S]*?)<\/style[^>]*>/gi,
};
function inlineHashes(html, element) {
  return [...html.matchAll(INLINE_ELEMENT_PATTERNS[element])]
    .filter(([, attributes, content]) => !/\ssrc\s*=/i.test(attributes) && content.trim())
    .map(([, , content]) => `'sha256-${createHash('sha256').update(content).digest('base64')}'`);
}
function apiOrigins(env) {
  return [env.VITE_API_BASE, env.VITE_API_URL]
    .filter((value) => typeof value === 'string' && /^https?:\/\//.test(value))
    .map((value) => new URL(value))
    .map((url) => (url.hostname.includes('devtunnels.ms') ? `${url.protocol}//${url.hostname}` : url.origin));
}
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