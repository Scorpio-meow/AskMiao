/* AskMiao 介紹頁互動：主題切換、導覽、捲動顯示、推理檔位示意、SSRF 檢查示意、複製指令。 */
(() => {
  const root = document.documentElement;
  root.classList.remove('no-js');

  const THEME_KEY = 'askmiao-site-theme';
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  const readTheme = () => {
    try { return localStorage.getItem(THEME_KEY); } catch { return null; }
  };
  const storeTheme = (value) => {
    try { localStorage.setItem(THEME_KEY, value); } catch { /* 私密視窗或停用儲存時略過 */ }
  };

  const themeToggle = document.querySelector('[data-theme-toggle]');
  const applyTheme = (theme) => {
    root.setAttribute('data-theme', theme);
    /* 截圖有淺色與深色兩版：<picture> 的 <source> 依目前主題決定是否生效 */
    document.querySelectorAll('picture[data-theme-pic] source').forEach((source) => {
      source.setAttribute('media', theme === 'dark' ? 'all' : 'not all');
    });
    if (themeToggle) {
      themeToggle.setAttribute('aria-label', theme === 'dark' ? '切換為淺色模式' : '切換為深色模式');
    }
  };
  applyTheme(readTheme() || (systemDark.matches ? 'dark' : 'light'));
  systemDark.addEventListener('change', (event) => {
    if (!readTheme()) applyTheme(event.matches ? 'dark' : 'light');
  });
  themeToggle?.addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    storeTheme(next);
    applyTheme(next);
  });

  /* 行動版導覽 */
  const navToggle = document.querySelector('[data-nav-toggle]');
  const navMenu = document.querySelector('[data-nav-menu]');
  if (navToggle && navMenu) {
    const setOpen = (open) => {
      navMenu.dataset.open = String(open);
      navToggle.setAttribute('aria-expanded', String(open));
    };
    navToggle.addEventListener('click', () => setOpen(navMenu.dataset.open !== 'true'));
    navMenu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setOpen(false)));
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') setOpen(false); });
  }

  /* 捲動顯示 */
  const revealTargets = document.querySelectorAll('.reveal');
  if (reduceMotion.matches || !('IntersectionObserver' in window)) {
    revealTargets.forEach((el) => el.classList.add('is-visible'));
  } else {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    revealTargets.forEach((el) => revealObserver.observe(el));
  }

  /* 導覽列目前區段 */
  const navLinks = Array.from(document.querySelectorAll('.nav__links a[href^="#"]'));
  const sections = navLinks.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
  if (sections.length && 'IntersectionObserver' in window) {
    const sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((link) => link.classList.toggle('is-active', link.getAttribute('href') === `#${entry.target.id}`));
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    sections.forEach((section) => sectionObserver.observe(section));
  }

  /* 運作方式：捲動到哪一步，左側軌道就亮哪一步 */
  const steps = Array.from(document.querySelectorAll('[data-step]'));
  const railItems = Array.from(document.querySelectorAll('[data-rail]'));
  if (steps.length && railItems.length && 'IntersectionObserver' in window) {
    const setActive = (index) => railItems.forEach((item, i) => item.classList.toggle('is-active', i === index));
    setActive(0);
    const stepObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) setActive(Number(entry.target.dataset.step));
      });
    }, { rootMargin: '-35% 0px -50% 0px' });
    steps.forEach((step) => stepObserver.observe(step));
    railItems.forEach((item, index) => item.addEventListener('click', () => {
      steps[index]?.scrollIntoView({ behavior: reduceMotion.matches ? 'auto' : 'smooth', block: 'center' });
    }));
  }

  /* 推理深度五檔（對應前端 ChatHeader 的選項） */
  const EFFORTS = {
    none: ['無推理（None / 快速）', '不啟用推理，回應最快，適合簡單查詢與直接的工具呼叫。'],
    low: ['輕度推理（Low / 平衡）', '少量思考換取穩定品質，日常問答的省時選擇。'],
    medium: ['標準推理（Medium / 預設）', '系統預設檔位，知識庫問答與一般研究的平衡點。'],
    high: ['深度推理（High / 嚴密）', '更長的思考鏈，適合需要交叉驗證與嚴密比較的問題。'],
    xhigh: ['極致推理（X-High / 長程）', '最長程的推理預算，留給多步研究與複雜彙整。'],
  };
  const seg = document.querySelector('[data-seg]');
  const segDesc = document.querySelector('[data-seg-desc]');
  if (seg && segDesc) {
    const render = (value) => {
      const [title, body] = EFFORTS[value];
      segDesc.innerHTML = `<b>${title}</b><br>${body}`;
      seg.querySelectorAll('button').forEach((btn) => btn.setAttribute('aria-pressed', String(btn.dataset.value === value)));
    };
    seg.querySelectorAll('button').forEach((btn) => btn.addEventListener('click', () => render(btn.dataset.value)));
    render('medium');
  }

  /* 複製指令 */
  document.querySelectorAll('[data-copy]').forEach((button) => {
    const target = document.getElementById(button.dataset.copy);
    if (!target) return;
    const label = button.querySelector('span');
    button.addEventListener('click', async () => {
      const text = Array.from(target.querySelectorAll('[data-cmd]')).map((el) => el.textContent).join('\n') || target.textContent;
      try {
        await navigator.clipboard.writeText(text.trim());
        button.dataset.copied = 'true';
        if (label) label.textContent = '已複製';
        setTimeout(() => { button.dataset.copied = 'false'; if (label) label.textContent = '複製'; }, 1800);
      } catch {
        if (label) label.textContent = '無法複製';
      }
    });
  });

  /* SSRF 防護閘門示意：依 backend/app/core/ssrf_protection.py 的順序在瀏覽器端重現 */
  const BLOCKED_PORTS = new Set([22, 23, 25, 111, 135, 139, 445, 1433, 1521, 2375, 2376, 3306, 5432, 6379, 11211, 27017]);
  const BLOCKED_HOSTS = new Set(['localhost', 'localhost.localdomain', 'broadcasthost', 'ip6-localhost', 'ip6-loopback', 'local', 'internal', 'metadata.google.internal', 'metadata.internal']);
  const BLOCKED_SUFFIXES = ['.localhost', '.local', '.internal', '.lan', '.home.arpa', '.localdomain', '.corp'];
  const V4_RANGES = [
    ['0.0.0.0', 8, '本機網段'], ['10.0.0.0', 8, '私有網段'], ['100.64.0.0', 10, '電信級 NAT 共用位址'], ['127.0.0.0', 8, '迴環位址'],
    ['169.254.0.0', 16, '連結本地 / 雲端中繼資料端點'], ['172.16.0.0', 12, '私有網段'], ['192.0.0.0', 24, 'IETF 保留'], ['192.0.2.0', 24, '文件測試網段'],
    ['192.88.99.0', 24, '6to4 中繼'], ['192.168.0.0', 16, '私有網段'], ['198.18.0.0', 15, '效能測試網段'], ['198.51.100.0', 24, '文件測試網段'],
    ['203.0.113.0', 24, '文件測試網段'], ['224.0.0.0', 4, '群播'], ['240.0.0.0', 4, '保留網段'], ['255.255.255.255', 32, '廣播位址'],
  ];
  const parseV4 = (host) => {
    const match = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (!match) return null;
    const parts = match.slice(1).map(Number);
    if (parts.some((n) => n > 255)) return null;
    return ((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3];
  };
  const inRange = (ip, base, bits) => {
    const mask = bits === 0 ? 0 : (~0 << (32 - bits)) >>> 0;
    return ((ip & mask) >>> 0) === ((parseV4(base) & mask) >>> 0);
  };
  const checkIpLiteral = (host) => {
    const bare = host.replace(/^\[|\]$/g, '').toLowerCase();
    const v4 = parseV4(bare);
    if (v4 !== null) {
      const hit = V4_RANGES.find(([base, bits]) => inRange(v4, base, bits));
      return hit ? { isIp: true, blocked: true, reason: `${bare} 位於禁止網段 ${hit[0]}/${hit[1]}（${hit[2]}）` } : { isIp: true, blocked: false };
    }
    if (!bare.includes(':')) return { isIp: false };
    if (bare === '::' || bare === '::1') return { isIp: true, blocked: true, reason: `禁止存取未指定或迴環 IPv6 位址 ${bare}` };
    const mapped = bare.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (mapped) return checkIpLiteral(mapped[1]);
    if (/^f[cd]/.test(bare)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 唯一本地位址 ${bare}（fc00::/7）` };
    if (/^fe[89ab]/.test(bare)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 連結本地位址 ${bare}（fe80::/10）` };
    if (/^ff/.test(bare)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 群播位址 ${bare}` };
    if (/^2001:db8:/.test(bare)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 文件測試網段 ${bare}` };
    return { isIp: true, blocked: false };
  };

  const ssrfInput = document.querySelector('[data-ssrf-input]');
  const ssrfChecks = Array.from(document.querySelectorAll('[data-check]'));
  const ssrfVerdict = document.querySelector('[data-ssrf-verdict]');
  const ICONS = { pass: '#i-check-circle', fail: '#i-x-circle', skip: '#i-check-circle', server: '#i-globe', idle: '#i-check-circle' };
  const setCheck = (name, state, message) => {
    const row = ssrfChecks.find((el) => el.dataset.check === name);
    if (!row) return;
    row.dataset.state = state;
    row.querySelector('.check__msg').textContent = message;
    row.querySelector('use').setAttribute('href', ICONS[state]);
  };
  const setVerdict = (kind, title, detail) => {
    if (!ssrfVerdict) return;
    ssrfVerdict.className = `verdict verdict--${kind}`;
    ssrfVerdict.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${kind === 'block' ? '#i-x-circle' : kind === 'allow' ? '#i-check-circle' : '#i-globe'}"></use></svg><div>${title}${detail ? `<small>${detail}</small>` : ''}</div>`;
  };
  const escapeHtml = (text) => text.replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  const runSsrf = (raw) => {
    const value = raw.trim();
    const skipRest = (from, message) => {
      const order = ['scheme', 'port', 'host', 'ip', 'dns'];
      order.slice(order.indexOf(from) + 1).forEach((name) => setCheck(name, 'skip', message));
    };
    if (!value) {
      ['scheme', 'port', 'host', 'ip', 'dns'].forEach((name) => setCheck(name, 'idle', '等待輸入'));
      setVerdict('pending', '輸入一個網址，或點選下方範例。');
      return;
    }
    let url;
    try {
      url = new URL(value);
    } catch {
      setCheck('scheme', 'fail', 'URL 解析失敗');
      skipRest('scheme', '未執行');
      setVerdict('block', '拒絕請求', 'URL 格式無法解析。');
      return;
    }
    const scheme = url.protocol.replace(':', '').toLowerCase();
    if (scheme !== 'http' && scheme !== 'https') {
      setCheck('scheme', 'fail', `不允許的 URL 協議「${scheme}」，僅支援 http、https`);
      skipRest('scheme', '未執行');
      setVerdict('block', '拒絕請求', '只有 http 與 https 會被放行。');
      return;
    }
    setCheck('scheme', 'pass', `${scheme} 允許`);
    if (url.username || url.password) {
      setCheck('port', 'fail', 'URL 禁止包含帳號密碼資訊（Userinfo）');
      skipRest('port', '未執行');
      setVerdict('block', '拒絕請求', '帶有帳號密碼的網址可能被用於偽造主機名稱。');
      return;
    }
    const port = url.port ? Number(url.port) : (scheme === 'https' ? 443 : 80);
    if (BLOCKED_PORTS.has(port)) {
      setCheck('port', 'fail', `禁止存取受保護的內部服務連接埠 ${port}`);
      skipRest('port', '未執行');
      setVerdict('block', '拒絕請求', '資料庫、快取與遠端管理服務的連接埠一律阻擋。');
      return;
    }
    setCheck('port', 'pass', `連接埠 ${port} 允許`);
    const host = url.hostname.toLowerCase();
    if (BLOCKED_HOSTS.has(host)) {
      setCheck('host', 'fail', `禁止訪問保留或內部主機名稱「${host}」`);
      skipRest('host', '未執行');
      setVerdict('block', '拒絕請求', '主機名稱本身就在封鎖清單中。');
      return;
    }
    const suffix = BLOCKED_SUFFIXES.find((s) => host.endsWith(s));
    if (suffix) {
      setCheck('host', 'fail', `禁止訪問內部專屬域名（結尾為 ${suffix}）`);
      skipRest('host', '未執行');
      setVerdict('block', '拒絕請求', '內網常見的網域後綴會被直接拒絕。');
      return;
    }
    setCheck('host', 'pass', `主機名稱「${host}」不在封鎖清單`);
    const ipResult = checkIpLiteral(host);
    if (ipResult.isIp) {
      if (ipResult.blocked) {
        setCheck('ip', 'fail', ipResult.reason);
        setCheck('dns', 'skip', '直接輸入 IP，不需解析');
        setVerdict('block', '拒絕請求', '私有、迴環、連結本地與雲端中繼資料位址一律阻擋。');
        return;
      }
      setCheck('ip', 'pass', `${host} 為公開 IP 位址`);
      setCheck('dns', 'skip', '直接輸入 IP，不需解析');
      setVerdict('allow', '允許請求', '以 safe_fetch_text 送出，轉址目標會逐一重新檢查，回應大小上限 10 MB。');
      return;
    }
    setCheck('ip', 'skip', '非 IP 字面值，交由 DNS 解析後檢查');
    setCheck('dns', 'server', '伺服器端解析主機的所有 IP，逐一比對私有與保留網段');
    setVerdict('pending', '通過瀏覽器端可重現的檢查', '最後一關在伺服器：DNS 解析出的每個 IP 都必須是公開位址，才會送出請求。');
  };
  if (ssrfInput) {
    ssrfInput.addEventListener('input', () => runSsrf(ssrfInput.value));
    document.querySelectorAll('[data-ssrf-example]').forEach((button) => {
      button.addEventListener('click', () => {
        ssrfInput.value = button.dataset.ssrfExample;
        runSsrf(ssrfInput.value);
      });
    });
    runSsrf('');
  }
  void escapeHtml;
})();
