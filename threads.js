/* Threads: the narratives of The Present Tense across editions, and the Chronicle beneath them. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const create = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; };
  const svgEl = (tag, attrs = {}) => { const el = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const k in attrs) el.setAttribute(k, attrs[k]); return el; };
  const stampDate = s => new Date(`${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}T${s.slice(9, 11)}:${s.slice(11, 13)}:00Z`);
  const fmt = (s, withTime = true) => { const d = typeof s === 'string' && /^\d{8}T/.test(s) ? stampDate(s) : new Date(s); if (isNaN(d)) return String(s); return d.toLocaleString('en-GB', withTime ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' } : { day: 'numeric', month: 'short', timeZone: 'UTC' }) + (withTime ? ' UTC' : ''); };
  const SCALES = { day: { colW: 230, labelMin: 1 }, week: { colW: 80, labelMin: 2 }, month: { colW: 30, labelMin: 3 } };
  let scale = 'day', editions = [], chronicle = null, versions = [], nodes = new Map(), chains = [], attentionDays = [];

  async function getJSON(path) { const r = await fetch(path, { cache: 'no-cache' }); if (!r.ok) throw Error(`${path}: HTTP ${r.status}`); return r.json(); }

  /* ---------- the chains ---------- */
  function buildChains() {
    nodes = new Map(); chains = [];
    editions.forEach((e, col) => e.narratives.forEach((n, row) => nodes.set(`${e.stamp}|${n.id}`, { stamp: e.stamp, id: n.id, line: n.line, kicker: n.kicker, headlines: n.headlines || 0, events: n.events || 0, continues: n.continues || '', col, row, next: [], prev: null, edition: e })));
    editions.forEach((e, col) => {
      if (col === 0) return;
      const before = editions[col - 1];
      e.narratives.forEach(n => {
        if (!n.continues) return;
        const p = nodes.get(`${before.stamp}|${n.continues}`), me = nodes.get(`${e.stamp}|${n.id}`);
        if (p && me) { p.next.push(me); me.prev = p; }
      });
    });
    // the Chronicle's own grouping: where it runs narratives together that do not declare a continuation, draw that too, dotted
    (chronicle && chronicle.threads || []).forEach(t => {
      const members = t.narratives.map(r => nodes.get(`${r.stamp}|${r.id}`)).filter(Boolean).sort((a, b) => a.col - b.col);
      for (let i = 1; i < members.length; i++) {
        const a = members[i - 1], b = members[i];
        if (a.col >= b.col || b.prev) continue;
        a.next.push(b); b.prev = a; b.grouped = true;
      }
    });
    // a chain follows first successors; further successors begin chains of their own, still linked by a line
    const used = new Set();
    [...nodes.values()].sort((a, b) => a.col - b.col || a.row - b.row).forEach(n => {
      if (used.has(n)) return;
      if (n.prev && !used.has(n.prev)) return;
      if (n.prev && n.prev.next[0] === n) return;  // reached by its predecessor's chain
      const c = []; let cur = n;
      while (cur && !used.has(cur)) { c.push(cur); used.add(cur); cur = cur.next[0]; }
      chains.push(c);
    });
    // lanes: a chain takes the first lane that is free from its first column
    const lanes = [];
    chains.sort((a, b) => a[0].col - b[0].col || b.length - a.length || a[0].row - b[0].row);
    chains.forEach(c => {
      const start = c[0].col, end = c[c.length - 1].col;
      let lane = lanes.findIndex(last => last < start - 1);  // a column of space, so unrelated runs never sit side by side
      if (lane < 0) { lane = lanes.length; lanes.push(end); } else lanes[lane] = end;
      c.lane = lane; c.forEach(n => { n.lane = lane; n.chain = c; });
    });
    return lanes.length;
  }

  /* ---------- the loom ---------- */
  const LANE_H = 34, TOP = 44, LEFT = 24, RIGHT = 380;
  const phone = () => window.innerWidth <= 760;
  /* On a phone time runs down the page: each edition is a row, newest at the top, lanes run across, and the newest row's
     narratives are numbered and listed beneath, since there is no room for lines of text beside the marks. */
  const ROWS = { day: 64, week: 30, month: 14 };
  let picked = null;
  function drawLoomVertical() {
    const svg = $('#loom'); svg.replaceChildren(); picked = null; $('#loom-tip').hidden = true;
    const laneCount = buildChains(), rowH = ROWS[scale];
    const W = Math.max(300, $('#loom-scroll').clientWidth - 2), left = 108, right = 20;
    const laneW = Math.min(44, (W - left - right) / Math.max(1, laneCount));
    const n = editions.length, top = 14, h = top + n * rowH + 16;
    svg.setAttribute('viewBox', `0 0 ${W} ${h}`); svg.setAttribute('width', W); svg.setAttribute('height', h);
    const x = lane => left + lane * laneW + laneW / 2, y = col => top + (n - 1 - col) * rowH + rowH / 2;
    const dayOf = e => `${e.stamp.slice(0, 4)}-${e.stamp.slice(4, 6)}-${e.stamp.slice(6, 8)}`;
    let lastDay = '';
    editions.forEach((e, col) => {
      const g = svgEl('g', { class: 'col' + (col === n - 1 ? ' now' : '') });
      g.append(svgEl('line', { x1: left - 10, x2: W - right, y1: y(col), y2: y(col) }));
      const day = dayOf(e), showLabel = scale === 'day' || day !== lastDay || col === n - 1; lastDay = day;
      if (showLabel) {
        const t = svgEl('text', { x: 0, y: y(col) - 3, class: 'when' }); t.textContent = scale === 'day' ? fmt(e.stamp).replace(' UTC', '').toUpperCase() : fmt(e.stamp, false).toUpperCase(); g.append(t);
        if (scale === 'day') { const m = svgEl('text', { x: 0, y: y(col) + 10, class: 'meta' }); m.textContent = `${e.narratives.length}${col === n - 1 ? ' · NOW' : ''}`; g.append(m); }
      }
      svg.append(g);
    });
    nodes.forEach(a => a.next.forEach(b => {
      const p = svgEl('path', { class: 'link' + (b.grouped ? ' grouped' : ''), d: `M${x(a.lane)},${y(a.col)} C${x(a.lane)},${y(a.col) - rowH * 0.45} ${x(b.lane)},${y(b.col) + rowH * 0.45} ${x(b.lane)},${y(b.col)}`, 'stroke-width': (1 + Math.min(a.headlines, b.headlines) / 9).toFixed(1) });
      p.dataset.from = `${a.stamp}|${a.id}`; p.dataset.to = `${b.stamp}|${b.id}`; svg.append(p);
    }));
    const legend = [];
    chains.forEach(c => c.forEach(m => {
      const r = Math.min(laneW / 2 - 2, 3 + Math.sqrt(m.headlines) * 0.9);
      const g = svgEl('g', { class: 'bead', tabindex: '0', role: 'button' }); g.dataset.key = `${m.stamp}|${m.id}`;
      g.append(svgEl('circle', { cx: x(m.lane), cy: y(m.col), r: r.toFixed(1) }));
      g.append(svgEl('circle', { cx: x(m.lane), cy: y(m.col), r: (r + 9).toFixed(1), class: 'halo' }));
      if (m.col === n - 1) { legend.push(m); const t = svgEl('text', { x: x(m.lane), y: y(m.col) - r - 5, 'text-anchor': 'middle', class: 'num' }); t.textContent = String(legend.length); svg.append(t); }
      const title = svgEl('title'); title.textContent = `${fmt(m.stamp)} · ${m.kicker}\n${m.line}`; g.append(title);
      // first tap shows the narrative; a second tap on the same mark opens it
      g.addEventListener('click', () => { if (picked === m) { location.href = `./#edition=${m.stamp}&reading=${encodeURIComponent(m.id)}&open=1`; return; } picked = m; showPick(m); });
      g.addEventListener('keydown', e => { if (e.key === 'Enter') g.click(); });
      svg.append(g);
    }));
    const lg = $('#loom-legend'); lg.replaceChildren();
    legend.sort((a, b) => a.lane - b.lane).forEach((m, i) => {
      const b = create('button', 'legend-item'); b.type = 'button';
      b.append(create('span', 'num mono', String(i + 1)), create('span', 'line', m.line), create('span', 'm mono', `${m.kicker}${m.chain && m.chain.length > 1 ? ` · thread of ${m.chain.length} editions` : ''}`));
      b.addEventListener('click', () => { location.href = `./#edition=${m.stamp}&reading=${encodeURIComponent(m.id)}&open=1`; });
      lg.append(b);
    });
    $('#loom-count').textContent = `${editions.length} EDITIONS · ${nodes.size} NARRATIVES · ${chains.filter(c => c.length > 1).length} THREADS THAT RAN MORE THAN ONE EDITION`;
  }
  function showPick(m) {
    const tip = $('#loom-tip'); tip.replaceChildren(create('span', 'k', `${fmt(m.stamp)} · ${m.kicker}`), create('span', 'n', m.line), create('span', 'm', `${m.events ? m.events + ' events · ' : ''}${m.headlines} headlines${m.chain && m.chain.length > 1 ? ` · thread of ${m.chain.length} editions` : ''} · tap again to open`));
    tip.hidden = false; tip.style.left = ''; tip.style.top = '';
    $$('#loom .bead').forEach(b => b.classList.toggle('hot', b.dataset.key === `${m.stamp}|${m.id}`));
  }
  function drawLoom() {
    if (phone()) return drawLoomVertical();
    $('#loom-legend').replaceChildren();
    const svg = $('#loom'); svg.replaceChildren();
    const laneCount = buildChains(), { colW, labelMin } = SCALES[scale];
    const dayOf = e => `${e.stamp.slice(0, 4)}-${e.stamp.slice(4, 6)}-${e.stamp.slice(6, 8)}`;
    const looked = scale === 'day' ? editions.map(e => attentionDays.find(d => d.date === dayOf(e)) || null) : [];
    const lookedRows = looked.some(Boolean) ? 6 : 0;
    const w = LEFT + Math.max(1, editions.length) * colW + RIGHT, h = TOP + Math.max(1, laneCount) * LANE_H + 24 + (lookedRows ? 16 + lookedRows * 15 : 0);
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`); svg.setAttribute('width', w); svg.setAttribute('height', h);
    const x = col => LEFT + col * colW + colW / 2, y = lane => TOP + lane * LANE_H + LANE_H / 2;
    // columns
    editions.forEach((e, col) => {
      const g = svgEl('g', { class: 'col' + (col === editions.length - 1 ? ' now' : '') });
      g.append(svgEl('line', { x1: x(col), x2: x(col), y1: TOP - 10, y2: h - 20 }));
      if (scale === 'day' || col % (scale === 'week' ? 2 : 7) === 0 || col === editions.length - 1) {
        const t = svgEl('text', { x: x(col), y: 16, 'text-anchor': 'middle', class: 'when' }); t.textContent = fmt(e.stamp, scale === 'day').toUpperCase(); g.append(t);
        if (scale === 'day') { const m = svgEl('text', { x: x(col), y: 30, 'text-anchor': 'middle', class: 'meta' }); m.textContent = `${e.narratives.length} NARRATIVES${col === editions.length - 1 ? ' · NOW' : ''}`; g.append(m); }
      }
      svg.append(g);
    });
    // links
    nodes.forEach(n => n.next.forEach(m => {
      const p = svgEl('path', { class: 'link' + (m.grouped ? ' grouped' : ''), d: `M${x(n.col)},${y(n.lane)} C${x(n.col) + colW * 0.45},${y(n.lane)} ${x(m.col) - colW * 0.45},${y(m.lane)} ${x(m.col)},${y(m.lane)}`, 'stroke-width': (1 + Math.min(n.headlines, m.headlines) / 9).toFixed(1) });
      p.dataset.from = `${n.stamp}|${n.id}`; p.dataset.to = `${m.stamp}|${m.id}`; svg.append(p);
    }));
    // beads and labels
    chains.forEach(c => {
      c.forEach(n => {
        const r = 3 + Math.sqrt(n.headlines) * 0.9;
        const g = svgEl('g', { class: 'bead', tabindex: '0', role: 'link' }); g.dataset.key = `${n.stamp}|${n.id}`;
        g.append(svgEl('circle', { cx: x(n.col), cy: y(n.lane), r: r.toFixed(1) }));
        g.append(svgEl('circle', { cx: x(n.col), cy: y(n.lane), r: (r + 7).toFixed(1), class: 'halo' }));
        const title = svgEl('title'); title.textContent = `${fmt(n.stamp)} · ${n.kicker}\n${n.line}`; g.append(title);
        g.addEventListener('click', () => { location.href = `./#edition=${n.stamp}&reading=${encodeURIComponent(n.id)}&open=1`; });
        g.addEventListener('keydown', e => { if (e.key === 'Enter') g.click(); });
        g.addEventListener('mouseenter', e => showTip(n, e)); g.addEventListener('mousemove', e => showTip(n, e)); g.addEventListener('mouseleave', hideTip);
        svg.append(g);
      });
      if (c.length >= labelMin) {
        // the newest column carries full lines; earlier columns carry the kicker, clipped to the column, so labels never run into the next day
        const last = c[c.length - 1], atEnd = last.col === editions.length - 1;
        const label = atEnd && scale === 'day' ? last.line : last.kicker;
        const room = atEnd ? 78 : Math.max(6, Math.floor((colW - 30) / 6.4));
        const t = svgEl('text', { x: x(last.col) + 12, y: y(last.lane) + 4, class: 'tl' + (c.length > 1 ? ' thread' : '') + (atEnd ? ' now' : '') });
        t.textContent = label.length > room ? label.slice(0, room - 1) + '…' : label; svg.append(t);
      }
    });
    // beneath the narratives: what people reached for that day, the subjects viewed in most language editions
    if (lookedRows) {
      const y0 = TOP + Math.max(1, laneCount) * LANE_H + 18;
      const head = svgEl('text', { x: LEFT, y: y0, class: 'meta' }); head.textContent = 'LOOKED UP · WIKIPEDIA SUBJECTS VIEWED IN MOST LANGUAGE EDITIONS THAT DAY'; svg.append(head);
      const shown = new Set();
      looked.forEach((d, col) => {
        if (!d || shown.has(d.date)) return; shown.add(d.date);
        d.top.slice(0, 5).forEach((g, i) => {
          const t = svgEl('text', { x: x(col) - colW / 2 + 10, y: y0 + 16 + i * 15, class: 'lu' }); const room = Math.floor((colW - 20) / 6.2);
          t.textContent = `${g.editions} · ${g.title.length > room ? g.title.slice(0, room - 1) + '…' : g.title}`; const tt = svgEl('title'); tt.textContent = `${g.title}: viewed in ${g.editions} language editions on ${d.date}`; t.append(tt);
          t.addEventListener('click', () => window.open(g.url, '_blank', 'noopener')); svg.append(t);
        });
      });
    }
    $('#loom-count').textContent = `${editions.length} EDITIONS · ${nodes.size} NARRATIVES · ${chains.filter(c => c.length > 1).length} THREADS THAT RAN MORE THAN ONE EDITION`;
    const sc = $('#loom-scroll'); if (sc.scrollWidth > sc.clientWidth) sc.scrollLeft = Math.max(0, x(editions.length - 1) + 300 - sc.clientWidth);
  }
  function showTip(n, e) {
    const tip = $('#loom-tip'); tip.replaceChildren(create('span', 'k', `${fmt(n.stamp)} · ${n.kicker}`), create('span', 'n', n.line), create('span', 'm', `${n.events ? n.events + ' events · ' : ''}${n.headlines} headlines${n.chain && n.chain.length > 1 ? ` · thread of ${n.chain.length} editions` : ''}`));
    tip.hidden = false; const r = $('.loom-wrap').getBoundingClientRect();
    tip.style.left = Math.min(e.clientX - r.left + 14, r.width - 300) + 'px'; tip.style.top = (e.clientY - r.top + 14) + 'px';
  }
  function hideTip() { $('#loom-tip').hidden = true; }
  function hot(refs, on) { const keys = new Set(refs.map(r => `${r.stamp}|${r.id}`)); $$('#loom .bead').forEach(b => b.classList.toggle('hot', on && keys.has(b.dataset.key))); $$('#loom .link').forEach(l => l.classList.toggle('hot', on && keys.has(l.dataset.from) && keys.has(l.dataset.to))); }

  /* ---------- the chronicle ---------- */
  function renderChronicle(ch, { earlier = false } = {}) {
    const body = $('#chronicle-body'); body.replaceChildren();
    if (!ch) {
      $('#chronicle-meta').textContent = 'NOT YET WRITTEN';
      body.append(create('p', 'chronicle-empty', 'The Chronicle is revised after each edition of narratives. The first version arrives with the next run.'));
      return;
    }
    $('#chronicle-meta').textContent = `REVISED FOR THE EDITION OF ${fmt(ch.asOf).toUpperCase()} · WRITTEN ${fmt(ch.generatedAt).toUpperCase()}${ch.model ? ' · ' + ch.model.toUpperCase() : ''}${earlier ? ' · AN EARLIER VERSION' : ''}`;
    body.append(create('p', 'standing', ch.standing));
    const two = create('div', 'chronicle-two');
    if (ch.moved && ch.moved.length) { const s = create('section'); s.append(create('p', 'sect', 'WHAT MOVED')); const ul = create('ul', 'plain'); ch.moved.forEach(m => ul.append(create('li', '', m))); s.append(ul); two.append(s); }
    if (ch.silent && ch.silent.length) { const s = create('section'); s.append(create('p', 'sect', 'WHAT FELL SILENT')); const ul = create('ul', 'plain'); ch.silent.forEach(m => ul.append(create('li', '', m))); s.append(ul); two.append(s); }
    if (two.children.length) body.append(two);
    const threads = (ch.threads || []).slice().sort((a, b) => (a.status === b.status ? 0 : a.status === 'live' ? -1 : 1) || (b.lastSeen > a.lastSeen ? 1 : -1));
    const live = threads.filter(t => t.status === 'live'), silent = threads.filter(t => t.status !== 'live');
    const list = (items, head) => {
      if (!items.length) return;
      body.append(create('p', 'sect', head));
      items.forEach(t => {
        const art = create('article', 'thread' + (t.status === 'live' ? '' : ' silent'));
        const h = create('h2'); h.append(create('span', 'label', t.label));
        const meta = create('p', 'thread-meta mono', `${t.since === t.lastSeen ? fmt(t.since, false).toUpperCase() : fmt(t.since, false).toUpperCase() + ' TO ' + fmt(t.lastSeen, false).toUpperCase()} · ${t.narratives.length} NARRATIVE${t.narratives.length === 1 ? '' : 'S'}${t.status === 'live' ? '' : ' · SILENT'}`);
        art.append(h, meta, create('p', 'thread-text', t.text));
        if (t.direction) art.append(create('p', 'thread-direction', t.direction));
        const refs = create('p', 'thread-refs mono');
        t.narratives.forEach(n => {
          const node = nodes.get(`${n.stamp}|${n.id}`); const a = create('a', 'ref', `${fmt(n.stamp, false)}: ${node ? node.line : n.id}`);
          a.href = `./#edition=${n.stamp}&reading=${encodeURIComponent(n.id)}&open=1`; refs.append(a);
        });
        art.append(refs);
        art.addEventListener('mouseenter', () => hot(t.narratives, true)); art.addEventListener('mouseleave', () => hot(t.narratives, false));
        body.append(art);
      });
    };
    list(live, 'THE THREADS'); list(silent, 'SILENT');
    if (ch.caseAgainst) { body.append(create('p', 'sect', 'THE CASE AGAINST THIS CHRONICLE')); body.append(create('p', 'case', ch.caseAgainst)); }
    if (ch.revision) { body.append(create('p', 'sect', 'WHAT CHANGED IN THE CHRONICLE')); body.append(create('p', 'revision', ch.revision)); }
    if (versions.length > 1) {
      body.append(create('p', 'sect', 'EARLIER VERSIONS'));
      const p = create('p', 'versions mono');
      versions.forEach(v => {
        const b = create('button', 'text' + (v.stamp === ch.editionStamp ? ' current' : ''), `for ${fmt(v.asOf, false)}`); b.type = 'button';
        b.addEventListener('click', async () => { try { renderChronicle(await getJSON(v.file), { earlier: v.stamp !== chronicle.editionStamp }); window.scrollTo({ top: $('#chronicle').offsetTop - 60, behavior: 'smooth' }); } catch { } });
        p.append(b);
      });
      body.append(p);
    }
    if (ch.notes) body.append(create('p', 'note', ch.notes.join(' ')));
  }

  /* ---------- init ---------- */
  function setNight(on) { document.documentElement.dataset.theme = on ? 'night' : ''; $('#night').setAttribute('aria-pressed', String(on)); try { localStorage.setItem('pt-night', on ? '1' : '0'); } catch {} }
  async function init() {
    try { if (localStorage.getItem('pt-night') === '1') setNight(true); } catch {}
    $('#night').addEventListener('click', () => setNight(document.documentElement.dataset.theme !== 'night'));
    try { editions = (await getJSON('data/narratives/index.json')).editions.slice().reverse(); } catch (e) { $('#loom-count').textContent = 'THE EDITIONS COULD NOT BE LOADED'; return; }
    try { chronicle = await getJSON('data/chronicle.json'); } catch { chronicle = null; }
    try { versions = (await getJSON('data/chronicle/index.json')).versions || []; } catch { versions = []; }
    try { attentionDays = (await getJSON('data/attention/index.json')).days || []; } catch { attentionDays = []; }
    $('#threads-edition').textContent = `THREADS · ${editions.length} EDITIONS SINCE ${fmt(editions[0].stamp, false).toUpperCase()}`;
    $$('[data-scale]').forEach(b => b.addEventListener('click', () => { scale = b.dataset.scale; $$('[data-scale]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawLoom(); }));
    drawLoom(); renderChronicle(chronicle);
    let lastPhone = phone(), rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (phone() !== lastPhone || phone()) { lastPhone = phone(); drawLoom(); } }, 150); });
  }
  init();
})();
