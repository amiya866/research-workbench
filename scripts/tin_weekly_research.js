'use strict';
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const wrap = $('#reportWrap');
const registry = new Map();
$$('.report-page[data-page]', wrap).forEach(section => {
  registry.set(section.dataset.page, {id: section.dataset.page, title: $('.page-heading h2', section).textContent,
    trail: (section.dataset.trail || '研究周报').split('/'), section});
});
const page = (id, label) => ({type: 'page', id, label});
const group = (label, children, open = false) => ({type: 'group', label, children, open});
const NAV = [
  group('总览', [page('sumsec', '本周总结'), page('framework', '产业框架'), page('sources', '数据缺口')], true),
  group('重点关注', [
    group('供给', [page('supply_mine', '矿端与进口'), page('supply_smelt', '冶炼与精锡'), page('inventory', '显性库存'), page('cost', '成本与平衡')], true),
    group('需求', [page('demand_solder', '焊料/电子/新能源'), page('demand_chemical', '锡化工/镀锡板/铅酸')], true)
  ], true),
  group('宏观与策略', [page('price', '价格与结构'), page('macro', '宏观环境')]),
  page('technical', '技术分析'),
  page('detailed', '详细周报'),
  group('研究工作台', [
    {type: 'tool', id: 'upstream', label: '原版全文'},
    {type: 'tool', id: 'insight', label: '锡息相关'},
    {type: 'tool', id: 'archive', label: '周报留档'}
  ])
];
const treeNav = $('#treeNav');
function buildNav(items, parent) {
  items.forEach(item => {
    if (item.type === 'group') {
      const details = document.createElement('details'); details.open = item.open;
      const summary = document.createElement('summary'); summary.textContent = item.label;
      const children = document.createElement('div'); children.className = 'tree-children';
      details.append(summary, children); parent.appendChild(details); buildNav(item.children, children);
    } else {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'tree-link';
      button.textContent = item.label; button.dataset[item.type === 'tool' ? 'tool' : 'page'] = item.id; parent.appendChild(button);
    }
  });
}
buildNav(NAV, treeNav);
const toolPage = $('#toolPage'), toolFrame = $('#toolFrame');
const toolUrls = {
  upstream: ['原版全文', './upstream.html'],
  insight: ['锡息相关', 'https://amiya866.github.io/tin-insight/'],
  archive: ['周报留档', 'https://gsy1005.github.io/tin-research/weekly_archive.html']
};
let currentPage = 'sumsec', technicalData = null, technicalLoading = false;
const id = value => document.getElementById(value);
function resizeCharts() {
  requestAnimationFrame(() => {
    if (window.Chart?.instances) Object.values(window.Chart.instances).forEach(chart => { try { chart.resize(); } catch (_) {} });
    drawKline();
  });
}
function showPage(pageId, updateUrl = true) {
  const record = registry.get(pageId); if (!record) return;
  currentPage = pageId; toolPage.hidden = true; toolFrame.hidden = true; wrap.hidden = false;
  registry.forEach(page => page.section.classList.toggle('active', page.id === pageId));
  $$('.tree-link[data-page]', treeNav).forEach(button => {
    const active = button.dataset.page === pageId;
    button.classList.toggle('active', active); button.setAttribute('aria-current', active ? 'page' : 'false');
    if (active) { let parent = button.parentElement; while (parent && parent !== treeNav) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; } }
  });
  $('#breadcrumb').innerHTML = record.trail.map(item => `<span>${item}</span>`).join('') + `<span>${record.title}</span>`;
  document.title = `${record.title} · 研究周报 · 锡`;
  if (updateUrl && location.protocol !== 'file:') history.replaceState(null, '', `./?page=${encodeURIComponent(pageId)}`);
  $('#researchSidebar').classList.remove('open'); $('#menuToggle').setAttribute('aria-expanded', 'false');
  window.scrollTo({top: 0, behavior: 'instant'});
  if (pageId === 'technical') initTechnical();
  resizeCharts();
}
function showTool(toolId) {
  const tool = toolUrls[toolId]; if (!tool) return;
  wrap.hidden = true; toolPage.hidden = false; toolFrame.hidden = false;
  $('#toolTitle').textContent = tool[0]; $('#breadcrumb').innerHTML = `<span>研究工作台</span><span>${tool[0]}</span>`;
  if (toolFrame.dataset.tool !== toolId) { toolFrame.src = tool[1]; toolFrame.dataset.tool = toolId; }
  $$('.tree-link', treeNav).forEach(button => button.classList.remove('active'));
  $('#researchSidebar').classList.remove('open'); document.title = `${tool[0]} · 研究周报 · 锡`;
  window.scrollTo({top: 0, behavior: 'instant'});
}
treeNav.addEventListener('click', event => {
  const pageButton = event.target.closest('[data-page]'), toolButton = event.target.closest('[data-tool]');
  if (pageButton) showPage(pageButton.dataset.page);
  if (toolButton) showTool(toolButton.dataset.tool);
});
$('#closeTool').addEventListener('click', () => showPage(currentPage));
$('#menuToggle').addEventListener('click', () => {
  const sidebar = $('#researchSidebar'), open = sidebar.classList.toggle('open');
  $('#menuToggle').setAttribute('aria-expanded', String(open));
});
const anchorRoutes = {'#sumsec': 'sumsec', '#framework': 'framework', '#sources': 'sources', '#price': 'price',
  '#supply': 'supply_mine', '#smelt': 'supply_smelt', '#inventory': 'inventory', '#invsec': 'inventory',
  '#cost': 'cost', '#balance': 'cost', '#demand': 'demand_solder', '#macro': 'macro', '#technical': 'technical', '#detailed': 'detailed'};
