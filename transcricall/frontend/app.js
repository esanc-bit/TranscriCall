const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
const cards = document.getElementById('cards');
const search = document.getElementById('search');
const agentFilter = document.getElementById('agentFilter');

let agentLatest = new Map(); // agent_id -> { text, ts, hot, call_id }

ws.addEventListener('open', () => {
  ws.send(JSON.stringify({ action: 'subscribe', agent_id: 'all' }));
});

ws.addEventListener('message', ev => {
  const msg = JSON.parse(ev.data);
  if (msg.type === 'transcript') {
    agentLatest.set(msg.agent_id, msg);
    renderCards();
  }
});

search.addEventListener('input', renderCards);
agentFilter.addEventListener('change', renderCards);

function renderCards() {
  const q = search.value.toLowerCase().trim();
  const filterAgent = agentFilter.value;
  const entries = Array.from(agentLatest.entries());

  // populate agentFilter options
  const agentIds = Array.from(new Set(entries.map(([aid]) => aid)));
  const existing = new Set(Array.from(agentFilter.options).map(o => o.value));
  for (const aid of agentIds) {
    if (!existing.has(aid)) {
      const opt = document.createElement('option');
      opt.value = aid; opt.textContent = aid; agentFilter.appendChild(opt);
    }
  }

  cards.innerHTML = '';
  for (const [aid, info] of entries) {
    if (filterAgent !== 'all' && aid !== filterAgent) continue;
    if (q && !info.text.toLowerCase().includes(q)) continue;
    const el = document.createElement('div');
    el.className = 'card' + (info.hot ? ' hot' : '');
    el.innerHTML = `<h3>Agente: ${aid} · Llamada: ${info.call_id}</h3><div class="text">${escapeHtml(info.text)}</div>`;
    cards.appendChild(el);
  }
}

function escapeHtml(str) {
  return str.replace(/[&<>"]+/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s]));
}

// Tabs
const tabLive = document.getElementById('tab-live');
const tabAnalytics = document.getElementById('tab-analytics');
const live = document.getElementById('live');
const analytics = document.getElementById('analytics');

tabLive.addEventListener('click', () => { tabLive.classList.add('active'); tabAnalytics.classList.remove('active'); live.classList.add('active'); analytics.classList.remove('active'); });
tabAnalytics.addEventListener('click', () => { tabAnalytics.classList.add('active'); tabLive.classList.remove('active'); analytics.classList.add('active'); live.classList.remove('active'); loadAnalytics(); });

// Analytics
let chartsInit = false;
let charts = {};

async function loadAnalytics() {
  try {
    const res = await fetch('/analytics/summary');
    const data = await res.json();
    renderAnalytics(data);
  } catch (e) {
    console.error('Analytics error', e);
  }
}

function renderAnalytics(data) {
  const hourLabels = Array.from({length:24}, (_,i)=>String(i));
  const byHour = hourLabels.map(h => data.calls_by_hour[h] || 0);
  const hotByHour = hourLabels.map(h => data.hot_calls_by_hour[h] || 0);

  const ctx1 = document.getElementById('byHour').getContext('2d');
  const ctx2 = document.getElementById('hotByHour').getContext('2d');
  const ctx3 = document.getElementById('durationHist').getContext('2d');

  if (!chartsInit) {
    charts.byHour = new Chart(ctx1, { type: 'bar', data: { labels: hourLabels, datasets: [{ label: 'Llamadas por hora (UTC)', data: byHour, backgroundColor: '#6aa0ff' }] }, options: {responsive: true} });
    charts.hotByHour = new Chart(ctx2, { type: 'bar', data: { labels: hourLabels, datasets: [{ label: 'Llamadas calientes por hora (UTC)', data: hotByHour, backgroundColor: '#ff6b6b' }] }, options: {responsive: true} });
    charts.durationHist = new Chart(ctx3, { type: 'bar', data: { labels: Object.keys(data.duration_histogram), datasets: [{ label: 'Distribución duración', data: Object.values(data.duration_histogram), backgroundColor: '#9fb4ff' }] }, options: {responsive: true} });
    chartsInit = true;
  } else {
    charts.byHour.data.datasets[0].data = byHour; charts.byHour.update();
    charts.hotByHour.data.datasets[0].data = hotByHour; charts.hotByHour.update();
    charts.durationHist.data.labels = Object.keys(data.duration_histogram);
    charts.durationHist.data.datasets[0].data = Object.values(data.duration_histogram); charts.durationHist.update();
  }

  // Agent ranking table
  const tbody = document.querySelector('#agentRanking tbody');
  tbody.innerHTML = '';
  for (const row of data.agent_ranking) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${row.agent_id}</td><td>${row.calls}</td><td>${row.hot_calls}</td><td>${row.avg_hot_score}</td>`;
    tbody.appendChild(tr);
  }
}