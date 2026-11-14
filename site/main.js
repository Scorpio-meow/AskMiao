(() => {
  const root = document.documentElement;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const motionAllowed = () => !reduceMotion.matches;
  const pointerEffects = () => finePointer.matches && motionAllowed();
  let liveTransition = null;
  const runTransition = (update) => {
    const transition = document.startViewTransition(update);
    liveTransition = transition;
    transition.finished.finally(() => {
      if (liveTransition === transition) liveTransition = null;
    });
    return transition;
  };
  const ticker = (() => {
    const tasks = new Set();
    let handle = 0;
    const tick = (now) => {
      tasks.forEach((task) => {
        if (task(now) === false) tasks.delete(task);
      });
      handle = tasks.size ? requestAnimationFrame(tick) : 0;
    };
    return {
      add(task) {
        tasks.add(task);
        if (!handle) handle = requestAnimationFrame(tick);
        return () => tasks.delete(task);
      },
    };
  })();
  const tween = (duration, onFrame) => {
    const start = performance.now();
    return ticker.add((now) => {
      const progress = Math.min(1, (now - start) / duration);
      onFrame(progress);
      return progress < 1;
    });
  };
  const onVisible = (() => {
    const handlers = new Map();
    const observers = new Map();
    return (element, handler, options = {}) => {
      const key = `${options.rootMargin ?? '0px'}|${options.threshold ?? 0}`;
      if (!observers.has(key)) {
        observers.set(key, new IntersectionObserver((entries) => {
          entries.forEach((entry) => handlers.get(entry.target)?.forEach((fn) => fn(entry.isIntersecting, entry)));
        }, { rootMargin: options.rootMargin ?? '0px', threshold: options.threshold ?? 0 }));
      }
      if (!handlers.has(element)) handlers.set(element, new Set());
      handlers.get(element).add(handler);
      observers.get(key).observe(element);
    };
  })();
  const reorder = (container, nodes) => {
    const canMove = typeof container.moveBefore === 'function';
    nodes.forEach((node) => {
      if (canMove && node.parentNode === container) container.moveBefore(node, null);
      else container.append(node);
    });
  };
  root.addEventListener('click', (event) => {
    if (!liveTransition || event.target !== root) return;
    liveTransition.skipTransition();
    liveTransition = null;
    document.elementFromPoint(event.clientX, event.clientY)?.closest('a, button, label, summary, input')?.click();
  });
  const sound = (() => {
    const SFX_KEY = 'askmiao-site-sfx';
    const MUSIC_KEY = 'askmiao-site-music';
    const SFX_LEVEL = 0.55;
    const MUSIC_LEVEL = 0.2;
    const NOTE = { A3: 220, C4: 261.63, D4: 293.66, E4: 329.63, A4: 440, C5: 523.25, D5: 587.33, E5: 659.25, FS5: 739.99, G5: 783.99, A5: 880, C6: 1046.5, D6: 1174.66, E6: 1318.51 };
    const MOTIF = [NOTE.D5, NOTE.FS5, NOTE.A5];
    const MOTIF_STEP_S = 0.11;
    const button = document.querySelector('[data-sound-btn]');
    const panel = document.querySelector('[data-sound-panel]');
    const sfxSwitch = document.querySelector('[data-sound-sfx]');
    const musicSwitch = document.querySelector('[data-sound-music]');
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const silent = { play: () => { }, duck: () => { }, musicLevel: () => null };
    if (!button || !panel || !AudioContextClass) {
      if (button) button.hidden = true;
      return silent;
    }
    const readPref = (key) => {
      try {
        return localStorage.getItem(key) === 'on';
      } catch {
        return false;
      }
    };
    const writePref = (key, value) => {
      try {
        localStorage.setItem(key, value ? 'on' : 'off');
      } catch {
        return;
      }
    };
    let sfxOn = readPref(SFX_KEY);
    let musicOn = readPref(MUSIC_KEY);
    let musicState = musicOn ? 'armed' : 'off';
    let ducked = false;
    let ctx = null;
    let sfxBus = null;
    let musicBus = null;
    let musicBuffer = null;
    let musicLoop = null;
    const SILENCE_LEVEL = 10 ** (-60 / 20);
    const audibleRange = (buffer) => {
      const channels = Array.from({ length: buffer.numberOfChannels }, (_, index) => buffer.getChannelData(index));
      const audible = (index) => channels.some((data) => Math.abs(data[index]) >= SILENCE_LEVEL);
      let first = 0;
      while (first < buffer.length - 1 && !audible(first)) first += 1;
      let last = buffer.length - 1;
      while (last > first && !audible(last)) last -= 1;
      return { start: first / buffer.sampleRate, end: (last + 1) / buffer.sampleRate };
    };
    let musicSource = null;
    let musicLoad = null;
    let stopTimer = 0;
    let analyser = null;
    let spectrum = null;
    const ANALYSER_SIZE = 256;
    const ANALYSER_SMOOTHING = 0.7;
    const LOW_BAND_HZ = [40, 900];
    const HIGH_BAND_HZ = [2500, 9000];
    const bandLevel = ([from, to]) => {
      const binHz = ctx.sampleRate / ANALYSER_SIZE;
      const first = Math.max(0, Math.floor(from / binHz));
      const last = Math.min(spectrum.length - 1, Math.ceil(to / binHz));
      let sum = 0;
      for (let index = first; index <= last; index += 1) sum += spectrum[index];
      return sum / ((last - first + 1) * 255);
    };
    const ensure = () => {
      if (!ctx) {
        ctx = new AudioContextClass();
        const compressor = ctx.createDynamicsCompressor();
        compressor.threshold.value = -18;
        compressor.ratio.value = 4;
        compressor.connect(ctx.destination);
        sfxBus = ctx.createGain();
        sfxBus.gain.value = SFX_LEVEL;
        const reverb = ctx.createConvolver();
        const length = Math.floor(ctx.sampleRate * 1.6);
        const impulse = ctx.createBuffer(2, length, ctx.sampleRate);
        for (let channel = 0; channel < 2; channel += 1) {
          const data = impulse.getChannelData(channel);
          for (let index = 0; index < length; index += 1) data[index] = (Math.random() * 2 - 1) * (1 - index / length) ** 3;
        }
        reverb.buffer = impulse;
        const wet = ctx.createGain();
        wet.gain.value = 0.22;
        sfxBus.connect(compressor);
        sfxBus.connect(reverb).connect(wet).connect(compressor);
        musicBus = ctx.createGain();
        musicBus.gain.value = 0;
        musicBus.connect(ctx.destination);
        analyser = ctx.createAnalyser();
        analyser.fftSize = ANALYSER_SIZE;
        analyser.smoothingTimeConstant = ANALYSER_SMOOTHING;
        musicBus.connect(analyser);
        spectrum = new Uint8Array(analyser.frequencyBinCount);
      }
      if (ctx.state === 'suspended' && !document.hidden) ctx.resume();
      return ctx;
    };
    const envelope = (node, at, peak, attack, duration) => {
      node.gain.setValueAtTime(0.0001, at);
      node.gain.exponentialRampToValueAtTime(peak, at + attack);
      node.gain.exponentialRampToValueAtTime(0.0001, at + duration);
    };
    const blip = (frequency, at, duration, peak, type) => {
      const oscillator = ctx.createOscillator();
      const amp = ctx.createGain();
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(frequency, at);
      envelope(amp, at, peak, 0.006, duration);
      oscillator.connect(amp).connect(sfxBus);
      oscillator.start(at);
      oscillator.stop(at + duration + 0.05);
    };
    const bell = (frequency, at, duration, peak) => {
      const carrier = ctx.createOscillator();
      const modulator = ctx.createOscillator();
      const depth = ctx.createGain();
      const amp = ctx.createGain();
      carrier.frequency.setValueAtTime(frequency, at);
      modulator.frequency.setValueAtTime(frequency * 3.5, at);
      depth.gain.setValueAtTime(frequency * 1.2, at);
      depth.gain.exponentialRampToValueAtTime(frequency * 0.02, at + duration);
      modulator.connect(depth).connect(carrier.frequency);
      envelope(amp, at, peak, 0.004, duration);
      carrier.connect(amp).connect(sfxBus);
      carrier.start(at);
      modulator.start(at);
      carrier.stop(at + duration + 0.05);
      modulator.stop(at + duration + 0.05);
    };
    const thud = (from, to, at, duration, peak) => {
      const oscillator = ctx.createOscillator();
      const filter = ctx.createBiquadFilter();
      const amp = ctx.createGain();
      oscillator.type = 'triangle';
      oscillator.frequency.setValueAtTime(from, at);
      oscillator.frequency.exponentialRampToValueAtTime(to, at + duration);
      filter.type = 'lowpass';
      filter.frequency.value = 900;
      envelope(amp, at, peak, 0.008, duration);
      oscillator.connect(filter).connect(amp).connect(sfxBus);
      oscillator.start(at);
      oscillator.stop(at + duration + 0.05);
    };
    const CUES = {
      motif: (t) => MOTIF.forEach((frequency, index) => bell(frequency, t + index * MOTIF_STEP_S, index === MOTIF.length - 1 ? 1.4 : 0.7, 0.08)),
      on: (t) => { blip(NOTE.D5, t, 0.12, 0.14, 'triangle'); blip(NOTE.A5, t + 0.07, 0.2, 0.14, 'triangle'); },
      off: (t) => { blip(NOTE.A5, t, 0.12, 0.12, 'triangle'); blip(NOTE.D5, t + 0.07, 0.2, 0.12, 'triangle'); },
      cite: (t) => { bell(NOTE.E6, t, 0.8, 0.09); bell(NOTE.A5, t + 0.04, 0.6, 0.04); },
      approve: (t) => [NOTE.C5, NOTE.E5, NOTE.G5, NOTE.C6].forEach((frequency, index) => bell(frequency, t + index * 0.075, 0.9, 0.08)),
      deny: (t) => { thud(NOTE.E4, NOTE.C4, t, 0.22, 0.2); thud(NOTE.C4, NOTE.A3, t + 0.12, 0.3, 0.18); },
      block: (t) => { thud(NOTE.A3, 110, t, 0.28, 0.24); blip(NOTE.D4, t + 0.03, 0.18, 0.05, 'square'); },
      allow: (t) => { bell(NOTE.G5, t, 0.6, 0.08); bell(NOTE.D6, t + 0.09, 0.8, 0.08); },
      server: (t) => bell(NOTE.D5, t, 0.7, 0.08),
      more: (t) => blip(NOTE.E5, t, 0.14, 0.1, 'triangle'),
      fewer: (t) => blip(NOTE.C5, t, 0.14, 0.1, 'triangle'),
      copy: (t) => { blip(NOTE.E5, t, 0.1, 0.12, 'sine'); blip(NOTE.A5, t + 0.06, 0.18, 0.12, 'sine'); },
      remember: (t) => [NOTE.C5, NOTE.E5, NOTE.G5, NOTE.C6, NOTE.E6].forEach((frequency, index) => bell(frequency, t + index * 0.07, 0.9, 0.07)),
      void: (t) => { bell(NOTE.A4, t, 0.9, 0.05); bell(NOTE.E4, t + 0.14, 1.1, 0.04); },
    };
    const play = (name) => {
      if (!sfxOn || !CUES[name]) return;
      ensure();
      if (ctx.state === 'running') {
        CUES[name](ctx.currentTime + 0.01);
        return;
      }
      ctx.resume().then(() => CUES[name](ctx.currentTime + 0.01));
    };
    const reflect = () => {
      button.dataset.state = sfxOn || musicOn ? 'on' : 'off';
      button.dataset.music = musicState;
      const parts = [];
      if (sfxOn) parts.push('互動音效開啟');
      if (musicState === 'playing') parts.push('背景音樂播放中');
      if (musicState === 'armed') parts.push('背景音樂待播放，按下即播放');
      button.setAttribute('aria-label', `聲音設定：${parts.length ? parts.join('、') : '目前關閉'}`);
      sfxSwitch.checked = sfxOn;
      musicSwitch.checked = musicOn;
    };
    const loadMusic = () => {
      if (!musicLoad) {
        const source = new Audio().canPlayType('audio/webm; codecs="opus"') ? panel.dataset.musicWebm : panel.dataset.musicM4a;
        musicLoad = fetch(source)
          .then((response) => {
            if (!response.ok) throw new Error(String(response.status));
            return response.arrayBuffer();
          })
          .then((data) => ctx.decodeAudioData(data))
          .then((buffer) => {
            musicBuffer = buffer;
            musicLoop = audibleRange(buffer);
          });
      }
      return musicLoad;
    };
    const announce = () => document.dispatchEvent(new CustomEvent('askmiao:music'));
    const rampMusic = (level, seconds) => {
      const now = ctx.currentTime;
      musicBus.gain.cancelScheduledValues(now);
      musicBus.gain.setValueAtTime(musicBus.gain.value, now);
      musicBus.gain.linearRampToValueAtTime(level, now + seconds);
    };
    const startMusic = () => {
      ensure();
      musicState = 'playing';
      reflect();
      loadMusic().then(() => {
        if (musicState !== 'playing') return;
        window.clearTimeout(stopTimer);
        if (!musicSource) {
          musicSource = ctx.createBufferSource();
          musicSource.buffer = musicBuffer;
          musicSource.loop = true;
          musicSource.loopStart = musicLoop.start;
          musicSource.loopEnd = musicLoop.end;
          musicSource.connect(musicBus);
          musicSource.start(0, musicLoop.start);
        }
        rampMusic(ducked ? 0 : MUSIC_LEVEL, 2.5);
        announce();
      }).catch(() => {
        musicLoad = null;
        musicOn = false;
        musicState = 'off';
        reflect();
      });
    };
    const stopMusic = () => {
      musicState = 'off';
      reflect();
      if (!ctx || !musicSource) return;
      rampMusic(0, 0.8);
      window.clearTimeout(stopTimer);
      stopTimer = window.setTimeout(() => {
        if (musicState === 'playing' || !musicSource) return;
        musicSource.stop();
        musicSource = null;
      }, 900);
    };
    button.addEventListener('click', () => {
      if (musicState === 'armed') startMusic();
    });
    sfxSwitch.addEventListener('change', () => {
      if (!sfxSwitch.checked) play('off');
      sfxOn = sfxSwitch.checked;
      writePref(SFX_KEY, sfxOn);
      reflect();
      if (sfxOn) {
        ensure();
        play('motif');
      }
    });
    musicSwitch.addEventListener('change', () => {
      musicOn = musicSwitch.checked;
      writePref(MUSIC_KEY, musicOn);
      if (musicOn) startMusic();
      else stopMusic();
      play(musicOn ? 'on' : 'off');
    });
    ['pointerdown', 'keydown'].forEach((type) => document.addEventListener(type, () => {
      if (sfxOn) ensure();
    }, { capture: true, passive: true }));
    document.addEventListener('visibilitychange', () => {
      if (!ctx) return;
      if (document.hidden) {
        if (musicSource) rampMusic(0, 0.3);
        window.setTimeout(() => { if (document.hidden) ctx.suspend(); }, 400);
      } else if (sfxOn || musicState === 'playing') {
        ctx.resume().then(() => {
          if (musicState === 'playing' && musicSource) rampMusic(ducked ? 0 : MUSIC_LEVEL, 1.2);
          announce();
        });
      }
    });
    window.addEventListener('storage', (event) => {
      if (event.key === SFX_KEY) {
        sfxOn = readPref(SFX_KEY);
        reflect();
      }
      if (event.key === MUSIC_KEY && !readPref(MUSIC_KEY) && musicState !== 'off') {
        musicOn = false;
        stopMusic();
      }
    });
    reflect();
    return {
      play,
      musicLevel() {
        if (musicState !== 'playing' || !musicSource || ducked || !analyser || ctx.state !== 'running') return null;
        analyser.getByteFrequencyData(spectrum);
        return { low: bandLevel(LOW_BAND_HZ), high: bandLevel(HIGH_BAND_HZ) };
      },
      duck(on) {
        ducked = on;
        if (ctx && musicSource && musicState === 'playing') rampMusic(on ? 0 : MUSIC_LEVEL, on ? 0.6 : 2);
        announce();
      },
    };
  })();
  const THEME_KEY = 'askmiao-site-theme';
  const SYSTEM_SCHEME = 'light dark';
  const schemeMeta = document.querySelector('meta[name="color-scheme"]');
  const themeColorMetas = Array.from(document.querySelectorAll('meta[name="theme-color"]'));
  themeColorMetas.forEach((meta) => { meta.dataset.system = meta.content; });
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const readStoredScheme = () => {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return value === 'light' || value === 'dark' ? value : null;
    } catch {
      return null;
    }
  };
  const writeStoredScheme = (value) => {
    try {
      if (value) localStorage.setItem(THEME_KEY, value);
      else localStorage.removeItem(THEME_KEY);
    } catch {
      return;
    }
  };
  const systemScheme = () => (systemDark.matches ? 'dark' : 'light');
  const renderedScheme = () => {
    const content = schemeMeta.content;
    return content === 'light' || content === 'dark' ? content : systemScheme();
  };
  const applyScheme = (stored) => {
    schemeMeta.content = stored === null ? SYSTEM_SCHEME : stored;
    if (stored === null) {
      themeColorMetas.forEach((meta) => { meta.content = meta.dataset.system; });
      return;
    }
    const background = getComputedStyle(document.body).backgroundColor;
    themeColorMetas.forEach((meta) => { meta.content = background; });
  };
  applyScheme(readStoredScheme());
  const themeToggle = document.querySelector('[data-theme-toggle]');
  if (themeToggle) {
    const NIGHTFALL_MS = 2600;
    const FLARE_MS = 1100;
    const flare = document.createElement('span');
    flare.className = 'sky-flare';
    flare.setAttribute('aria-hidden', 'true');
    document.body.append(flare);
    let nightfallTimer = 0;
    const horizon = (target, x, y) => {
      flare.dataset.kind = target === 'dark' ? 'sunset' : 'sunrise';
      flare.style.setProperty('--fx', `${x}px`);
      flare.style.setProperty('--fy', `${y}px`);
      flare.getAnimations().forEach((animation) => animation.cancel());
      flare.animate([{ opacity: 0.95, scale: 0.15 }, { opacity: 0.6, scale: 3, offset: 0.35 }, { opacity: 0, scale: 9 }], { duration: FLARE_MS, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' });
    };
    const nightfall = (target) => {
      clearTimeout(nightfallTimer);
      root.classList.remove('is-nightfall');
      if (target !== 'dark' || !motionAllowed()) return;
      void root.offsetWidth;
      root.classList.add('is-nightfall');
      nightfallTimer = setTimeout(() => root.classList.remove('is-nightfall'), NIGHTFALL_MS);
    };
    themeToggle.addEventListener('click', () => {
      const target = renderedScheme() === 'dark' ? 'light' : 'dark';
      const stored = target === systemScheme() ? null : target;
      writeStoredScheme(stored);
      const swap = () => {
        applyScheme(stored);
        nightfall(target);
      };
      if (document.startViewTransition && motionAllowed()) {
        const rect = themeToggle.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        horizon(target, x, y);
        const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
        root.style.setProperty('--vt-x', `${x}px`);
        root.style.setProperty('--vt-y', `${y}px`);
        root.style.setProperty('--vt-r', `${radius}px`);
        root.classList.add('is-theme-swap');
        const transition = runTransition(swap);
        transition.finished.finally(() => {
          if (liveTransition === null || liveTransition === transition) root.classList.remove('is-theme-swap');
        });
      } else {
        swap();
      }
    });
  }
  window.addEventListener('storage', (event) => {
    if (event.key === THEME_KEY) applyScheme(readStoredScheme());
  });
  systemDark.addEventListener('change', () => applyScheme(readStoredScheme()));
  const nav = document.querySelector('[data-nav]');
  new IntersectionObserver(([entry]) => {
    nav.classList.toggle('is-scrolled', !entry.isIntersecting);
  }).observe(document.querySelector('[data-nav-sentinel]'));
  const menu = document.querySelector('[data-menu]');
  const menuOpen = document.querySelector('[data-menu-open]');
  if (menu && menuOpen) {
    menuOpen.addEventListener('click', () => {
      menu.showModal();
      menuOpen.setAttribute('aria-expanded', 'true');
    });
    menu.addEventListener('close', () => {
      menuOpen.setAttribute('aria-expanded', 'false');
    });
    menu.querySelector('[data-menu-close]').addEventListener('click', () => menu.close());
    menu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => menu.close()));
    window.matchMedia('(min-width: 1080px)').addEventListener('change', (event) => {
      if (event.matches && menu.open) menu.close();
    });
  }
  const navList = document.querySelector('.nav__links');
  const navLinks = Array.from(navList.querySelectorAll('a'));
  const linkById = new Map(navLinks.map((link) => [link.hash.slice(1), link]));
  const placeMarker = () => {
    const current = navLinks.find((link) => link.getAttribute('aria-current') === 'true');
    if (!current) {
      delete navList.dataset.current;
      return;
    }
    navList.style.setProperty('--marker-x', `${current.offsetLeft + current.offsetWidth / 2 - 2}px`);
    if (navList.dataset.current) navList.dataset.moved = '';
    navList.dataset.current = current.hash.slice(1);
  };
  const spy = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => link.removeAttribute('aria-current'));
      const link = linkById.get(entry.target.id);
      if (link) link.setAttribute('aria-current', 'true');
      placeMarker();
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  window.addEventListener('resize', placeMarker, { passive: true });
  document.querySelectorAll('main > section[id]').forEach((section) => spy.observe(section));
  const hero = document.querySelector('[data-spotlight]');
  if (hero) {
    let pointer = null;
    let queued = false;
    hero.addEventListener('pointermove', (event) => {
      if (!pointerEffects()) return;
      pointer = event;
      if (queued) return;
      queued = true;
      ticker.add(() => {
        queued = false;
        const rect = hero.getBoundingClientRect();
        hero.style.setProperty('--mx', `${pointer.clientX - rect.left}px`);
        hero.style.setProperty('--my', `${pointer.clientY - rect.top}px`);
        hero.classList.add('is-lit');
        return false;
      });
    }, { passive: true });
    hero.addEventListener('pointerleave', () => hero.classList.remove('is-lit'));
  }
  document.querySelectorAll('[data-magnetic]').forEach((element) => {
    element.addEventListener('pointermove', (event) => {
      if (!pointerEffects()) return;
      const rect = element.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2);
      const dy = event.clientY - (rect.top + rect.height / 2);
      element.style.setProperty('--tx', `${(dx * 0.22).toFixed(1)}px`);
      element.style.setProperty('--ty', `${(dy * 0.32).toFixed(1)}px`);
    });
    element.addEventListener('pointerleave', () => {
      element.style.removeProperty('--tx');
      element.style.removeProperty('--ty');
    });
  });
  document.querySelectorAll('[data-glow]').forEach((card) => {
    card.addEventListener('pointermove', (event) => {
      if (!finePointer.matches) return;
      const rect = card.getBoundingClientRect();
      card.style.setProperty('--x', `${event.clientX - rect.left}px`);
      card.style.setProperty('--y', `${event.clientY - rect.top}px`);
    });
  });
  const stream = document.querySelector('[data-stream]');
  if (stream) {
    const finish = () => {
      stream.querySelectorAll('.is-caret').forEach((token) => token.classList.remove('is-caret'));
      stream.querySelectorAll('[data-sblock]').forEach((block) => block.classList.add('is-on'));
      stream.querySelectorAll('.app__sources .src').forEach((source, index) => source.style.setProperty('--n', String(index)));
      stream.classList.add('is-done');
    };
    if (!motionAllowed()) {
      finish();
    } else {
      const plan = Array.from(stream.querySelectorAll('[data-sblock]'))
        .filter((block) => !block.classList.contains('app__sources'))
        .map((block) => {
          const tokens = [];
          const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
          const textNodes = [];
          while (walker.nextNode()) textNodes.push(walker.currentNode);
          textNodes.forEach((node) => {
            if (!node.nodeValue.trim()) return;
            const cite = node.parentElement.closest('.cite');
            if (cite) {
              cite.classList.add('tk');
              tokens.push(cite);
              return;
            }
            const fragment = document.createDocumentFragment();
            const text = node.nodeValue;
            let index = 0;
            while (index < text.length) {
              const size = 1 + Math.floor(Math.random() * 3);
              const span = document.createElement('span');
              span.className = 'tk';
              span.textContent = text.slice(index, index + size);
              fragment.append(span);
              tokens.push(span);
              index += size;
            }
            node.replaceWith(fragment);
          });
          return { block, tokens };
        });
      let started = false;
      const play = () => {
        if (started) return;
        started = true;
        let blockIndex = 0;
        let tokenIndex = 0;
        let last = null;
        const tick = () => {
          let budget = 2 + Math.floor(Math.random() * 3);
          while (budget > 0) {
            const group = plan[blockIndex];
            if (!group) {
              finish();
              return;
            }
            group.block.classList.add('is-on');
            const token = group.tokens[tokenIndex];
            tokenIndex += 1;
            if (token) {
              if (last) last.classList.remove('is-caret');
              token.classList.add('is-on', 'is-caret');
              last = token;
            }
            if (tokenIndex >= group.tokens.length) {
              blockIndex += 1;
              tokenIndex = 0;
            }
            budget -= 1;
          }
          window.setTimeout(tick, 40 + Math.random() * 45);
        };
        window.setTimeout(tick, 450);
      };
      const watcher = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          watcher.disconnect();
          play();
        }
      }, { threshold: 0.15 });
      watcher.observe(stream);
    }
  }
  const marquee = document.querySelector('[data-marquee]');
  const marqueeToggle = document.querySelector('[data-marquee-toggle]');
  if (marquee && marqueeToggle) {
    const track = marquee.querySelector('.marquee__track');
    const clone = track.cloneNode(true);
    clone.setAttribute('aria-hidden', 'true');
    clone.inert = true;
    marquee.append(clone);
    const label = marqueeToggle.querySelector('[data-marquee-label]');
    const icon = marqueeToggle.querySelector('use');
    marqueeToggle.addEventListener('click', () => {
      const paused = marquee.classList.toggle('is-paused');
      marqueeToggle.setAttribute('aria-pressed', String(paused));
      label.textContent = paused ? '繼續捲動' : '暫停捲動';
      icon.setAttribute('href', paused ? '#i-play' : '#i-pause');
    });
  }
  const steps = Array.from(document.querySelectorAll('[data-step]'));
  if (steps.length) {
    const stepWatcher = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        steps.forEach((step) => step.classList.toggle('is-active', step === entry.target));
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    steps.forEach((step) => stepWatcher.observe(step));
  }
  const restartAnimation = (element, className) => {
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
  };
  const story = document.querySelector('[data-story]');
  const compose = document.querySelector('[data-compose]');
  if (story && compose) {
    const hintMode = compose.querySelector('[data-hint-mode]');
    const hintWeb = compose.querySelector('[data-hint-web]');
    const webToggle = compose.querySelector('[data-web-toggle]');
    const traceTitle = story.querySelector('span[data-trace-title]');
    const hintText = (key) => compose.querySelector(`template[data-hint="${key}"]`).content.textContent;
    const traceText = (key) => story.querySelector(`template[data-trace-title="${key}"]`).content.textContent;
    const swapText = (element, text) => {
      if (element.textContent === text) return;
      element.textContent = text;
      restartAnimation(element, 'is-swap');
    };
    compose.querySelectorAll('input[name="chat-mode"]').forEach((input) => {
      input.addEventListener('change', () => {
        story.dataset.mode = input.value;
        swapText(hintMode, hintText(input.value));
        traceTitle.textContent = traceText(input.value);
      });
    });
    webToggle.addEventListener('click', () => {
      const allowed = webToggle.getAttribute('aria-pressed') !== 'true';
      webToggle.setAttribute('aria-pressed', String(allowed));
      swapText(hintWeb, hintText(allowed ? 'web-on' : 'web-off'));
    });
  }
  const plan = document.querySelector('[data-plan]');
  if (plan) {
    const planWatcher = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      planWatcher.disconnect();
      plan.classList.add('is-played');
    }, { threshold: 0.6 });
    planWatcher.observe(plan);
  }
  const citeDemo = document.querySelector('[data-cite-demo]');
  if (citeDemo) {
    const detail = citeDemo.querySelector('[data-cite-detail]');
    const cites = Array.from(citeDemo.querySelectorAll('.cite[data-cite]'));
    const sources = Array.from(citeDemo.querySelectorAll('[data-src]'));
    const tracer = citeDemo.querySelector('[data-tracer]');
    const tracerLine = tracer.firstElementChild;
    const TRACE_DELAY_MS = 160;
    const TRACE_MS = 520;
    let shown = null;
    let traced = false;
    const offsetWithin = (element) => {
      let x = 0;
      let y = 0;
      let node = element;
      while (node && node !== citeDemo) {
        x += node.offsetLeft;
        y += node.offsetTop;
        node = node.offsetParent;
      }
      return { x, y, width: element.offsetWidth, height: element.offsetHeight };
    };
    const trace = (animate) => {
      const cite = cites.find((item) => item.dataset.cite === shown);
      const target = detail.querySelector('[data-trace-target]');
      if (!cite || !target) return;
      const from = offsetWithin(cite);
      const to = offsetWithin(target);
      const x1 = from.x + from.width / 2;
      const y1 = from.y + from.height;
      const x2 = Math.min(Math.max(x1, to.x + 14), to.x + to.width - 14);
      const y2 = to.y + 2;
      const length = Math.hypot(x2 - x1, y2 - y1);
      tracer.style.setProperty('--x', `${x1}px`);
      tracer.style.setProperty('--y', `${y1}px`);
      tracer.style.setProperty('--len', `${length}px`);
      tracer.style.setProperty('--angle', `${Math.atan2(y2 - y1, x2 - x1)}rad`);
      tracer.classList.add('is-on');
      if (!animate || !motionAllowed()) return;
      tracerLine.getAnimations().forEach((animation) => animation.cancel());
      tracerLine.animate([{ scale: '0 1' }, { scale: '1 1' }], { duration: TRACE_MS, delay: TRACE_DELAY_MS, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'backwards' });
      tracer.lastElementChild.animate([{ opacity: 0, scale: 0.2 }, { opacity: 1, scale: 1 }], { duration: TRACE_MS / 2, delay: TRACE_DELAY_MS + TRACE_MS * 0.7, easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)', fill: 'backwards' });
    };
    const show = (number, animate) => {
      if (number === shown) return;
      const direction = Number(number) > Number(shown) ? 'is-next' : 'is-prev';
      shown = number;
      cites.forEach((cite) => cite.setAttribute('aria-pressed', String(cite.dataset.cite === number)));
      sources.forEach((source) => source.classList.toggle('is-on', source.dataset.src === number));
      const template = citeDemo.querySelector(`template[data-cite-template="${number}"]`);
      detail.replaceChildren(template.content.cloneNode(true));
      if (animate) {
        detail.classList.remove('is-next', 'is-prev');
        restartAnimation(detail, direction);
      }
      if (traced) trace(animate);
    };
    cites.forEach((cite) => {
      cite.addEventListener('click', () => {
        show(cite.dataset.cite, true);
        sound.play('cite');
      });
      cite.addEventListener('mouseenter', () => {
        if (finePointer.matches && cite.getAttribute('aria-pressed') !== 'true') show(cite.dataset.cite, true);
      });
    });
    show((cites.find((cite) => cite.getAttribute('aria-pressed') === 'true') ?? cites[0]).dataset.cite, false);
    onVisible(citeDemo, (visible) => {
      if (!visible || traced) return;
      traced = true;
      citeDemo.classList.add('is-traced');
      trace(true);
    }, { threshold: 0.6 });
    new ResizeObserver(() => {
      if (traced) trace(false);
    }).observe(citeDemo);
  }
  const APPROVAL_TIMEOUT_SECONDS = 300;
  const approval = document.querySelector('[data-approval]');
  if (approval) {
    const card = approval.querySelector('[data-approval-card]');
    const timer = approval.querySelector('[data-approval-timer]');
    const result = approval.querySelector('[data-approval-result]');
    const events = approval.querySelector('[data-approval-events]');
    const status = approval.querySelector('[data-approval-status]');
    const resetButton = approval.querySelector('[data-approval-reset]');
    const initialEvents = events.innerHTML;
    const clock = approval.querySelector('[data-approval-clock]');
    const decideButtons = Array.from(approval.querySelectorAll('[data-approval-decide]'));
    const OUTCOMES = {
      approve: {
        approved: true,
        icon: '#i-check-circle',
        title: '你核准了這次呼叫，工具已執行',
        detail: '回傳單號 LR-20261120-0418。工具結果同樣包在不可信資料標記裡交給模型。',
        events: [
          ['step_end', '{"step": 3, "duration_seconds": 1.27, "status": "success"}', 'ok'],
          ['token', '{"content": "已送出 11/20 至 11/21 的特休申請…"}', ''],
          ['done', '{"message_id": 312, "research_trace": […]}', ''],
        ],
      },
      deny: {
        approved: false,
        icon: '#i-x-circle',
        title: '你拒絕了這次呼叫，工具沒有執行',
        detail: '模型收到「使用者未核准」，並被要求不要再次呼叫同一工具。',
        events: [
          ['step_end', '{"step": 3, "status": "error", "output_preview": "使用者未核准執行此工具"}', 'bad'],
          ['token', '{"content": "你沒有核准建立請假單，所以我沒有送出申請…"}', ''],
          ['done', '{"message_id": 312, "research_trace": […]}', ''],
        ],
      },
      remember: {
        approved: true,
        remember: true,
        icon: '#i-check-circle',
        title: '這次提問都允許，工具已執行',
        detail: '這次回答中再呼叫「建立請假單」就不再詢問；下一次提問會重新請你確認。',
        events: [
          ['step_end', '{"step": 3, "duration_seconds": 1.27, "status": "success"}', 'ok'],
          ['token', '{"content": "已送出 11/20 至 11/21 的特休申請…"}', ''],
          ['done', '{"message_id": 312, "research_trace": […]}', ''],
        ],
      },
      timeout: {
        approved: false,
        icon: '#i-x-circle',
        title: `${APPROVAL_TIMEOUT_SECONDS} 秒內沒有回應，視為拒絕`,
        detail: '逾時與拒絕的處理相同：approved 為 false，工具不會執行。',
        events: [
          ['step_end', '{"step": 3, "status": "error", "output_preview": "使用者未核准執行此工具"}', 'bad'],
          ['done', '{"message_id": 312, "research_trace": […]}', ''],
        ],
      },
    };
    let remaining = APPROVAL_TIMEOUT_SECONDS;
    let ticker = 0;
    let decided = false;
    let visible = false;
    const formatTime = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    const stopTimer = () => {
      window.clearInterval(ticker);
      ticker = 0;
    };
    const startTimer = () => {
      if (ticker || decided) return;
      ticker = window.setInterval(() => {
        remaining -= 1;
        timer.textContent = formatTime(remaining);
        clock.style.setProperty('--left', String(remaining / APPROVAL_TIMEOUT_SECONDS));
        if (remaining <= 0) decide('timeout');
      }, 1000);
    };
    const addEvent = (name, data, tone, order) => {
      const item = document.createElement('li');
      item.className = tone ? `is-new is-${tone}` : 'is-new';
      item.style.setProperty('--n', String(order));
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
      decideButtons.forEach((button) => { button.disabled = true; });
      const outcome = OUTCOMES[kind];
      const settle = () => {
        card.hidden = true;
        card.style.removeProperty('view-transition-name');
        addEvent('approval_resolved', `{"approval_id": "q3VxT0bL8mYc…", "approved": ${outcome.approved}, "remember": ${outcome.remember === true}}`, outcome.approved ? 'ok' : 'bad', 0);
        outcome.events.forEach(([name, data, tone], index) => addEvent(name, data, tone, index + 1));
        const title = document.createElement('p');
        title.className = 'approval__outcome';
        title.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${outcome.icon}"></use></svg>`;
        title.append(outcome.title);
        const detail = document.createElement('p');
        detail.textContent = outcome.detail;
        result.dataset.kind = kind;
        result.replaceChildren(title, detail);
        result.hidden = false;
        status.textContent = `${outcome.title}。${outcome.detail}`;
        resetButton.hidden = false;
        resetButton.focus();
      };
      if (document.startViewTransition && motionAllowed() && kind !== 'timeout') {
        card.style.setProperty('view-transition-name', 'approval-panel');
        result.dataset.morph = '';
        const morph = runTransition(() => {
          settle();
          result.style.setProperty('view-transition-name', 'approval-panel');
        });
        morph.finished.finally(() => {
          result.style.removeProperty('view-transition-name');
          delete result.dataset.morph;
        });
      } else {
        settle();
      }
    }
    const reset = () => {
      decided = false;
      remaining = APPROVAL_TIMEOUT_SECONDS;
      timer.textContent = formatTime(remaining);
      events.innerHTML = initialEvents;
      clock.style.setProperty('--left', '1');
      decideButtons.forEach((button) => { button.disabled = false; });
      result.hidden = true;
      result.replaceChildren();
      status.textContent = '';
      card.hidden = false;
      resetButton.hidden = true;
      card.querySelector('[data-approval-decide="approve"]').focus();
      if (visible) startTimer();
    };
    approval.querySelectorAll('[data-approval-decide]').forEach((button) => {
      button.addEventListener('click', () => {
        sound.play({ approve: 'approve', remember: 'remember', deny: 'deny' }[button.dataset.approvalDecide]);
        decide(button.dataset.approvalDecide);
      });
    });
    resetButton.addEventListener('click', reset);
    new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        visible = entry.isIntersecting;
        if (visible) startTimer();
        else stopTimer();
      });
    }, { threshold: 0.4 }).observe(approval);
  }
  const rrf = document.querySelector('[data-rrf]');
  const rrfData = document.getElementById('rrf-data');
  if (rrf && rrfData) {
    const { rerankWeight, finalK, chunks, queries, space } = JSON.parse(rrfData.textContent);
    const FLIP_MS = 460;
    const ENTER_MS = 320;
    const ENTER_STAGGER_MS = 40;
    const LINK_DELAY_MS = 480;
    const LINK_STAGGER_MS = 90;
    const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)';
    const flip = (container, nodes) => {
      const before = new Map();
      Array.from(container.children).forEach((node) => {
        node.getAnimations().forEach((animation) => animation.cancel());
        before.set(node, node.getBoundingClientRect().top);
      });
      Array.from(container.children).filter((node) => !nodes.includes(node)).forEach((node) => node.remove());
      reorder(container, nodes);
      if (!motionAllowed()) return;
      nodes.forEach((node, index) => {
        if (before.has(node)) {
          const delta = before.get(node) - node.getBoundingClientRect().top;
          if (Math.abs(delta) > 1) node.animate([{ translate: `0 ${delta}px` }, { translate: '0 0' }], { duration: FLIP_MS, easing: EASE_OUT });
          return;
        }
        node.animate([{ opacity: 0, translate: '0 8px' }, { opacity: 1, translate: '0 0' }], { duration: ENTER_MS, delay: index * ENTER_STAGGER_MS, easing: EASE_OUT, fill: 'backwards' });
      });
    };
    const laneRows = { vector: new Map(), bm25: new Map() };
    const buildLaneRow = (id) => {
      const item = document.createElement('li');
      item.dataset.chunk = id;
      item.title = chunks[id].text;
      const rank = document.createElement('span');
      rank.className = 'rrf__rank';
      const bar = document.createElement('span');
      bar.className = 'lanebar';
      bar.setAttribute('aria-hidden', 'true');
      bar.append(document.createElement('span'));
      const value = document.createElement('small');
      value.className = 'lanebar__v';
      item.append(rank, nameMarkup(id), bar, value);
      return { item, rank, bar, value };
    };
    const spaceMap = rrf.querySelector('[data-space-map]');
    const spaceList = rrf.querySelector('[data-space-list]');
    const SVG_NS = 'http://www.w3.org/2000/svg';
    const svgEl = (tag, attrs) => {
      const element = document.createElementNS(SVG_NS, tag);
      Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, String(value)));
      return element;
    };
    const spacePoints = new Map();
    const spaceLinks = [];
    let spaceMarker = null;
    let spaceQuery = null;
    if (spaceMap && space) {
      const linkLayer = svgEl('g', { class: 'space__links' });
      const pointLayer = svgEl('g', { class: 'space__points' });
      Object.entries(space.chunks).forEach(([id, [x, y]]) => {
        const group = svgEl('g', { class: 'space__pt', 'data-chunk': id, transform: `translate(${x} ${y})` });
        const dot = svgEl('circle', { class: 'space__dot', r: 4.5 });
        const glow = svgEl('circle', { class: 'space__glow', r: 7.5 });
        const label = svgEl('text', { class: 'space__label', x: 0, y: -12, 'text-anchor': 'middle' });
        label.textContent = space.short[id];
        const rank = svgEl('text', { class: 'space__rank', x: 0, y: 3, 'text-anchor': 'middle' });
        group.append(dot, glow, rank, label);
        pointLayer.append(group);
        spacePoints.set(id, { group, rank, x, y });
      });
      for (let index = 0; index < 5; index += 1) {
        const line = svgEl('line', { class: 'space__link', x1: 0, y1: 0, x2: 0, y2: 0 });
        linkLayer.append(line);
        spaceLinks.push(line);
      }
      spaceMarker = svgEl('g', { class: 'space__q' });
      const halo = svgEl('circle', { class: 'space__q-halo', r: 12 });
      const core = svgEl('path', { class: 'space__q-core', d: 'M0 -7 L1.9 -2.2 L7 -2.2 L2.9 0.9 L4.4 6 L0 3 L-4.4 6 L-2.9 0.9 L-7 -2.2 L-1.9 -2.2 Z' });
      const label = svgEl('text', { class: 'space__q-label', x: 0, y: 23, 'text-anchor': 'middle' });
      label.textContent = '問題';
      spaceMarker.append(halo, core, label);
      spaceMap.append(linkLayer, pointLayer, spaceMarker);
    }
    const renderSpace = (queryKey, query) => {
      if (!spaceMarker) return;
      const [qx, qy] = space.queries[queryKey];
      const moved = spaceQuery !== queryKey;
      spaceQuery = queryKey;
      spaceMarker.style.translate = `${qx}px ${qy}px`;
      spacePoints.forEach((point, id) => {
        const rank = query.vector.indexOf(id);
        point.group.classList.toggle('is-near', rank >= 0);
        point.rank.textContent = rank >= 0 ? String(rank + 1) : '';
      });
      query.vector.forEach((id, index) => {
        const { x, y } = spacePoints.get(id);
        const line = spaceLinks[index];
        line.setAttribute('x1', qx);
        line.setAttribute('y1', qy);
        line.setAttribute('x2', x);
        line.setAttribute('y2', y);
        line.style.transformOrigin = `${qx}px ${qy}px`;
        if (moved && motionAllowed()) {
          line.getAnimations().forEach((animation) => animation.cancel());
          line.animate([{ scale: 0, opacity: 0 }, { scale: 1, opacity: 1 }], { duration: ENTER_MS + index * LINK_STAGGER_MS, delay: LINK_DELAY_MS, easing: EASE_OUT, fill: 'backwards' });
        }
      });
      spaceList.textContent = query.vector.map((id, index) => `${index + 1}. ${chunks[id].doc}${chunks[id].part}`).join('、');
    };
    const kInput = rrf.querySelector('[data-rrf-k]');
    const tInput = rrf.querySelector('[data-rrf-t]');
    const kOutput = rrf.querySelector('[data-out-k]');
    const tOutput = rrf.querySelector('[data-out-t]');
    const caption = rrf.querySelector('[data-rrf-caption]');
    const lanes = { vector: rrf.querySelector('[data-lane="vector"]'), bm25: rrf.querySelector('[data-lane="bm25"]') };
    const results = rrf.querySelector('[data-rrf-results]');
    const verdict = rrf.querySelector('[data-rrf-verdict]');
    const queryInputs = Array.from(rrf.querySelectorAll('input[name="rrf-query"]'));
    const LOG_FLOOR = 0.001;
    const logScale = (value) => Math.min(1, Math.max(0, (Math.log10(Math.max(value, LOG_FLOOR)) - Math.log10(LOG_FLOOR)) / -Math.log10(LOG_FLOOR)));
    const rows = new Map();
    const buildRow = (id) => {
      const item = document.createElement('li');
      item.dataset.chunk = id;
      item.title = chunks[id].text;
      const score = document.createElement('span');
      score.className = 'rrf-row__rrf';
      score.append(document.createTextNode(''));
      const scoreNote = document.createElement('small');
      score.append(scoreNote);
      const bar = document.createElement('span');
      bar.className = 'relbar';
      bar.setAttribute('aria-hidden', 'true');
      const fill = document.createElement('span');
      fill.className = 'relbar__fill';
      const mark = document.createElement('span');
      mark.className = 'relbar__mark';
      bar.append(fill, mark);
      const state = document.createElement('span');
      state.className = 'rrf-row__state';
      state.append(document.createTextNode(''));
      const value = document.createElement('b');
      state.append(value);
      item.append(nameMarkup(id), score, bar, state);
      return { item, score, scoreNote, bar, state, value, pass: null };
    };
    const fuse = (rankedLists, k) => {
      const fused = new Map();
      rankedLists.forEach((list) => list.forEach((id, index) => {
        fused.set(id, (fused.has(id) ? fused.get(id) : 0) + 1 / (k + index + 1));
      }));
      return Array.from(fused, ([id, score]) => ({ id, score })).sort((a, b) => b.score - a.score);
    };
    const nameMarkup = (id) => {
      const wrapper = document.createElement('span');
      wrapper.className = 'rrf__name';
      const doc = document.createElement('b');
      doc.textContent = chunks[id].doc;
      const part = document.createElement('span');
      part.textContent = chunks[id].part;
      wrapper.append(doc, part);
      return wrapper;
    };
    const paintSlider = (input) => {
      const ratio = (Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min));
      input.style.setProperty('--fill', `${(ratio * 100).toFixed(2)}%`);
    };
    const render = () => {
      const queryKey = queryInputs.find((input) => input.checked).value;
      const query = queries[queryKey];
      const k = Number(kInput.value);
      const threshold = Number(tInput.value);
      kOutput.textContent = String(k);
      tOutput.textContent = threshold.toFixed(3);
      [kInput, tInput].forEach(paintSlider);
      caption.textContent = query.caption;
      Object.entries(lanes).forEach(([lane, list]) => {
        const nodes = query[lane].map((id, index) => {
          if (!laneRows[lane].has(id)) laneRows[lane].set(id, buildLaneRow(id));
          const row = laneRows[lane].get(id);
          row.rank.textContent = String(index + 1);
          row.bar.style.setProperty('--p', ((k + 1) / (k + index + 1)).toFixed(4));
          row.value.textContent = (1 / (k + index + 1)).toFixed(4);
          return row.item;
        });
        flip(list, nodes);
      });
      renderSpace(queryKey, query);
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
      const ordered = ranked.map((row) => {
        if (!rows.has(row.id)) rows.set(row.id, buildRow(row.id));
        const entry = rows.get(row.id);
        const changed = entry.pass !== row.pass && entry.pass !== null;
        entry.pass = row.pass;
        entry.item.className = `rrf-row ${row.pass ? 'is-pass' : 'is-fail'}`;
        entry.score.firstChild.textContent = row.score.toFixed(4);
        entry.scoreNote.textContent = `融合第 ${row.fusedRank} 名`;
        entry.bar.style.setProperty('--p', logScale(row.relevance).toFixed(4));
        entry.bar.style.setProperty('--t', logScale(threshold).toFixed(4));
        entry.state.firstChild.textContent = row.pass ? '通過門檻' : '低於門檻';
        entry.value.textContent = row.relevance.toFixed(3);
        if (changed) restartAnimation(entry.state, 'is-changed');
        return entry.item;
      });
      Array.from(results.children).filter((item) => !ordered.includes(item)).forEach((item) => {
        rows.get(item.dataset.chunk).pass = null;
      });
      flip(results, ordered);
      const passed = ranked.filter((row) => row.pass).slice(0, finalK);
      const verdictTitle = document.createElement('span');
      const verdictNote = document.createElement('small');
      if (passed.length) {
        verdict.dataset.kind = 'pass';
        verdictTitle.textContent = `${passed.length} 段通過門檻，依上方順序交給模型`;
        verdictNote.textContent = '最多取前 FINAL_K 段；精確比對到網址、貼文 ID、日期的片段不受門檻限制，排在最前面。';
      } else {
        verdict.dataset.kind = 'none';
        verdictTitle.textContent = '全部低於門檻：回報「知識庫中查無相關資料」';
        verdictNote.textContent = '模型收到明確的查無結果，會照實說明，不拿無關片段硬答。';
      }
      verdict.replaceChildren(verdictTitle, verdictNote);
      return passed.length;
    };
    let lastPassed = 0;
    const renderWithCue = (cue) => {
      const passedCount = render();
      cue(passedCount);
      lastPassed = passedCount;
    };
    const verdictCue = (passedCount) => sound.play(passedCount ? 'allow' : 'fewer');
    const sliderCue = (passedCount) => {
      if (passedCount !== lastPassed) sound.play(passedCount > lastPassed ? 'more' : 'fewer');
    };
    queryInputs.forEach((input) => input.addEventListener('change', () => renderWithCue(verdictCue)));
    kInput.addEventListener('input', () => renderWithCue(sliderCue));
    tInput.addEventListener('input', () => renderWithCue(sliderCue));
    let linkedChunk = null;
    const linkChunk = (id) => {
      if (id === linkedChunk) return;
      linkedChunk = id;
      rrf.querySelectorAll('[data-chunk]').forEach((element) => element.classList.toggle('is-linked', element.dataset.chunk === id));
    };
    rrf.addEventListener('pointerover', (event) => {
      const target = event.target.closest('[data-chunk]');
      linkChunk(target ? target.dataset.chunk : null);
    });
    rrf.addEventListener('pointerleave', () => linkChunk(null));
    lastPassed = render();
  }
  const counters = Array.from(document.querySelectorAll('[data-count-from]'));
  if (counters.length && motionAllowed()) {
    const easeOut = (t) => 1 - (1 - t) ** 4;
    const DURATION = 1600;
    counters.forEach((counter) => {
      counter.textContent = Number(counter.dataset.countFrom).toFixed(Number(counter.dataset.countDigits));
    });
    const countWatcher = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        countWatcher.unobserve(entry.target);
        const element = entry.target;
        const from = Number(element.dataset.countFrom);
        const to = Number(element.dataset.countTo);
        const digits = Number(element.dataset.countDigits);
        tween(DURATION, (progress) => {
          element.textContent = (from + (to - from) * easeOut(progress)).toFixed(digits);
        });
      });
    }, { threshold: 0.6 });
    counters.forEach((counter) => countWatcher.observe(counter));
  }
  const BLOCKED_PORTS = new Set([22, 23, 25, 111, 135, 139, 445, 1433, 1521, 2375, 2376, 3306, 5432, 6379, 11211, 27017]);
  const BLOCKED_HOSTS = new Set(['localhost', 'localhost.localdomain', 'broadcasthost', 'ip6-localhost', 'ip6-loopback', 'local', 'internal', 'metadata.google.internal', 'metadata.internal']);
  const BLOCKED_SUFFIXES = ['.localhost', '.local', '.internal', '.lan', '.home.arpa', '.localdomain', '.corp'];
  const V4_RANGES = [
    ['0.0.0.0', 8, '本機網段'], ['10.0.0.0', 8, '私有網段'], ['100.64.0.0', 10, '電信級 NAT 共用位址'], ['127.0.0.0', 8, '迴環位址'],
    ['169.254.0.0', 16, '連結本地與雲端中繼資料端點'], ['172.16.0.0', 12, '私有網段'], ['192.0.0.0', 24, 'IETF 保留'], ['192.0.2.0', 24, '文件測試網段'],
    ['192.88.99.0', 24, '6to4 中繼'], ['192.168.0.0', 16, '私有網段'], ['198.18.0.0', 15, '效能測試網段'], ['198.51.100.0', 24, '文件測試網段'],
    ['203.0.113.0', 24, '文件測試網段'], ['224.0.0.0', 4, '群播'], ['240.0.0.0', 4, '保留網段'], ['255.255.255.255', 32, '廣播位址'],
  ];
  const V6_RANGES = [
    ['::', 128, '未指定位址'], ['::1', 128, '迴環位址'], ['64:ff9b::', 96, 'IPv4／IPv6 轉換'], ['64:ff9b:1::', 48, '本地 IPv4／IPv6 轉換'],
    ['100::', 64, '丟棄專用位址'], ['2001::', 23, 'IETF 協定保留'], ['2001:db8::', 32, '文件測試網段'], ['2002::', 16, '6to4'],
    ['fc00::', 7, '唯一本地位址'], ['fe80::', 10, '連結本地位址'], ['ff00::', 8, '群播'],
  ];
  const parseV4 = (host) => {
    const match = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
    if (!match) return null;
    const parts = match.slice(1).map(Number);
    if (parts.some((part) => part > 255)) return null;
    return ((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3];
  };
  const inV4 = (ip, base, bits) => {
    const mask = bits === 0 ? 0 : (~0 << (32 - bits)) >>> 0;
    return ((ip & mask) >>> 0) === ((parseV4(base) & mask) >>> 0);
  };
  const parseV6 = (host) => {
    const halves = host.split('::');
    if (halves.length > 2) return null;
    const toGroups = (part) => (part ? part.split(':').map((group) => (/^[0-9a-f]{1,4}$/.test(group) ? parseInt(group, 16) : Number.NaN)) : []);
    const head = toGroups(halves[0]);
    const tail = halves.length === 2 ? toGroups(halves[1]) : [];
    const gap = 8 - head.length - tail.length;
    if (gap < 0 || (halves.length === 1 && gap !== 0)) return null;
    const groups = [...head, ...new Array(halves.length === 2 ? gap : 0).fill(0), ...tail];
    return groups.some((group) => Number.isNaN(group)) ? null : groups;
  };
  const inV6 = (groups, base, bits) => {
    const prefix = parseV6(base);
    let left = bits;
    for (let index = 0; index < 8 && left > 0; index += 1) {
      const take = Math.min(16, left);
      const mask = (0xffff << (16 - take)) & 0xffff;
      if ((groups[index] & mask) !== (prefix[index] & mask)) return false;
      left -= take;
    }
    return true;
  };
  const checkV4 = (host, value) => {
    const hit = V4_RANGES.find(([base, bits]) => inV4(value, base, bits));
    return hit ? `${host} 位於禁止網段 ${hit[0]}/${hit[1]}（${hit[2]}）` : null;
  };
  const checkIp = (host) => {
    const v4 = parseV4(host);
    if (v4 !== null) return { isIp: true, reason: checkV4(host, v4) };
    if (!host.includes(':')) return { isIp: false };
    const groups = parseV6(host);
    if (!groups) return { isIp: true, reason: `無效的 IP 位址格式：${host}` };
    if (groups.slice(0, 5).every((group) => group === 0) && groups[5] === 0xffff) {
      const mapped = `${groups[6] >> 8}.${groups[6] & 0xff}.${groups[7] >> 8}.${groups[7] & 0xff}`;
      const reason = checkV4(mapped, parseV4(mapped));
      return { isIp: true, reason: reason ? `IPv4 對應位址 ${host} 指向 ${reason}` : null };
    }
    const hit = V6_RANGES.find(([base, bits]) => inV6(groups, base, bits));
    return { isIp: true, reason: hit ? `${host} 位於禁止網段 ${hit[0]}/${hit[1]}（${hit[2]}）` : null };
  };
  const scrambleFrames = new WeakMap();
  const SCRAMBLE_GLYPHS = '01<>/[]{}=+#%ABCDEFxz';
  const SCRAMBLE_MS = 560;
  const scramble = (element, text) => {
    scrambleFrames.get(element)?.();
    if (!motionAllowed()) {
      element.textContent = text;
      return;
    }
    scrambleFrames.set(element, tween(SCRAMBLE_MS, (progress) => {
      const settled = Math.floor(progress * text.length);
      let output = text.slice(0, settled);
      for (let index = settled; index < text.length; index += 1) {
        output += text[index] === ' ' ? ' ' : SCRAMBLE_GLYPHS[Math.floor(Math.random() * SCRAMBLE_GLYPHS.length)];
      }
      element.textContent = output;
    }));
  };
  const inspector = document.querySelector('[data-inspector]');
  if (inspector) {
    const input = inspector.querySelector('[data-url-input]');
    const verdict = inspector.querySelector('[data-verdict]');
    const rows = new Map(Array.from(inspector.querySelectorAll('[data-check]')).map((row) => [row.dataset.check, row]));
    const order = Array.from(rows.keys());
    const checkList = inspector.querySelector('[data-checks]');
    rows.forEach((row) => { row.dataset.idle = row.querySelector('.checks__m').textContent; });
    order.forEach((name, index) => rows.get(name).style.setProperty('--n', String(index)));
    const SWEEP_STEP_MS = 70;
    let sweepTimers = [];
    const sweep = () => {
      sweepTimers.forEach((timer) => window.clearTimeout(timer));
      sweepTimers = [];
      const verdictCue = { block: 'block', allow: 'allow', server: 'server' }[verdict.dataset.kind];
      if (!motionAllowed()) {
        sound.play(verdictCue);
        return;
      }
      restartAnimation(checkList, 'is-sweeping');
      const reached = order.filter((name) => rows.get(name).dataset.state !== 'skip');
      sweepTimers.push(window.setTimeout(() => sound.play(verdictCue), reached.length * SWEEP_STEP_MS));
    };
    const verdictVisual = document.createElement('span');
    verdictVisual.setAttribute('aria-hidden', 'true');
    const verdictSpoken = document.createElement('span');
    verdictSpoken.className = 'sr-only';
    const verdictNote = document.createElement('small');
    verdict.replaceChildren(verdictVisual, verdictSpoken, verdictNote);
    let lastVerdict = '';
    const setRow = (name, state, message) => {
      const row = rows.get(name);
      row.dataset.state = state;
      row.querySelector('.checks__m').textContent = message;
    };
    const setVerdict = (kind, title, note) => {
      verdict.dataset.kind = kind;
      verdictSpoken.textContent = title;
      verdictNote.textContent = note;
      if (title !== lastVerdict) scramble(verdictVisual, title);
      lastVerdict = title;
    };
    const block = (name, message, note) => {
      setRow(name, 'fail', message);
      order.slice(order.indexOf(name) + 1).forEach((next) => setRow(next, 'skip', '未執行'));
      setVerdict('block', '拒絕請求', note);
    };
    const run = () => {
      order.forEach((name) => setRow(name, 'idle', rows.get(name).dataset.idle));
      const raw = input.value.trim();
      if (!raw) {
        setVerdict('idle', '輸入一個網址，或點選範例', '檢查順序與後端 ssrf_protection.py 相同。');
        return;
      }
      let url;
      try {
        url = new URL(raw);
      } catch {
        block('scheme', '網址格式無法解析', '無法解析的網址一律拒絕。');
        return;
      }
      const scheme = url.protocol.slice(0, -1).toLowerCase();
      if (scheme !== 'http' && scheme !== 'https') {
        block('scheme', `不允許的協定「${scheme}」，只支援 http、https`, 'file:、ftp:、gopher: 這類協定可能讀到本機檔案或內部服務。');
        return;
      }
      setRow('scheme', 'pass', scheme);
      if (url.username || url.password) {
        block('userinfo', '網址禁止包含帳號密碼', '帶帳號密碼的網址常被拿來偽裝主機名稱，例如 https://good.example@evil.example/。');
        return;
      }
      setRow('userinfo', 'pass', '未包含帳號密碼');
      const port = url.port ? Number(url.port) : (scheme === 'https' ? 443 : 80);
      if (BLOCKED_PORTS.has(port)) {
        block('port', `禁止存取受保護的內部服務連接埠 ${port}`, '資料庫、快取、SSH 與 Docker 等連接埠一律阻擋。');
        return;
      }
      setRow('port', 'pass', `連接埠 ${port}`);
      const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
      if (BLOCKED_HOSTS.has(host)) {
        block('host', `禁止存取保留或內部主機名稱「${host}」`, '主機名稱本身就在封鎖清單中。');
        return;
      }
      const suffix = BLOCKED_SUFFIXES.find((item) => host.endsWith(item));
      if (suffix) {
        block('host', `禁止存取內部專屬網域（結尾為 ${suffix}）`, '內網常見的網域後綴直接拒絕，不必等 DNS。');
        return;
      }
      setRow('host', 'pass', `「${host}」不在封鎖清單`);
      const ip = checkIp(host);
      if (ip.isIp) {
        if (ip.reason) {
          block('ip', ip.reason, '私有、迴環、連結本地與雲端中繼資料位址一律阻擋；網址來自工具結果時，提示注入也拿不到內網資料。');
          return;
        }
        setRow('ip', 'pass', `${host} 是公開位址`);
        setRow('dns', 'skip', '直接輸入 IP，不需解析');
        setRow('redirect', 'server', '停用自動轉址，每一跳重新驗證，最多 5 次');
        setVerdict('allow', '允許送出請求', '連線直接打到這個 IP；若有轉址，每一跳都重新檢查。');
        return;
      }
      setRow('ip', 'skip', '不是 IP，交給 DNS 解析後檢查');
      setRow('dns', 'server', '解析出的每個 IP 都必須是公開位址，連線固定到核可的 IP');
      setRow('redirect', 'server', '停用自動轉址，每一跳重新驗證，最多 5 次');
      setVerdict('server', '瀏覽器端的檢查都通過了', '最後兩關在伺服器：DNS 結果逐一檢查並固定連線 IP，擋下 DNS rebinding；聯網白名單不是 * 時，轉址目標也要在白名單內。');
    };
    input.addEventListener('input', run);
    inspector.querySelectorAll('[data-url-example]').forEach((button) => {
      button.addEventListener('click', () => {
        input.value = button.dataset.urlExample;
        run();
        sweep();
      });
    });
    run();
  }
  document.querySelectorAll('[data-copy]').forEach((button) => {
    const label = button.querySelector('span');
    const icon = button.querySelector('use');
    const idleLabel = label.textContent;
    label.setAttribute('aria-live', 'polite');
    let resetTimer = 0;
    button.addEventListener('click', async () => {
      const code = button.parentElement.querySelector('code').textContent;
      window.clearTimeout(resetTimer);
      try {
        await navigator.clipboard.writeText(code);
        sound.play('copy');
        label.textContent = '已複製';
        icon.setAttribute('href', '#i-check');
        button.classList.add('is-done');
      } catch {
        label.textContent = '無法複製';
      }
      resetTimer = window.setTimeout(() => {
        label.textContent = idleLabel;
        icon.setAttribute('href', '#i-copy');
        button.classList.remove('is-done');
      }, 1800);
    });
  });
  const film = document.querySelector('[data-film]');
  if (film) {
    const chapters = Array.from(document.querySelectorAll('[data-chapter]'));
    let video = null;
    const markChapter = () => {
      const now = video.currentTime;
      const current = chapters.filter((chapter) => Number(chapter.dataset.chapter) <= now).pop();
      chapters.forEach((chapter) => {
        if (chapter === current) chapter.setAttribute('aria-current', 'time');
        else chapter.removeAttribute('aria-current');
      });
    };
    const ensureVideo = (fragment) => {
      if (video) return video;
      video = document.createElement('video');
      video.src = film.dataset.filmSrc + fragment;
      video.poster = film.dataset.filmPoster;
      video.controls = true;
      video.playsInline = true;
      video.setAttribute('aria-label', film.dataset.filmLabel);
      video.addEventListener('play', () => sound.duck(true));
      video.addEventListener('pause', () => sound.duck(false));
      video.addEventListener('ended', () => sound.duck(false));
      video.addEventListener('timeupdate', markChapter);
      film.replaceChildren(video);
      return video;
    };
    const playFrom = (seconds) => {
      const fresh = !video;
      const player = ensureVideo(fresh && seconds !== null ? `#t=${seconds}` : '');
      if (!fresh && seconds !== null) player.currentTime = seconds;
      player.play().catch(() => player.focus());
      player.focus({ preventScroll: true });
    };
    film.querySelector('[data-film-play]').addEventListener('click', () => playFrom(null));
    chapters.forEach((chapter) => chapter.addEventListener('click', () => {
      playFrom(Number(chapter.dataset.chapter));
      film.scrollIntoView({ block: 'nearest', behavior: motionAllowed() ? 'smooth' : 'instant' });
    }));
  }
  window.askmiao = Object.freeze({ sound, ticker, tween, onVisible, reorder, motionAllowed, finePointer, restartAnimation });
})();