(() => {
  const app = window.askmiao;
  if (!app) return;
  const { sound, ticker, onVisible, motionAllowed, finePointer } = app;
  const lab = window.askmiaoLab;
  const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
  const EASE_IN_OUT = 'cubic-bezier(0.45, 0, 0.25, 1)';
  const OVERSHOOT = 'cubic-bezier(0.34, 1.56, 0.64, 1)';
  const FLING_IN = 'cubic-bezier(0.22, 1, 0.36, 1)';
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs) => {
    const element = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
    return element;
  };
  const centerIn = (element, frame) => {
    const box = element.getBoundingClientRect();
    return { x: box.left + box.width / 2 - frame.left, y: box.top + box.height / 2 - frame.top };
  };
  const later = (delay, fn) => (motionAllowed() ? window.setTimeout(fn, delay) : fn());

  const TAIL_LIMIT_DEG = 115;
  const TAIL_POINT_MS = 520;
  const BLINK_MS = 200;
  const IDLE_MS = 20000;
  const WAKE_BLINK_DELAY_MS = 260;
  const ZZZ = [['z', 118, 176, 44], ['z', 80, 122, 56], ['Z', 36, 60, 72]];
  const createCat = (svg) => {
    const root = svg.closest('.mascot');
    const mirror = root.classList.contains('is-mirrored');
    const whole = svg.querySelector('.m-mascot');
    const tail = svg.querySelector('.m-tail');
    const eye = svg.querySelector('.m-eye-open');
    const glow = svg.querySelector('.m-stinger-glow');
    const frame = svg.viewBox.baseVal;
    const tip = { x: Number(glow.getAttribute('cx')), y: Number(glow.getAttribute('cy')) };
    const zzz = svgEl('g', { class: 'm-zzz', 'aria-hidden': 'true' });
    ZZZ.forEach(([letter, x, y, size], index) => {
      const text = svgEl('text', { x, y, 'font-size': size });
      text.style.setProperty('--z', String(index));
      text.textContent = letter;
      zzz.append(text);
    });
    svg.append(zzz);
    let aim = null;
    const toScreen = (point) => {
      const rect = svg.getBoundingClientRect();
      const scale = rect.width / frame.width;
      const offset = (point.x - frame.x) * scale;
      return { x: mirror ? rect.right - offset : rect.left + offset, y: rect.top + (point.y - frame.y) * scale };
    };
    const pivot = () => {
      const [x, y] = getComputedStyle(tail).transformOrigin.split(' ').map(parseFloat);
      return { x, y };
    };
    const currentRotate = () => {
      const value = parseFloat(getComputedStyle(tail).rotate);
      return Number.isFinite(value) ? value : 0;
    };
    const turnTail = (degrees) => {
      const next = tail.animate([{ rotate: `${currentRotate()}deg` }, { rotate: `${degrees}deg` }], { duration: motionAllowed() ? TAIL_POINT_MS : 0, easing: OVERSHOOT, fill: 'forwards' });
      aim?.cancel();
      aim = next;
    };
    const angleTo = (target) => {
      const origin = toScreen(pivot());
      const rest = toScreen(tip);
      const box = target.getBoundingClientRect();
      const goal = { x: box.left + box.width / 2, y: box.top + box.height / 2 };
      const delta = (Math.atan2(goal.y - origin.y, goal.x - origin.x) - Math.atan2(rest.y - origin.y, rest.x - origin.x)) * 180 / Math.PI;
      const wrapped = ((delta % 360) + 540) % 360 - 180;
      const clamped = Math.max(-TAIL_LIMIT_DEG, Math.min(TAIL_LIMIT_DEG, wrapped));
      return mirror ? -clamped : clamped;
    };
    const blink = () => {
      if (root.classList.contains('is-asleep')) return;
      eye.animate([{ scale: '1 1' }, { scale: '1 0.1', offset: 0.45 }, { scale: '1 0.1', offset: 0.55 }, { scale: '1 1' }], { duration: BLINK_MS, easing: 'ease-in-out' });
    };
    const cat = {
      svg,
      root,
      whole,
      tail,
      glow,
      blink,
      sway: (angles, duration) => tail.animate(angles.map((angle) => ({ rotate: `${angle}deg`, easing: 'ease-in-out' })), { duration, composite: 'add' }),
      point: (target) => turnTail(angleTo(target)),
      rest: () => {
        if (aim) turnTail(0);
      },
      sleep: () => root.classList.add('is-asleep'),
      wake: () => {
        if (!root.classList.contains('is-asleep')) return;
        root.classList.remove('is-asleep');
        window.setTimeout(blink, WAKE_BLINK_DELAY_MS);
      },
    };
    onVisible(root, (visible) => root.classList.toggle('is-seen', visible), { threshold: 0.2 });
    return cat;
  };
  const idle = (() => {
    const cats = new Set();
    let last = performance.now();
    let asleep = false;
    const check = () => {
      const quiet = performance.now() - last;
      if (quiet < IDLE_MS) {
        window.setTimeout(check, IDLE_MS - quiet);
        return;
      }
      asleep = true;
      cats.forEach((cat) => cat.sleep());
    };
    const stir = () => {
      last = performance.now();
      if (!asleep) return;
      asleep = false;
      cats.forEach((cat) => cat.wake());
      window.setTimeout(check, IDLE_MS);
    };
    return (cat) => {
      if (!motionAllowed()) return;
      cats.add(cat);
      if (cats.size > 1) return;
      ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach((type) => window.addEventListener(type, stir, { passive: true, capture: true }));
      window.setTimeout(check, IDLE_MS);
    };
  })();

  const footerMascot = document.querySelector('[data-mascot]');
  const footerCat = footerMascot ? createCat(footerMascot.querySelector('svg')) : null;
  if (footerCat) idle(footerCat);

  const ask = document.querySelector('[data-ask]');
  if (ask) {
    const BEAM_MS = 620;
    const BEAM_STAGGER_MS = 140;
    const BEAM_DELAY_MS = 120;
    const SETTLE_MS = 900;
    const LAB_HITS = 3;
    const MAX_STARS = 120;
    const STAR_FIELD = { cx: 392, cy: 250, r: 186 };
    const STAR_RADIUS = [1.8, 3.8];
    const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
    const SNIPPET_LEAD = 8;
    const SNIPPET_TAIL = 64;
    const ANSWERS = {
      leave: {
        keys: ['特休', '請假', '休假', '假期', '簽核'],
        stars: ['antares', 5, 7],
        parts: ['特休要在假期開始前三個工作天，經人資系統提出申請', 1, '；送出後由直屬主管簽核', 2, '，主管三個工作天內沒簽，會自動轉給上一層主管', 3, '。'],
        sources: ['員工請假辦法.pdf，段落 4', '員工請假辦法.pdf，段落 7', '簽核作業要點.docx，段落 2'],
      },
      password: {
        keys: ['密碼', '特權', '多因子', '鎖定', '登入'],
        stars: [2, 3],
        parts: ['特權帳號的密碼每 60 天要換一次，並且要啟用多因子驗證', 1, '；同一帳號連續登入失敗 5 次，會鎖定 30 分鐘', 2, '。'],
        sources: ['資訊安全管理政策，段落 15', '帳號權限管理辦法，段落 3'],
      },
      parking: {
        keys: ['停車', '車位'],
        stars: [],
        parts: ['知識庫裡沒有講停車位申請的段落；最接近的「停車費報支」重排機率低於門檻。AskMiao 會照實說查不到，不拿無關段落硬答。'],
        sources: [],
      },
    };
    const form = ask;
    const input = ask.querySelector('[data-ask-input]');
    const answer = ask.querySelector('[data-ask-answer]');
    const beams = ask.querySelector('[data-ask-beams]');
    const sky = ask.querySelector('[data-ask-sky]');
    const chart = ask.querySelector('[data-ask-chart]');
    const hits = sky.querySelector('[data-ask-hits]');
    const dots = Array.from(sky.querySelectorAll('.hero__dots circle'));
    const antares = sky.querySelector('[data-star="antares"]');
    const examples = Array.from(ask.querySelectorAll('[data-ask-example]'));
    const mine = {
      root: ask.querySelector('[data-mine]'),
      toggle: ask.querySelector('[data-mine-toggle]'),
      panel: ask.querySelector('[data-mine-panel]'),
      text: ask.querySelector('[data-mine-text]'),
      cut: ask.querySelector('[data-mine-cut]'),
      reset: ask.querySelector('[data-mine-reset]'),
      rule: ask.querySelector('[data-mine-rule]'),
      chunks: ask.querySelector('[data-mine-chunks]'),
      count: ask.querySelector('[data-mine-count]'),
      list: ask.querySelector('[data-mine-list]'),
      stars: sky.querySelector('[data-mine-stars]'),
    };
    const settings = (() => {
      const text = ask.querySelector('[data-rag-settings]')?.textContent.trim();
      if (!text || !lab) return null;
      try {
        return JSON.parse(text);
      } catch {
        return null;
      }
    })();
    const placeholder = input.placeholder;
    const heroCat = (() => {
      if (!footerMascot) return null;
      const svg = footerMascot.querySelector('svg').cloneNode(true);
      svg.querySelector('.m-zzz')?.remove();
      svg.querySelectorAll('[id]').forEach((node) => {
        const id = `${node.id}-ask`;
        svg.querySelectorAll(`[fill="url(#${node.id})"]`).forEach((user) => user.setAttribute('fill', `url(#${id})`));
        node.id = id;
      });
      const holder = document.createElement('span');
      holder.className = 'mascot ask__cat';
      holder.setAttribute('aria-hidden', 'true');
      holder.append(svg);
      chart.append(holder);
      const cat = createCat(svg);
      idle(cat);
      return cat;
    })();
    const starOf = (key) => (key === 'antares' ? antares : dots[key]);
    let links = [];
    let queued = false;
    let labState = null;
    const match = (text) => Object.entries(ANSWERS).find(([, entry]) => entry.keys.some((key) => text.includes(key)));
    const el = (tag, className, text) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const cite = (number) => {
      const badge = el('span', 'ask__cite');
      badge.dataset.n = String(number);
      badge.append(el('span', 'sr-only', '出處 '), String(number));
      return badge;
    };
    const layout = () => {
      const frame = beams.getBoundingClientRect();
      links.forEach(({ star, badge, beam, tag }) => {
        const from = centerIn(star, frame);
        const to = centerIn(badge, frame);
        beam.style.setProperty('--x', `${from.x}px`);
        beam.style.setProperty('--y', `${from.y}px`);
        beam.style.setProperty('--len', `${Math.hypot(to.x - from.x, to.y - from.y)}px`);
        beam.style.setProperty('--angle', `${Math.atan2(to.y - from.y, to.x - from.x)}rad`);
        tag.style.setProperty('--x', `${from.x + 16}px`);
        tag.style.setProperty('--y', `${from.y - 16}px`);
      });
    };
    const relayout = () => {
      if (!links.length || queued) return;
      queued = true;
      ticker.add(() => {
        queued = false;
        layout();
        return false;
      });
    };
    let settleUntil = 0;
    const settle = (duration) => {
      const first = settleUntil === 0;
      settleUntil = Math.max(settleUntil, performance.now() + duration);
      if (!first) return;
      ticker.add((now) => {
        layout();
        if (now < settleUntil) return true;
        settleUntil = 0;
        return false;
      });
    };
    const clearHits = () => {
      hits.replaceChildren();
      beams.replaceChildren();
      links = [];
    };
    let landing = 0;
    const present = (nodes, stars, badges) => {
      clearHits();
      window.clearTimeout(landing);
      answer.replaceChildren(...nodes);
      ask.classList.add('has-answer');
      ask.classList.toggle('is-asking', stars.length > 0);
      ask.classList.toggle('is-void', stars.length === 0);
      const animate = motionAllowed();
      stars.forEach((star, index) => {
        const cx = star.getAttribute('cx');
        const cy = star.getAttribute('cy');
        const halo = svgEl('circle', { class: 'hero__hit-halo', cx, cy, r: 16 });
        const core = svgEl('circle', { cx, cy, r: 5 });
        hits.append(halo, core);
        const beam = el('span', 'sky-beam');
        beam.append(el('span'));
        const tag = el('span', 'sky-tag', String(index + 1));
        beams.append(beam, tag);
        links.push({ star, badge: badges[index], beam, tag });
        if (!animate) return;
        const delay = BEAM_DELAY_MS + index * BEAM_STAGGER_MS;
        halo.animate([{ opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1 }], { duration: BEAM_MS, delay, easing: EASE_OUT, fill: 'backwards' });
        core.animate([{ opacity: 0, scale: 0.2 }, { opacity: 1, scale: 1.6, offset: 0.6 }, { opacity: 1, scale: 1 }], { duration: BEAM_MS, delay, easing: EASE_OUT, fill: 'backwards' });
        beam.firstElementChild.animate([{ scale: '0 1' }, { scale: '1 1' }], { duration: BEAM_MS, delay: delay + BEAM_MS / 3, easing: EASE_OUT, fill: 'backwards' });
        tag.animate([{ opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1 }], { duration: BEAM_MS / 2, delay, easing: OVERSHOOT, fill: 'backwards' });
      });
      settle(SETTLE_MS);
      if (!stars.length) {
        heroCat?.rest();
        sound.play('void');
        return;
      }
      landing = later(BEAM_DELAY_MS, () => {
        heroCat?.point(stars[0]);
        sound.play('motif');
      });
    };
    const scripted = (text, key) => {
      const entry = key ? ANSWERS[key] : null;
      examples.forEach((button) => button.classList.toggle('is-on', button.dataset.askExample === key));
      const reply = el('p', 'ask__reply');
      reply.append(el('span', 'ask__tag', '示意'));
      if (entry) entry.parts.forEach((part) => reply.append(typeof part === 'number' ? cite(part) : part));
      else reply.append(`知識庫裡找不到和「${text}」有關的段落，AskMiao 會照實說查不到。換個說法，或試試上面的範例問題。`);
      const stars = entry ? entry.stars.map(starOf) : [];
      reply.classList.toggle('is-none', !stars.length);
      const nodes = [reply];
      if (entry && entry.sources.length) {
        const list = el('ol', 'ask__srcs');
        list.setAttribute('aria-label', '參考來源');
        entry.sources.forEach((source, index) => {
          const item = el('li');
          item.append(el('b', '', String(index + 1)), source);
          list.append(item);
        });
        nodes.push(list);
      }
      present(nodes, stars, stars.map((_, index) => reply.querySelector(`.ask__cite[data-n="${index + 1}"]`)));
    };
    const snippet = (text, terms) => {
      const chars = Array.from(text);
      const marked = new Array(chars.length).fill(false);
      let first = -1;
      terms.forEach((term) => {
        const size = Array.from(term).length;
        for (let index = 0; index + size <= chars.length; index += 1) {
          if (chars.slice(index, index + size).join('') !== term) continue;
          for (let offset = 0; offset < size; offset += 1) marked[index + offset] = true;
          if (first < 0 || index < first) first = index;
        }
      });
      const start = Math.max(0, first - SNIPPET_LEAD);
      const end = Math.min(chars.length, first + SNIPPET_TAIL);
      const out = el('p', 'ask__snippet');
      if (start > 0) out.append('…');
      let run = '';
      let runMarked = false;
      const flush = () => {
        if (!run) return;
        out.append(runMarked ? el('mark', '', run) : run);
        run = '';
      };
      for (let index = start; index < end; index += 1) {
        if (marked[index] !== runMarked) {
          flush();
          runMarked = marked[index];
        }
        run += chars[index];
      }
      flush();
      if (end < chars.length) out.append('…');
      return out;
    };
    const labAnswer = () => {
      const { hits: found } = labState.index.search(input.value);
      const top = found.slice(0, LAB_HITS);
      const reply = el('p', 'ask__reply ask__reply--lab');
      reply.append(el('span', 'ask__tag ask__tag--live', '瀏覽器裡實際計算'));
      reply.append(top.length
        ? `關鍵字那一軌選中 ${found.length} 段（共 ${labState.chunks.length} 段），分數最高的 ${top.length} 段：`
        : `關鍵字那一軌一段都沒選中（共 ${labState.chunks.length} 段）。用字不同但意思相近的段落，正式系統會由向量那一軌找回來。`);
      reply.classList.toggle('is-none', !top.length);
      const list = el('ol', 'ask__labhits');
      list.setAttribute('aria-label', '關鍵字檢索結果');
      const badges = top.map((hit, rank) => {
        const item = el('li');
        const badge = cite(rank + 1);
        const head = el('p', 'ask__labhead');
        head.append(badge, el('b', '', `第 ${hit.index + 1} 段`), el('span', 'mono', `BM25 ${hit.score.toFixed(2)}`));
        item.append(head, snippet(labState.chunks[hit.index], hit.terms));
        list.append(item);
        return badge;
      });
      const note = el('p', 'ask__labnote');
      note.append(el('b', '', '這裡只示範關鍵字那一軌，正式系統還有向量檢索與重排。'), '分數照正式系統 BM25 的漢字單字、雙字兩個欄位計算；jieba 斷詞那一欄要載入詞典，沒有放進瀏覽器，所以英文與數字在這裡比對不到。');
      const matched = new Set(found.map((hit) => hit.index));
      labState.stars.forEach((star, index) => star.classList.toggle('is-match', matched.has(index)));
      present(top.length ? [reply, list, note] : [reply, note], top.map((hit) => labState.stars[hit.index]), badges);
    };
    const overlapOf = (previous, current) => {
      const limit = Math.min(previous.length, current.length);
      for (let size = limit; size > 0; size -= 1) {
        if (previous.endsWith(current.slice(0, size))) return size;
      }
      return 0;
    };
    const showRule = () => {
      if (!settings) {
        mine.rule.textContent = '這份頁面沒有帶入後端的切段設定（部署時才會從後端寫進來），所以暫時不能切。';
        mine.cut.disabled = true;
        return;
      }
      mine.rule.textContent = `切法和正式系統相同：遞迴切段，依序找段落、換行、句號、逗號、空白切開，每段最多 ${settings.chunkSize} 字，相鄰兩段重疊 ${settings.chunkOverlap} 字。最多顯示 ${MAX_STARS} 顆星。`;
    };
    const openPanel = () => {
      mine.panel.hidden = false;
      mine.toggle.setAttribute('aria-expanded', 'true');
    };
    const cutText = (raw) => {
      if (!settings) return;
      const text = raw.slice(0, MAX_STARS * settings.chunkSize);
      const all = lab.createSplitter(settings)(text);
      if (!all.length) {
        mine.rule.textContent = '沒有可以切的文字，貼一段內容再試一次。';
        return;
      }
      const chunks = all.slice(0, MAX_STARS);
      const animate = motionAllowed();
      const stars = chunks.map((chunk, index) => {
        const angle = index * GOLDEN_ANGLE;
        const radius = STAR_FIELD.r * Math.sqrt((index + 0.5) / chunks.length);
        const size = Math.min(1, lab.length(chunk) / settings.chunkSize);
        const star = svgEl('circle', {
          class: 'ask__mine-star',
          cx: (STAR_FIELD.cx + radius * Math.cos(angle)).toFixed(1),
          cy: (STAR_FIELD.cy + radius * Math.sin(angle)).toFixed(1),
          r: (STAR_RADIUS[0] + (STAR_RADIUS[1] - STAR_RADIUS[0]) * size).toFixed(2),
        });
        if (animate) star.style.setProperty('--i', String(index));
        return star;
      });
      mine.stars.replaceChildren(...stars);
      labState = { chunks, stars, index: lab.createKeywordIndex(chunks, settings) };
      const items = chunks.map((chunk, index) => {
        const item = el('li');
        const overlap = index ? overlapOf(chunks[index - 1], chunk) : 0;
        item.append(el('b', '', `第 ${index + 1} 段，${lab.length(chunk)} 字`));
        const body = el('p');
        if (overlap) {
          body.append(el('span', 'sr-only', '和上一段重疊的部分：'), el('mark', '', chunk.slice(0, overlap)), el('span', 'sr-only', '。新內容：'));
        }
        body.append(chunk.slice(overlap));
        item.append(body);
        return item;
      });
      mine.list.replaceChildren(...items);
      mine.count.textContent = all.length > MAX_STARS ? `切成 ${all.length} 段，這裡取前 ${MAX_STARS} 段` : `切成 ${chunks.length} 段，看每段的內容`;
      mine.chunks.hidden = false;
      mine.reset.hidden = false;
      ask.classList.add('is-mine');
      examples.forEach((button) => button.classList.remove('is-on'));
      input.value = '';
      input.placeholder = '問一句和你的文字有關的話';
      clearHits();
      heroCat?.rest();
      ask.classList.remove('is-asking', 'is-void');
      const reply = el('p', 'ask__reply ask__reply--lab');
      reply.append(el('span', 'ask__tag ask__tag--live', '瀏覽器裡實際計算'), `切成 ${chunks.length} 段，每顆星是一段。現在問一句話，看關鍵字那一軌選中哪幾顆星。`);
      answer.replaceChildren(reply);
      ask.classList.add('has-answer');
      showRule();
      input.focus({ preventScroll: true });
    };
    const leaveLab = () => {
      labState = null;
      mine.stars.replaceChildren();
      mine.list.replaceChildren();
      mine.chunks.hidden = true;
      mine.reset.hidden = true;
      ask.classList.remove('is-mine', 'has-answer', 'is-asking', 'is-void');
      input.placeholder = placeholder;
      answer.replaceChildren();
      clearHits();
      heroCat?.rest();
      mine.text.focus();
    };
    showRule();
    mine.toggle.addEventListener('click', () => {
      const open = mine.panel.hidden;
      mine.panel.hidden = !open;
      mine.toggle.setAttribute('aria-expanded', String(open));
      if (open) mine.text.focus();
    });
    mine.cut.addEventListener('click', () => {
      if (!mine.text.value.trim()) {
        mine.text.focus();
        return;
      }
      cutText(mine.text.value);
    });
    mine.reset.addEventListener('click', leaveLab);
    const DROP_TYPES = ['text/plain', 'Files'];
    const TEXT_FILE = /\.(txt|md|markdown|csv)$/i;
    const droppable = (event) => Boolean(settings) && Array.from(event.dataTransfer?.types ?? []).some((type) => DROP_TYPES.includes(type));
    ask.addEventListener('dragover', (event) => {
      if (!droppable(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      ask.classList.add('is-dropping');
    });
    ask.addEventListener('dragleave', (event) => {
      if (!ask.contains(event.relatedTarget)) ask.classList.remove('is-dropping');
    });
    ask.addEventListener('drop', async (event) => {
      if (!droppable(event)) return;
      event.preventDefault();
      ask.classList.remove('is-dropping');
      const file = Array.from(event.dataTransfer.files).find((item) => item.type.startsWith('text/') || TEXT_FILE.test(item.name));
      const text = file ? await file.text() : event.dataTransfer.getData('text/plain');
      if (!text.trim()) return;
      openPanel();
      mine.text.value = text;
      cutText(text);
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) {
        input.focus();
        return;
      }
      if (labState) {
        labAnswer();
        return;
      }
      const found = match(text);
      scripted(text, found ? found[0] : null);
    });
    examples.forEach((button) => button.addEventListener('click', () => {
      input.value = button.textContent;
      scripted(button.textContent, button.dataset.askExample);
    }));
    window.addEventListener('scroll', relayout, { passive: true });
    new ResizeObserver(relayout).observe(ask.closest('.hero__inner'));
  }

  const hero = document.querySelector('.hero');
  const heroLayers = hero ? Array.from(hero.querySelectorAll('.hero__stars--far, .hero__stars--near')) : [];
  if (heroLayers.length && motionAllowed()) {
    const GLINT_GAIN = { far: 2.2, near: 1.6 };
    const GLINT_ATTACK = 0.35;
    const GLINT_RELEASE = 0.08;
    const GLINT_FLOOR = 0.002;
    const glint = heroLayers.map(() => 0);
    let heroSeen = false;
    let running = false;
    const step = () => {
      const level = document.hidden ? null : sound.musicLevel();
      let quiet = true;
      heroLayers.forEach((layer, index) => {
        const far = layer.classList.contains('hero__stars--far');
        const target = level ? Math.min(1, (far ? level.high * GLINT_GAIN.far : level.low * GLINT_GAIN.near)) : 0;
        const rate = target > glint[index] ? GLINT_ATTACK : GLINT_RELEASE;
        glint[index] += (target - glint[index]) * rate;
        if (glint[index] > GLINT_FLOOR || target > 0) quiet = false;
        layer.style.setProperty('--glint', glint[index].toFixed(3));
      });
      if (heroSeen && !(quiet && !level)) return true;
      heroLayers.forEach((layer, index) => {
        glint[index] = 0;
        layer.style.removeProperty('--glint');
      });
      running = false;
      return false;
    };
    const start = () => {
      if (running || !heroSeen || !sound.musicLevel()) return;
      running = true;
      ticker.add(step);
    };
    onVisible(hero, (visible) => {
      heroSeen = visible;
      start();
    });
    document.addEventListener('askmiao:music', start);
  }

  const evals = document.querySelector('[data-evals]');
  if (evals) {
    onVisible(evals, (visible) => {
      if (visible) evals.classList.add('is-played');
    }, { threshold: 0.3 });
  }

  const branch = document.querySelector('[data-branch]');
  if (branch) {
    onVisible(branch, (visible) => {
      if (visible) branch.classList.add('is-played');
    }, { threshold: 0.5 });
  }

  const stops = Array.from(document.querySelectorAll('[data-qstop]'));
  if (stops.length > 1) {
    const QSTAR_BREAKPOINT = window.matchMedia('(min-width: 1100px)');
    const READ_LINE = 0.52;
    const HOP_MIN_PX = 90;
    const FADE_PX = 160;
    const LEFT_GAP_PX = 16;
    const TOP_GAP_PX = 14;
    const pageOffset = (element) => {
      let x = 0;
      let y = 0;
      for (let node = element; node; node = node.offsetParent) {
        x += node.offsetLeft;
        y += node.offsetTop;
      }
      return { x, y, width: element.offsetWidth, height: element.offsetHeight };
    };
    const anchorOf = (stop) => {
      const kind = stop.dataset.qstop;
      const target = kind === 'first' ? stop.querySelector('li') : stop;
      if (!target) return null;
      const box = pageOffset(target);
      if (kind === 'top') return { x: box.x + box.width / 2, y: box.y - TOP_GAP_PX };
      return { x: box.x - LEFT_GAP_PX, y: box.y + box.height / 2 };
    };
    const marks = stops.map((stop) => {
      const mark = document.createElement('span');
      mark.className = 'qstop';
      mark.dataset.kind = stop.dataset.qstop;
      mark.setAttribute('aria-hidden', 'true');
      stop.classList.add('has-qstop');
      stop.append(mark);
      return mark;
    });
    const placeFirst = () => stops.forEach((stop, index) => {
      if (stop.dataset.qstop !== 'first') return;
      const first = stop.querySelector('li');
      marks[index].style.top = first ? `${pageOffset(first).y - pageOffset(stop).y + first.offsetHeight / 2}px` : '';
    });
    const star = document.createElement('span');
    star.className = 'qstar';
    star.setAttribute('aria-hidden', 'true');
    let points = [];
    let anchors = [];
    let active = false;
    let queued = false;
    let landed = false;
    const spline = (p0, p1, p2, p3, t) => {
      const t2 = t * t;
      const t3 = t2 * t;
      const axis = (a, b, c, d) => 0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      return { x: axis(p0.x, p1.x, p2.x, p3.x), y: axis(p0.y, p1.y, p2.y, p3.y) };
    };
    const measure = () => {
      placeFirst();
      points = stops.map(anchorOf);
      if (points.some((point) => !point)) {
        points = [];
        return;
      }
      const line = window.innerHeight * READ_LINE;
      const natural = points.map((point) => point.y - line);
      anchors = [];
      for (let first = 0; first < natural.length;) {
        let last = first;
        while (last + 1 < natural.length && natural[last + 1] - natural[last] < HOP_MIN_PX) last += 1;
        const mean = natural.slice(first, last + 1).reduce((sum, value) => sum + value, 0) / (last - first + 1);
        const base = mean - ((last - first) * HOP_MIN_PX) / 2;
        for (let index = first; index <= last; index += 1) {
          const spread = base + (index - first) * HOP_MIN_PX;
          anchors.push(index ? Math.max(spread, anchors[index - 1] + HOP_MIN_PX) : spread);
        }
        first = last + 1;
      }
    };
    const render = () => {
      queued = false;
      if (!points.length) return;
      const scroll = window.scrollY;
      const last = points.length - 1;
      let segment = anchors.findIndex((anchor, index) => index < last && scroll < anchors[index + 1]);
      if (segment < 0) segment = last;
      const local = segment === last ? 0 : Math.max(0, Math.min(1, (scroll - anchors[segment]) / (anchors[segment + 1] - anchors[segment])));
      const at = (index) => points[Math.max(0, Math.min(last, index))];
      const point = segment === last ? points[last] : spline(at(segment - 1), at(segment), at(segment + 1), at(segment + 2), local);
      const fade = Math.max(0, Math.min(1, 1 - (anchors[0] - scroll) / FADE_PX));
      star.style.translate = `${point.x.toFixed(1)}px ${point.y.toFixed(1)}px`;
      star.style.opacity = fade.toFixed(3);
      marks.forEach((mark, index) => mark.classList.toggle('is-reached', scroll >= anchors[index] - 1));
      const nowLanded = scroll >= anchors[last] - 1;
      if (nowLanded !== landed) {
        landed = nowLanded;
        star.classList.toggle('is-landed', landed);
        stops[last].classList.toggle('is-landed', landed);
      }
    };
    const queue = () => {
      if (!active || queued) return;
      queued = true;
      ticker.add(() => {
        render();
        return false;
      });
    };
    const moving = () => QSTAR_BREAKPOINT.matches && motionAllowed();
    const mode = () => {
      placeFirst();
      const move = moving();
      document.documentElement.classList.toggle('qstar-static', !move);
      if (move && !star.isConnected) document.body.append(star);
      if (!move) star.remove();
      if (move) {
        measure();
        queue();
      }
    };
    const sections = Array.from(new Set(stops.map((stop) => stop.closest('section'))));
    const seen = new Set();
    sections.forEach((section) => onVisible(section, (visible) => {
      if (visible) seen.add(section);
      else seen.delete(section);
      active = seen.size > 0 && moving();
      if (active) {
        measure();
        queue();
      }
    }, { rootMargin: '50% 0px' }));
    window.addEventListener('scroll', queue, { passive: true });
    const remeasure = () => {
      if (!moving()) {
        placeFirst();
        return;
      }
      measure();
      queue();
    };
    new ResizeObserver(remeasure).observe(document.body);
    document.fonts?.ready.then(remeasure);
    QSTAR_BREAKPOINT.addEventListener('change', mode);
    mode();
  }

  const gates = document.querySelector('[data-gates]');
  if (gates) {
    const STEP_MS = 340;
    const HOLD_MS = 380;
    const BOUNCE_MS = 460;
    const FADE_MS = 240;
    const GAP_MS = 320;
    const stage = gates.querySelector('[data-gates-stage]');
    const token = gates.querySelector('[data-gates-token]');
    const start = gates.querySelector('[data-gates-start]');
    const goal = gates.querySelector('[data-gates-goal]');
    const posts = Array.from(gates.querySelectorAll('[data-gate]'));
    const cases = Array.from(gates.querySelectorAll('[data-gates-cases] > li'));
    const toggle = gates.querySelector('[data-gates-toggle]');
    const toggleLabel = gates.querySelector('[data-gates-toggle-label]');
    const LABELS = { idle: '播放示範', again: '重新播放', pause: '暫停示範', resume: '繼續示範' };
    let run = null;
    let current = null;
    let held = false;
    let offscreen = false;
    let played = false;
    const label = (key) => {
      toggleLabel.textContent = LABELS[key];
    };
    const LANE_INSET = 10;
    const stacked = window.matchMedia('(max-width: 819px)');
    const place = (point) => `${point.x - token.offsetWidth / 2}px ${point.y - token.offsetHeight / 2}px`;
    const spot = (element) => {
      const frame = stage.getBoundingClientRect();
      const point = centerIn(element, frame);
      if (stacked.matches && posts.includes(element)) point.x = element.getBoundingClientRect().right - frame.left - token.offsetWidth / 2 - LANE_INSET;
      return point;
    };
    const step = (session, keyframes, duration, easing) => {
      if (session.cancelled) return Promise.reject(new Error('cancelled'));
      current = token.animate(keyframes, { duration, easing, fill: 'forwards' });
      if (held || offscreen) current.pause();
      return current.finished;
    };
    const clear = () => {
      posts.forEach((post) => post.classList.remove('is-hit', 'is-pass', 'is-wrap'));
      token.classList.remove('is-wrapped');
    };
    const playCase = async (session, item) => {
      cases.forEach((entry) => entry.classList.toggle('is-current', entry === item));
      clear();
      token.textContent = item.querySelector('b').textContent;
      const kind = item.dataset.kind;
      const stop = Number(item.dataset.stop);
      let here = spot(start);
      await step(session, [{ translate: place(here), opacity: 0 }, { translate: place(here), opacity: 1 }], FADE_MS, EASE_OUT);
      const route = posts.slice(0, Math.min(stop + 1, posts.length));
      for (let index = 0; index < route.length; index += 1) {
        const next = spot(route[index]);
        await step(session, [{ translate: place(here), opacity: 1 }, { translate: place(next), opacity: 1 }], STEP_MS, EASE_IN_OUT);
        here = next;
        if (kind === 'block' && index === stop) {
          route[index].classList.add('is-hit');
          if (session.audible) sound.play('block');
          const back = spot(index ? route[index - 1] : start);
          const retreat = { x: here.x + (back.x - here.x) * 0.45, y: here.y + (back.y - here.y) * 0.45 };
          await step(session, [{ translate: place(here), opacity: 1 }, { translate: place(here), opacity: 1 }], HOLD_MS, 'linear');
          await step(session, [{ translate: place(here), opacity: 1 }, { translate: place(retreat), opacity: 0 }], BOUNCE_MS, EASE_OUT);
          return;
        }
        if (kind === 'contain' && index === posts.length - 1) {
          route[index].classList.add('is-wrap');
          token.classList.add('is-wrapped');
        } else {
          route[index].classList.add('is-pass');
        }
      }
      const end = spot(goal);
      await step(session, [{ translate: place(here), opacity: 1 }, { translate: place(end), opacity: 1 }], STEP_MS, EASE_IN_OUT);
      if (session.audible) sound.play('allow');
      await step(session, [{ translate: place(end), opacity: 1 }, { translate: place(end), opacity: 0 }], HOLD_MS, 'linear');
    };
    const begin = async (audible) => {
      if (run) run.cancelled = true;
      current?.cancel();
      const session = { cancelled: false, audible };
      run = session;
      held = false;
      label('pause');
      try {
        for (const item of cases) {
          await playCase(session, item);
          await step(session, [{ opacity: 0 }, { opacity: 0 }], GAP_MS, 'linear');
        }
      } catch {
        return;
      }
      if (run !== session) return;
      run = null;
      cases.forEach((entry) => entry.classList.remove('is-current'));
      clear();
      label('again');
    };
    const resume = () => {
      if (current && current.playState === 'paused' && !held && !offscreen) current.play();
    };
    if (motionAllowed()) {
      toggle.hidden = false;
      toggle.addEventListener('click', () => {
        if (!run) {
          begin(true);
          return;
        }
        held = !held;
        label(held ? 'resume' : 'pause');
        if (held) current?.pause();
        else resume();
      });
      onVisible(gates, (visible) => {
        offscreen = !visible;
        if (!visible) {
          current?.pause();
          return;
        }
        if (!played) {
          played = true;
          begin(false);
          return;
        }
        resume();
      }, { threshold: 0.12 });
    }
  }

  const track = document.querySelector('[data-startrack]');
  if (track) {
    const radios = Array.from(track.querySelectorAll('input[name="release"]'));
    const infos = Array.from(track.querySelectorAll('.relinfo'));
    const viewport = track.querySelector('[data-startrack-viewport]');
    const select = (id) => infos.forEach((info) => info.classList.toggle('is-current', info.id === id));
    radios.forEach((radio) => {
      radio.addEventListener('change', () => select(radio.value));
      radio.addEventListener('focus', () => {
        const box = radio.parentElement.getBoundingClientRect();
        const frame = viewport.getBoundingClientRect();
        if (box.left < frame.left || box.right > frame.right) viewport.scrollBy({ left: box.left - frame.left - frame.width / 2, behavior: motionAllowed() ? 'smooth' : 'instant' });
      });
    });
    select((radios.find((radio) => radio.checked) ?? radios[radios.length - 1]).value);
    viewport.scrollLeft = viewport.scrollWidth;
  }

  const relay = document.querySelector('[data-relay]');
  if (relay && footerCat) {
    const FLIGHT_MS = 900;
    const CATCH_LEAD_MS = 80;
    const CATCH_MS = 520;
    const UNROLL_MS = 520;
    const LINES_AT = 0.6;
    const LINE_STAGGER_MS = 60;
    const LINE_MS = 280;
    const POINT_GAP_MS = 120;
    const MARK_GAP_MS = 300;
    const MARK_MS = 280;
    const CITE_MS = 520;
    const SPIN_DEG = 540;
    const ARC_PX = 70;
    const scrollBox = relay.querySelector('[data-relay-scroll]');
    const from = relay.querySelector('[data-relay-from]');
    const catButton = relay.querySelector('[data-relay-cat]');
    const scrollSvg = scrollBox.querySelector('svg');
    const paper = scrollSvg.querySelector('.relay__paper');
    const rollerTop = scrollSvg.querySelector('.relay__roller-top rect');
    const rollerBottom = scrollSvg.querySelector('.relay__roller-bottom');
    const entries = Array.from(scrollSvg.querySelectorAll('.relay__lines text'));
    const mark = scrollSvg.querySelector('.relay__mark');
    const citeMark = scrollSvg.querySelector('.relay__cite');
    const target = mark.querySelector('rect');
    const drop = Number(rollerBottom.querySelector('rect').getAttribute('y')) - Number(rollerTop.getAttribute('y')) - Number(rollerTop.getAttribute('height'));
    const frame = scrollSvg.viewBox.baseVal;
    scrollBox.style.transformOrigin = `50% ${((Number(rollerTop.getAttribute('height')) / frame.height) * 100).toFixed(2)}%`;
    const running = [];
    let session = 0;
    const keep = (animation) => {
      running.push(animation);
      return animation;
    };
    const rolled = () => {
      keep(paper.animate([{ scale: '1 0' }], { duration: 0, fill: 'forwards' }));
      keep(rollerBottom.animate([{ translate: `0 ${-drop}px` }], { duration: 0, fill: 'forwards' }));
      entries.forEach((line) => keep(line.animate([{ opacity: 0 }], { duration: 0, fill: 'forwards' })));
      keep(mark.animate([{ opacity: 0 }], { duration: 0, fill: 'forwards' }));
      keep(citeMark.animate([{ opacity: 0 }], { duration: 0, fill: 'forwards' }));
      keep(scrollBox.animate([{ opacity: 0 }], { duration: 0, fill: 'forwards' }));
    };
    const reset = () => {
      running.splice(0).forEach((animation) => animation.cancel());
    };
    const finale = (token) => {
      if (token !== session) return;
      footerCat.point(target);
      later(MARK_GAP_MS, () => {
        if (token !== session) return;
        keep(mark.animate([{ opacity: 0 }, { opacity: 1 }], { duration: MARK_MS, easing: EASE_OUT, fill: 'both' }));
        keep(citeMark.animate([{ opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1 }], { duration: CITE_MS, easing: OVERSHOOT, fill: 'both' }));
        sound.play('motif');
      });
    };
    const play = () => {
      session += 1;
      const token = session;
      reset();
      footerCat.rest();
      if (!motionAllowed()) {
        finale(token);
        return;
      }
      const start = from.getBoundingClientRect();
      const end = scrollBox.getBoundingClientRect();
      const origin = { x: end.left + end.width / 2, y: end.top + end.height * (Number(rollerTop.getAttribute('height')) / frame.height) };
      const dx = start.left + start.width / 2 - origin.x;
      const dy = start.top + start.height / 2 - origin.y;
      keep(scrollBox.animate([
        { translate: `${dx}px ${dy}px`, rotate: `${-SPIN_DEG}deg`, opacity: 0 },
        { opacity: 1, offset: 0.12 },
        { translate: `${dx * 0.4}px ${dy * 0.4 - ARC_PX}px`, offset: 0.5 },
        { translate: '0 0', rotate: '0deg', opacity: 1 },
      ], { duration: FLIGHT_MS, easing: FLING_IN, fill: 'both' }));
      keep(footerCat.whole.animate([{ scale: '1 1' }, { scale: '1.08 0.9', offset: 0.25 }, { scale: '1 1' }], { duration: CATCH_MS, delay: FLIGHT_MS - CATCH_LEAD_MS, easing: OVERSHOOT }));
      window.setTimeout(() => token === session && footerCat.blink(), FLIGHT_MS - CATCH_LEAD_MS);
      keep(paper.animate([{ scale: '1 0' }, { scale: '1 1' }], { duration: UNROLL_MS, delay: FLIGHT_MS, easing: EASE_OUT, fill: 'both' }));
      keep(rollerBottom.animate([{ translate: `0 ${-drop}px` }, { translate: '0 0' }], { duration: UNROLL_MS, delay: FLIGHT_MS, easing: EASE_OUT, fill: 'both' }));
      entries.forEach((line, index) => keep(line.animate([{ opacity: 0, translate: '0 4px' }, { opacity: 1, translate: '0 0' }], { duration: LINE_MS, delay: FLIGHT_MS + UNROLL_MS * LINES_AT + Math.floor(index / 2) * LINE_STAGGER_MS, easing: EASE_OUT, fill: 'both' })));
      keep(mark.animate([{ opacity: 0 }, { opacity: 0 }], { duration: 0, fill: 'forwards' }));
      keep(citeMark.animate([{ opacity: 0 }, { opacity: 0 }], { duration: 0, fill: 'forwards' }));
      window.setTimeout(() => finale(token), FLIGHT_MS + UNROLL_MS + POINT_GAP_MS);
    };
    if (motionAllowed()) {
      rolled();
      let played = false;
      onVisible(relay, (visible) => {
        if (!visible || played) return;
        played = true;
        play();
      }, { threshold: 0.6 });
    } else {
      onVisible(relay, (visible) => {
        if (visible) footerCat.point(target);
      }, { threshold: 0.6 });
    }
    catButton.addEventListener('click', play);
  }

  if (footerMascot && motionAllowed()) {
    const LOOK_RADIUS = 380;
    const FACE_SHIFT = 14;
    const LEAN_DEG = 3;
    const FOLLOW = 0.16;
    const BLINK_GAP_MS = 2600;
    const FLICK_GAP_MS = 4200;
    const { svg, whole, tail, glow, blink, sway } = footerCat;
    const facing = footerMascot.classList.contains('is-mirrored') ? -1 : 1;
    const face = svg.querySelector('.m-face');
    const bye = document.querySelector('[data-mascot-bye]');
    let entered = false;
    let near = false;
    let lastBlink = 0;
    let lastFlick = 0;
    let pointer = null;
    let following = false;
    const state = { x: 0, y: 0, lean: 0 };
    const enter = () => {
      entered = true;
      whole.animate([{ opacity: 0, translate: '0 44px', scale: 0.9 }, { opacity: 1, translate: '0 0', scale: 1 }], { duration: 720, easing: OVERSHOOT, fill: 'backwards' });
      tail.animate([{ rotate: '-28deg' }, { rotate: '7deg', offset: 0.55 }, { rotate: '-2deg', offset: 0.8 }, { rotate: '0deg' }], { duration: 1100, delay: 180, easing: EASE_OUT, fill: 'backwards', composite: 'add' });
      glow.animate([{ opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1.2, offset: 0.5 }, { opacity: 1, scale: 1 }], { duration: 1200, delay: 520, easing: EASE_OUT, fill: 'backwards' });
      window.setTimeout(blink, 1250);
    };
    const follow = () => {
      if (following) return;
      following = true;
      ticker.add(() => {
        let goal = { x: 0, y: 0, lean: 0 };
        if (pointer) {
          const box = svg.getBoundingClientRect();
          const dx = pointer.x - (box.left + box.width / 2);
          const dy = pointer.y - (box.top + box.height * 0.4);
          const distance = Math.hypot(dx, dy);
          const wasNear = near;
          near = distance < LOOK_RADIUS;
          if (near) {
            const pull = Math.min(1, distance / (box.width * 0.6)) * FACE_SHIFT;
            goal = { x: (dx / distance) * pull, y: (dy / distance) * pull * 0.7, lean: Math.max(-1, Math.min(1, dx / LOOK_RADIUS)) * LEAN_DEG };
            const now = performance.now();
            if (!wasNear && now - lastBlink > BLINK_GAP_MS) {
              lastBlink = now;
              blink();
            }
            if (!wasNear && now - lastFlick > FLICK_GAP_MS) {
              lastFlick = now;
              sway([0, -7, 5, 0], 700);
            }
          }
        }
        state.x += (goal.x - state.x) * FOLLOW;
        state.y += (goal.y - state.y) * FOLLOW;
        state.lean += (goal.lean - state.lean) * FOLLOW;
        face.style.translate = `${(state.x * facing).toFixed(2)}px ${state.y.toFixed(2)}px`;
        whole.style.rotate = `${(state.lean * facing).toFixed(3)}deg`;
        const settled = Math.abs(goal.x - state.x) < 0.05 && Math.abs(goal.y - state.y) < 0.05 && Math.abs(goal.lean - state.lean) < 0.01;
        if (settled && !pointer) following = false;
        return !(settled && !pointer);
      });
    };
    const watchPointer = (event) => {
      pointer = { x: event.clientX, y: event.clientY };
      follow();
    };
    const release = () => {
      pointer = null;
      near = false;
      follow();
    };
    onVisible(footerMascot, (visible) => {
      if (visible && !entered) enter();
      if (visible && finePointer.matches) {
        window.addEventListener('pointermove', watchPointer, { passive: true });
        document.documentElement.addEventListener('pointerleave', release);
        return;
      }
      window.removeEventListener('pointermove', watchPointer);
      document.documentElement.removeEventListener('pointerleave', release);
      release();
    }, { threshold: 0.2 });
    footerMascot.addEventListener('pointerdown', () => {
      blink();
      sway([0, -10, 8, -4, 0], 900);
    });
    if (bye) {
      let armed = true;
      onVisible(bye, (visible) => {
        if (!visible) {
          armed = true;
          return;
        }
        if (!armed || !entered) return;
        const box = svg.getBoundingClientRect();
        const navBottom = document.querySelector('[data-nav]')?.getBoundingClientRect().bottom ?? 0;
        if (box.top < navBottom || box.bottom > window.innerHeight) return;
        armed = false;
        sway([0, 16, -12, 14, -8, 5, 0], 1700);
        window.setTimeout(blink, 900);
      });
    }
  }
})();