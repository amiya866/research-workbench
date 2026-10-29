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
  group('总览', [page('sumsec', '本周总结'), page('price', '价格与结构（图）'), page('balance', '年度平衡与2027策略'), page('framework', '产业框架'), page('sources', '数据缺口')], true),
  group('重点关注', [
    group('供给', [page('supply', '纯镍与印尼供应'), page('inventory', '库存与仓单'), page('cost', '成本与利润')], true),
    group('需求', [page('demand', '不锈钢与新能源')], true)
  ], true),
  group('研究工作台', [
    {type: 'tool', id: 'panel', label: '镍市瞭望'},
    {type: 'tool', id: 'framework', label: '原研究框架'},
    {type: 'tool', id: 'sources', label: '周报图表溯源'}
  ])
];
const treeNav = $('#treeNav');
function buildNav(items, parent, depth = 0, label = '研究目录') {
  const row = document.createElement('div'); row.className = `nav-row nav-row-depth-${depth}`;
  const caption = document.createElement('span'); caption.className = 'nav-row-label'; caption.textContent = label;
  row.appendChild(caption); parent.appendChild(row);
  items.forEach(item => {
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'tree-link nav-choice' + (item.type === 'group' ? ' is-parent' : '');
    button.textContent = item.label; row.appendChild(button);
    if (item.type === 'group') {
      button.addEventListener('click', () => {
        let target = item;
        while (target.type === 'group') target = target.children[0];
        if (target.type === 'tool') showTool(target.id); else showPage(target.id);
      });
      buildNav(item.children, parent, depth + 1, item.label);
    } else {
      button.dataset[item.type === 'tool' ? 'tool' : 'page'] = item.id;
    }
  });
}
buildNav(NAV, treeNav);
const toolPage = $('#toolPage'), toolFrame = $('#toolFrame');
const toolUrls = {
  panel: ['镍市瞭望', 'https://amiya866.github.io/nickel-panel/'],
  framework: ['原研究框架', 'https://amiya866.github.io/nickel-panel/framework.html'],
  sources: ['周报图表溯源', 'https://amiya866.github.io/nickel-panel/sources.html']
};
let currentPage = 'sumsec';
function resizeCharts() {
  requestAnimationFrame(() => {
    if (window.Chart?.instances) Object.values(window.Chart.instances).forEach(chart => { try { chart.resize(); } catch (_) {} });
  });
}
function showPage(pageId, updateUrl = true) {
  const record = registry.get(pageId); if (!record) return;
  currentPage = pageId; toolPage.hidden = true; toolFrame.hidden = true; wrap.hidden = false;
  registry.forEach(page => page.section.classList.toggle('active', page.id === pageId));
  $$('.tree-link[data-page]', treeNav).forEach(button => {
    const active = button.dataset.page === pageId;
    button.classList.toggle('active', active); button.setAttribute('aria-current', active ? 'page' : 'false');
    if (active) {
      let parent = button.parentElement;
      while (parent && parent !== treeNav) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; }
    }
  });
  $('#breadcrumb').innerHTML = record.trail.map(item => `<span>${item}</span>`).join('') + `<span>${record.title}</span>`;
  document.title = `${record.title} · 研究周报 · 镍`;
  if (updateUrl && location.protocol !== 'file:') history.replaceState(null, '', `./?page=${encodeURIComponent(pageId)}`);
  $('#researchSidebar').classList.remove('open'); $('#menuToggle').setAttribute('aria-expanded', 'false');
  window.scrollTo({top: 0, behavior: 'instant'}); resizeCharts();
}
function showTool(toolId) {
  const tool = toolUrls[toolId]; if (!tool) return;
  wrap.hidden = true; toolPage.hidden = false; toolFrame.hidden = false;
  $('#toolTitle').textContent = tool[0]; $('#breadcrumb').innerHTML = `<span>研究工作台</span><span>${tool[0]}</span>`;
  if (toolFrame.dataset.tool !== toolId) { toolFrame.src = tool[1]; toolFrame.dataset.tool = toolId; }
  $$('.tree-link', treeNav).forEach(button => button.classList.remove('active'));
  $('#researchSidebar').classList.remove('open'); document.title = `${tool[0]} · 研究周报 · 镍`;
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
  '#supply': 'supply', '#demand': 'demand', '#inventory': 'inventory', '#cost': 'cost', '#balance': 'balance'};
wrap.addEventListener('click', event => {
  const anchor = event.target.closest('a[href^="#"]'); if (!anchor) return;
  const hash = anchor.getAttribute('href');
  if (anchorRoutes[hash]) { event.preventDefault(); showPage(anchorRoutes[hash]); }
});
const viewToggle = $('#viewToggle');
let viewMode = 'desktop';
try { viewMode = localStorage.getItem('nickel-view-mode') || (innerWidth <= 820 ? 'mobile' : 'desktop'); } catch (_) { viewMode = innerWidth <= 820 ? 'mobile' : 'desktop'; }
function applyView(mode) {
  viewMode = mode === 'mobile' ? 'mobile' : 'desktop';
  document.body.classList.toggle('view-mobile', viewMode === 'mobile');
  document.body.classList.toggle('view-desktop', viewMode === 'desktop');
  viewToggle.textContent = viewMode === 'mobile' ? '切换电脑版' : '切换手机版';
  viewToggle.setAttribute('aria-pressed', String(viewMode === 'mobile'));
  try { localStorage.setItem('nickel-view-mode', viewMode); } catch (_) {}
  resizeCharts();
}
viewToggle.addEventListener('click', () => applyView(viewMode === 'mobile' ? 'desktop' : 'mobile'));
window.addEventListener('resize', resizeCharts, {passive: true});
const requested = new URLSearchParams(location.search).get('page') || anchorRoutes[location.hash] || 'sumsec';
applyView(viewMode); showPage(registry.has(requested) ? requested : 'sumsec', false);
