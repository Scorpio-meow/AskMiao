/* AskMiao 介紹頁互動：主題切換、導覽、運作方式軌道、推理檔位、分頁、引用示範、RRF 檢索示範、
   工具呼叫核准、web_fetch 出站檢查器、子行程環境變數比較、卡片游標光暈與 Hero 傾斜、
   5.0.0 的登入失敗節流與權杖撤銷示範、複製指令。示範的判斷規則對應後端原始碼，註解標出出處。 */
(() => {
  const root = document.documentElement;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  /* ---------- 主題：預設跟隨系統；切成與系統相反時才固定，切回與系統相同就取消固定 ---------- */
  const THEME_KEY = 'askmiao-site-theme';
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const schemeMeta = document.querySelector('meta[name="color-scheme"]');
  const themeColorMetas = Array.from(document.querySelectorAll('meta[name="theme-color"]'));
  themeColorMetas.forEach((meta) => { meta.dataset.original = meta.content; });
  const themeSources = Array.from(document.querySelectorAll('picture[data-theme-pic] source'));
  const themeToggle = document.querySelector('[data-theme-toggle]');

  const readPin = () => {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return value === 'light' || value === 'dark' ? value : null;
    } catch { return null; }
  };
  const writePin = (value) => {
    try {
      if (value) localStorage.setItem(THEME_KEY, value);
      else localStorage.removeItem(THEME_KEY);
    } catch { /* 私密視窗或停用儲存時只影響這次瀏覽 */ }
  };
  let pinned = readPin();
  const systemTheme = () => (systemDark.matches ? 'dark' : 'light');
  const effectiveTheme = () => pinned || systemTheme();
  const applyTheme = () => {
    if (pinned) root.setAttribute('data-theme', pinned);
    else root.removeAttribute('data-theme');
    if (schemeMeta) schemeMeta.content = pinned || 'light dark';
    /* 固定主題時網址列顏色改用目前主題的頁面底色，否則交回 media 屬性依系統決定 */
    const pageBackground = getComputedStyle(root).getPropertyValue('--bg').trim();
    themeColorMetas.forEach((meta) => { meta.content = pinned ? pageBackground : meta.dataset.original; });
    /* 截圖有淺色與深色兩版：固定主題時讓 <source> 直接生效或失效，否則交回 prefers-color-scheme */
    themeSources.forEach((source) => {
      source.media = pinned ? (pinned === 'dark' ? 'all' : 'not all') : '(prefers-color-scheme: dark)';
    });
    themeToggle?.setAttribute('aria-label', effectiveTheme() === 'dark' ? '切換為淺色模式' : '切換為深色模式');
  };
  applyTheme();
  systemDark.addEventListener('change', applyTheme);
  themeToggle?.addEventListener('click', () => {
    const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
    pinned = next === systemTheme() ? null : next;
    writePin(pinned);
    applyTheme();
  });

  /* ---------- 行動版導覽 ---------- */
  const navToggle = document.querySelector('[data-nav-toggle]');
  const navMenu = document.querySelector('[data-nav-menu]');
  if (navToggle && navMenu) {
    const setOpen = (open) => {
      navMenu.dataset.open = String(open);
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? '關閉選單' : '開啟選單');
      navToggle.querySelector('use').setAttribute('href', open ? '#i-x' : '#i-list');
    };
    navToggle.addEventListener('click', () => setOpen(navMenu.dataset.open !== 'true'));
    navMenu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setOpen(false)));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && navMenu.dataset.open === 'true') {
        setOpen(false);
        navToggle.focus();
      }
    });
    document.addEventListener('click', (event) => {
      if (navMenu.dataset.open === 'true' && !navMenu.contains(event.target) && !navToggle.contains(event.target)) setOpen(false);
    });
  }

  /* ---------- 導覽列標示目前區段（不在導覽列的區段會清除標示） ---------- */
  const navLinks = Array.from(document.querySelectorAll('.nav__links a[href^="#"]'));
  const pageSections = Array.from(document.querySelectorAll('main section[id]'));
  if (navLinks.length && pageSections.length && 'IntersectionObserver' in window) {
    const sectionObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navLinks.forEach((link) => {
          const active = link.getAttribute('href') === `#${entry.target.id}`;
          link.classList.toggle('is-active', active);
          if (active) link.setAttribute('aria-current', 'location');
          else link.removeAttribute('aria-current');
        });
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    pageSections.forEach((section) => sectionObserver.observe(section));
  }

  /* ---------- 運作方式：捲動到哪一步，左側軌道就亮哪一步 ---------- */
  const steps = Array.from(document.querySelectorAll('[data-step]'));
  const railItems = Array.from(document.querySelectorAll('[data-rail]'));
  if (steps.length && railItems.length === steps.length) {
    const setStep = (index) => railItems.forEach((item, i) => {
      item.classList.toggle('is-active', i === index);
      const button = item.querySelector('button');
      if (i === index) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    setStep(0);
    if ('IntersectionObserver' in window) {
      const stepObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setStep(Number(entry.target.dataset.step));
        });
      }, { rootMargin: '-35% 0px -50% 0px' });
      steps.forEach((step) => stepObserver.observe(step));
    }
    railItems.forEach((item, index) => item.querySelector('button').addEventListener('click', () => {
      steps[index].scrollIntoView({ behavior: reduceMotion.matches ? 'auto' : 'smooth', block: 'center' });
    }));
  }

  /* ---------- 推理深度五檔（文字與前端 ChatHeader 的選項相同，放在按鈕的 data 屬性） ---------- */
  const seg = document.querySelector('[data-seg]');
  const segDesc = document.querySelector('[data-seg-desc]');
  if (seg && segDesc) {
    const segButtons = Array.from(seg.querySelectorAll('button'));
    segButtons.forEach((button) => button.addEventListener('click', () => {
      segButtons.forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
      const title = document.createElement('b');
      title.textContent = button.dataset.title;
      segDesc.replaceChildren(title, document.createElement('br'), button.dataset.desc);
    }));
  }

  /* ---------- 分頁（WAI-ARIA tabs：方向鍵、Home、End 切換） ---------- */
  document.querySelectorAll('[role="tablist"]').forEach((list) => {
    const tabs = Array.from(list.querySelectorAll('[role="tab"]'));
    const select = (tab, moveFocus) => {
      tabs.forEach((t) => {
        const selected = t === tab;
        t.setAttribute('aria-selected', String(selected));
        t.tabIndex = selected ? 0 : -1;
        document.getElementById(t.getAttribute('aria-controls')).hidden = !selected;
      });
      if (moveFocus) tab.focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab, false));
      tab.addEventListener('keydown', (event) => {
        const targets = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 };
        if (!(event.key in targets)) return;
        event.preventDefault();
        select(tabs[(targets[event.key] + tabs.length) % tabs.length], true);
      });
    });
  });

  /* ---------- 引用示範：回答中的 [n] 對應引用編號表與來源標籤 ---------- */
  const citeDemo = document.querySelector('[data-cite-demo]');
  if (citeDemo) {
    const detail = citeDemo.querySelector('[data-cite-detail]');
    const linked = Array.from(citeDemo.querySelectorAll('[data-cite], [data-cite-badge], [data-ledger]'));
    const citeButtons = Array.from(citeDemo.querySelectorAll('.cite'));
    const showCitation = (number) => {
      linked.forEach((el) => {
        const own = el.dataset.cite || el.dataset.citeBadge || el.dataset.ledger;
        el.classList.toggle('is-active', own === number);
      });
      citeButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.cite === number)));
      const template = citeDemo.querySelector(`template[data-cite-template="${number}"]`);
      detail.replaceChildren(template.content.cloneNode(true));
    };
    citeButtons.forEach((button) => {
      ['mouseenter', 'focus', 'click'].forEach((type) => button.addEventListener(type, () => showCitation(button.dataset.cite)));
    });
  }

  /* ---------- RRF 檢索示範：融合、排序與門檻與 backend/app/rag/retrievers/hybrid.py 相同 ---------- */
  const rrf = document.querySelector('[data-rrf]');
  const rrfDataElement = document.getElementById('rrf-data');
  if (rrf && rrfDataElement) {
    /* 內嵌 JSON 讀自 DOM，其中的值插入 HTML 前一律經過 escapeHtml */
    const { rerankWeight, chunks, queries } = JSON.parse(rrfDataElement.textContent);
    const kInput = rrf.querySelector('[data-rrf-k]');
    const tInput = rrf.querySelector('[data-rrf-t]');
    const kOutput = rrf.querySelector('[data-out-k]');
    const tOutput = rrf.querySelector('[data-out-t]');
    const caption = rrf.querySelector('[data-rrf-caption]');
    const lanes = { vector: rrf.querySelector('[data-lane="vector"]'), bm25: rrf.querySelector('[data-lane="bm25"]') };
    const results = rrf.querySelector('[data-rrf-results]');
    const verdict = rrf.querySelector('[data-rrf-verdict]');
    const queryInputs = Array.from(rrf.querySelectorAll('input[name="rrf-query"]'));

    /* reciprocal_rank_fusion：分數 = Σ 1 / (rrf_k + 名次)，名次從 1 起算 */
    const fuse = (rankedLists, k) => {
      const fused = new Map();
      rankedLists.forEach((list) => list.forEach((id, index) => {
        fused.set(id, (fused.has(id) ? fused.get(id) : 0) + 1 / (k + index + 1));
      }));
      return Array.from(fused, ([id, score]) => ({ id, score })).sort((a, b) => b.score - a.score);
    };
    const chunkLabel = (id) => `<span class="rrf__name"><b>${escapeHtml(chunks[id].doc)}</b><span>${escapeHtml(chunks[id].part)}</span></span>`;

    /* 滑桿已填滿的比例交給 CSS 的 --fill 畫出來 */
    const paintSlider = (input) => {
      const ratio = (Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min));
      input.style.setProperty('--fill', `${ratio * 100}%`);
    };

    const render = () => {
      const query = queries[queryInputs.find((input) => input.checked).value];
      const k = Number(kInput.value);
      const threshold = Number(tInput.value);
      kOutput.textContent = String(k);
      tOutput.textContent = threshold.toFixed(2);
      [kInput, tInput].forEach(paintSlider);
      caption.textContent = query.caption;

      Object.entries(lanes).forEach(([lane, list]) => {
        list.innerHTML = query[lane].map((id, index) => (
          `<li data-chunk="${escapeHtml(id)}" title="${escapeHtml(chunks[id].text)}"><span class="rrf__rank">${index + 1}</span>${chunkLabel(id)}</li>`
        )).join('');
      });

      /* 候選原分數 = RRF 分數 / 最高分；混合分數只用於排序，門檻只看重排機率 */
      const fused = fuse([query.vector, query.bm25], k);
      const topScore = fused[0].score;
      const ranked = fused.map((item, index) => {
        const relevance = query.relevance[item.id];
        return {
          ...item,
          fusedRank: index + 1,
          relevance,
          mixed: rerankWeight * relevance + (1 - rerankWeight) * (item.score / topScore),
          pass: relevance >= threshold,
        };
      }).sort((a, b) => b.mixed - a.mixed);

      results.innerHTML = ranked.map((row) => `
        <li class="rrf-row ${row.pass ? 'is-pass' : 'is-fail'}" data-chunk="${escapeHtml(row.id)}" title="${escapeHtml(chunks[row.id].text)}" style="view-transition-name: rrf-${escapeHtml(row.id)}">
          ${chunkLabel(row.id)}
          <span class="rrf-row__rrf">${row.score.toFixed(4)}<small>融合第 ${row.fusedRank} 名</small></span>
          <span class="rrf-row__rel">
            <span class="relbar" style="--p: ${escapeHtml(row.relevance)}; --t: ${threshold}" aria-hidden="true"><span class="relbar__fill"></span><span class="relbar__mark"></span></span>
            <span class="mono">${row.relevance.toFixed(2)}</span>
            <span class="rrf-row__state">${row.pass ? '通過門檻' : '低於門檻'}</span>
          </span>
        </li>`).join('');

      const passed = ranked.filter((row) => row.pass);
      if (passed.length) {
        verdict.dataset.kind = 'pass';
        verdict.innerHTML = `${passed.length} 段通過門檻，依上方順序交給 search_knowledge_base<small>工具預設回傳前 3 段（top_k）；精確比對到網址、貼文 ID、日期的片段會另外全數回傳。</small>`;
      } else {
        verdict.dataset.kind = 'none';
        verdict.innerHTML = '全部低於門檻：工具回報「知識庫中查無相關資料」<small>模型收到明確的查無結果，會照實說明，不會拿無關片段硬答。</small>';
      }
    };

    queryInputs.forEach((input) => input.addEventListener('change', () => {
      if (document.startViewTransition && !reduceMotion.matches) document.startViewTransition(render);
      else render();
    }));
    kInput.addEventListener('input', render);
    tInput.addEventListener('input', render);

    /* 游標停在某個片段上時，三欄中同一片段一起標示 */
    let linkedChunk = null;
    const linkChunk = (id) => {
      if (id === linkedChunk) return;
      linkedChunk = id;
      rrf.querySelectorAll('[data-chunk]').forEach((el) => el.classList.toggle('is-linked', el.dataset.chunk === id));
    };
    rrf.addEventListener('mouseover', (event) => linkChunk(event.target.closest('[data-chunk]')?.dataset.chunk ?? null));
    rrf.addEventListener('mouseleave', () => linkChunk(null));
    render();
  }

  /* ---------- web_fetch 出站檢查器 ----------
     1. 讀過知識庫後停用聯網、2. 網址來源：backend/app/rag/research_session.py
     3. 網域白名單：backend/app/rag/tools.py 與 app/core/config.py
     4-9. SSRF：backend/app/core/ssrf_protection.py（DNS 與轉址只能在伺服器執行） */
  const BLOCKED_PORTS = new Set([22, 23, 25, 111, 135, 139, 445, 1433, 1521, 2375, 2376, 3306, 5432, 6379, 11211, 27017]);
  const BLOCKED_HOSTS = new Set(['localhost', 'localhost.localdomain', 'broadcasthost', 'ip6-localhost', 'ip6-loopback', 'local', 'internal', 'metadata.google.internal', 'metadata.internal']);
  const BLOCKED_SUFFIXES = ['.localhost', '.local', '.internal', '.lan', '.home.arpa', '.localdomain', '.corp'];
  const V4_RANGES = [
    ['0.0.0.0', 8, '本機網段'], ['10.0.0.0', 8, '私有網段'], ['100.64.0.0', 10, '電信級 NAT 共用位址'], ['127.0.0.0', 8, '迴環位址'],
    ['169.254.0.0', 16, '連結本地與雲端中繼資料端點'], ['172.16.0.0', 12, '私有網段'], ['192.0.0.0', 24, 'IETF 保留'], ['192.0.2.0', 24, '文件測試網段'],
    ['192.88.99.0', 24, '6to4 中繼'], ['192.168.0.0', 16, '私有網段'], ['198.18.0.0', 15, '效能測試網段'], ['198.51.100.0', 24, '文件測試網段'],
    ['203.0.113.0', 24, '文件測試網段'], ['224.0.0.0', 4, '群播'], ['240.0.0.0', 4, '保留網段'], ['255.255.255.255', 32, '廣播位址'],
  ];
  const DOMAIN_PATTERN = /^[a-z0-9-]+(\.[a-z0-9-]+)*$/;

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
    const v4 = parseV4(host);
    if (v4 !== null) {
      const hit = V4_RANGES.find(([base, bits]) => inRange(v4, base, bits));
      return hit ? { isIp: true, blocked: true, reason: `${host} 位於禁止網段 ${hit[0]}/${hit[1]}（${hit[2]}）` } : { isIp: true, blocked: false };
    }
    if (!host.includes(':')) return { isIp: false };
    if (host === '::' || host === '::1') return { isIp: true, blocked: true, reason: `禁止存取未指定或迴環的 IPv6 位址 ${host}` };
    const mapped = host.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (mapped) return checkIpLiteral(mapped[1]);
    if (/^f[cd]/.test(host)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 唯一本地位址 ${host}（fc00::/7）` };
    if (/^fe[89ab]/.test(host)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 連結本地位址 ${host}（fe80::/10）` };
    if (/^ff/.test(host)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 群播位址 ${host}` };
    if (/^2001:db8:/.test(host)) return { isIp: true, blocked: true, reason: `禁止存取 IPv6 文件測試網段 ${host}` };
    return { isIp: true, blocked: false };
  };
  /* 網址來源比對與 research_session.py 相同：兩邊都取正規化後的完整網址逐字比對，不做 unquote 之類的解碼。
     後端以 httpx.URL 正規化，這裡以瀏覽器的 URL 近似（同樣小寫主機、百分比編碼非 ASCII 字元） */
  const URL_TOKEN_PATTERN = /https?:\/\/[^\s<>"'`]+/gi;
  const URL_TRAILING_PUNCTUATION = '.,;:!?)]}\'"，。、；：！？）」』】';
  const canonicalUrl = (text) => {
    try {
      const url = new URL(text.trim());
      return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname ? url.href : null;
    } catch { return null; }
  };
  /* extract_url_tokens：完整記號、截在第一個非 ASCII 字元前的形式，以及逐一去掉結尾標點的形式 */
  const extractUrlTokens = (text) => {
    const tokens = new Set();
    for (const match of text.matchAll(URL_TOKEN_PATTERN)) {
      const candidates = new Set([match[0]]);
      const asciiPrefix = match[0].match(/^[!-~]+/);
      if (asciiPrefix) candidates.add(asciiPrefix[0]);
      Array.from(candidates).forEach((candidate) => {
        let trimmed = candidate;
        while (trimmed && URL_TRAILING_PUNCTUATION.includes(trimmed.at(-1))) {
          trimmed = trimmed.slice(0, -1);
          candidates.add(trimmed);
        }
      });
      candidates.forEach((candidate) => {
        const normalized = canonicalUrl(candidate);
        if (normalized) tokens.add(normalized);
      });
    }
    return tokens;
  };
  /* 與 config.py 的 _validate_web_fetch_domains 相同：不可為空、* 不可與其他網域並列、只接受網域名稱 */
  const parseAllowlist = (raw) => {
    const domains = raw.split(',').map((d) => d.trim().toLowerCase()).filter(Boolean);
    if (!domains.length) return { error: '不可為空；不限制網域請明確設定為 *' };
    if (domains.includes('*') && domains.length > 1) return { error: '設為 * 時不可再列其他網域' };
    const invalid = domains.filter((d) => d !== '*' && !DOMAIN_PATTERN.test(d));
    if (invalid.length) return { error: `含無效網域（只填網域，不含通訊協定與路徑）：${invalid.join(', ')}` };
    return { domains };
  };

  const inspector = document.querySelector('[data-inspector]');
  if (inspector) {
    const urlInput = inspector.querySelector('[data-url-input]');
    const kbToggle = inspector.querySelector('[data-kb-toggle]');
    const blockToggle = inspector.querySelector('[data-block-toggle]');
    const allowInput = inspector.querySelector('[data-allow-input]');
    const kbContext = inspector.querySelector('[data-kb-context]');
    const verdictElement = inspector.querySelector('[data-verdict]');
    const sources = Array.from(inspector.querySelectorAll('[data-source]'));
    const checkRows = new Map(Array.from(inspector.querySelectorAll('[data-check]')).map((row) => [row.dataset.check, row]));
    const ORDER = Array.from(checkRows.keys());
    const ICONS = { idle: '#i-check-circle', pass: '#i-check-circle', fail: '#i-x-circle', skip: '#i-check-circle', server: '#i-globe', config: '#i-warning-circle' };
    const VERDICT_ICONS = { allow: '#i-check-circle', block: '#i-x-circle', config: '#i-warning-circle', pending: '#i-globe' };

    const setCheck = (name, state, message) => {
      const row = checkRows.get(name);
      row.dataset.state = state;
      row.querySelector('.check__msg').textContent = message;
      row.querySelector('use').setAttribute('href', ICONS[state]);
    };
    const skipAfter = (name, message) => ORDER.slice(ORDER.indexOf(name) + 1).forEach((next) => setCheck(next, 'skip', message));
    const setVerdict = (kind, title, detail) => {
      verdictElement.className = `verdict verdict--${kind}`;
      verdictElement.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${VERDICT_ICONS[kind]}"></use></svg><div>${escapeHtml(title)}${detail ? `<small>${escapeHtml(detail)}</small>` : ''}</div>`;
    };
    const block = (name, message, title, detail) => {
      setCheck(name, 'fail', message);
      skipAfter(name, '未執行');
      setVerdict('block', title, detail);
    };

    const run = () => {
      sources.forEach((el) => el.classList.remove('is-match'));
      const target = urlInput.value.trim();
      if (!target) {
        ORDER.forEach((name) => setCheck(name, 'idle', '等待輸入'));
        setVerdict('pending', '輸入一個網址，或點選上方範例。');
        return;
      }

      /* 1. BLOCK_WEB_TOOLS_AFTER_KB：同一次提問讀過知識庫內容後，web_search 與 web_fetch 一律拒絕 */
      if (blockToggle.checked && kbToggle.checked) {
        block('kb', '本次提問已讀取知識庫內容，依設定不再使用聯網工具',
          '拒絕呼叫工具', '避免讀過的內部資料被帶進外部請求；模型只能用已取得的資料回答。');
        return;
      }
      setCheck('kb', 'pass', kbToggle.checked ? 'BLOCK_WEB_TOOLS_AFTER_KB 已關閉' : '這次提問還沒讀到知識庫內容');

      /* 2. 網址須以完整網址出現在使用者訊息或本次工具結果的資料欄位；實際送出的就是比對到的正規化網址 */
      const canonicalTarget = canonicalUrl(target);
      const matches = canonicalTarget
        ? sources.filter((el) => !el.closest('[hidden]') && extractUrlTokens(el.textContent).has(canonicalTarget))
        : [];
      if (!matches.length) {
        block('origin', '只能讀取使用者訊息或本次工具結果中原樣出現過的網址',
          '拒絕呼叫工具', '兩邊都取正規化後的完整網址逐字比對：模型自己組的、改寫過的網址（例如補上結尾斜線、只取網址的一段）都不算出現過，資料無法藉此外送。');
        return;
      }
      matches.forEach((el) => el.classList.add('is-match'));
      setCheck('origin', 'pass', `以完整網址出現在${matches[0].dataset.source}`);

      /* 3. WEB_FETCH_ALLOWED_DOMAINS：主機須為清單中的網域或其子網域 */
      const allow = parseAllowlist(allowInput.value);
      if (allow.error) {
        setCheck('domain', 'config', allow.error);
        skipAfter('domain', '未執行');
        setVerdict('config', '設定無效', '後端啟動時就會拒絕這個 WEB_FETCH_ALLOWED_DOMAINS。');
        return;
      }
      let url = null;
      try { url = new URL(target); } catch { /* 交給下一關回報格式錯誤 */ }
      const host = url ? url.hostname.toLowerCase().replace(/^\[|\]$/g, '').replace(/\.+$/, '') : '';
      const unrestricted = allow.domains[0] === '*';
      if (!unrestricted && !allow.domains.some((d) => host === d || host.endsWith(`.${d}`))) {
        block('domain', `${host || '無法取得主機名稱'} 不在允許清單內`,
          '拒絕請求', '網域白名單只檢查初始網址，轉址目的地由後面的 SSRF 驗證把關。');
        return;
      }
      setCheck('domain', 'pass', unrestricted ? '設為 *，不限制網域' : `${host} 符合允許清單`);

      /* 4. 協定只允許 http、https，且不得夾帶帳號密碼 */
      if (!url) {
        block('scheme', 'URL 格式無法解析', '拒絕請求', 'URL 格式無法解析。');
        return;
      }
      const scheme = url.protocol.replace(':', '');
      if (scheme !== 'http' && scheme !== 'https') {
        block('scheme', `不允許的協定「${scheme}」，只支援 http、https`, '拒絕請求', '只有 http 與 https 會被放行。');
        return;
      }
      if (url.username || url.password) {
        block('scheme', 'URL 禁止包含帳號密碼（Userinfo）', '拒絕請求', '帶有帳號密碼的網址可能被用來偽造主機名稱。');
        return;
      }
      setCheck('scheme', 'pass', `${scheme}，未包含帳號密碼`);

      /* 5. 危險連接埠 */
      const port = url.port ? Number(url.port) : (scheme === 'https' ? 443 : 80);
      if (BLOCKED_PORTS.has(port)) {
        block('port', `禁止存取受保護的內部服務連接埠 ${port}`, '拒絕請求', '資料庫、快取與遠端管理服務的連接埠一律阻擋。');
        return;
      }
      setCheck('port', 'pass', `連接埠 ${port} 允許`);

      /* 6. 保留或內部主機名稱 */
      if (BLOCKED_HOSTS.has(host)) {
        block('host', `禁止存取保留或內部主機名稱「${host}」`, '拒絕請求', '主機名稱本身就在封鎖清單中。');
        return;
      }
      const suffix = BLOCKED_SUFFIXES.find((s) => host.endsWith(s));
      if (suffix) {
        block('host', `禁止存取內部專屬網域（結尾為 ${suffix}）`, '拒絕請求', '內網常見的網域後綴會被直接拒絕。');
        return;
      }
      setCheck('host', 'pass', `「${host}」不在封鎖清單`);

      /* 7. 直接輸入的 IP；8. 網域名稱交給伺服器解析；9. 每一跳轉址都重新驗證 */
      const ip = checkIpLiteral(host);
      setCheck('redirect', 'server', '停用自動轉址，每一跳重新執行 SSRF 驗證（最多 5 次）');
      if (ip.isIp) {
        if (ip.blocked) {
          setCheck('ip', 'fail', ip.reason);
          setCheck('dns', 'skip', '直接輸入 IP，不需解析');
          setCheck('redirect', 'skip', '未執行');
          setVerdict('block', '拒絕請求', '私有、迴環、連結本地與雲端中繼資料位址一律阻擋。即使網址來自工具結果，提示注入也拿不到內網資料。');
          return;
        }
        setCheck('ip', 'pass', `${host} 為公開 IP 位址`);
        setCheck('dns', 'skip', '直接輸入 IP，不需解析');
        setVerdict('allow', '允許送出請求', '以 safe_fetch_text 抓取：轉址逐跳重驗、連線固定在驗證過的 IP，回應超過 5 MiB 即中斷。');
        return;
      }
      setCheck('ip', 'skip', '不是 IP，交由 DNS 解析後檢查');
      setCheck('dns', 'server', '伺服器以專用執行緒池解析（5 秒逾時），所有 IP 都須是公開位址，連線再固定到核可的 IP');
      setVerdict('pending', '瀏覽器能重現的檢查都通過了', '最後兩關在伺服器：DNS 解析出的每個 IP 都必須是公開位址，連線直接打到核可的 IP，轉址也要逐跳重驗，才會真的送出請求。');
    };

    urlInput.addEventListener('input', run);
    allowInput.addEventListener('input', run);
    [kbToggle, blockToggle].forEach((toggle) => toggle.addEventListener('change', () => {
      kbContext.hidden = !kbToggle.checked;
      run();
    }));
    /* 每個範例都帶著自己的情境：是否已讀過知識庫、是否開啟 BLOCK_WEB_TOOLS_AFTER_KB */
    inspector.querySelectorAll('[data-url-example]').forEach((button) => button.addEventListener('click', () => {
      urlInput.value = button.dataset.urlExample;
      kbToggle.checked = button.dataset.kb === 'true';
      blockToggle.checked = button.dataset.block === 'true';
      kbContext.hidden = !kbToggle.checked;
      run();
    }));
    kbContext.hidden = !kbToggle.checked;
    run();
  }

  /* ---------- 工具呼叫核准：事件與逾時與 backend/app/rag/agent.py、tool_approval.py 相同 ---------- */
  const APPROVAL_TIMEOUT_SECONDS = 300;
  const approval = document.querySelector('[data-approval]');
  if (approval) {
    const card = approval.querySelector('[data-approval-card]');
    const timerElement = approval.querySelector('[data-approval-timer]');
    const result = approval.querySelector('[data-approval-result]');
    const events = approval.querySelector('[data-approval-events]');
    const waitNote = approval.querySelector('[data-approval-wait]');
    const step = approval.querySelector('[data-approval-step]');
    const stepMessage = approval.querySelector('[data-approval-step-msg]');
    const stepTime = approval.querySelector('[data-approval-step-time]');
    const decideButtons = Array.from(approval.querySelectorAll('[data-approval-decide]'));
    const initialEvents = events.innerHTML;
    const OUTCOMES = {
      approve: {
        approved: true,
        stepState: 'done', stepMessage: '已核准，回傳單號 LR-20261002-0418', stepTime: '1.27 秒',
        stepEnd: '{"step": 2, "duration_seconds": 1.27, "status": "success", ...}',
        status: '你核准了這次呼叫，工具已執行',
        detail: '工具結果同樣包在不可信資料標記裡交給模型。',
        answer: '已替王小明（E1042）送出 10/2 至 10/3 的特休申請，單號 LR-20261002-0418，接下來由直屬主管簽核。依規定，特休須在假期開始前三個工作天提出',
      },
      deny: {
        approved: false,
        stepState: 'fail', stepMessage: '使用者未核准執行此工具', stepTime: '未執行',
        stepEnd: '{"step": 2, "status": "error", "output_preview": "{\\"error\\": \\"使用者未核准執行此工具…\\"}"}',
        status: '你拒絕了這次呼叫，工具沒有執行',
        detail: '模型收到「使用者未核准」，並被要求不要再次呼叫同一工具。',
        answer: '你沒有核准建立請假單，所以我沒有送出申請。依規定，特休也可以在人資系統的「請假申請」頁面自行填寫',
      },
      timeout: {
        approved: false,
        stepState: 'fail', stepMessage: '300 秒內沒有回應，視為拒絕', stepTime: '未執行',
        stepEnd: '{"step": 2, "status": "error", "output_preview": "{\\"error\\": \\"使用者未核准執行此工具…\\"}"}',
        status: `${APPROVAL_TIMEOUT_SECONDS} 秒內沒有回應，視為拒絕`,
        detail: '逾時與拒絕的處理相同：approval_resolved 的 approved 為 false，工具不會執行。',
        answer: '這次沒有收到你的確認，所以我沒有送出請假申請。依規定，特休也可以在人資系統的「請假申請」頁面自行填寫',
      },
    };

    let remaining = APPROVAL_TIMEOUT_SECONDS;
    let ticker = null;
    let decided = false;
    const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    const stopTimer = () => { clearInterval(ticker); ticker = null; };
    const startTimer = () => {
      stopTimer();
      ticker = setInterval(() => {
        remaining -= 1;
        timerElement.textContent = formatTime(remaining);
        if (remaining <= 0) decide('timeout');
      }, 1000);
    };
    const addEvent = (name, data, tone) => {
      const item = document.createElement('li');
      item.className = `is-new${tone ? ` is-${tone}` : ''}`;
      const nameElement = document.createElement('span');
      nameElement.className = 'events__name';
      nameElement.textContent = name;
      const dataElement = document.createElement('span');
      dataElement.className = 'events__data';
      dataElement.textContent = data;
      item.append(nameElement, dataElement);
      events.append(item);
    };

    function decide(kind) {
      if (decided) return;
      decided = true;
      stopTimer();
      const outcome = OUTCOMES[kind];
      card.hidden = true;
      waitNote.hidden = true;
      step.dataset.state = outcome.stepState;
      stepMessage.textContent = outcome.stepMessage;
      stepTime.textContent = outcome.stepTime;

      addEvent('approval_resolved', `{"approval_id": "q3VxT0bL8mYc…", "approved": ${outcome.approved}}`, outcome.approved ? 'ok' : 'bad');
      addEvent('step_end', outcome.stepEnd, outcome.approved ? 'ok' : 'bad');
      addEvent('token', `{"content": "${outcome.answer.slice(0, 18)}…[1]"}`);
      addEvent('sources', '{"sources_detail": [{"citation": 1, "source": "員工請假辦法.pdf", ...}]}');
      addEvent('done', '{"message_id": 312, "research_trace": [...]}');

      const status = document.createElement('p');
      status.className = 'approval__status';
      status.dataset.kind = kind;
      status.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${outcome.approved ? '#i-check-circle' : '#i-x-circle'}"></use></svg><span>${escapeHtml(outcome.status)}<small>${escapeHtml(outcome.detail)}</small></span>`;
      const answer = document.createElement('p');
      answer.append(outcome.answer);
      const cite = document.createElement('span');
      cite.className = 'cite';
      cite.textContent = '[1]';
      answer.append(cite, '。');
      result.replaceChildren(status, answer);
      result.hidden = false;
    }

    const reset = () => {
      decided = false;
      remaining = APPROVAL_TIMEOUT_SECONDS;
      timerElement.textContent = formatTime(remaining);
      events.innerHTML = initialEvents;
      card.hidden = false;
      waitNote.hidden = false;
      result.hidden = true;
      result.replaceChildren();
      step.dataset.state = 'wait';
      stepMessage.textContent = '等待核准';
      stepTime.textContent = '暫停中';
      startTimer();
    };

    decideButtons.forEach((button) => button.addEventListener('click', () => decide(button.dataset.approvalDecide)));
    approval.querySelector('[data-approval-reset]').addEventListener('click', reset);
    /* 倒數在示範捲進畫面時才開始，離開畫面時暫停 */
    if ('IntersectionObserver' in window) {
      new IntersectionObserver((entries) => entries.forEach((entry) => {
        if (entry.isIntersecting && !decided && !ticker) startTimer();
        else if (!entry.isIntersecting) stopTimer();
      }), { threshold: 0.25 }).observe(approval);
    }
  }

  /* ---------- 自訂 API 工具的預設核准：與 tool_approval.default_requires_approval 相同 ---------- */
  const SAFE_HTTP_METHODS = ['GET', 'HEAD', 'OPTIONS'];
  const methodRules = document.querySelector('[data-method-rules]');
  if (methodRules) {
    const methodButtons = Array.from(methodRules.querySelectorAll('[data-method]'));
    const verdict = methodRules.querySelector('[data-method-verdict]');
    const value = methodRules.querySelector('[data-method-value]');
    const showMethod = (method) => {
      const needsApproval = !SAFE_HTTP_METHODS.includes(method);
      methodButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.method === method)));
      const label = document.createElement('b');
      label.dataset.kind = needsApproval ? 'yes' : 'no';
      label.textContent = needsApproval ? `${method}：預設需要核准` : `${method}：預設不需要核准`;
      verdict.replaceChildren(label, document.createElement('br'), needsApproval
        ? '這個方法可能建立、修改或刪除外部系統的資料，Agent 呼叫前會先暫停，等發問者確認。'
        : '這個方法只讀取資料，Agent 可以直接呼叫；管理員仍可為個別工具勾選「需要核准」。');
      value.textContent = needsApproval ? '需要' : '不需要';
      value.className = `rule-list__value rule-list__value--${needsApproval ? 'yes' : 'no'}`;
    };
    methodButtons.forEach((button) => button.addEventListener('click', () => showMethod(button.dataset.method)));
    showMethod('POST');
  }

  /* ---------- stdio 子行程環境變數：依作業系統切換繼承清單（backend/app/services/mcp_service.py） ---------- */
  const envdiff = document.querySelector('[data-envdiff]');
  if (envdiff) {
    const inheritedCell = envdiff.querySelector('[data-inherited]');
    const platformButtons = Array.from(envdiff.querySelectorAll('[data-platform-vars]'));
    platformButtons.forEach((button) => button.addEventListener('click', () => {
      platformButtons.forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
      inheritedCell.textContent = button.dataset.platformVars;
    }));
  }

  /* ---------- 卡片游標光暈與 Hero 傾斜：只在精準指標裝置、未要求減少動態時跟隨游標 ---------- */
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const followPointer = () => finePointer.matches && !reduceMotion.matches;
  let spotFrame = 0;
  document.addEventListener('pointermove', (event) => {
    if (!followPointer() || !(event.target instanceof Element)) return;
    const card = event.target.closest('.cell, .guard, .spot');
    if (!card) return;
    cancelAnimationFrame(spotFrame);
    spotFrame = requestAnimationFrame(() => {
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--mx', `${Math.round(event.clientX - rect.left)}px`);
      card.style.setProperty('--my', `${Math.round(event.clientY - rect.top)}px`);
    });
  }, { passive: true });

  const hero = document.querySelector('.hero');
  const tiltTarget = document.querySelector('[data-tilt]');
  if (hero && tiltTarget) {
    let tiltFrame = 0;
    const setTilt = (x, y) => {
      tiltTarget.style.setProperty('--tilt-y', `${(x * 7).toFixed(2)}deg`);
      tiltTarget.style.setProperty('--tilt-x', `${(-y * 5).toFixed(2)}deg`);
    };
    hero.addEventListener('pointermove', (event) => {
      if (!followPointer()) return;
      cancelAnimationFrame(tiltFrame);
      tiltFrame = requestAnimationFrame(() => {
        const rect = hero.getBoundingClientRect();
        setTilt((event.clientX - rect.left) / rect.width - 0.5, (event.clientY - rect.top) / rect.height - 0.5);
      });
    }, { passive: true });
    hero.addEventListener('pointerleave', () => {
      cancelAnimationFrame(tiltFrame);
      setTilt(0, 0);
    });
  }

  /* ---------- 5.0.0：登入失敗節流（backend/app/core/login_throttle.py 與 api/auth.py 的 login） ----------
     先檢查鎖定（429 + Retry-After，連正確密碼也不驗），再驗證密碼；失敗時帳號與來源位址各記一次，
     達到門檻就清空失敗紀錄並鎖定。登入成功只清除該帳號的紀錄，位址的計數保留。門檻取 .env.example 的建議值。 */
  const throttleDemo = document.querySelector('[data-throttle]');
  if (throttleDemo) {
    const MAX_FAILURES_PER_ACCOUNT = 5;
    const MAX_FAILURES_PER_ADDRESS = 20;
    const WINDOW_SECONDS = 900;
    const LOCKOUT_SECONDS = 900;
    const ADDRESS = '203.0.113.7';
    const EXISTING_ACCOUNTS = new Set(['alice']);
    const SPRAY_NAMES = ['admin', 'root', 'test', 'guest', 'hr', 'it', 'finance', 'sales', 'support', 'service',
      'backup', 'dev', 'ops', 'manager', 'office', 'info', 'demo', 'user', 'staff', 'intern'];
    const HINTS = {
      alice: 'alice 是存在的帳號，正確密碼可以登入。',
      ALICE: '大小寫不同仍是同一個識別：去掉前後空白、轉成小寫後與 alice 共用同一份計數。',
      ghost: 'ghost 不存在：失敗照樣計數，回應與密碼錯誤完全相同，無法藉此探測帳號是否存在。',
      spray: '每次換一個帳號猜密碼：單一帳號都到不了門檻，但同一個來源位址累積 20 次失敗就會被暫停。',
    };

    const makeTracker = (maxFailures) => {
      const records = new Map();
      return {
        retryAfter(key, now) {
          const record = records.get(key);
          return !record || record.lockedUntil <= now ? 0 : record.lockedUntil - now;
        },
        recordFailure(key, now) {
          let record = records.get(key);
          if (!record) {
            record = { failures: [], lockedUntil: 0 };
            records.set(key, record);
          }
          record.failures = record.failures.filter((time) => time > now - WINDOW_SECONDS);
          record.failures.push(now);
          if (record.failures.length >= maxFailures) {
            record.failures = [];
            record.lockedUntil = now + LOCKOUT_SECONDS;
            return true;
          }
          return false;
        },
        count(key, now) {
          const record = records.get(key);
          return record ? record.failures.filter((time) => time > now - WINDOW_SECONDS).length : 0;
        },
        clear(key) { records.delete(key); },
      };
    };

    const whoButtons = Array.from(throttleDemo.querySelectorAll('[data-who]'));
    const hint = throttleDemo.querySelector('[data-who-hint]');
    const keyLabel = throttleDemo.querySelector('[data-meter-key]');
    const accountCount = throttleDemo.querySelector('[data-meter-acct-count]');
    const addressCount = throttleDemo.querySelector('[data-meter-addr-count]');
    const accountDots = Array.from(throttleDemo.querySelectorAll('[data-meter-acct] li'));
    const addressTicks = Array.from(throttleDemo.querySelectorAll('[data-meter-addr] li'));
    const lockBanner = throttleDemo.querySelector('[data-lock]');
    const lockText = throttleDemo.querySelector('[data-lock-text]');
    const lockTimer = throttleDemo.querySelector('[data-lock-timer]');
    const log = throttleDemo.querySelector('[data-throttle-log]');
    const emptyLog = log.innerHTML;

    let accounts;
    let addresses;
    let startedAt;
    let skipped;
    let sprayIndex;
    let who = 'alice';
    let shownKey = 'alice';
    let ticker = null;
    const now = () => (performance.now() - startedAt) / 1000 + skipped;
    const clock = (seconds) => `+${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
    const countdown = (seconds) => {
      const whole = Math.ceil(seconds);
      return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
    };

    const addLog = (code, title, detail, { at = now(), animate = true } = {}) => {
      log.querySelector('.throttle__empty')?.remove();
      const item = document.createElement('li');
      item.className = animate ? 'log is-new' : 'log';
      item.dataset.code = String(code);
      const codeElement = document.createElement('span');
      codeElement.className = 'log__code';
      codeElement.textContent = String(code);
      const body = document.createElement('span');
      body.className = 'log__body';
      const titleElement = document.createElement('b');
      titleElement.textContent = title;
      const detailElement = document.createElement('small');
      detailElement.textContent = detail;
      body.append(titleElement, detailElement);
      const time = document.createElement('span');
      time.className = 'log__time';
      time.textContent = clock(at);
      item.append(codeElement, body, time);
      log.prepend(item);
    };

    /* 開場就有三筆失敗：alice 錯兩次，再以 ALICE 錯一次（大小寫不同仍共用計數），再錯兩次就會鎖定 */
    const SEED = [['alice', 0], ['alice', 6], ['ALICE', 11]];
    const seed = () => {
      SEED.forEach(([identifier, at]) => {
        const key = identifier.trim().toLowerCase();
        accounts.recordFailure(key, at);
        addresses.recordFailure(ADDRESS, at);
        addLog(401, '使用者名稱或密碼錯誤', `${identifier} · 密碼錯誤 · 識別 ${accounts.count(key, at)}/${MAX_FAILURES_PER_ACCOUNT}、位址 ${addresses.count(ADDRESS, at)}/${MAX_FAILURES_PER_ADDRESS}`, { at, animate: false });
      });
      skipped = SEED.at(-1)[1] + 3;
    };

    const render = () => {
      const t = now();
      const accountWait = accounts.retryAfter(shownKey, t);
      const addressWait = addresses.retryAfter(ADDRESS, t);
      const accountFailures = accounts.count(shownKey, t);
      const addressFailures = addresses.count(ADDRESS, t);
      keyLabel.textContent = shownKey;
      accountCount.textContent = accountWait ? '鎖定中' : `${accountFailures} / ${MAX_FAILURES_PER_ACCOUNT}`;
      addressCount.textContent = addressWait ? '鎖定中' : `${addressFailures} / ${MAX_FAILURES_PER_ADDRESS}`;
      accountDots.forEach((dot, i) => {
        dot.classList.toggle('is-locked', accountWait > 0);
        dot.classList.toggle('is-on', !accountWait && i < accountFailures);
      });
      addressTicks.forEach((tick, i) => {
        tick.classList.toggle('is-locked', addressWait > 0);
        tick.classList.toggle('is-on', !addressWait && i < addressFailures);
      });
      const wait = Math.max(accountWait, addressWait);
      lockBanner.hidden = wait <= 0;
      if (wait > 0) {
        lockText.textContent = addressWait >= accountWait ? `來源位址 ${ADDRESS} 暫停登入（所有帳號）` : `${shownKey} 暫停登入`;
        lockTimer.textContent = countdown(wait);
      }
      if (wait > 0 && !ticker) ticker = setInterval(render, 1000);
      if (wait <= 0 && ticker) {
        clearInterval(ticker);
        ticker = null;
      }
    };

    const attempt = (kind) => {
      const t = now();
      const identifier = who === 'spray' ? (SPRAY_NAMES[sprayIndex] ?? `user${sprayIndex + 1}`) : who;
      if (who === 'spray') sprayIndex += 1;
      const key = identifier.trim().toLowerCase();
      shownKey = key;
      const wait = Math.max(accounts.retryAfter(key, t), addresses.retryAfter(ADDRESS, t));
      if (wait > 0) {
        addLog(429, '登入失敗次數過多，請稍後再試', `${identifier} · Retry-After: ${Math.ceil(wait)}${kind === 'right' ? ' · 鎖定期間不驗證密碼' : ''}`);
        render();
        return;
      }
      if (kind === 'right' && EXISTING_ACCOUNTS.has(key)) {
        accounts.clear(key);
        addLog(200, '登入成功', `${identifier} · 只清除這個帳號的失敗紀錄，來源位址的計數保留`);
        render();
        return;
      }
      const accountLocked = accounts.recordFailure(key, t);
      const addressLocked = addresses.recordFailure(ADDRESS, t);
      const reason = EXISTING_ACCOUNTS.has(key) ? '密碼錯誤' : '帳號不存在';
      const counts = `識別 ${accountLocked ? MAX_FAILURES_PER_ACCOUNT : accounts.count(key, t)}/${MAX_FAILURES_PER_ACCOUNT}、位址 ${addressLocked ? MAX_FAILURES_PER_ADDRESS : addresses.count(ADDRESS, t)}/${MAX_FAILURES_PER_ADDRESS}`;
      const lockNote = accountLocked || addressLocked ? '；達到門檻，接下來 15 分鐘一律回 429' : '';
      addLog(401, '使用者名稱或密碼錯誤', `${identifier} · ${reason} · ${counts}${lockNote}`);
      render();
    };

    const selectWho = (value) => {
      who = value;
      whoButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.who === value)));
      hint.textContent = HINTS[value];
      if (value !== 'spray') shownKey = value.trim().toLowerCase();
      render();
    };

    const reset = () => {
      accounts = makeTracker(MAX_FAILURES_PER_ACCOUNT);
      addresses = makeTracker(MAX_FAILURES_PER_ADDRESS);
      startedAt = performance.now();
      skipped = 0;
      sprayIndex = 0;
      log.innerHTML = emptyLog;
      seed();
      selectWho(who);
    };

    whoButtons.forEach((button) => button.addEventListener('click', () => selectWho(button.dataset.who)));
    throttleDemo.querySelectorAll('[data-attempt]').forEach((button) => button.addEventListener('click', () => attempt(button.dataset.attempt)));
    throttleDemo.querySelector('[data-skip]').addEventListener('click', () => {
      skipped += LOCKOUT_SECONDS;
      log.querySelector('.throttle__empty')?.remove();
      const marker = document.createElement('li');
      marker.className = 'log log--skip';
      marker.textContent = `快轉 15 分鐘（${clock(now())}）：鎖定到期，視窗外的失敗不再計數`;
      log.prepend(marker);
      render();
    });
    throttleDemo.querySelector('[data-throttle-reset]').addEventListener('click', reset);
    reset();
  }

  /* ---------- 5.0.0：變更密碼撤銷權杖（backend/app/core/jwt_auth.py 的 resolve_token_user） ----------
     權杖的 iat 早於帳號的 tokens_valid_after 就無效；兩邊都保留微秒，所以同一秒內稍早簽發的權杖也會失效。 */
  const tokensDemo = document.querySelector('[data-tokens]');
  if (tokensDemo) {
    const CHANGED_AT = '1791627312.420117';
    const sessions = Array.from(tokensDemo.querySelectorAll('.session'));
    const tva = tokensDemo.querySelector('[data-tva]');
    const tvaLabel = tokensDemo.querySelector('[data-tva-label]');
    const note = tokensDemo.querySelector('[data-tokens-note]');
    const changeButton = tokensDemo.querySelector('[data-change-password]');
    const resetButton = tokensDemo.querySelector('[data-tokens-reset]');
    const initial = { tva: tva.textContent, label: tvaLabel.textContent, note: note.textContent };
    /* 以字串比較整數秒與微秒，避免浮點數誤差 */
    const isEarlier = (a, b) => {
      const [aSeconds, aFraction = ''] = a.split('.');
      const [bSeconds, bFraction = ''] = b.split('.');
      if (aSeconds !== bSeconds) return Number(aSeconds) < Number(bSeconds);
      return aFraction.padEnd(6, '0') < bFraction.padEnd(6, '0');
    };

    changeButton.addEventListener('click', () => {
      sessions.forEach((session, index) => {
        const revoked = isEarlier(session.dataset.iat, CHANGED_AT);
        session.style.transitionDelay = reduceMotion.matches ? '0s' : `${index * 140}ms`;
        session.classList.toggle('is-revoked', revoked);
        session.querySelector('[data-state]').textContent = revoked ? '已失效 · 401' : '有效';
        if (session.classList.contains('session--leak')) {
          const comparison = document.createElement('span');
          comparison.className = 'session__cmp';
          comparison.dataset.cmp = '';
          comparison.textContent = `${session.dataset.iat} < ${CHANGED_AT}`;
          session.append(comparison);
        }
      });
      tva.textContent = CHANGED_AT;
      tva.classList.add('is-changed');
      tvaLabel.textContent = '18:15:12.420 變更密碼';
      note.textContent = '三個權杖的 iat 都早於 tokens_valid_after，下一次請求一律回 401「認證權杖無效：驗證失敗」，回應也清除了重新整理權杖的 Cookie。外洩的權杖與改密碼在同一秒：iat 若只記到整數秒，1791627312 不小於 1791627312，它就會漏網，所以 iat 保留到微秒。';
      changeButton.disabled = true;
      resetButton.hidden = false;
    });

    resetButton.addEventListener('click', () => {
      sessions.forEach((session) => {
        session.style.transitionDelay = '0s';
        session.classList.remove('is-revoked');
        session.querySelector('[data-state]').textContent = '有效';
        session.querySelector('[data-cmp]')?.remove();
      });
      tva.textContent = initial.tva;
      tva.classList.remove('is-changed');
      tvaLabel.textContent = initial.label;
      note.textContent = initial.note;
      changeButton.disabled = false;
      resetButton.hidden = true;
      changeButton.focus();
    });
  }

  /* ---------- 版本時間軸：預設捲到最右邊，先看到最新版本 ---------- */
  const timeline = document.querySelector('.timeline');
  if (timeline) timeline.scrollLeft = timeline.scrollWidth;

  /* ---------- 複製指令 ---------- */
  document.querySelectorAll('[data-copy]').forEach((button) => {
    const target = document.getElementById(button.dataset.copy);
    const label = button.querySelector('span');
    const icon = button.querySelector('use');
    const idleLabel = label.textContent;
    let resetTimer;
    button.addEventListener('click', async () => {
      const commands = Array.from(target.querySelectorAll('[data-cmd]')).map((el) => el.textContent);
      const text = (commands.length ? commands.join('\n') : target.textContent).trim();
      clearTimeout(resetTimer);
      try {
        await navigator.clipboard.writeText(text);
        button.dataset.copied = 'true';
        label.textContent = '已複製';
        icon.setAttribute('href', '#i-check');
      } catch {
        label.textContent = '無法複製，請手動選取';
      }
      resetTimer = setTimeout(() => {
        button.dataset.copied = 'false';
        label.textContent = idleLabel;
        icon.setAttribute('href', '#i-copy');
      }, 1800);
    });
  });
})();
