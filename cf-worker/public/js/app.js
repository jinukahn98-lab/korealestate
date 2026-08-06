/* ============================================================
   한국 부동산 분석 시스템 — frontend app logic (vanilla JS)
   RAG+RSI v5.0
   ------------------------------------------------------------
   Tabs: ranking, cheongyak, development, evaluation, wiki
   API (served by Cloudflare Worker):
     GET /api/regions              -> [{ region, total_score, grade, factors, version, scored_at }]
     GET /api/regions/:region      -> { ...scorer_result, monthly: [{ year_month, avg_price, ... }] }
     GET /api/cheongyak            -> [{ id, region, pblanc_name, total_supply, ... }]
     GET /api/development          -> [{ id, region, project_name, project_type, status, ... }]
     GET /api/evaluation/weights   -> [{ factor_name, default_weight, optimized_weight, updated_at }]
     GET /api/evaluation           -> [{ id, run_date, task, status, result_json, created_at }]
     GET /api/search?q=            -> [{ title, category, content, date_token, indexed_at, snippet }]
   ============================================================ */

(function () {
  'use strict';

  /* ---------- Config ---------- */
  const API = '/api';
  const GRADE_META = {
    '강력매수': { cls: 'grade-fire',  icon: '🔥' },
    '매수':    { cls: 'grade-buy',   icon: '✅' },
    '관망':    { cls: 'grade-watch', icon: '➡️' },
    '매도':    { cls: 'grade-sell',  icon: '⚠️' }
  };

  /* ---------- Small DOM helpers ---------- */
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const el = (tag, attrs = {}, html = '') => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') node.className = v;
      else if (k === 'html') node.innerHTML = v;
      else node.setAttribute(k, v);
    }
    if (html) node.innerHTML = html;
    return node;
  };
  const escapeHtml = (s) =>
    String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  const fmtNum = (n, d = 0) => {
    const num = Number(n);
    if (!isFinite(num)) return '—';
    return num.toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  };
  const fmtPct = (n, d = 1) => (isFinite(Number(n)) ? (Number(n) * 100).toFixed(d) + '%' : '—');
  const fmtWon = (n) => (isFinite(Number(n)) ? fmtNum(Math.round(Number(n) / 10000)) + '만' : '—');
  const fmtDate = (s) => (s ? String(s).slice(0, 10) : '—');

  /* ---------- API envelope + state helpers ---------- */
  // Always unwrap `{ count, results }` envelopes. Never returns a non-array,
  // so callers can safely .map()/.forEach() the result — even if the API
  // misbehaves (missing `results`, `{ error: ... }` with HTTP 200, etc.).
  const unwrapResults = (data) => {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.results)) return data.results;
    if (data && Array.isArray(data.data)) return data.data;
    return [];
  };

  const EMPTY_MSG = '데이터가 없습니다';
  const ERROR_MSG = '불러오지 못했습니다. 잠시 후 다시 시도해주세요';
  const emptyStateHTML = (msg = EMPTY_MSG, extraCls = '') =>
    `<div class="placeholder text-sm p-10 text-center ${extraCls}">${escapeHtml(msg)}</div>`;
  const errorStateHTML = (detail, extraCls = '') =>
    `<div class="state-error ${extraCls}">
       <div class="font-medium">${ERROR_MSG}</div>
       ${detail ? `<div class="text-xs mt-1 opacity-75">${escapeHtml(detail)}</div>` : ''}
     </div>`;

  /* ---------- Data freshness (last updated + 14-day staleness warning) ---------- */
  const FRESHNESS_KEYS = ['scored_at', 'indexed_at', 'updated_at', 'created_at', 'timestamp'];
  let latestDataTs = null; // epoch ms of the newest data timestamp seen
  function trackFreshness(src) {
    if (src == null) return;
    const scan = (obj) => {
      if (!obj || typeof obj !== 'object') return;
      for (const k of FRESHNESS_KEYS) {
        if (obj[k] == null) continue;
        const t = Date.parse(String(obj[k]));
        if (isFinite(t) && (latestDataTs == null || t > latestDataTs)) latestDataTs = t;
      }
    };
    if (Array.isArray(src)) src.forEach(scan); else scan(src);
  }
  function renderFreshness() {
    const node = $('[data-last-updated]');
    const warn = $('#freshness-warn');
    if (latestDataTs == null) {
      if (node) node.textContent = '—';
      if (warn) warn.classList.add('hidden');
      return;
    }
    const ageDays = (Date.now() - latestDataTs) / 86400000;
    if (node) node.textContent = '업데이트 ' + fmtDate(new Date(latestDataTs).toISOString());
    if (warn) {
      if (ageDays > 14) {
        warn.textContent = `⚠️ 데이터 오래됨 (${Math.floor(ageDays)}일 전)`;
        warn.classList.remove('hidden');
        warn.classList.add('inline-flex');
      } else {
        warn.classList.add('hidden');
        warn.classList.remove('inline-flex');
      }
    }
  }

  /* ---------- API helper ---------- */
  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, { headers: { 'Accept': 'application/json' }, ...opts });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { const j = await res.json(); msg = j.error || j.message || msg; } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  /* ---------- State ---------- */
  const state = {
    regions: [],          // ranking list (cached)
    cheongyak: [],        // full cheongyak list (cached for client-side search)
    selectedRegion: null,
    charts: { price: null, weights: null }
  };

  /* ============================================================
     TABS
     ============================================================ */
  function showTab(name) {
    $$('.tab-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === name));
    $$('.tab-pane').forEach((p) => p.classList.toggle('hidden', p.id !== 'tab-' + name));
    // Lazy-load tab data once
    if (name === 'ranking'    && !state.regions.length)   loadRanking();
    if (name === 'cheongyak'  && !state.cheongyak.length) loadCheongyak();
    if (name === 'development') loadDevelopment();
    if (name === 'evaluation')  loadEvaluation();
    // wiki loads on submit only
  }

  /* ============================================================
     KPIs
     ============================================================ */
  async function loadKPIs() {
    try {
      const [regions, cheongyak] = await Promise.allSettled([
        fetchJSON(`${API}/regions`),
        fetchJSON(`${API}/cheongyak`)
      ]);

      const regs = regions.status === 'fulfilled' ? unwrapResults(regions.value) : [];
      const cyk  = cheongyak.status === 'fulfilled' ? unwrapResults(cheongyak.value) : [];

      const scores = regs.map((r) => Number(r.total_score)).filter(isFinite);
      const top = scores.length ? regs.reduce((a, b) =>
        (Number(b.total_score) > Number(a.total_score) ? b : a)) : null;
      const avg = scores.length ? scores.reduce((x, y) => x + y, 0) / scores.length : null;
      const cykSupply = cyk.reduce((s, c) => s + (Number(c.total_supply) || 0), 0);

      setKpi('regions', fmtNum(regs.length));
      setKpi('topScore', top ? Number(top.total_score).toFixed(1) : '—');
      $('[data-kpi-top-region]').textContent = top ? `🏆 ${top.region}` : '—';
      setKpi('avgScore', avg != null ? avg.toFixed(1) : '—');
      setKpi('cheongyak', fmtNum(cykSupply));
      $('[data-kpi-cheongyak-count]').textContent = `${fmtNum(cyk.length)}개 공고`;

      trackFreshness(regs);      // scored_at
      trackFreshness(cyk);
      renderFreshness();
    } catch (e) {
      console.warn('loadKPIs failed:', e);
    }
  }
  function setKpi(key, val) {
    const node = $(`[data-kpi="${key}"]`);
    if (node) node.textContent = val;
  }

  /* ============================================================
     RANKING + REGION DETAIL
     ============================================================ */
  async function loadRanking() {
    const list = $('#ranking-list');
    list.innerHTML = '<div class="placeholder text-sm text-slate-400 p-4 text-center">불러오는 중…</div>';
    try {
      const data = await fetchJSON(`${API}/regions`);
      state.regions = unwrapResults(data).slice().sort(
        (a, b) => Number(b.total_score) - Number(a.total_score));
      $('#ranking-count').textContent = fmtNum(state.regions.length);
      trackFreshness(state.regions);   // scored_at
      renderFreshness();
      renderRankingList();
      // Auto-select top region
      if (state.regions.length && !state.selectedRegion) {
        loadRegionDetail(state.regions[0].region);
      }
    } catch (e) {
      list.innerHTML = errorStateHTML(`지역 목록: ${e.message}`);
    }
  }

  function renderRankingList() {
    const list = $('#ranking-list');
    list.innerHTML = '';
    if (!state.regions.length) {
      list.innerHTML = emptyStateHTML('표시할 지역 데이터가 없습니다', 'p-6');
      return;
    }
    state.regions.forEach((r, i) => {
      const grade = gradeOf(r.grade);
      const card = el('div', {
        class: 'region-card' + (state.selectedRegion === r.region ? ' selected' : ''),
        'data-region': r.region,
        role: 'button',
        tabindex: '0'
      });
      card.innerHTML = `
        <div class="min-w-0">
          <div class="region-name truncate">${escapeHtml(r.region)}</div>
          <div class="region-meta">#${i + 1} · ${escapeHtml(r.version || 'v?')} · ${fmtDate(r.scored_at)}</div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span class="font-bold text-slate-800 text-sm">${Number(r.total_score).toFixed(1)}</span>
          <span class="score-badge ${grade.cls}">${grade.icon} ${escapeHtml(r.grade || '—')}</span>
        </div>`;
      card.addEventListener('click', () => loadRegionDetail(r.region));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); loadRegionDetail(r.region); }
      });
      list.appendChild(card);
    });
  }

  async function loadRegionDetail(region) {
    state.selectedRegion = region;
    // mark selected in list
    $$('.region-card').forEach((c) =>
      c.classList.toggle('selected', c.dataset.region === region));

    const host = $('#region-detail');
    host.innerHTML = `<div class="placeholder text-sm text-slate-400 p-10 text-center">"${escapeHtml(region)}" 불러오는 중…</div>`;

    try {
      const r = await fetchJSON(`${API}/regions/${encodeURIComponent(region)}`);
      renderRegionDetail(r);
    } catch (e) {
      host.innerHTML = errorStateHTML(`지역 상세: ${e.message}`);
    }
  }

  function renderRegionDetail(r) {
    const host = $('#region-detail');
    if (!r || typeof r !== 'object') {
      host.innerHTML = emptyStateHTML('지역 상세 데이터가 없습니다');
      return;
    }
    // The Worker returns `{ score, overrides, monthly_stats, cheongyak, development }`;
    // older shapes put the score fields at the top level — handle both envelopes.
    const s = (r.score && typeof r.score === 'object') ? r.score : r;
    const grade = gradeOf(s.grade);
    const factors = parseFactors(s.factors);
    const totalScore = Number(s.total_score);
    const scoreStr = isFinite(totalScore) ? totalScore.toFixed(1) : '—';

    const factorBars = factors.length
      ? factors.map((f) => factorBarHTML(f)).join('')
      : '<div class="text-xs text-slate-400">팩터 정보 없음</div>';

    host.innerHTML = `
      <div class="flex items-start justify-between gap-3 flex-wrap mb-4">
        <div>
          <h2 class="text-lg font-bold text-slate-800">${escapeHtml(s.region || r.region || '—')}</h2>
          <p class="text-xs text-slate-500">
            ${escapeHtml(s.version || 'v?')} · scored ${fmtDate(s.scored_at)}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <div class="text-3xl font-extrabold text-slate-800">${scoreStr}</div>
          <span class="score-badge ${grade.cls} text-sm">${grade.icon} ${escapeHtml(s.grade || '—')}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <h3 class="text-sm font-semibold text-slate-700 mb-2">팩터 점수</h3>
          <div id="factor-bars">${factorBars}</div>
        </div>
        <div>
          <h3 class="text-sm font-semibold text-slate-700 mb-2">월별 평균 매매가 추이</h3>
          <div class="chart-container">
            <canvas id="price-chart"></canvas>
          </div>
          <p id="price-empty" class="text-xs text-slate-400 mt-2 hidden">월별 데이터 없음</p>
        </div>
      </div>`;

    // Animate factor fills after paint
    requestAnimationFrame(() => {
      $$('#factor-bars .factor-fill').forEach((f) => {
        const w = f.getAttribute('data-w');
        requestAnimationFrame(() => { f.style.width = w + '%'; });
      });
    });

    // Price chart
    renderPriceChart(r.monthly || r.monthly_stats || []);

    // Freshness: score row carries scored_at
    trackFreshness(s);
    renderFreshness();
  }

  function factorBarHTML(f) {
    const name = escapeHtml(f.name || f.factor || f.factor_name || '—');
    const score = Number(f.score != null ? f.score : f.value);
    const pct = isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
    const tint = pct >= 70 ? 't-high' : (pct < 40 ? 't-low' : '');
    return `
      <div class="factor-row">
        <div class="factor-label">
          <span>${name}</span>
          <span class="mono">${isFinite(score) ? score.toFixed(1) : '—'}</span>
        </div>
        <div class="factor-bar">
          <div class="factor-fill ${tint}" data-w="${pct}" style="width:0%"></div>
        </div>
      </div>`;
  }

  function renderPriceChart(monthly) {
    const canvas = $('#price-chart');
    if (!canvas) return;
    const arr = (Array.isArray(monthly) ? monthly : []).slice().sort(
      (a, b) => String(a.year_month).localeCompare(String(b.year_month)));
    if (state.charts.price) { state.charts.price.destroy(); state.charts.price = null; }
    if (!arr.length) {
      $('#price-empty')?.classList.remove('hidden');
      return;
    }
    const labels = arr.map((m) => m.year_month);
    const prices = arr.map((m) => Number(m.avg_price));

    state.charts.price = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: '평균 매매가 (만원)',
          data: prices,
          borderColor: '#2563eb',
          backgroundColor: 'rgba(37,99,235,0.12)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: (c) => fmtNum(c.parsed.y) + '만원' }
          }
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 45, autoSkip: true } },
          y: { ticks: { callback: (v) => fmtNum(v) } }
        }
      }
    });
  }

  /* ============================================================
     CHEONGYAK
     ============================================================ */
  async function loadCheongyak() {
    const host = $('#cheongyak-list');
    host.innerHTML = '<div class="placeholder text-sm text-slate-400 p-10 text-center col-span-full">불러오는 중…</div>';
    try {
      const data = await fetchJSON(`${API}/cheongyak`);
      state.cheongyak = unwrapResults(data);
      trackFreshness(state.cheongyak);
      renderFreshness();
      renderCheongyak(state.cheongyak);
    } catch (e) {
      host.innerHTML = errorStateHTML(`청약: ${e.message}`, 'col-span-full');
    }
  }

  function renderCheongyak(items) {
    const host = $('#cheongyak-list');
    host.innerHTML = '';
    if (!Array.isArray(items)) items = [];
    if (!items.length) {
      host.innerHTML = emptyStateHTML('조건에 맞는 청약 데이터가 없습니다', 'col-span-full');
      return;
    }
    items.forEach((c) => {
      const gap = (Number(c.market_price) || 0) - (Number(c.supply_price) || 0);
      const gapStr = gap > 0 ? `시세차익 +${fmtWon(gap)}` : '—';
      const card = el('div', { class: 'info-card flex flex-col' });
      card.innerHTML = `
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-xs text-brand-600 font-semibold">${escapeHtml(c.region || '—')}</div>
            <h3 class="text-sm font-bold text-slate-800 mt-0.5 truncate">${escapeHtml(c.pblanc_name || '공고명 미상')}</h3>
          </div>
          <span class="stat-pill shrink-0">공급 ${fmtNum(c.total_supply)}세대</span>
        </div>
        <div class="grid grid-cols-2 gap-2 mt-3 text-xs">
          <div><span class="text-slate-400">공급가</span><div class="font-semibold text-slate-700">${fmtWon(c.supply_price)}</div></div>
          <div><span class="text-slate-400">시세</span><div class="font-semibold text-slate-700">${fmtWon(c.market_price)}</div></div>
          <div><span class="text-slate-400">경쟁률</span><div class="font-semibold text-slate-700">${fmtNum(c.total_competition, 1)}:1</div></div>
          <div><span class="text-slate-400">커트라인</span><div class="font-semibold text-slate-700">${fmtNum(c.score_cutoff)}</div></div>
        </div>
        <div class="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
          <span class="text-xs text-slate-500">🗓️ ${fmtDate(c.pblanc_start)} ~ ${fmtDate(c.pblanc_end)}</span>
          <span class="stat-pill text-emerald-700 bg-emerald-50">${escapeHtml(gapStr)}</span>
        </div>`;
      host.appendChild(card);
    });
  }

  function searchCheongyak() {
    const q = $('#cheongyak-search').value.trim().toLowerCase();
    if (!q) { renderCheongyak(state.cheongyak); return; }
    const filtered = state.cheongyak.filter((c) =>
      String(c.region || '').toLowerCase().includes(q) ||
      String(c.pblanc_name || '').toLowerCase().includes(q));
    renderCheongyak(filtered);
  }

  /* ============================================================
     DEVELOPMENT
     ============================================================ */
  async function loadDevelopment() {
    const host = $('#development-list');
    // avoid reload if already loaded
    if (host.dataset.loaded === '1') return;
    host.innerHTML = '<div class="placeholder text-sm text-slate-400 p-10 text-center col-span-full">불러오는 중…</div>';
    try {
      const data = await fetchJSON(`${API}/development`);
      const items = unwrapResults(data).slice().sort(
        (a, b) => Number(b.impact_score) - Number(a.impact_score));
      host.dataset.loaded = '1';
      $('#dev-count').textContent = fmtNum(items.length);
      trackFreshness(items);
      renderFreshness();
      renderDevelopment(items);
    } catch (e) {
      host.innerHTML = errorStateHTML(`개발호재: ${e.message}`, 'col-span-full');
    }
  }

  function renderDevelopment(items) {
    const host = $('#development-list');
    host.innerHTML = '';
    if (!Array.isArray(items)) items = [];
    if (!items.length) {
      host.innerHTML = emptyStateHTML('등록된 개발호재 데이터가 없습니다', 'col-span-full');
      return;
    }
    items.forEach((d) => {
      const impact = Number(d.impact_score);
      const impactPct = isFinite(impact) ? Math.max(0, Math.min(100, impact)) : 0;
      const card = el('div', { class: 'info-card flex flex-col' });
      card.innerHTML = `
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-xs text-brand-600 font-semibold">${escapeHtml(d.region || '—')}</div>
            <h3 class="text-sm font-bold text-slate-800 mt-0.5">${escapeHtml(d.project_name || '프로젝트 미상')}</h3>
          </div>
          <span class="stat-pill shrink-0">${escapeHtml(d.project_type || '—')}</span>
        </div>
        <div class="mt-3">
          <div class="factor-label">
            <span class="text-xs text-slate-500">영향도</span>
            <span class="mono text-xs font-semibold text-slate-700">${isFinite(impact) ? impact.toFixed(1) : '—'}</span>
          </div>
          <div class="factor-bar">
            <div class="factor-fill ${impactPct >= 70 ? 't-high' : (impactPct < 40 ? 't-low' : '')}" style="width:${impactPct}%"></div>
          </div>
        </div>
        <div class="flex items-center justify-between mt-3 pt-3 border-t border-slate-100 text-xs">
          <span class="text-slate-500">완료 예정 ${fmtDate(d.expected_completion)}</span>
          <span class="stat-pill ${statusColor(d.status)}">${escapeHtml(d.status || '—')}</span>
        </div>`;
      host.appendChild(card);
    });
  }

  function statusColor(s) {
    const v = String(s || '').toLowerCase();
    if (v.includes('완료') || v.includes('done') || v.includes('complete')) return 'bg-emerald-50 text-emerald-700';
    if (v.includes('진행') || v.includes('progress') || v.includes('active')) return 'bg-amber-50 text-amber-700';
    if (v.includes('계획') || v.includes('plan')) return 'bg-sky-50 text-sky-700';
    if (v.includes('지연') || v.includes('delay') || v.includes('cancel')) return 'bg-rose-50 text-rose-700';
    return '';
  }

  /* ============================================================
     EVALUATION (weights bar chart + history)
     ============================================================ */
  let _evalLoaded = false;
  async function loadEvaluation() {
    if (_evalLoaded) return;
    const hist = $('#evaluation-history');
    hist.innerHTML = '<div class="placeholder text-sm text-slate-400 p-6 text-center">불러오는 중…</div>';
    try {
      const [w, h] = await Promise.allSettled([
        fetchJSON(`${API}/evaluation/weights`),
        fetchJSON(`${API}/evaluation`)
      ]);
      const weights = w.status === 'fulfilled' ? unwrapResults(w.value) : [];
      const history = h.status === 'fulfilled' ? unwrapResults(h.value) : [];
      _evalLoaded = true;
      trackFreshness(weights);   // updated_at
      trackFreshness(history);   // created_at
      renderFreshness();
      renderWeightsChart(weights, w.status === 'rejected' ? w.reason.message : null);
      renderEvalHistory(history, h.status === 'rejected' ? h.reason.message : null);
    } catch (e) {
      hist.innerHTML = errorStateHTML(`평가: ${e.message}`);
    }
  }

  function renderWeightsChart(weights, errMsg) {
    const canvas = $('#weights-chart');
    if (!canvas) return;
    if (state.charts.weights) { state.charts.weights.destroy(); state.charts.weights = null; }
    // remove previously injected notes so re-renders don't duplicate them
    $$('.chart-note', canvas.parentElement).forEach((n) => n.remove());
    if (errMsg && !Array.isArray(weights)) {
      canvas.parentElement.insertAdjacentHTML('beforeend',
        errorStateHTML(`가중치: ${errMsg}`, 'chart-note mt-2'));
      return;
    }
    if (!weights.length) {
      canvas.parentElement.insertAdjacentHTML('beforeend',
        '<p class="chart-note text-xs text-slate-400 mt-2">가중치 데이터가 없습니다</p>');
      return;
    }
    const labels = weights.map((x) => x.factor_name);
    const defs   = weights.map((x) => Number(x.default_weight));
    const opts   = weights.map((x) => Number(x.optimized_weight));

    state.charts.weights = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'default',   data: defs, backgroundColor: 'rgba(148,163,184,0.7)',  borderRadius: 4 },
          { label: 'optimized', data: opts, backgroundColor: 'rgba(37,99,235,0.85)',   borderRadius: 4 }
        ]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } },
          tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${Number(c.parsed.x).toFixed(3)}` } }
        },
        scales: {
          x: { beginAtZero: true, ticks: { callback: (v) => Number(v).toFixed(2) } },
          y: { grid: { display: false }, ticks: { font: { size: 11 } } }
        }
      }
    });
  }

  function renderEvalHistory(history, errMsg) {
    const host = $('#evaluation-history');
    host.innerHTML = '';
    if (!Array.isArray(history)) history = [];
    if (errMsg && !history.length) {
      host.innerHTML = errorStateHTML(`히스토리: ${errMsg}`);
      return;
    }
    if (!history.length) {
      host.innerHTML = emptyStateHTML('평가 히스토리 데이터가 없습니다', 'p-6');
      return;
    }
    const sorted = history.slice().sort((a, b) =>
      String(b.run_date || b.created_at || '').localeCompare(String(a.run_date || a.created_at || '')));
    sorted.forEach((h) => {
      const st = String(h.status || '').toLowerCase();
      const stCls = st === 'success' || st === 'ok' || st === '완료'
        ? 'bg-emerald-50 text-emerald-700'
        : st === 'fail' || st === 'error' || st === '실패'
          ? 'bg-rose-50 text-rose-700'
          : 'bg-amber-50 text-amber-700';
      const item = el('div', { class: 'border border-slate-200 rounded-lg p-2.5 text-xs' });
      item.innerHTML = `
        <div class="flex items-center justify-between gap-2">
          <span class="font-semibold text-slate-700 truncate">${escapeHtml(h.task || 'task')}</span>
          <span class="stat-pill ${stCls}">${escapeHtml(h.status || '—')}</span>
        </div>
        <div class="text-slate-400 mt-1">${fmtDate(h.run_date || h.created_at)}</div>`;
      host.appendChild(item);
    });
  }

  /* ============================================================
     WIKI SEARCH
     ============================================================ */
  async function searchWiki(q) {
    const host = $('#wiki-results');
    const query = String(q || '').trim();
    // Client-side guard: never fire a request for an empty query.
    if (!query) {
      host.innerHTML = emptyStateHTML('검색어를 입력해 주세요');
      $('#wiki-query').focus();
      return;
    }
    host.innerHTML = '<div class="placeholder text-sm text-slate-400 p-10 text-center">검색 중…</div>';
    try {
      const data = await fetchJSON(`${API}/search?q=${encodeURIComponent(query)}`);
      const results = unwrapResults(data);
      trackFreshness(results);   // indexed_at
      renderFreshness();
      renderWikiResults(results, query);
    } catch (e) {
      host.innerHTML = errorStateHTML(`위키 검색: ${e.message}`);
    }
  }

  function renderWikiResults(results, q) {
    const host = $('#wiki-results');
    host.innerHTML = '';
    if (!Array.isArray(results)) results = [];
    if (!results.length) {
      host.innerHTML = emptyStateHTML(`"${escapeHtml(q)}"에 대한 결과가 없습니다`);
      return;
    }
    const head = el('div', { class: 'text-xs text-slate-500 mb-1' },
      `${fmtNum(results.length)}개 결과 · "${escapeHtml(q)}"`);
    host.appendChild(head);
    results.forEach((r) => {
      const item = el('div', { class: 'wiki-result' });
      item.innerHTML = `
        <h3>${highlight(escapeHtml(r.title || '—'), q)}</h3>
        <div class="wiki-meta">
          ${escapeHtml(r.category || '미분류')}
          ${r.date_token ? ' · ' + escapeHtml(r.date_token) : ''}
          ${r.indexed_at ? ' · ' + fmtDate(r.indexed_at) : ''}
        </div>
        <div class="wiki-snippet">${highlight(escapeHtml(r.snippet || r.content || ''), q)}</div>`;
      host.appendChild(item);
    });
  }

  function highlight(text, q) {
    if (!q) return text;
    const terms = q.trim().split(/\s+/).filter(Boolean).map(escapeRegex);
    if (!terms.length) return text;
    const re = new RegExp(`(${terms.join('|')})`, 'gi');
    return text.replace(re, '<mark>$1</mark>');
  }
  function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  /* ============================================================
     Helpers
     ============================================================ */
  function gradeOf(g) {
    const key = String(g || '').trim();
    return GRADE_META[key] || { cls: 'grade-na', icon: '•' };
  }
  function parseFactors(f) {
    if (!f) return [];
    if (Array.isArray(f)) return f;
    try { const j = JSON.parse(f); return Array.isArray(j) ? j : (j ? [j] : []); }
    catch (_) { return []; }
  }

  /* ============================================================
     Wire-up + init
     ============================================================ */
  function wireEvents() {
    // Tabs
    $$('.tab-btn').forEach((b) =>
      b.addEventListener('click', () => showTab(b.dataset.tab)));

    // Cheongyak search
    $('#cheongyak-search-btn').addEventListener('click', searchCheongyak);
    $('#cheongyak-reset-btn').addEventListener('click', () => {
      $('#cheongyak-search').value = '';
      renderCheongyak(state.cheongyak);
    });
    $('#cheongyak-search').addEventListener('input', debounce(searchCheongyak, 250));
    $('#cheongyak-search').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); searchCheongyak(); }
    });

    // Wiki form — client-side guard: an empty query never fires a request
    $('#wiki-form').addEventListener('submit', (e) => {
      e.preventDefault();
      searchWiki($('#wiki-query').value);   // searchWiki() itself guards empty queries
    });
  }

  function debounce(fn, ms) {
    let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  // Expose for debugging / HTMX interop
  window.App = {
    fetchJSON, loadKPIs, loadRanking, loadRegionDetail,
    loadCheongyak, searchCheongyak, loadDevelopment,
    loadEvaluation, searchWiki, showTab, state,
    unwrapResults, trackFreshness, renderFreshness
  };

  // ---- Boot ----
  document.addEventListener('DOMContentLoaded', () => {
    wireEvents();
    loadKPIs();         // KPIs on every load
    loadRanking();      // default tab
    showTab('ranking');
  });
})();