wrap.addEventListener('click', event => {
  const anchor = event.target.closest('a[href^="#"]'); if (!anchor) return;
  const hash = anchor.getAttribute('href');
  if (anchorRoutes[hash]) { event.preventDefault(); showPage(anchorRoutes[hash]); }
});
const viewToggle = $('#viewToggle');
let viewMode = 'desktop';
try { viewMode = localStorage.getItem('tin-view-mode') || (innerWidth <= 820 ? 'mobile' : 'desktop'); } catch (_) { viewMode = innerWidth <= 820 ? 'mobile' : 'desktop'; }
function applyView(mode) {
  viewMode = mode === 'mobile' ? 'mobile' : 'desktop';
  document.body.classList.toggle('view-mobile', viewMode === 'mobile');
  document.body.classList.toggle('view-desktop', viewMode === 'desktop');
  viewToggle.textContent = viewMode === 'mobile' ? '切换电脑版' : '切换手机版';
  viewToggle.setAttribute('aria-pressed', String(viewMode === 'mobile'));
  try { localStorage.setItem('tin-view-mode', viewMode); } catch (_) {}
  resizeCharts();
}
viewToggle.addEventListener('click', () => applyView(viewMode === 'mobile' ? 'desktop' : 'mobile'));
window.addEventListener('resize', drawKline, {passive: true});
const fmt = (value, digits = 0) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', {maximumFractionDigits: digits, minimumFractionDigits: digits});
const MA_COLORS = {MA5: '#a3760e', MA10: '#8b6cc1', MA20: '#1F4E79', MA60: '#188865', MA288: '#c44b5d'};
function drawKline() {
  const canvas = id('snKline');
  if (!canvas || !technicalData?.kline || !registry.get('technical')?.section.classList.contains('active')) return;
  const data = technicalData.kline, rect = canvas.getBoundingClientRect();
  if (rect.width < 50 || rect.height < 50) return;
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width, h = rect.height, pad = {l: 66, r: 18, t: 44, b: 30}, pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
  const nums = [];
  data.candles.forEach(c => { if (c) nums.push(c.h, c.l); });
  Object.values(data.mas || {}).forEach(values => values.forEach(v => { if (v != null) nums.push(v); }));
  let lo = Math.min(...nums), hi = Math.max(...nums); const extra = (hi - lo) * .04 || 1; lo -= extra; hi += extra;
  const y = value => pad.t + (hi - value) / (hi - lo) * ph;
  ctx.clearRect(0, 0, w, h); ctx.font = '10px Arial,"Microsoft YaHei",sans-serif'; ctx.lineWidth = 1;
  for (let j = 0; j <= 6; j++) {
    const yy = pad.t + ph * j / 6, value = hi - (hi - lo) * j / 6;
    ctx.strokeStyle = '#e3e6e8'; ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke();
    ctx.fillStyle = '#777'; ctx.textAlign = 'right'; ctx.fillText(fmt(value), pad.l - 8, yy + 3);
  }
  const n = data.labels.length, step = pw / Math.max(n, 1), body = Math.max(1, Math.min(6, step * .66));
  ctx.textAlign = 'center';
  for (let j = 0; j <= 6; j++) {
    const index = Math.min(n - 1, Math.round((n - 1) * j / 6)), xx = pad.l + step * (index + .5);
    ctx.fillStyle = '#777'; ctx.fillText(data.labels[index].slice(2, 7), xx, h - 8);
  }
  data.candles.forEach((candle, index) => {
    if (!candle) return;
    const xx = pad.l + step * (index + .5), up = candle.c >= candle.o, color = up ? '#c44b5d' : '#188865';
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(xx, y(candle.h)); ctx.lineTo(xx, y(candle.l)); ctx.stroke();
    const top = y(Math.max(candle.o, candle.c)), bottom = y(Math.min(candle.o, candle.c));
    ctx.fillRect(xx - body / 2, top, body, Math.max(1, bottom - top));
  });
  Object.entries(data.mas || {}).forEach(([name, values]) => {
    ctx.strokeStyle = MA_COLORS[name] || '#333'; ctx.lineWidth = name === 'MA288' ? 1.8 : 1.2; ctx.beginPath();
    let open = false;
    values.forEach((value, index) => {
      if (value == null) { open = false; return; }
      const xx = pad.l + step * (index + .5), yy = y(value);
      if (!open) { ctx.moveTo(xx, yy); open = true; } else ctx.lineTo(xx, yy);
    }); ctx.stroke();
  });
  let lx = pad.l; ctx.textAlign = 'left'; ctx.font = '11px Arial,"Microsoft YaHei",sans-serif';
  Object.entries(data.mas || {}).forEach(([name, values]) => {
    const last = [...values].reverse().find(value => value != null), label = `${name} ${last == null ? '—' : fmt(last)}`;
    ctx.fillStyle = MA_COLORS[name] || '#333'; ctx.fillText(label, lx, 18); lx += ctx.measureText(label).width + 15;
  });
}
function initTechnical() {
  if (technicalLoading || technicalData) { drawKline(); return; }
  technicalLoading = true;
  if (window.TIN_TECHNICAL) {
    const data = window.TIN_TECHNICAL;
    technicalData = data;
    id('techGrid').innerHTML = data.tech.map(item => `<article class="tech-card ${['up', 'down', 'neutral'].includes(item.tone) ? item.tone : 'neutral'}"><h3>${item.frame}<span class="score">${item.status}</span></h3><p>${item.detail}</p></article>`).join('');
    id('techUpdated').textContent = `快照 ${data.updated_at || '已更新'}`;
    id('techMeta').textContent = `${data.source || '技术快照'} · MA5 / MA10 / MA20 / MA60 / MA288`;
    requestAnimationFrame(drawKline);
    technicalLoading = false;
    return;
  }
  fetch('./technical.json').then(response => { if (!response.ok) throw new Error('technical snapshot unavailable'); return response.json(); }).then(data => {
    technicalData = data;
    id('techGrid').innerHTML = data.tech.map(item => `<article class="tech-card ${['up', 'down', 'neutral'].includes(item.tone) ? item.tone : 'neutral'}"><h3>${item.frame}<span class="score">${item.status}</span></h3><p>${item.detail}</p></article>`).join('');
    id('techUpdated').textContent = `快照 ${data.updated_at || '已更新'}`;
    id('techMeta').textContent = `${data.source || '技术快照'} · MA5 / MA10 / MA20 / MA60 / MA288`;
    requestAnimationFrame(drawKline);
  }).catch(() => {
    id('techUpdated').textContent = '技术快照读取失败';
    id('techGrid').innerHTML = '<div class="tech-note">暂时无法读取技术快照，请稍后刷新重试。</div>';
  }).finally(() => { technicalLoading = false; });
}
const requested = new URLSearchParams(location.search).get('page') || anchorRoutes[location.hash] || 'sumsec';
applyView(viewMode); showPage(registry.has(requested) ? requested : 'sumsec', false);
