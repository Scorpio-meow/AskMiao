import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkGfmSafe, { isAutolinkWorkBounded } from './remarkGfmSafe';

const render = (markdown: string, plugin: typeof remarkGfm | typeof remarkGfmSafe): string =>
  renderToStaticMarkup(<ReactMarkdown remarkPlugins={[plugin]}>{markdown}</ReactMarkdown>);

const ORDINARY_MARKDOWN = [
  '請參考 https://example.com/docs?a=1&b=2 與 www.example.org。',
  '聯絡 support@example.com 或 a.b-c+tag@sub.example.co.uk，結尾的 x@y. 不算',
  '中文緊接網址https://a.com/x、https://b.com/y、說明',
  '(see https://en.wikipedia.org/wiki/Foo_(bar)) and http://localhost:8080/path.',
  '| 左 | 右 |\n|:--|--:|\n| https://t.example | ~~刪除~~ |',
  '- [x] 完成 www.example.com\n- [ ] 待辦',
  '腳註[^1]\n\n[^1]: 參考 https://ref.example.com',
  '`https://code.example.com` 與 [連結](https://link.example.com) 以及 <https://auto.example.com>',
  'WWW.EXAMPLE.COM 與 HTTPS://UPPER.EXAMPLE.COM/PATH',
  'file.name_v1-final.txt、user_name@example.com 與 /path/x@y.com',
  'a-b-c-d-e-f-g-h-i-j-k-l-m-n-o-p-q-r-s-t-u-v-w-x-y-z@example.com 與 awww.example.com',
  `${'很長的段落'.repeat(400)} https://long.example.com/${'x'.repeat(300)} ${'結尾'.repeat(200)}`,
];

// 每一種都會讓 GFM 自動連結的轉換耗時隨長度平方成長
const adversarial = (length: number): Record<string, string> => ({
  dots: `1${'.'.repeat(length)}!`,
  hyphens: `a${'-'.repeat(length)}!`,
  underscores: `a${'_'.repeat(length)}!`,
  plus: `a${'+'.repeat(length)}!`,
  repeatedWww: 'awww.'.repeat(length / 5),
  wwwWithInvalidDomain: `${'www.'.repeat(length / 4)}x_y`,
});

describe('remarkGfmSafe', () => {
  it('renders ordinary markdown exactly like remark-gfm', () => {
    for (const markdown of ORDINARY_MARKDOWN) {
      expect(isAutolinkWorkBounded(markdown)).toBe(true);
      expect(render(markdown, remarkGfmSafe)).toBe(render(markdown, remarkGfm));
    }
  });

  it('still turns plain URLs and email addresses into links', () => {
    const html = render('看 https://example.com/a 或寫信到 someone@example.com', remarkGfmSafe);
    expect(html).toContain('<a href="https://example.com/a">');
    expect(html).toContain('<a href="mailto:someone@example.com">');
  });

  it('skips autolinking only in text whose scan cost is quadratic', () => {
    for (const [name, text] of Object.entries(adversarial(20_000))) {
      expect(isAutolinkWorkBounded(text), name).toBe(false);
    }
    const markdown = `https://kept.example.com\n\n${adversarial(20_000).dots}`;
    const html = render(markdown, remarkGfmSafe);
    expect(html).toContain('<a href="https://kept.example.com">');
    expect(html).toContain(adversarial(20_000).dots);
  });

  it('renders adversarial answers in roughly linear time', () => {
    // 未加上限時，10 萬字元的任一種輸入都要數秒到數十秒
    for (const [name, text] of Object.entries(adversarial(100_000))) {
      const started = performance.now();
      const html = render(text, remarkGfmSafe);
      const elapsed = performance.now() - started;
      expect(elapsed, name).toBeLessThan(2_000);
      expect(html.length, name).toBeGreaterThan(text.length);
    }
  });
});
