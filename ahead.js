/* Ahead: where the narratives of The Present Tense say things go. The board of open expectations over the next four
   weeks, the paths each narrative in today's edition could take with the one the writer favours, and the record of
   every expectation the site has set and how it was settled. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const create = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; };
  const svgEl = (tag, attrs = {}) => { const el = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const k in attrs) el.setAttribute(k, attrs[k]); return el; };
  const fmtDay = (iso, weekday = false) => { const d = new Date(iso); return isNaN(d) ? String(iso) : d.toLocaleString('en-GB', weekday ? { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' } : { day: 'numeric', month: 'short', timeZone: 'UTC' }); };
  const dayOf = iso => Math.floor(new Date(iso).getTime() / 864e5);
  const dayISO = d => new Date(d * 864e5).toISOString().slice(0, 10);
  const WORD = { open: 'OPEN', kept: 'KEPT', failed: 'FAILED' };
  const WEIGHT = { favoured: 0, possible: 1, unlikely: 2 };
  let readings = null, ledger = null;

  async function getJSON(path) { const r = await fetch(path, { cache: 'no-cache' }); if (!r.ok) throw Error(`${path}: HTTP ${r.status}`); return r.json(); }
  const openNarrative = w => `./#edition=${w.stamp}&reading=${encodeURIComponent(w.narrativeId)}&open=1`;
  function headlineLinks(w) {
    return (w.resolved && w.resolved.headlines || []).map(h => { const a = create('a', 'wl-h'); a.href = h.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.append(create('span', 'w mono', `${h.publisher || ''}${h.sourceCountry ? ' · ' + h.sourceCountry : ''}`), create('span', 'q', (h.titleEnglish || h.title || '') + ' ↗')); return a; });
  }

  /* ---------- the board: every open expectation on the next four weeks, and the list beneath, day by day ---------- */
  function renderBoard(items) {
    const meta = $('#board-meta'), strip = $('#board-strip'), body = $('#board-body'); strip.replaceChildren(); body.replaceChildren();
    const open = items.filter(w => w.status === 'open').sort((a, b) => (a.by < b.by ? -1 : a.by > b.by ? 1 : 0));
    const n = st => items.filter(w => w.status === st).length;
    if (!items.length) {
      meta.textContent = 'NOT YET BEGUN';
      body.append(create('p', 'chronicle-empty', 'From its next edition each narrative sets one or two things to watch for. They will be laid out here on the four weeks ahead.'));
      return;
    }
    const today = dayOf(new Date().toISOString());
    meta.textContent = `${open.length} OPEN${open.length ? ' · NEXT DUE ' + fmtDay(open[0].by).toUpperCase() : ''} · ${n('kept')} KEPT · ${n('failed')} FAILED · ${items.length} SET SINCE ${fmtDay(items.map(w => w.asOf).sort()[0]).toUpperCase()}`;
    // the strip: a week back and four weeks forward from today
    const d0 = today - 7, span = 35, W = 720, H = 74, x0 = 12, x1 = W - 12, ax = 46;
    const X = d => x0 + (x1 - x0) * Math.max(0, Math.min(span, d)) / span;
    const s = svgEl('svg', { class: 'board-svg', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'The next four weeks, with a mark on each expectation' });
    s.append(svgEl('line', { class: 'axis', x1: x0, x2: x1, y1: ax, y2: ax }));
    for (let d = 0; d <= span; d++) {
      const x = X(d), iso = dayISO(d0 + d), week = (d0 + d - today) % 7 === 0;
      s.append(svgEl('line', { class: 'tick' + (week ? ' week' : ''), x1: x, x2: x, y1: ax - (week ? 5 : 2), y2: ax + (week ? 5 : 2) }));
      if (week) { const t = svgEl('text', { x, y: ax + 17, 'text-anchor': d === 0 ? 'start' : d === span ? 'end' : 'middle' }); t.textContent = fmtDay(iso).toUpperCase(); s.append(t); }
    }
    const g = svgEl('g', { class: 'today' }), tx = X(7);
    g.append(svgEl('line', { x1: tx, x2: tx, y1: 6, y2: ax + 6 }));
    const tt = svgEl('text', { x: tx + 4, y: 11 }); tt.textContent = 'TODAY'; g.append(tt); s.append(g);
    const stack = {};
    const onStrip = items.filter(w => { const d = dayOf(w.by) - d0; return d >= 0 && d <= span && (w.status === 'open' || dayOf(w.by) >= today - 7); });
    onStrip.sort((a, b) => (a.by < b.by ? -1 : 1)).forEach(w => {
      const d = dayOf(w.by) - d0, x = X(d), lift = (stack[d] || 0) * 10; stack[d] = (stack[d] || 0) + 1;
      const m = svgEl('g', { class: 'm ' + w.status, tabindex: '0', role: 'link' });
      if (w.status === 'failed') m.append(svgEl('line', { x1: x - 4, x2: x + 4, y1: ax - 4 - lift, y2: ax + 4 - lift }), svgEl('line', { x1: x - 4, x2: x + 4, y1: ax + 4 - lift, y2: ax - 4 - lift }));
      else m.append(svgEl('circle', { cx: x, cy: ax - lift, r: 4.5 }));
      const title = svgEl('title'); title.textContent = `${WORD[w.status]} · by ${fmtDay(w.by)}: ${w.what}`; m.append(title);
      const go = () => { const el = document.getElementById('x-' + w.id); if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.classList.add('lit'); setTimeout(() => el.classList.remove('lit'), 1600); } };
      m.addEventListener('click', go); m.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      s.append(m);
    });
    strip.append(s);
    // the list, day by day
    if (!open.length) { body.append(create('p', 'chronicle-empty', 'Nothing is open. Every expectation set so far has been settled; the record is below.')); return; }
    let lastDay = null, ol = null;
    open.forEach(w => {
      const day = w.by.slice(0, 10);
      if (day !== lastDay) {
        lastDay = day; const rel = dayOf(day) - today;
        const h = create('p', 'day-head mono'); h.id = 'day-' + day;
        h.append(create('span', 'd', fmtDay(day, true).toUpperCase()), create('span', 'r', rel === 0 ? 'TODAY' : rel < 0 ? `${-rel} DAY${rel === -1 ? '' : 'S'} AGO · DUE, NOT YET CHECKED` : `IN ${rel} DAY${rel === 1 ? '' : 'S'}`));
        body.append(h); ol = create('ol', 'watch-ledger'); body.append(ol);
      }
      ol.append(ledgerItem(w, false));
    });
  }

  function ledgerItem(w, withStatus = true) {
    const li = create('li', 'wl ' + w.status); li.id = 'x-' + w.id;
    if (withStatus) {
      const head = create('p', 'wl-head mono');
      const when = w.status === 'open' ? `runs to ${fmtDay(w.by)}` : w.resolved.how === 'expired' ? `not reported by ${fmtDay(w.by)}` : `${fmtDay(w.resolved.asOf)}`;
      head.append(create('span', 'st', w.status.toUpperCase()), create('span', 'when', ` · ${when}`)); li.append(head);
    }
    li.append(create('p', 'wl-what', w.what));
    const set = create('p', 'wl-set mono'); const a = create('a', 'wl-ref', w.line);
    a.href = openNarrative(w); a.title = 'Open the narrative that set it';
    set.append(create('span', 'w', `SET ${fmtDay(w.asOf).toUpperCase()} · ${(w.firmness || '').toUpperCase()} · BY `), a); li.append(set);
    if (w.because) li.append(create('p', 'wl-because', w.because));
    if (w.resolved && w.resolved.note) li.append(create('p', 'wl-note', w.resolved.note));
    headlineLinks(w).forEach(x => li.append(x));
    return li;
  }

  /* ---------- the paths: each narrative in today's edition, where the writer says it goes ---------- */
  function renderPaths(rd, items) {
    const meta = $('#paths-meta'), body = $('#paths-body'); body.replaceChildren();
    const list = (rd && rd.readings) || [], withAhead = list.filter(r => r.ahead && r.ahead.paths && r.ahead.paths.length);
    if (!withAhead.length) {
      meta.textContent = rd ? `EDITION OF ${fmtDay(rd.newsGeneratedAt).toUpperCase()} · BEFORE THE PATHS` : 'NO EDITION';
      body.append(create('p', 'chronicle-empty', 'This edition predates the paths. From the next one, each narrative names the precedent its join most resembles, lays out the paths it could take, favours one, and says where the decade points. They will be set out here.'));
      return;
    }
    meta.textContent = `EDITION OF ${fmtDay(rd.newsGeneratedAt).toUpperCase()} · ${withAhead.length} NARRATIVE${withAhead.length === 1 ? '' : 'S'}`;
    const byId = new Map(items.map(w => [w.id, w]));
    withAhead.forEach((r, i) => {
      const card = create('article', 'pcard');
      const k = create('p', 'pcard-k mono'); k.append(create('span', '', `${String(i + 1).padStart(2, '0')} · ${r.kicker}`), create('span', 'firm ' + (r.firmness || ''), (r.firmness || '').toUpperCase())); card.append(k);
      const h = create('h2', 'pcard-line'); const a = create('a', '', r.line); a.href = `./#reading=${encodeURIComponent(r.id)}&open=1`; a.title = 'Open the narrative'; h.append(a); card.append(h);
      const paths = r.ahead.paths.slice().sort((x, y) => (WEIGHT[x.weight] ?? 1) - (WEIGHT[y.weight] ?? 1));
      const pl = create('ol', 'ppaths');
      paths.forEach(p => {
        const li = create('li', 'ppath ' + p.weight);
        li.append(create('p', 'pw mono', (p.weight || '').toUpperCase()), create('p', 'pn', p.name));
        if (p.weight === 'favoured') li.append(create('p', 'pt', p.text));
        const sg = create('p', 'ps'); sg.append(create('span', 'mono', 'FIRST SIGN · '), document.createTextNode(p.sign)); li.append(sg);
        pl.append(li);
      });
      card.append(pl);
      const w = (r.watch || []).map(x => byId.get(x.id) || x);
      if (w.length) { const tw = create('p', 'pcard-watch'); tw.append(create('span', 'mono', 'TO WATCH FOR · '), document.createTextNode(w.map(x => `${x.what} By ${fmtDay(x.by)}${x.status && x.status !== 'open' ? ` (${x.status})` : ''}.`).join(' '))); card.append(tw); }
      if (r.ahead.precedent) { const p = create('p', 'pcard-text'); p.append(create('span', 'mono', 'THE PRECEDENT · '), document.createTextNode(r.ahead.precedent)); card.append(p); }
      if (r.ahead.decade) { const p = create('p', 'pcard-text'); p.append(create('span', 'mono', 'AT THE SCALE OF A DECADE · '), document.createTextNode(r.ahead.decade)); card.append(p); }
      body.append(card);
    });
  }

  /* ---------- the record: the count by firmness, and every settled expectation ---------- */
  function renderRecord(wl, items) {
    const meta = $('#record-meta'), body = $('#record-body'); body.replaceChildren();
    const settled = items.filter(w => w.status !== 'open');
    if (!items.length) { meta.textContent = 'NOT YET BEGUN'; return; }
    meta.textContent = `${items.length} SET · ${settled.filter(w => w.status === 'kept').length} KEPT · ${settled.filter(w => w.status === 'failed').length} FAILED · ${items.length - settled.length} OPEN`;
    const byF = ['firm', 'plausible', 'tentative'].map(f => { const s = settled.filter(w => w.firmness === f); return { f, kept: s.filter(w => w.status === 'kept').length, n: s.length, open: items.filter(w => w.firmness === f && w.status === 'open').length }; }).filter(x => x.n || x.open);
    if (byF.length) {
      const p = create('p', 'watch-firmness mono');
      byF.forEach(x => p.append(create('span', 'f ' + x.f, `${x.f.toUpperCase()}: ${x.n ? `${x.kept} OF ${x.n} KEPT` : 'NONE SETTLED'}${x.open ? ` · ${x.open} OPEN` : ''}`)));
      body.append(p, create('p', 'watch-intro', 'A firm narrative should keep more of what it expects than a tentative one. If it does not, the word means nothing, and this page will show it.'));
    }
    if (settled.length) {
      body.append(create('p', 'sect', 'SETTLED · NEWEST FIRST'));
      const ol = create('ol', 'watch-ledger'); settled.sort((a, b) => (b.resolved.asOf > a.resolved.asOf ? 1 : -1)).forEach(w => ol.append(ledgerItem(w))); body.append(ol);
    } else body.append(create('p', 'chronicle-empty', 'Nothing has settled yet. The soonest expectation runs to ' + fmtDay(items.filter(w => w.status === 'open').map(w => w.by).sort()[0]) + '.'));
    if (wl && wl.notes) body.append(create('p', 'note', wl.notes.join(' ')));
  }

  /* ---------- init ---------- */
  function setNight(on) { document.documentElement.dataset.theme = on ? 'night' : ''; $('#night').setAttribute('aria-pressed', String(on)); try { localStorage.setItem('pt-night', on ? '1' : '0'); } catch {} }
  function bindTips() {
    const tip = $('#tip'); if (!tip) return; let timer = null;
    const show = el => { const r = el.getBoundingClientRect(); tip.textContent = el.dataset.tip; tip.hidden = false; const w = tip.offsetWidth; let left = r.left + r.width / 2 - w / 2; left = Math.max(8, Math.min(left, window.innerWidth - w - 8)); tip.style.left = left + 'px'; tip.style.setProperty('--tip-x', (r.left + r.width / 2 - left - 5) + 'px'); };
    const hide = () => { clearTimeout(timer); tip.hidden = true; };
    $$('[data-tip]').forEach(el => {
      el.addEventListener('mouseenter', () => { clearTimeout(timer); timer = setTimeout(() => show(el), 260); });
      el.addEventListener('mouseleave', hide);
      el.addEventListener('focus', () => show(el)); el.addEventListener('blur', hide);
      el.addEventListener('click', hide);
    });
  }
  async function init() {
    bindTips();
    try { if (localStorage.getItem('pt-night') === '1') setNight(true); } catch {}
    $('#night').addEventListener('click', () => setNight(document.documentElement.dataset.theme !== 'night'));
    try { readings = await getJSON('data/readings.json'); } catch { readings = null; }
    try { ledger = await getJSON('data/watch.json'); } catch { ledger = null; }
    const items = (ledger && ledger.items || []).slice();
    const open = items.filter(w => w.status === 'open').length;
    $('#ahead-edition').textContent = `AHEAD · ${open} TO WATCH FOR · ${items.filter(w => w.status === 'kept').length} KEPT · ${items.filter(w => w.status === 'failed').length} FAILED`;
    renderBoard(items); renderPaths(readings, items); renderRecord(ledger, items);
    if (location.hash === '#watch' || location.hash === '#record') { const el = $(location.hash === '#watch' ? '#board' : '#record'); if (el) el.scrollIntoView(); }
  }
  init();
})();
