(() => {
  'use strict';
  const API = ''; // same origin: FastAPI serves this UI
  const $ = (s, r = document) => r.querySelector(s);
  const state = { last: null };

  /* ---------- helpers ---------- */
  function h(tag, props = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid);
    return n;
  }
  const icons = () => window.lucide && window.lucide.createIcons();
  const icon = (name, cls) => h('i', { 'data-lucide': name, 'aria-hidden': 'true', class: cls });
  const fmt = v => Array.isArray(v) ? v.map(fmt).join('\n') : (v && typeof v === 'object') ? JSON.stringify(v, null, 2) : String(v ?? '');
  const tone = s => {
    s = String(s || '').toLowerCase();
    if (/err|fail|not_|reject/.test(s)) return 'bad';
    if (/pass|success|complete|done|ok/.test(s)) return 'good';
    if (/pend|run|retry|warn/.test(s)) return 'warn';
    return '';
  };
  const pill = (text, t = tone(text)) => h('span', { class: 'pill ' + t, text });
  const empty = (ic, text) => h('div', { class: 'empty' }, icon(ic), h('div', { text }));
  const banner = (kind, text) => h('div', { class: 'banner ' + kind, text });
  const show = (node, ...kids) => { node.replaceChildren(...kids.flat()); icons(); };

  async function api(path, opts) {
    let res;
    try { res = await fetch(API + path, opts); }
    catch { throw new Error('Cannot reach the server. Check that FastAPI is running and you opened this page from it, not as a file.'); }
    if (!res.ok) {
      let d = '';
      try { d = (await res.json()).detail; } catch { /* not JSON */ }
      throw new Error((typeof d === 'string' && d) || `Request failed (${res.status}).`);
    }
    return res.json();
  }

  /* ---------- routing / shell ---------- */
  const pages = { overview: 'Overview', copilot: 'AI Copilot', monitor: 'Workflow monitor', knowledge: 'Knowledge base', history: 'Incident history' };
  function route() {
    const p = pages[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
    for (const k in pages) $('#page-' + k).hidden = k !== p;
    document.querySelectorAll('nav a').forEach(a => a.dataset.page === p ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
    $('#page-title').textContent = pages[p];
    document.body.classList.remove('nav-open');
    if (p === 'overview') loadOverview();
    if (p === 'knowledge') loadDocs();
    if (p === 'history') loadLogs();
    if (p === 'monitor') renderMonitor();
  }
  window.addEventListener('hashchange', route);
  $('#collapse').onclick = () => document.body.classList.toggle('collapsed');
  $('#menu').onclick = () => document.body.classList.add('nav-open');
  $('#scrim').onclick = () => document.body.classList.remove('nav-open');

  /* ---------- generic renderers for shapes the backend files don't define ---------- */
  function entryTitle(x, i, keys) {
    if (typeof x === 'string') return x;
    for (const k of keys) if (x && x[k]) return String(x[k]);
    return 'Entry ' + (i + 1);
  }
  function entryDetails(x) {
    if (!x || typeof x !== 'object') return null;
    return h('dl', { class: 'kv' }, Object.entries(x).flatMap(([k, v]) => [h('dt', { text: k }), h('dd', { text: fmt(v) })]));
  }
  function listEntries(items, keys, emptyIcon, emptyText) {
    if (!items.length) return [empty(emptyIcon, emptyText)];
    return items.map((x, i) => h('details', {}, h('summary', { text: entryTitle(x, i, keys).slice(0, 140) }), entryDetails(x)));
  }

  /* ---------- overview ---------- */
  async function loadOverview() {
    const [d, l] = await Promise.allSettled([api('/api/documents'), api('/api/audit')]);
    $('#st-docs').textContent = d.status === 'fulfilled' ? (d.value.documents || []).length : 'Unavailable';
    $('#st-logs').textContent = l.status === 'fulfilled' ? (l.value.logs || []).length : 'Unavailable';
    const r = state.last;
    $('#st-eval').textContent = r ? r.evaluation_status : 'No run yet';
    $('#st-source').textContent = r ? r.source_type : '–';
    if (l.status === 'rejected') return show($('#ov-recent'), banner('bad', l.reason.message));
    const logs = (l.value.logs || []).slice(0, 5);
    show($('#ov-recent'), listEntries(logs, ['user_query', 'query', 'question'], 'inbox', 'No investigations logged yet. Run one from the AI Copilot.'));
  }

  /* ---------- copilot ---------- */
  let timer;
  function setBusy(on) {
    const btn = $('#run');
    btn.disabled = on;
    btn.querySelector('span').textContent = on ? 'Investigating…' : 'Investigate';
    $('#chat-loading').hidden = !on;
    clearInterval(timer);
    if (on) { const t0 = Date.now(); timer = setInterval(() => $('#elapsed').textContent = Math.floor((Date.now() - t0) / 1000) + 's', 500); }
  }

  $('#chat-form').addEventListener('submit', async e => {
    e.preventDefault();
    const question = $('#question').value.trim();
    const thread_id = $('#thread').value.trim() || 'INC-001';
    show($('#chat-error'));
    if (!question) return show($('#chat-error'), banner('bad', 'Describe the incident before running an investigation.'));
    show($('#chat-result'));
    setBusy(true);
    try {
      const data = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, thread_id }) });
      state.last = data;
      renderResult(data);
    } catch (err) {
      show($('#chat-error'), banner('bad', err.message));
    } finally { setBusy(false); }
  });

  function renderResult(d) {
    const list = a => Array.isArray(a) ? a : [];
    const errs = [...list(d.evaluation_error), ...list(d.retrieval_grading_errors)];
    const yn = v => v === true ? 'Yes' : v === false ? 'No' : 'Not evaluated';
    const answer = h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', { text: 'Analysis' }), pill(d.source_type || 'Unknown', '')),
      h('div', { class: 'answer', text: d.answer }),
      d.rewritten_query && d.rewritten_query !== $('#question').value.trim()
        ? h('p', { class: 'hint', text: 'Query used for retrieval: ' + d.rewritten_query }) : null);

    const evalCard = h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', { text: 'Self-RAG evaluation' }), pill(d.evaluation_status || 'not_run')),
      h('dl', { class: 'kv' },
        h('dt', { text: 'Grounded in sources' }), h('dd', { text: yn(d.is_supported) }),
        h('dt', { text: 'Answers the question' }), h('dd', { text: yn(d.is_useful) }),
        h('dt', { text: 'Generation retries' }), h('dd', { text: String(d.generation_retry_count ?? 0) })),
      errs.length ? h('div', { style: 'margin-top:12px' }, errs.map(m => banner('bad', m))) : null);

    const docs = list(d.sources);
    const srcCard = h('div', { class: 'card' },
      h('div', { class: 'card-head' }, h('h2', { text: 'Retrieved documents' }), pill(docs.length + ' found', '')),
      docs.length ? docs.map((s, i) => h('details', {}, h('summary', { text: `Source ${i + 1}: ${fmt(s).slice(0, 90)}…` }), h('pre', { text: fmt(s) })))
        : empty('file-question', 'No documents were returned for this answer.'));

    show($('#chat-result'), answer, h('div', { class: 'two' }, evalCard, srcCard), h('p', { class: 'hint' }, 'Full step-by-step trace: ', h('a', { href: '#monitor', text: 'Workflow monitor' })));
  }

  /* ---------- monitor ---------- */
  function renderMonitor() {
    const d = state.last, box = $('#monitor-body');
    if (!d) return show(box, h('div', { class: 'card' }, empty('activity', 'No run in this session yet. Submit an incident in the AI Copilot to see its execution trace.')));
    const events = Array.isArray(d.execution_events) ? d.execution_events : [];
    const steps = Array.isArray(d.steps_taken) ? d.steps_taken : [];
    show(box,
      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', { text: 'Execution events' }), pill(`Thread ${d.thread_id}`, '')),
        events.length ? h('ol', { class: 'timeline' }, events.map(ev => h('li', { class: tone(ev.status) },
          h('div', { class: 't' }, h('strong', { text: ev.node }), pill(ev.status), h('span', { class: 'muted', text: ev.timestamp })),
          ev.details ? h('p', { text: ev.details }) : null)))
          : empty('list-x', 'The workflow returned no execution events.')),
      h('div', { class: 'card' },
        h('div', { class: 'card-head' }, h('h2', { text: 'Steps taken' })),
        steps.length ? h('div', { class: 'chips' }, steps.map(s => pill(s, ''))) : empty('list-x', 'No steps were recorded.')));
  }

  /* ---------- knowledge base ---------- */
  const fileInput = $('#file');
  fileInput.addEventListener('change', () => { $('#file-name').textContent = fileInput.files[0]?.name || 'Choose a PDF (max 20 MB)'; });

  $('#upload-form').addEventListener('submit', async e => {
    e.preventDefault();
    const msg = $('#upload-msg'), f = fileInput.files[0];
    show(msg);
    if (!f) return show(msg, banner('bad', 'Choose a PDF file first.'));
    if (!f.name.toLowerCase().endsWith('.pdf')) return show(msg, banner('bad', 'Only PDF files are accepted.'));
    if (f.size > 20 * 1024 * 1024) return show(msg, banner('bad', 'This file is over the 20 MB limit.'));
    const btn = $('#upload-btn'); btn.disabled = true; btn.querySelector('span').textContent = 'Ingesting…';
    try {
      const fd = new FormData(); fd.append('file', f);
      const r = await api('/api/upload', { method: 'POST', body: fd });
      show(msg, banner('good', r.message));
      fileInput.value = ''; $('#file-name').textContent = 'Choose a PDF (max 20 MB)';
      loadDocs();
    } catch (err) { show(msg, banner('bad', err.message)); }
    finally { btn.disabled = false; btn.querySelector('span').textContent = 'Upload and ingest'; }
  });

  async function loadDocs() {
    const box = $('#docs-list');
    show(box, h('div', { class: 'bar' }, h('i')));
    try { show(box, listEntries((await api('/api/documents')).documents || [], ['filename', 'name', 'file_name'], 'book-open', 'No runbooks ingested yet. Upload a PDF above.')); }
    catch (err) { show(box, banner('bad', err.message)); }
  }
  $('#docs-refresh').onclick = loadDocs;

  /* ---------- history ---------- */
  async function loadLogs() {
    const box = $('#logs-list');
    show(box, h('div', { class: 'bar' }, h('i')));
    try { show(box, listEntries((await api('/api/audit')).logs || [], ['user_query', 'query', 'question'], 'inbox', 'No investigations logged yet.')); }
    catch (err) { show(box, banner('bad', err.message)); }
  }
  $('#logs-refresh').onclick = loadLogs;

  icons();
  route();
})();
