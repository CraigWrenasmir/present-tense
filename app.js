/* The Present Tense: one continuous field, the day's narratives along the bottom, constellations, a tide. No build step. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const errlog = $('#errlog');
  window.addEventListener('error', e => { errlog.textContent += `[error] ${e.message} @${e.filename}:${e.lineno}\n`; });
  window.addEventListener('unhandledrejection', e => { errlog.textContent += `[rejection] ${e.reason}\n`; });

  const WORLD_W = 9000, WORLD_H = Math.round(9000 * 145 / 360);
  const Z_MAX = 2.6;
  /* Semantic zoom. atlas: the whole world, each country a swarm of dots. region: a continent, swarms unfolding.
     near: countries as blocks of readable headlines, laid out 1:1 at NEAR_Z. close: large type. */
  const LEVEL_Z = { region: 0.3, near: 0.8, close: 1.5 };
  const UNFOLD = [0.42, 0.8];
  const NEAR_Z = 0.8;
  const CARD_W = 220, CELL_W = (CARD_W + 36) / NEAR_Z, SWARM = 26;
  const LEVEL_NAME = { atlas: 'WORLD', region: 'REGION', near: 'HEADLINES', close: 'CLOSE' };
  const zMin = () => { const v = viewport(); return clamp(Math.min((v.w - 48) / WORLD_W, (v.h - 40) / WORLD_H), 0.03, 0.42); };
  const mobile = () => window.innerWidth <= 760;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');

  const state = { z: 0.4, panX: 0, panY: 0, lang: 'en', reading: '', rung: '', frag: '', focusIds: null, ghosts: false, panel: '', drawer: false };
  let news, readings, library, world, ledger, config, held = [], fieldArticles = [];
  let beads = [], ghosts = [], labels = [];
  const byId = new Map(), beadById = new Map();
  let cameraDirty = true, lastFrame = 0, anim = null, dragged = false;
  const ground = $('#ground'), ctx = ground.getContext('2d');
  const worldEl = $('#world'), labelsEl = $('#labels'), fieldEl = $('#field');

  /* ---------- helpers ---------- */
  const create = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; };
  const toWorld = (lon, lat) => [(lon + 180) / 360 * WORLD_W, (85 - lat) / 145 * WORLD_H];
  const toScreen = (x, y) => [x * state.z + state.panX, y * state.z + state.panY];
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const rand = seed => { const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const hashStr = s => { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return Math.abs(h); };
  const safeURL = u => { try { const p = new URL(u); return p.protocol === 'https:' ? p.href : null; } catch { return null; } };
  const headline = a => state.lang === 'en' ? (a.titleEnglish || a.title) : a.title;
  const alt = a => { const h = headline(a), o = state.lang === 'en' ? a.title : (a.titleEnglish || a.title); return o && o !== h ? o : ''; };
  const LANGS = { en: 'English', es: 'Spanish', ar: 'Arabic', pt: 'Portuguese', ru: 'Russian', fr: 'French', 'zh-Hant': 'Chinese (Traditional)', zh: 'Chinese', id: 'Indonesian', it: 'Italian', ja: 'Japanese', ko: 'Korean', tr: 'Turkish', de: 'German', el: 'Greek', vi: 'Vietnamese', pl: 'Polish', he: 'Hebrew', sv: 'Swedish', hi: 'Hindi', ceb: 'Cebuano', fi: 'Finnish', uk: 'Ukrainian', und: 'unknown language' };
  const langName = c => LANGS[c] || c;
  const fmt = iso => { if (!iso) return ''; const d = new Date(iso); if (isNaN(d)) return iso; return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }).replace(',', ',') + ' UTC'; };
  const fmtDate = iso => { const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC'; };
  let toastTimer; const toast = t => { const el = $('#toast'); el.textContent = t; el.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => el.hidden = true, 3200); };
  const ink = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  /* ---------- hash state ---------- */
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.reading = p.get('reading') || '';
    state.rung = p.get('rung') || ''; state.frag = p.get('frag') || '';
    state.drawer = p.get('open') === '1';
    state.panel = ['tide', 'index', 'about'].includes(p.get('view')) ? p.get('view') : '';
    if (p.get('lang') === 'orig') state.lang = 'orig';
    state.ghosts = p.get('ghosts') === '1';
    state.debugZ = parseFloat(p.get('z')) || 0; state.debugLon = parseFloat(p.get('lon')); state.debugLat = parseFloat(p.get('lat'));
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.reading) p.set('reading', state.reading);
    if (state.drawer) p.set('open', '1');
    if (state.rung) p.set('rung', state.rung);
    if (state.frag) p.set('frag', state.frag);
    if (state.panel) p.set('view', state.panel);
    if (state.lang === 'orig') p.set('lang', 'orig');
    if (state.ghosts) p.set('ghosts', '1');
    const h = '#' + p.toString();
    if (location.hash !== h) history.replaceState(null, '', h.length > 1 ? h : location.pathname);
  }

  /* ---------- data ---------- */
  async function getJSON(path) { const r = await fetch(path, { cache: 'no-cache' }); if (!r.ok) throw Error(`${path}: HTTP ${r.status}`); return r.json(); }
  async function load() {
    [news, readings, library, world, config] = await Promise.all(['data/news.json', 'data/readings.json', 'data/library.json', 'data/world.json', 'data/source-config.json'].map(getJSON));
    try { ledger = await getJSON('data/ledger.json'); } catch { ledger = null; }
    news.articles = news.articles.filter(a => a && a.id && a.title && safeURL(a.url));
    news.articles.forEach(a => byId.set(a.id, a));
    held = (readings.sourceArticles || []).filter(a => a && a.id && a.title && safeURL(a.url) && !byId.has(a.id)).map(a => Object.assign({}, a, { held: true }));
    held.forEach(a => byId.set(a.id, a));
    fieldArticles = news.articles.concat(held);
  }

  /* ---------- layout ----------
     Every headline has two homes. Compact: a dot in its country's swarm, so the whole world reads as a map of who is
     talking. Expanded: a card in its country's block, so a country reads as a page of its own headlines. The frame
     interpolates between them with zoom, so swarms unfold into pages as you approach. */
  function estimate(a) {
    const len = headline(a).length;
    const lines = clamp(Math.ceil(len / 26), 1, 6);
    return { w: CARD_W, h: lines * 17 + 12 + 14 + 12 };
  }
  const smooth = t => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
  const unfold = z => smooth((z - UNFOLD[0]) / (UNFOLD[1] - UNFOLD[0]));
  const posAt = (p, z) => { const t = unfold(z); return [p.cx + (p.ex - p.cx) * t, p.cy + (p.ey - p.cy) * t]; };
  let blocks = [];
  function layout() {
    const anchors = {}; config.countries.forEach(c => { anchors[c.code] = toWorld(c.lon, c.lat); });
    const groups = new Map();
    fieldArticles.forEach(a => { (groups.get(a.sourceCountryCode) || groups.set(a.sourceCountryCode, []).get(a.sourceCountryCode)).push(a); });
    blocks = [];
    for (const [code, list] of groups) {
      const [ax, ay] = anchors[code] || toWorld(list[0].sourceLon, list[0].sourceLat);
      list.sort((a, b) => (a.publisher + (a.publishedAt || '')).localeCompare(b.publisher + (b.publishedAt || '')));
      const n = list.length, r = SWARM * Math.sqrt(n) + 14, turn = hashStr(code) % 7;
      const cols = clamp(Math.round(Math.sqrt(n / 1.5)), 1, 4), colH = new Array(cols).fill(0);
      const items = list.map((a, i) => {
        const s = estimate(a), rr = SWARM * Math.sqrt(i + 0.6), ang = i * 2.39996 + turn;
        const c = colH.indexOf(Math.min(...colH));
        const it = { a, w: s.w, h: s.h, sx: rr * Math.cos(ang) * 1.25, sy: rr * Math.sin(ang), bx: c * CELL_W, by: colH[c] };
        colH[c] += (s.h + 10) / NEAR_Z;
        return it;
      });
      blocks.push({ code, ax, ay, n, r, items, bw: cols * CELL_W, bh: Math.max(...colH), cx: ax, cy: ay, ex: ax, ey: ay });
    }
    relaxRects(blocks.map(b => ({ b, x: b.cx, y: b.cy, w: b.r * 2 + 36, h: b.r * 2 + 36, ax: b.ax, ay: b.ay })), 400, 0.75);
    blocks.forEach(b => { b.cx = b._x; b.cy = b._y; });
    relaxRects(blocks.map(b => ({ b, x: b.ex, y: b.ey, w: b.bw + 170, h: b.bh + 230, ax: b.ax, ay: b.ay })), 700, 0.7);
    blocks.forEach(b => { b.ex = b._x; b.ey = b._y; });
    const out = [];
    blocks.forEach(b => b.items.forEach(it => {
      it.cx = b.cx + it.sx; it.cy = b.cy + it.sy;
      it.ex = b.ex - b.bw / 2 + it.bx; it.ey = b.ey - b.bh / 2 + it.by;
      it.block = b; it.i = out.length; out.push(it);
    }));
    return out;
  }
  /* Rigid rectangles (centre x, y) pushed apart, pulled gently to their anchors, kept inside the world. */
  function relaxRects(items, iters, xBias) {
    items.forEach((p, i) => { p.i = i; });
    for (let it = 0; it < iters; it++) {
      const pull = it < iters * 0.4 ? 0.03 : 0.006;
      for (const p of items) {
        for (const q of items) {
          if (q.i <= p.i) continue;
          const ox = (p.w + q.w) / 2 - Math.abs(p.x - q.x); if (ox <= 0) continue;
          const oy = (p.h + q.h) / 2 - Math.abs(p.y - q.y); if (oy <= 0) continue;
          const left = p.x === q.x ? p.i < q.i : p.x < q.x, above = p.y === q.y ? p.i < q.i : p.y < q.y;
          if (ox * xBias < oy) { const s = (left ? -1 : 1) * ox * 0.5; p.x += s; q.x -= s; }
          else { const s = (above ? -1 : 1) * oy * 0.5; p.y += s; q.y -= s; }
        }
        p.x += (p.ax - p.x) * pull; p.y += (p.ay - p.y) * pull;
        p.x = clamp(p.x, p.w / 2, WORLD_W - p.w / 2); p.y = clamp(p.y, p.h / 2 + 10, WORLD_H + 200 - p.h / 2);
      }
    }
    items.forEach(p => { p.b._x = p.x; p.b._y = p.y; });
  }

  /* ---------- beads ---------- */
  function beadEl(a, ghost) {
    const el = create('button', 'bead' + (ghost ? ' ghost' : '')); el.type = 'button'; el.dataset.id = a.id; el.tabIndex = -1;
    el.append(create('span', 'dot'), create('span', 't'), create('span', 'alt'), create('span', 'm'));
    el.addEventListener('click', e => { if (dragged) return; e.stopPropagation(); openCard(a, el); });
    el.addEventListener('keydown', e => { if (e.key === 'Enter') openCard(a, el); });
    return el;
  }
  function fillBead(p) {
    const a = p.a, el = p.el;
    $('.t', el).textContent = headline(a); $('.t', el).lang = state.lang === 'en' ? 'en' : (a.language || ''); $('.t', el).dir = 'auto';
    $('.alt', el).textContent = alt(a); $('.alt', el).dir = 'auto';
    $('.m', el).textContent = `${a.sourceCountry} / ${a.publisher}` + (a.language && a.language !== 'en' ? ` / ${langName(a.language)}` : '');
    el.setAttribute('aria-label', `${headline(a)}. ${a.publisher}, ${a.sourceCountry}.`);
  }
  function buildField() {
    const items = layout();
    worldEl.replaceChildren(); labelsEl.replaceChildren(); beads = []; beadById.clear();
    const frag = document.createDocumentFragment();
    items.forEach(p => {
      p.el = beadEl(p.a, false); fillBead(p);
      p.x = p.cx; p.y = p.cy; p.ph = rand(p.i * 3 + 1) * Math.PI * 2; p.f1 = 0.00028 + rand(p.i) * 0.00022; p.f2 = 0.00021 + rand(p.i * 7) * 0.0002;
      if (ledger && ledger.previousAt && ledger.arrived.includes(p.a.id)) p.el.classList.add('arrived');
      if (p.a.held) p.el.classList.add('held');
      frag.append(p.el); beads.push(p); beadById.set(p.a.id, p);
    });
    worldEl.append(frag);
    // ghosts: departed headlines, in a ring around their country's swarm or block
    ghosts = [];
    if (ledger && ledger.departed && ledger.departed.length) {
      const byCode = {}; blocks.forEach(b => { byCode[b.code] = b; });
      const anchors = {}; config.countries.forEach(c => { anchors[c.code] = toWorld(c.lon, c.lat); });
      const count = {};
      const gf = document.createDocumentFragment();
      ledger.departed.forEach((a, j) => {
        if (!safeURL(a.url) || beadById.has(a.id)) return;
        const b = byCode[a.sourceCountryCode], an = anchors[a.sourceCountryCode]; if (!b && !an) return;
        const i = (count[a.sourceCountryCode] = (count[a.sourceCountryCode] || 0) + 1);
        const ang = i * 2.39996 + 1.1;
        const g = { a, el: beadEl(a, true), ph: rand(j) * 6, f1: 0.0002, f2: 0.00015, w: 200, h: 40 };
        if (b) {
          const rc = b.r + 24 + 14 * Math.sqrt(i), re = Math.max(b.bw, b.bh) / 2 + 90 + 40 * Math.sqrt(i);
          g.cx = b.cx + rc * Math.cos(ang) * 1.3; g.cy = b.cy + rc * Math.sin(ang);
          g.ex = b.ex + re * Math.cos(ang) * 1.3; g.ey = b.ey + re * Math.sin(ang);
        } else {
          const rr = 40 + 22 * Math.sqrt(i);
          g.cx = an[0] + rr * Math.cos(ang) * 1.3; g.cy = an[1] + rr * Math.sin(ang); g.ex = g.cx * 1 + rr * 2 * Math.cos(ang); g.ey = g.cy + rr * 2 * Math.sin(ang);
        }
        g.x = g.cx; g.y = g.cy;
        fillBead(g); g.el.hidden = !state.ghosts; gf.append(g.el); ghosts.push(g); byId.set(a.id, a);
      });
      worldEl.append(gf);
    }
    // labels: one per country with headlines (above its swarm, then its block) plus silent countries at their anchor
    labels = [];
    const byCode = {}; blocks.forEach(b => { byCode[b.code] = b; });
    const states = {}; (ledger ? ledger.countries : []).forEach(c => { states[c.code] = c.state; });
    config.countries.forEach(c => {
      const b = byCode[c.code];
      const el = create('div', 'label');
      let l;
      if (b) {
        el.append(document.createTextNode(c.name), create('b', '', String(b.n)));
        if (states[c.code] === 'new-voice') el.classList.add('new-voice');
        l = { el, cx: b.cx - b.r * 0.8, cy: b.cy - b.r, ex: b.ex - b.bw / 2 + 8, ey: b.ey - b.bh / 2, dy: -26, silent: false, code: c.code, count: b.n, block: b };
      } else {
        const [x, y] = toWorld(c.lon, c.lat);
        el.classList.add('silent'); el.append(document.createTextNode(c.name)); el.title = 'Configured publishers returned nothing in this collection';
        l = { el, cx: x, cy: y, ex: x, ey: y, dx: 11, dy: -7, silent: true, code: c.code, count: -1, ax: x, ay: y };
      }
      labels.push(l); labelsEl.append(el);
    });
    cameraDirty = true;
  }

  /* ---------- camera ---------- */
  const stripH = () => { const s = $('#narratives'); return s ? s.offsetHeight : 0; };
  function viewport() {
    const w = window.innerWidth - (state.drawer && !mobile() ? parseInt(getComputedStyle(document.documentElement).getPropertyValue('--drawer-w')) : 0);
    const top = fieldEl.getBoundingClientRect().top;
    const h = window.innerHeight - top - stripH();
    return { w, h, top };
  }
  function bucket() {
    const z = state.z;
    return z < LEVEL_Z.region ? 'atlas' : z < LEVEL_Z.near ? 'region' : z < LEVEL_Z.close ? 'near' : 'close';
  }
  function applyBucket() {
    const b = bucket();
    if (!worldEl.classList.contains(b)) {
      worldEl.classList.remove('atlas', 'region', 'near', 'close'); worldEl.classList.add(b);
      $('#zoom-level').textContent = LEVEL_NAME[b];
      litKey = '';
    }
    $('#zoom-out').disabled = state.z <= zMin() * 1.001; $('#zoom-in').disabled = state.z >= Z_MAX * 0.999;
  }
  /* The country nearest the pointer is the anchor of a zoom: it stays under the pointer while the layout unfolds around it. */
  function anchorAt(sx, sy) {
    const wx = (sx - state.panX) / state.z, wy = (sy - state.panY) / state.z, t = unfold(state.z);
    let b = null, bd = Infinity;
    for (const k of blocks) { const bx = k.cx + (k.ex - k.cx) * t, by = k.cy + (k.ey - k.cy) * t, d = Math.hypot(bx - wx, by - wy); if (d < bd) { bd = d; b = k; } }
    if (!b) return null;
    const t0 = unfold(state.z);
    return { b, ox: wx - (b.cx + (b.ex - b.cx) * t0), oy: wy - (b.cy + (b.ey - b.cy) * t0), sx, sy };
  }
  function panForAnchor(nz, sx, sy, a) {
    const t = unfold(nz), bx = a.b.cx + (a.b.ex - a.b.cx) * t, by = a.b.cy + (a.b.ey - a.b.cy) * t;
    return [sx - (bx + a.ox) * nz, sy - (by + a.oy) * nz];
  }
  function zoomAt(nz, sx, sy, anchor) {
    nz = clamp(nz, zMin(), Z_MAX);
    if (anchor) { [state.panX, state.panY] = panForAnchor(nz, sx, sy, anchor); }
    else { const wx = (sx - state.panX) / state.z, wy = (sy - state.panY) / state.z; state.panX = sx - wx * nz; state.panY = sy - wy * nz; }
    state.z = nz; cameraDirty = true; applyBucket();
  }
  /* Wheel zoom eases towards a target in log space, so a mouse wheel glides instead of stepping. */
  let zoomTarget = null;
  function easeZoom() {
    if (!zoomTarget) return;
    const k = reduced.matches ? 1 : 0.2;
    const lz = Math.log(state.z), lt = Math.log(zoomTarget.z);
    let nz = Math.exp(lz + (lt - lz) * k);
    if (Math.abs(lt - Math.log(nz)) < 0.002) { nz = zoomTarget.z; zoomAt(nz, zoomTarget.sx, zoomTarget.sy, zoomTarget.anchor); zoomTarget = null; return; }
    zoomAt(nz, zoomTarget.sx, zoomTarget.sy, zoomTarget.anchor);
  }
  function fitRect(minX, minY, maxX, maxY, maxZ, pad) {
    const v = viewport();
    const bw = Math.max(200, maxX - minX), bh = Math.max(120, maxY - minY);
    const z = clamp(Math.min((v.w - pad * 2) / bw, (v.h - pad * 2) / bh), zMin(), maxZ);
    return { z, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, v };
  }
  /* Fit a set of headlines. Their positions depend on the zoom they will be seen at, so solve for it. */
  function fitBeads(list, maxZ = 1.05, pad = 60) {
    if (!list.length) return fitWorld();
    let z = clamp(state.z, zMin(), maxZ), f;
    for (let k = 0; k < 4; k++) {
      const t = unfold(z), ew = t * 230 / NEAR_Z, eh = t * 70 / NEAR_Z;
      const pts = list.map(p => posAt(p, z));
      const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
      f = fitRect(Math.min(...xs) - 80, Math.min(...ys) - 50, Math.max(...xs) + 80 + ew, Math.max(...ys) + 50 + eh, maxZ, pad);
      if (Math.abs(f.z - z) < 0.002) break;
      z = f.z;
    }
    animateTo(f.z, f.v.w / 2 - f.cx * f.z, f.v.h / 2 + 20 - f.cy * f.z);
  }
  function animateTo(z, px, py, dur = 700, anchor = null) {
    zoomTarget = null;
    if (anchor) [px, py] = panForAnchor(z, anchor.sx, anchor.sy, anchor);
    if (reduced.matches) { state.z = z; state.panX = px; state.panY = py; cameraDirty = true; applyBucket(); return; }
    const from = { z: state.z, px: state.panX, py: state.panY }, t0 = performance.now();
    cancelAnimationFrame(anim);
    const step = now => {
      const t = clamp((now - t0) / dur, 0, 1), e = 1 - Math.pow(1 - t, 3);
      // zoom in log space so the motion feels even
      state.z = Math.exp(Math.log(from.z) + (Math.log(z) - Math.log(from.z)) * e);
      if (anchor) [state.panX, state.panY] = panForAnchor(state.z, anchor.sx, anchor.sy, anchor);
      else { state.panX = from.px + (px - from.px) * e; state.panY = from.py + (py - from.py) * e; }
      cameraDirty = true; applyBucket();
      if (t < 1) anim = requestAnimationFrame(step);
    };
    anim = requestAnimationFrame(step);
  }
  function zoomBy(factor, sx, sy, dur = 420) {
    const v = viewport(); if (sx === undefined) { sx = v.w / 2; sy = v.h / 2; }
    const nz = clamp((zoomTarget ? zoomTarget.z : state.z) * factor, zMin(), Z_MAX);
    const wx = (sx - state.panX) / state.z, wy = (sy - state.panY) / state.z;
    animateTo(nz, sx - wx * nz, sy - wy * nz, dur, anchorAt(sx, sy));
  }
  function fitReading() {
    const r = currentReading();
    const list = r ? r.articleIds.map(id => beadById.get(id)).filter(Boolean) : [];
    if (list.length) fitBeads(list, 1.0); else fitWorld();
  }
  function fitWorld() {
    const f = fitRect(0, 0, WORLD_W, WORLD_H, 0.6, 16);
    animateTo(f.z, f.v.w / 2 - f.cx * f.z, f.v.h / 2 + 10 - f.cy * f.z);
  }
  function locate(id) {
    const p = beadById.get(id) || ghosts.find(g => g.a.id === id); if (!p) return false;
    const v = viewport(); const z = Math.max(state.z, 1.0);
    const [x, y] = posAt(p, z);
    animateTo(z, v.w / 2 - (x + 110) * z, v.h / 2 - (y + 30) * z);
    p.el.classList.add('focus'); setTimeout(() => p.el.classList.remove('focus'), 2600);
    return true;
  }

  /* ---------- frame ---------- */
  function frame(now) {
    requestAnimationFrame(frame);
    easeZoom();
    const moving = !reduced.matches && !document.hidden;
    if (!moving && !cameraDirty) return;
    const z = state.z, px = state.panX, py = state.panY, t = unfold(z);
    const amp = z < LEVEL_Z.region ? 0.35 : z < LEVEL_Z.near ? 0.7 : 1;
    for (const p of beads) {
      const dx = amp * Math.sin(now * p.f1 + p.ph) * 9, dy = amp * Math.cos(now * p.f2 + p.ph) * 5;
      p.x = p.cx + (p.ex - p.cx) * t + dx; p.y = p.cy + (p.ey - p.cy) * t + dy;
      if (!p.lit) p.el.style.transform = `translate3d(${(p.x * z + px).toFixed(1)}px,${(p.y * z + py).toFixed(1)}px,0)`;
    }
    placeLit();
    if (state.ghosts) for (const g of ghosts) {
      g.x = g.cx + (g.ex - g.cx) * t + amp * Math.sin(now * g.f1 + g.ph) * 6; g.y = g.cy + (g.ey - g.cy) * t + amp * Math.cos(now * g.f2 + g.ph) * 4;
      g.el.style.transform = `translate3d(${(g.x * z + px).toFixed(1)}px,${(g.y * z + py).toFixed(1)}px,0)`;
    }
    for (const l of labels) {
      l.sx = (l.cx + (l.ex - l.cx) * t) * z + px + (l.dx || 0); l.sy = (l.cy + (l.ey - l.cy) * t) * z + py + (l.dy || 0);
      l.el.style.transform = `translate3d(${l.sx.toFixed(1)}px,${l.sy.toFixed(1)}px,0)`;
    }
    if (cameraDirty) thinLabels();
    drawGround();
    cameraDirty = false;
  }
  /* Lit headlines are labels for their stars: they are pushed apart in screen space and tied back with a leader. */
  let litKey = '';
  function placeLit() {
    const r = currentReading(); if (!r) return;
    const z = state.z, px = state.panX, py = state.panY;
    const v = viewport(); const W = v.w, H = v.h + (mobile() ? 0 : 30);
    const all = r.articleIds.map(id => beadById.get(id)).filter(p => p && p.lit);
    const lvl = bucket();
    if (lvl === 'near' || lvl === 'close') {
      // cards stay in their country's block; no leaders, no displacement
      for (const p of all) { p.el.classList.remove('quiet'); p.lx = p.ax = p.x * z + px; p.ly = p.ay = p.y * z + py; p.el.style.transform = `translate3d(${p.lx.toFixed(1)}px,${p.ly.toFixed(1)}px,0)`; }
      return;
    }
    const onScreen = p => { const sx = p.x * z + px, sy = p.y * z + py; return sx > -30 && sx < W + 30 && sy > -30 && sy < H + 30; };
    const cap = lvl === 'atlas' ? (mobile() ? 3 : 7) : (mobile() ? 5 : Math.min(9, Math.floor((W * H) / (200 * 70) / 5)));
    // which lit headlines get a label when there is not room for all: one per country first, in citation order
    let labelled = all.filter(onScreen);
    if (labelled.length > cap) {
      const seen = new Set(); const first = labelled.filter(p => !seen.has(p.a.sourceCountryCode) && seen.add(p.a.sourceCountryCode));
      labelled = [...first, ...labelled.filter(p => !first.includes(p))].slice(0, cap);
    }
    const items = all.filter(p => { const quiet = !labelled.includes(p); p.el.classList.toggle('quiet', quiet); if (quiet) p.el.style.transform = `translate3d(${(p.x * z + px).toFixed(1)}px,${(p.y * z + py).toFixed(1)}px,0)`; return !quiet; });
    const key = `${z.toFixed(3)}|${px.toFixed(0)}|${py.toFixed(0)}|${items.length}|${state.drawer}`;
    const fresh = key !== litKey; litKey = key;
    const boxes = items.map(p => {
      const ax = p.x * z + px, ay = p.y * z + py, w = p.el.offsetWidth || 200, h = p.el.offsetHeight || 48;
      if (fresh || p.lx === undefined) { p.lx = ax + 10; p.ly = ay - 12; }
      p.ax = ax; p.ay = ay;
      return { p, ax, ay, w, h, x: p.lx, y: p.ly };
    });
    const iters = fresh ? 90 : 3;
    for (let it = 0; it < iters; it++) {
      for (let i = 0; i < boxes.length; i++) {
        const a = boxes[i];
        for (let j = i + 1; j < boxes.length; j++) {
          const b = boxes[j];
          const ox = (a.w + b.w) / 2 + 12 - Math.abs((a.x + a.w / 2) - (b.x + b.w / 2)); if (ox <= 0) continue;
          const oy = (a.h + b.h) / 2 + 8 - Math.abs((a.y + a.h / 2) - (b.y + b.h / 2)); if (oy <= 0) continue;
          if (ox * 0.4 < oy) { const s = (a.x < b.x ? -1 : 1) * ox * 0.25; a.x += s; b.x -= s; }
          else { const s = (a.y < b.y ? -1 : 1) * oy * 0.25; a.y += s; b.y -= s; }
        }
        a.x += (a.ax + 10 - a.x) * 0.025; a.y += (a.ay - 12 - a.y) * 0.025;
        a.x = clamp(a.x, 6, Math.max(6, W - a.w - 6)); a.y = clamp(a.y, 6, Math.max(6, H - a.h - 6));
      }
    }
    boxes.forEach(b => { b.p.lx = b.x; b.p.ly = b.y; b.p.el.style.transform = `translate3d(${b.x.toFixed(1)}px,${b.y.toFixed(1)}px,0)`; });
  }
  function thinLabels() {
    const placed = [];
    const order = [...labels].sort((a, b) => (b.count || 0) - (a.count || 0));
    for (const l of order) {
      const x = l.sx || 0, y = l.sy || 0, w = l.el.offsetWidth || 80, h = 14;
      const hit = placed.some(q => x < q.x + q.w + 6 && x + w + 6 > q.x && y < q.y + q.h + 4 && y + h + 4 > q.y);
      l.el.style.visibility = hit ? 'hidden' : 'visible';
      if (!hit) placed.push({ x, y, w, h });
    }
  }
  function sizeCanvas() {
    const r = fieldEl.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
    ground.width = Math.round(r.width * dpr); ground.height = Math.round(r.height * dpr);
    ground.style.width = r.width + 'px'; ground.style.height = r.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); cameraDirty = true;
  }
  function drawGround() {
    const w = ground.clientWidth, h = ground.clientHeight; ctx.clearRect(0, 0, w, h);
    const z = state.z, px = state.panX, py = state.panY;
    // land: one dot per degree of Natural Earth land, a stipple that reads as continents when small and as grain when near
    ctx.fillStyle = ink(z < LEVEL_Z.region ? '--land-far' : '--land-near');
    const s = clamp(z * 9, 1.4, 2.2);
    const kx = WORLD_W / 360 * z, ky = WORLD_H / 145 * z, x0 = 180 * kx + px, y0 = 85 * ky + py;
    for (const [lon, lat] of world.points) {
      const x = lon * kx + x0, y = y0 - lat * ky;
      if (x < -4 || y < -4 || x > w + 4 || y > h + 4) continue;
      ctx.fillRect(x, y, s, s);
    }
    // country blocks: a rule above each page of headlines once the swarms have unfolded
    const tu = unfold(z);
    if (tu > 0.85) {
      ctx.strokeStyle = ink('--ink'); ctx.lineWidth = 1; ctx.globalAlpha = (tu - 0.85) / 0.15;
      for (const b of blocks) {
        const x1 = (b.ex - b.bw / 2) * z + px, y1 = (b.ey - b.bh / 2) * z + py - 10, x2 = x1 + (b.bw - 36 / NEAR_Z) * z;
        if (x2 < 0 || x1 > w || y1 < -10 || y1 > h + 10) continue;
        ctx.beginPath(); ctx.moveTo(x1, y1 + 0.5); ctx.lineTo(x2, y1 + 0.5); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }
    // silent countries: hollow rings at the anchor
    ctx.strokeStyle = ink('--ink-3'); ctx.lineWidth = 1;
    for (const l of labels) if (l.silent) { const [x, y] = toScreen(l.ax, l.ay); ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI * 2); ctx.stroke(); }
    // constellation
    const r = currentReading(); if (!r) return;
    const pts = r.articleIds.map(id => beadById.get(id)).filter(Boolean);
    if (!pts.length) return;
    const star = p => [p.x * z + px + 4, p.y * z + py + 4];
    ctx.save();
    const focus = state.focusIds ? new Set(state.focusIds) : null;
    // the constellation: dotted lines star to star, in the order the narrative cites them
    ctx.setLineDash([1.2, 5.5]); ctx.lineCap = 'round'; ctx.lineWidth = 1.3;
    const nearLevel = z >= LEVEL_Z.near, inView = (x, y) => x > -w * 0.5 && x < w * 1.5 && y > -h * 0.5 && y < h * 1.5;
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1], [x1, y1] = star(a), [x2, y2] = star(b);
      if (nearLevel && !inView(x1, y1) && !inView(x2, y2)) continue;
      const hot = focus && focus.has(a.a.id) && focus.has(b.a.id);
      ctx.strokeStyle = hot ? ink('--ink') : (focus || nearLevel ? ink('--ink-4') : ink('--ink-2'));
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    // leaders: each headline label back to its star, and the star itself
    ctx.setLineDash([]); ctx.lineWidth = 1; ctx.font = '13px ' + getComputedStyle(document.documentElement).getPropertyValue('--mono');
    for (const p of pts) {
      const [sx, sy] = star(p); const hot = !focus || focus.has(p.a.id);
      ctx.strokeStyle = hot ? ink('--ink-3') : ink('--ink-4'); ctx.fillStyle = hot ? ink('--ink') : ink('--ink-4');
      if (p.lx !== undefined) {
        const lx = clamp(sx, p.lx, p.lx + (p.el.offsetWidth || 200)), ly = clamp(sy, p.ly, p.ly + (p.el.offsetHeight || 40));
        if (Math.hypot(lx - sx, ly - sy) > 6) { ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(lx, ly); ctx.stroke(); }
      }
      ctx.fillText('*', sx - 4, sy + 5);
    }
    // a dotted thread from the selected narrative's card to its nearest star
    const o = $('#narratives-strip .narrative[aria-pressed="true"]'); if (!o || !o.offsetParent) { ctx.restore(); return; }
    const orect = o.getBoundingClientRect(), frect = fieldEl.getBoundingClientRect();
    if (orect.right < 0 || orect.left > frect.width) { ctx.restore(); return; }
    const ox = clamp(orect.left + orect.width / 2 - frect.left, 0, frect.width), oy = orect.top - frect.top;
    let best = null, bd = Infinity;
    for (const p of pts) { const [x, y] = star(p); const d = Math.hypot(x - ox, y - oy); if (d < bd) { bd = d; best = [x, y]; } }
    if (best) { ctx.strokeStyle = ink('--ink-3'); ctx.setLineDash([1, 7]); ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(best[0], best[1]); ctx.stroke(); }
    ctx.restore();
  }

  /* ---------- readings ---------- */
  const currentReading = () => readings.readings.find(r => r.id === state.reading) || null;
  function selectReading(id, { open = state.drawer, fit = true } = {}) {
    const prev = state.reading;
    state.reading = id || ''; if (prev !== state.reading) { state.rung = ''; state.frag = ''; state.focusIds = null; }
    const r = currentReading();
    beads.forEach(p => { p.lit = !!r && r.articleIds.includes(p.a.id); p.el.classList.toggle('lit', p.lit); p.el.tabIndex = p.lit ? 0 : -1; p.lx = undefined; });
    litKey = '';
    worldEl.classList.toggle('reading', !!r);
    renderStrip();
    state.drawer = !!r && open;
    document.body.classList.toggle('drawer-open', state.drawer);
    $('#drawer').hidden = !state.drawer;
    if (state.drawer) renderDrawer();
    if (fit) fitReading();
    cameraDirty = true; writeHash();
  }
  let stripBuilt = false;
  function renderStrip() {
    const r = currentReading(), list = readings.readings;
    $('#narratives-count').textContent = `${list.length} NARRATIVES IN THE HEADLINES OF ${fmt(readings.newsGeneratedAt).toUpperCase()}`;
    $('#narratives-clear').hidden = !r;
    const strip = $('#narratives-strip');
    if (!stripBuilt) {
      strip.replaceChildren();
      list.forEach((x, i) => {
        const b = create('button', 'narrative'); b.type = 'button'; b.setAttribute('role', 'listitem'); b.dataset.id = x.id;
        const n = new Set(x.articleIds.map(id => (byId.get(id) || {}).sourceCountry).filter(Boolean)).size;
        b.append(create('span', 'k', `${String(i + 1).padStart(2, '0')} · ${x.kicker}`), create('span', 'n', x.line), create('span', 'm', `${x.articleIds.length} headlines · ${n} countries`));
        b.addEventListener('click', () => selectReading(x.id, { open: true, fit: state.reading !== x.id }));
        strip.append(b);
      });
      stripBuilt = true;
    }
    strip.querySelectorAll('.narrative').forEach(b => {
      const on = !!r && b.dataset.id === r.id; b.setAttribute('aria-pressed', String(on));
      if (on && typeof b.scrollIntoView === 'function') b.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
  }
  function stepReading(d) {
    const list = readings.readings, i = list.findIndex(x => x.id === state.reading);
    const n = list[(i + d + list.length) % list.length]; selectReading(n.id);
  }
  function setFocus(ids) {
    state.focusIds = ids && ids.length ? ids : null;
    worldEl.classList.toggle('focusing', !!state.focusIds);
    beads.forEach(p => p.el.classList.toggle('focus', !!state.focusIds && state.focusIds.includes(p.a.id)));
    cameraDirty = true;
  }
  const KIND = { observation: 'what the headlines say', interpretation: 'what might connect them', break: 'why this might be wrong' };
  function renderDrawer() {
    const r = currentReading(), body = $('#drawer-body'); body.replaceChildren(); if (!r) return;
    const list = readings.readings, idx = list.findIndex(x => x.id === r.id);
    $('#drawer-eyebrow').textContent = `NARRATIVE ${String(idx + 1).padStart(2, '0')} / ${String(list.length).padStart(2, '0')} · ${readings.method === 'claude-authored-seed' ? 'SEED EDITION' : 'AI EDITION'} · ${fmt(readings.generatedAt).toUpperCase()}`;
    body.append(create('p', 'reading-kicker', r.kicker), create('h2', 'reading-line', r.line), create('p', 'reading-claim', r.claim));
    const ol = create('ol', 'rungs');
    r.rungs.forEach((rung, i) => {
      const li = create('li', 'rung ' + rung.kind + (state.rung === rung.id ? ' open' : ''));
      const btn = create('button', 'rung-btn'); btn.type = 'button'; btn.setAttribute('aria-expanded', String(state.rung === rung.id));
      btn.append(create('span', 'k'), create('span', 'l', rung.label), create('span', 'kind', KIND[rung.kind] || rung.kind));
      btn.addEventListener('click', () => { state.rung = state.rung === rung.id ? '' : rung.id; state.frag = ''; setFocus(null); renderDrawer(); writeHash(); });
      li.append(btn);
      if (state.rung === rung.id) {
        const fl = create('ol', 'frags');
        rung.fragments.forEach(f => {
          const fi = create('li', 'frag' + (state.frag === f.id ? ' open' : ''));
          const fb = create('button', 'frag-btn'); fb.type = 'button'; fb.setAttribute('aria-expanded', String(state.frag === f.id));
          fb.append(create('span', 's', state.frag === f.id ? '−' : '+'), create('span', '', f.label));
          fb.addEventListener('click', () => { const open = state.frag === f.id; state.frag = open ? '' : f.id; setFocus(open ? null : f.articleIds); renderDrawer(); writeHash(); if (!open && f.articleIds.length) fitFocus(f.articleIds); });
          fb.addEventListener('mouseenter', () => { if (!state.frag) setFocus(f.articleIds); });
          fb.addEventListener('mouseleave', () => { if (!state.frag) setFocus(null); });
          fi.append(fb);
          if (state.frag === f.id) fi.append(fragBody(f));
          fl.append(fi);
        });
        li.append(fl);
      }
      ol.append(li);
    });
    body.append(ol);
    if (r.horizons && r.horizons.length) body.append(horizonsEl(r));
    const foot = create('div', 'reading-foot');
    const cites = create('span', 'cites', `${r.articleIds.length} headlines · ${new Set(r.articleIds.map(id => (byId.get(id) || {}).sourceCountry)).size} countries`);
    const nav = create('span', 'reading-nav');
    const prev = create('button', 'text', '← previous'), next = create('button', 'text', 'next narrative →');
    prev.addEventListener('click', () => stepReading(-1)); next.addEventListener('click', () => stepReading(1));
    nav.append(prev, next); foot.append(cites, nav); body.append(foot);
    body.scrollTop = 0;
    const openRung = $('.rung.open', body); if (openRung && state.frag) openRung.scrollIntoView({ block: 'start', behavior: 'instant' });
  }
  /* How we got here: the day's pattern placed on four longer trajectories, with a ruler of the moments it cites. */
  const SPAN_YEARS = { decade: 2016, 'half-century': 1976, 'since-2001': 2001, 'since-1945': 1945, 'long-run': 1800 };
  const yearOf = t => { const m = String(t.when || '').match(/\d{4}/); return m ? parseInt(m[0]) : null; };
  function horizonsEl(r) {
    const wrap = create('section', 'horizons');
    wrap.append(create('p', 'sect', 'HOW WE GOT HERE'));
    wrap.append(create('p', 'horizons-intro', 'The same pattern on four longer clocks. A trajectory, not a verdict.'));
    const now = new Date(news.generatedAt || Date.now()).getUTCFullYear();
    const cited = new Map();
    const addT = (id, where) => { const t = library.trajectories.find(x => x.id === id); if (t) { const y = yearOf(t); if (y) cited.set(id, { t, y, where }); } };
    r.rungs.forEach(ru => ru.fragments.forEach(f => (f.trajectoryIds || []).forEach(id => addT(id, 'rung'))));
    r.horizons.forEach(h => (h.trajectoryIds || []).forEach(id => addT(id, h.span)));
    // the ruler: 1945 to now, with earlier moments gathered at the left edge
    const ruler = create('div', 'ruler'); const y0 = 1945, span = now - y0;
    const line = create('div', 'ruler-line'); ruler.append(line);
    [[1945, '1945'], [1973, '1973'], [2001, '2001'], [2016, '2016'], [now, String(now)]].forEach(([y, l]) => { const tk = create('span', 'ruler-tick', l); tk.style.left = ((y - y0) / span * 100) + '%'; ruler.append(tk); });
    const marks = [...cited.values()].sort((a, b) => a.y - b.y); let lastX = -99;
    marks.forEach(({ t, y }) => {
      const x = clamp((y - y0) / span * 100, 0, 100);
      const m = create('a', 'ruler-mark' + (y < y0 ? ' before' : ''), '*'); m.href = t.url; m.target = '_blank'; m.rel = 'noopener noreferrer';
      m.style.left = x + '%'; m.title = `${t.when}: ${t.title}`; m.setAttribute('aria-label', `${t.when}: ${t.title}`);
      if (x - lastX < 2.2) m.classList.add('stack'); lastX = x;
      ruler.append(m);
    });
    wrap.append(ruler);
    r.horizons.forEach(h => {
      const d = create('div', 'horizon ' + h.span);
      const head = create('div', 'horizon-head');
      const from = SPAN_YEARS[h.span];
      head.append(create('span', 'hl', h.label), create('span', 'hy', from ? `${from} to ${now}` : ''));
      d.append(head);
      if (h.lens) d.append(create('p', 'horizon-lens', h.lens));
      d.append(create('p', 'horizon-text', h.text));
      const books = (h.bookIds || []).map(id => library.books.find(b => b.id === id)).filter(Boolean);
      const trajs = (h.trajectoryIds || []).map(id => library.trajectories.find(t => t.id === id)).filter(Boolean);
      if (books.length || trajs.length) {
        const refs = create('div', 'horizon-refs');
        trajs.forEach(t => { const a = create('a', 'ref', ''); a.href = t.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.append(create('span', 'w', `LOOK BACK / ${t.when}`), create('span', 'h', t.title + ' ↗'), create('span', 'q', t.note)); refs.append(a); });
        books.forEach(b => { const a = create('a', 'ref', ''); a.href = b.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.append(create('span', 'w', `READ / ${b.author}, ${b.year}`), create('span', 'h', b.title + ' ↗'), create('span', 'q', b.question)); refs.append(a); });
        const tog = create('button', 'text horizon-toggle', `${trajs.length + books.length} ${trajs.length + books.length === 1 ? 'reference' : 'references'}`); tog.type = 'button'; tog.setAttribute('aria-expanded', 'false');
        tog.addEventListener('click', () => { const open = refs.classList.toggle('open'); tog.setAttribute('aria-expanded', String(open)); });
        d.append(tog, refs);
      }
      wrap.append(d);
    });
    return wrap;
  }
  function fitFocus(ids) {
    const list = ids.map(id => beadById.get(id)).filter(Boolean);
    if (list.length) fitBeads(list, 1.1, 90);
  }
  function fragBody(f) {
    const d = create('div', 'frag-body');
    d.append(create('p', 'frag-text', f.text));
    if (f.articleIds.length) {
      d.append(create('p', 'sect', 'THE HEADLINES'));
      f.articleIds.forEach(id => { const a = byId.get(id); if (a) d.append(sourceEl(a)); });
    }
    const books = (f.bookIds || []).map(id => library.books.find(b => b.id === id)).filter(Boolean);
    const trajs = (f.trajectoryIds || []).map(id => library.trajectories.find(t => t.id === id)).filter(Boolean);
    if (books.length || trajs.length) {
      d.append(create('p', 'sect', 'TAKE IT FURTHER'));
      books.forEach(b => { const a = create('a', 'ref'); a.href = b.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.append(create('span', 'w', `READ / ${b.author}, ${b.year}`), create('span', 'h', b.title + ' ↗'), create('span', 'q', b.question)); d.append(a); });
      trajs.forEach(t => { const a = create('a', 'ref'); a.href = t.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.append(create('span', 'w', `LOOK BACK / ${t.when}`), create('span', 'h', t.title + ' ↗'), create('span', 'q', t.note)); d.append(a); });
    }
    return d;
  }
  function sourceEl(a) {
    const wrap = create('div', 'src-wrap');
    const s = create('a', 'src'); s.href = safeURL(a.url); s.target = '_blank'; s.rel = 'noopener noreferrer';
    const w = create('span', 'w', `${a.sourceCountry} / ${a.publisher}${a.language && a.language !== 'en' ? ' / ' + langName(a.language) : ''} · ${fmt(a.publishedAt || a.seenAt)}`);
    const h = create('span', 'h', headline(a) + ' ↗'); h.dir = 'auto';
    s.append(w, h); const o = alt(a); if (o) { const oe = create('span', 'o', o); oe.dir = 'auto'; oe.lang = a.language || ''; s.append(oe); }
    const loc = create('button', 'text', '◎ field'); loc.type = 'button'; loc.title = 'Find this headline in the field';
    loc.addEventListener('click', () => { if (!locate(a.id)) toast('This headline is from an earlier collection and is not in the field.'); });
    wrap.append(s, loc); return wrap;
  }

  /* ---------- card ---------- */
  function openCard(a, anchor) {
    const card = $('#card'); card.replaceChildren();
    const w = create('div', 'w'); w.append(create('span', '', `${a.sourceCountry} / ${a.publisher}`), create('span', '', langName(a.language)));
    const h = create('p', 'h', headline(a)); h.dir = 'auto'; h.lang = state.lang === 'en' ? 'en' : (a.language || '');
    card.append(w, h);
    const o = alt(a); if (o) { const oe = create('p', 'o', o); oe.dir = 'auto'; oe.lang = state.lang === 'en' ? (a.language || '') : 'en'; card.append(oe); }
    card.append(create('p', 't', `${a.dateBasis === 'published-or-first-seen' ? 'published or first seen' : 'published'} ${fmt(a.publishedAt || a.seenAt)}` + (a.held ? ' · held in the field for the readings; no longer in the collection' : ledger && ledger.departed.some(d => d.id === a.id) ? ' · no longer in this edition' : ledger && ledger.previousAt && ledger.arrived.includes(a.id) ? ' · new in this edition' : '')));
    const go = create('a', 'go', 'Read the story at ' + (a.publisherDomain || a.publisher) + ' ↗'); go.href = safeURL(a.url); go.target = '_blank'; go.rel = 'noopener noreferrer'; card.append(go);
    const cites = readings.readings.filter(r => r.articleIds.includes(a.id));
    if (cites.length) {
      const inn = create('div', 'in'); inn.append(create('div', 'w', 'IN THE NARRATIVES'));
      cites.forEach(r => { const b = create('button', '', r.line); b.type = 'button'; b.addEventListener('click', () => { closeCard(); selectReading(r.id, { open: true }); }); inn.append(b); });
      card.append(inn);
    }
    const x = create('button', 'close', '×'); x.setAttribute('aria-label', 'Close'); x.addEventListener('click', closeCard); card.append(x);
    card.hidden = false;
    if (!mobile()) {
      const r = anchor.getBoundingClientRect(); const cw = card.offsetWidth, ch = card.offsetHeight;
      let left = r.right + 10, top = r.top - 6;
      if (left + cw > window.innerWidth - 12) left = r.left - cw - 10; if (left < 12) left = 12;
      if (top + ch > window.innerHeight - 12) top = window.innerHeight - ch - 12; if (top < 60) top = 60;
      card.style.left = left + 'px'; card.style.top = top + 'px';
    }
    $('#scrim').hidden = false;
  }
  function closeCard() { $('#card').hidden = true; $('#scrim').hidden = true; }

  /* ---------- panels ---------- */
  function openPanel(name) {
    state.panel = state.panel === name ? '' : name;
    ['tide', 'index', 'about'].forEach(n => { $(`#${n}-panel`).hidden = state.panel !== n; $(`[data-open="${n}"]`).setAttribute('aria-pressed', String(state.panel === n)); });
    if (state.panel === 'tide') renderTide(); if (state.panel === 'index') renderIndex(); if (state.panel === 'about') renderAbout();
    writeHash();
  }
  function renderAbout() {
    $('#about-edition').textContent = `Headlines collected ${fmtDate(news.generatedAt)} · ${news.articles.length} headlines, ${new Set(news.articles.map(a => a.sourceCountryCode)).size} countries, ${new Set(news.articles.map(a => a.language)).size} languages · Readings composed ${fmtDate(readings.generatedAt)} (${readings.method}${readings.model ? ', ' + readings.model : ''})` + (ledger && ledger.previousAt ? ` · Previous edition ${fmtDate(ledger.previousAt)}` : '');
  }
  function tideItem(a, ghost) {
    const li = create('li', ghost ? 'ghost' : '');
    li.append(create('span', 'w', `${a.sourceCountry} / ${a.publisher}`));
    const l = create('a', '', headline(a)); l.href = safeURL(a.url) || '#'; l.target = '_blank'; l.rel = 'noopener noreferrer'; l.dir = 'auto'; li.append(l);
    const f = create('button', 'here', 'find'); f.type = 'button'; f.addEventListener('click', () => { if (ghost && !state.ghosts) toggleGhosts(true); if (!locate(a.id)) toast('Not in the field.'); }); li.append(f);
    return li;
  }
  function renderTide() {
    const b = $('#tide-body'); b.replaceChildren();
    if (!ledger) { b.append(create('p', '', 'No ledger yet. The tide begins with the second collection.')); return; }
    b.append(create('p', 'small mono', ledger.previousAt ? `This edition ${fmtDate(ledger.editionAt)} compared with the previous collection ${fmtDate(ledger.previousAt)}.` : `First edition ${fmtDate(ledger.editionAt)}. There is nothing to compare yet.`));
    const c = create('div', 'tide-counts');
    [['arrived', 'ARRIVED'], ['stayed', 'STAYED'], ['departed', 'DEPARTED']].forEach(([k, w]) => { const d = create('div'); d.append(create('div', 'n', String(ledger.counts[k])), create('div', 'w', w)); c.append(d); });
    b.append(c);
    const tg = create('label', 'toggle'); const cb = create('input'); cb.type = 'checkbox'; cb.checked = state.ghosts; cb.addEventListener('change', () => toggleGhosts(cb.checked));
    tg.append(cb, document.createTextNode('show departed headlines as ghosts in the field')); b.append(tg);
    const silent = ledger.countries.filter(x => x.state === 'silent' || x.state === 'fell-silent'), fresh = ledger.countries.filter(x => x.state === 'new-voice');
    if (fresh.length) { b.append(create('p', 'sect', 'NEW VOICES')); b.append(create('p', 'silent-list', fresh.map(x => x.name).join(' · '))); }
    if (silent.length) { b.append(create('p', 'sect', 'SILENT: PUBLISHERS WE LISTEN FOR WHO SAID NOTHING IN THIS SAMPLE')); b.append(create('p', 'silent-list', silent.map(x => x.name + (x.state === 'fell-silent' ? ' (fell silent)' : '')).join(' · '))); }
    const arrived = ledger.arrived.map(id => byId.get(id)).filter(Boolean).slice(0, 14);
    if (arrived.length) { b.append(create('p', 'sect', `ARRIVED · ${ledger.counts.arrived} HEADLINES, A FEW OF THEM`)); const ul = create('ul', 'tide-list'); arrived.forEach(a => ul.append(tideItem(a, false))); b.append(ul); }
    const departed = ledger.departed.slice(0, 14);
    if (departed.length) { b.append(create('p', 'sect', `DEPARTED · ${ledger.counts.departed} HEADLINES NO LONGER IN THE SAMPLE, A FEW OF THEM`)); const ul = create('ul', 'tide-list'); departed.forEach(a => ul.append(tideItem(a, true))); b.append(ul); }
    b.append(create('p', 'small', ledger.notes.join(' ')));
  }
  function toggleGhosts(on) { state.ghosts = on; ghosts.forEach(g => { g.el.hidden = !on; }); worldEl.classList.toggle('tide', on); cameraDirty = true; writeHash(); const cb = $('#tide-body input'); if (cb) cb.checked = on; }

  let indexBuilt = false, region = '';
  function renderIndex() {
    const chips = $('#region-chips');
    if (!indexBuilt) {
      const regions = ['', ...new Set(news.articles.map(a => a.sourceRegion))].sort();
      regions.forEach(rg => { const c = create('button', 'chip', rg || 'Everywhere'); c.type = 'button'; c.dataset.region = rg; c.setAttribute('aria-pressed', String(rg === region)); c.addEventListener('click', () => { region = rg; $$('.chip', chips).forEach(x => x.setAttribute('aria-pressed', String(x.dataset.region === region))); renderIndexList(); }); chips.append(c); });
      $('#search').addEventListener('input', renderIndexList); indexBuilt = true;
    }
    renderIndexList();
  }
  function renderIndexList() {
    const q = $('#search').value.trim().toLowerCase(), ol = $('#index-list'); ol.replaceChildren();
    const list = news.articles.filter(a => (!region || a.sourceRegion === region) && (!q || [a.title, a.titleEnglish, a.publisher, a.sourceCountry, langName(a.language)].join(' ').toLowerCase().includes(q)))
      .sort((a, b) => (b.publishedAt || b.seenAt || '').localeCompare(a.publishedAt || a.seenAt || ''));
    const frag = document.createDocumentFragment();
    list.forEach(a => {
      const li = create('li');
      li.append(create('span', 'w', `${a.sourceCountry} / ${a.publisher}${a.language !== 'en' ? ' / ' + langName(a.language) : ''} · ${fmt(a.publishedAt || a.seenAt)}`));
      const h = create('a', 'h', headline(a)); h.href = safeURL(a.url); h.target = '_blank'; h.rel = 'noopener noreferrer'; h.dir = 'auto'; li.append(h);
      const o = alt(a); if (o) { const oe = create('span', 'o', o); oe.dir = 'auto'; li.append(oe); }
      const f = create('button', 'here', 'find in the field'); f.type = 'button'; f.addEventListener('click', () => locate(a.id)); li.append(f);
      frag.append(li);
    });
    ol.append(frag);
    if (!list.length) ol.append(create('li', '', 'Nothing matches. Try fewer words.'));
  }

  /* ---------- language, night ---------- */
  function setLang(l) {
    state.lang = l; $('#lang').setAttribute('aria-pressed', String(l === 'orig')); $('#lang').innerHTML = l === 'orig' ? '<span class="long">English</span><span class="short">EN</span>' : '<span class="long">Original</span><span class="short">文</span>';
    beads.forEach(fillBead); ghosts.forEach(fillBead);
    if (state.drawer) renderDrawer(); if (state.panel === 'index') renderIndexList(); if (state.panel === 'tide') renderTide();
    try { localStorage.setItem('pt-lang', l); } catch {}
    writeHash();
  }
  function setNight(on) { document.documentElement.dataset.theme = on ? 'night' : ''; $('#night').setAttribute('aria-pressed', String(on)); $('meta[name=theme-color]').content = on ? '#050505' : '#ffffff'; try { localStorage.setItem('pt-night', on ? '1' : '0'); } catch {} cameraDirty = true; }

  /* ---------- pointer: pan, zoom, pinch ---------- */
  function bindField() {
    const pointers = new Map(); let start = null, pinch = null;
    fieldEl.addEventListener('pointerdown', e => {
      if (e.button !== 0 && e.pointerType === 'mouse') return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 1) { start = { x: e.clientX, y: e.clientY, px: state.panX, py: state.panY }; dragged = false; fieldEl.setPointerCapture(e.pointerId); }
      if (pointers.size === 2) { zoomTarget = null; cancelAnimationFrame(anim); const [a, b] = [...pointers.values()]; const rect = fieldEl.getBoundingClientRect(); pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: state.z, anchor: anchorAt((a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top) }; }
    });
    fieldEl.addEventListener('pointermove', e => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2 && pinch) {
        const [a, b] = [...pointers.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y);
        const rect = fieldEl.getBoundingClientRect();
        zoomAt(pinch.z * d / pinch.d, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top, pinch.anchor); dragged = true; return;
      }
      if (start && pointers.size === 1) {
        const dx = e.clientX - start.x, dy = e.clientY - start.y;
        if (!dragged && Math.hypot(dx, dy) > 4) { dragged = true; fieldEl.classList.add('dragging'); cancelAnimationFrame(anim); }
        if (dragged) { state.panX = start.px + dx; state.panY = start.py + dy; cameraDirty = true; }
      }
    });
    const up = e => { pointers.delete(e.pointerId); if (pointers.size < 2) pinch = null; if (!pointers.size) { start = null; fieldEl.classList.remove('dragging'); setTimeout(() => { dragged = false; }, 0); } };
    fieldEl.addEventListener('pointerup', up); fieldEl.addEventListener('pointercancel', up);
    fieldEl.addEventListener('wheel', e => {
      e.preventDefault(); const rect = fieldEl.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 20 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      const factor = Math.exp(-clamp(dy, -120, 120) * (e.ctrlKey ? 0.012 : 0.0028));
      const base = zoomTarget ? zoomTarget.z : state.z, sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      cancelAnimationFrame(anim);
      const anchor = zoomTarget && zoomTarget.anchor && Math.hypot(sx - zoomTarget.sx, sy - zoomTarget.sy) < 40 ? zoomTarget.anchor : anchorAt(sx, sy);
      if (anchor && anchor !== (zoomTarget && zoomTarget.anchor)) { anchor.sx = sx; anchor.sy = sy; }
      zoomTarget = { z: clamp(base * factor, zMin(), Z_MAX), sx: anchor ? anchor.sx : sx, sy: anchor ? anchor.sy : sy, anchor };
    }, { passive: false });
    fieldEl.addEventListener('dblclick', e => {
      if (e.target.closest('.bead')) return;
      const rect = fieldEl.getBoundingClientRect();
      zoomBy(e.shiftKey ? 1 / 2.2 : 2.2, e.clientX - rect.left, e.clientY - rect.top, 520);
    });
    fieldEl.addEventListener('click', e => { if (!dragged && (e.target === fieldEl || e.target === ground || e.target === worldEl)) closeCard(); });
    $('#zoom-in').addEventListener('click', () => zoomBy(1.7));
    $('#zoom-out').addEventListener('click', () => zoomBy(1 / 1.7));
    $('#zoom-fit').addEventListener('click', () => currentReading() ? fitReading() : fitWorld());
    $('#zoom-world').addEventListener('click', fitWorld);
  }

  /* ---------- events ---------- */
  function bind() {
    bindField();
    $('#narratives-clear').addEventListener('click', () => { selectReading('', { open: false, fit: false }); fitWorld(); });
    if ('ResizeObserver' in window) {
      const setStrip = () => { document.documentElement.style.setProperty('--strip-h', stripH() + 'px'); sizeCanvas(); cameraDirty = true; };
      new ResizeObserver(setStrip).observe($('#narratives')); setStrip();
    }
    $$('[data-open]').forEach(b => b.addEventListener('click', e => { e.preventDefault(); openPanel(b.dataset.open); }));
    $$('[data-close]').forEach(b => b.addEventListener('click', () => { if (b.dataset.close === 'drawer') { state.drawer = false; document.body.classList.toggle('drawer-open', false); $('#drawer').hidden = true; setFocus(null); writeHash(); } else openPanel(b.dataset.close); }));
    $('[data-action="home"]').addEventListener('click', e => { e.preventDefault(); if (state.panel) openPanel(state.panel); selectReading(readings.readings[0].id, { open: false }); });
    $('#lang').addEventListener('click', () => setLang(state.lang === 'en' ? 'orig' : 'en'));
    $('#night').addEventListener('click', () => setNight(document.documentElement.dataset.theme !== 'night'));
    $('#scrim').addEventListener('click', closeCard);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { if (!$('#card').hidden) return closeCard(); if (state.panel) return openPanel(state.panel); if (state.drawer) { state.drawer = false; document.body.classList.remove('drawer-open'); $('#drawer').hidden = true; setFocus(null); writeHash(); } return; }
      if (e.target.matches('input, textarea')) return;
      if (e.key === 'ArrowRight' && e.altKey) stepReading(1); if (e.key === 'ArrowLeft' && e.altKey) stepReading(-1);
      if (e.key === '+' || e.key === '=') zoomBy(1.7); if (e.key === '-' || e.key === '_') zoomBy(1 / 1.7); if (e.key === '0') fitWorld(); if (e.key === '1') fitReading();
    });
    window.addEventListener('resize', () => { sizeCanvas(); if (state.z < zMin()) { const v = viewport(); zoomAt(zMin(), v.w / 2, v.h / 2); } cameraDirty = true; });
    document.addEventListener('visibilitychange', () => { cameraDirty = true; });
    matchMedia('(prefers-color-scheme: dark)');
  }

  /* ---------- init ---------- */
  async function init() {
    readHash();
    try { if (!location.hash.includes('lang=') && localStorage.getItem('pt-lang') === 'orig') state.lang = 'orig'; if (localStorage.getItem('pt-night') === '1') setNight(true); } catch {}
    try { await load(); } catch (e) { $('#edition').textContent = 'The collection could not be loaded. Serve this folder over HTTP.'; errlog.textContent += String(e); return; }
    setLang(state.lang);
    const countries = new Set(news.articles.map(a => a.sourceCountryCode)).size, langs = new Set(news.articles.map(a => a.language)).size;
    $('#edition').textContent = `${fmt(news.generatedAt)} · ${news.articles.length} headlines · ${countries} countries · ${langs} languages`;
    if (readings.newsGeneratedAt && readings.newsGeneratedAt !== news.generatedAt) $('#edition').textContent += held.length ? ` · readings from ${fmt(readings.newsGeneratedAt)}, ${held.length} of their headlines held in the field` : ' · readings are from an earlier collection';
    sizeCanvas(); buildField(); bind();
    if (state.ghosts) toggleGhosts(true);
    const first = readings.readings.find(r => r.id === state.reading) ? state.reading : readings.readings[0].id;
    if (!state.reading) state.reading = first;
    // start on the whole world, then settle onto the constellation
    state.z = zMin(); const v = viewport(); state.panX = v.w / 2 - WORLD_W / 2 * state.z; state.panY = v.h / 2 + 10 - WORLD_H / 2 * state.z; applyBucket();
    requestAnimationFrame(frame);
    selectReading(first, { open: state.drawer, fit: !state.debugZ });
    if (state.debugZ) { const v2 = viewport(); state.z = state.debugZ; const c = toWorld(isNaN(state.debugLon) ? 10 : state.debugLon, isNaN(state.debugLat) ? 48 : state.debugLat); state.panX = v2.w / 2 - c[0] * state.z; state.panY = v2.h / 2 - c[1] * state.z; applyBucket(); cameraDirty = true; }
    if (state.panel) { const p = state.panel; state.panel = ''; openPanel(p); }
    $('#hint').hidden = mobile();
  }
  init();
})();
