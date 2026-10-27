'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const wrap = $('#reportWrap');
const registry = new Map();
const meaningful = node => node.nodeType === 1 || (node.nodeType === 3 && node.textContent.trim());
const isH2 = node => node.nodeType === 1 && node.tagName === 'H2';
const withoutHeading = nodes => nodes.filter(node => !isH2(node));

function takeUntil(start, stop) {
  const nodes = [];
  let node = start;
  while (node && node !== stop) { nodes.push(node); node = node.nextSibling; }
  return nodes;
}

function splitOnMarkers(nodes, predicate) {
  const groups = [];
  let current = [];
  nodes.forEach(node => {
    if (predicate(node) && current.some(meaningful)) {
      const onlyHeading = current.filter(meaningful).every(isH2);
      if (!onlyHeading) { groups.push(current); current = []; }
      else current = [];
    }
    current.push(node);
  });
  if (current.some(meaningful)) groups.push(current);
  return groups;
}

function register(id, title, trail, nodes) {
  registry.set(id, { id, title, trail, nodes: withoutHeading(nodes.filter(meaningful)) });
}

const ppt = $(':scope > .pptzone', wrap);
const id = value => document.getElementById(value);
const nextH2 = node => {
  let current = node.nextSibling;
  while (current && !isH2(current)) current = current.nextSibling;
  return current;
};

/* Overview */
register('summary', '本周总结', ['总览'], [id('sumsec').previousElementSibling?.classList.contains('roll') ? null : null].filter(Boolean));
const summaryNodes = [$('.tone', wrap), $('.roll', wrap), id('sumsec'), $('footer', wrap)].filter(Boolean);
registry.get('summary').nodes = summaryNodes;
register('quarter', '季度展望', ['总览'], [id('q4outlook')]);
register('framework', '产业框架', ['总览'], [id('framework')]);
register('datagap', '数据缺口', ['总览'], [id('datagap')]);

/* Focus: sentiment and macro */
const focusGroups = splitOnMarkers(takeUntil(id('focus'), id('ai')), node => node.nodeType === 1 && node.classList.contains('lead'));
register('focus-sentiment', '锡市场情绪', ['宏观与策略'], focusGroups[0] || []);
register('focus-macro', '宏观环境', ['宏观与策略'], focusGroups[1] || []);
register('ai', 'AI 高频验证', ['宏观与策略'], takeUntil(id('ai'), id('supply')));

/* Supply and inventory */
const supplyGroups = splitOnMarkers(takeUntil(id('supply'), id('invsec')), node => node.nodeType === 1 && node.classList.contains('lead'));
register('supply-mine', '矿端与进口', ['重点关注', '供给'], supplyGroups[0] || []);
register('supply-smelt', '冶炼与精锡', ['重点关注', '供给'], supplyGroups[1] || []);
register('inventory', '显性库存', ['重点关注', '供给'], takeUntil(id('invsec'), id('balance')));
register('balance', '平衡表与全年情景', ['平衡表'], [id('balance')]);

/* Demand: follow the industry-chain ownership, not the original chart order. */
const demandGroups = splitOnMarkers(takeUntil(id('demand'), id('spot')), node => node.nodeType === 1 && node.classList.contains('lead'));
const solderTrail = ['重点关注', '需求', '锡焊料'];
const chemicalTrail = ['重点关注', '需求', '锡化工'];
register('demand-solder', '焊料开工与成交', solderTrail, demandGroups[0] || []);
register('demand-battery', '铅蓄电池', ['重点关注', '需求'], demandGroups[2] || []);
register('demand-appliance', '三大白电', solderTrail, demandGroups[3] || []);
register('demand-tinplate', '马口铁', ['重点关注', '需求'], demandGroups[5] || []);
register('demand-semi', '半导体', solderTrail, demandGroups[6] || []);

function splitChartGroup(nodes, indexes) {
  const container = nodes.find(node => node.nodeType === 1 && node.classList.contains('charts3'));
  const charts = container.cloneNode(false);
  $$(':scope > .cbox', container).forEach((box, index) => {
    if (!indexes.includes(index)) return;
    const clone = box.cloneNode(true);
    clone.classList.remove('ec');
    $$('canvas', clone).forEach(canvas => canvas.remove());
    $$('img', clone).forEach(image => { image.loading = 'eager'; });
    charts.appendChild(clone);
  });
  return charts;
}
function lead(text) {
  const node = document.createElement('div'); node.className = 'lead'; node.textContent = text; return node;
}

/* Tin chemicals: PVC and float glass are parallel downstream pages. */
register('demand-pvc', 'PVC', chemicalTrail, [...withoutHeading(demandGroups[1].filter(node => !(node.nodeType === 1 && node.classList.contains('charts3')))), splitChartGroup(demandGroups[1], [0])]);
register('demand-float', '浮法玻璃', chemicalTrail, [lead('浮法玻璃：周产量 · PVC＋浮法玻璃合计耗锡'), splitChartGroup(demandGroups[1], [1, 2])]);

/* Solder downstream: new-energy vehicles and photovoltaics are separate pages. */
register('demand-newenergy', '新能源汽车', solderTrail, [...withoutHeading(demandGroups[4].filter(node => !(node.nodeType === 1 && node.classList.contains('charts3')))), splitChartGroup(demandGroups[4], [0])]);
register('demand-solar', '光伏', solderTrail, [lead('光伏：组件产量 · 光伏耗锡量'), splitChartGroup(demandGroups[4], [1, 2])]);

/* Other weekly pages */
register('spot', '现货与进出口', ['宏观与策略'], takeUntil(id('spot'), id('strategy')));
register('strategy', '策略与验证点', ['宏观与策略'], takeUntil(id('strategy'), id('lab')));
register('lab', '图表工作区', ['图表工作区'], takeUntil(id('lab'), id('ai-detail')));
register('cost', '矿山成本与边际', ['重点关注', '供给'], takeUntil(id('minecost'), id('decks')));

/* AI tin-demand chapters */
const aiGroups = splitOnMarkers(takeUntil(id('ai-detail'), id('minecost')), node => node.nodeType === 1 && node.classList.contains('lead'));
const aiLabels = ['核心结论', '研究背景', '测算边界', '芯片端', '板级制造', '全链路结果', 'PCB 扩产', '结论与验证', '跟踪与口径'];
const aiIds = ['ai-core', 'ai-background', 'ai-boundary', 'ai-chip', 'ai-board', 'ai-results', 'ai-pcb', 'ai-conclusion', 'ai-tracking'];
aiGroups.forEach((nodes, index) => register(aiIds[index], aiLabels[index], ['AI 耗锡专题'], nodes));

/* Detailed decks: each DECK continues into its own chart topics. */
const deckConfigs = [
  { start: 'ai-weekly-detail', label: 'AI 与美股', labels: ['产业链扩展数据', '美股财报验证'] },
  { label: 'DECK 1 · 矿端', labels: ['储量', '全球产量', '潜在项目', '矿山季度产量', '海外矿山一', '海外矿山二', '中国矿端', '锡精矿进口'] },
  { label: 'DECK 2 · 冶炼', labels: ['全球冶炼占比', 'ITA 精锡', '中国冶炼', '周度冶炼', '锡锭进口', '精锡进出口'] },
  { label: 'DECK 3 · 焊料家电', labels: ['需求结构', '锡材与焊料', '白电排产', '白电耗锡', '冰箱', '洗衣机', '空调', '冷柜', '彩电'] },
  { label: 'DECK 4 · 电子光伏', labels: ['电子产品产量', '电子产品耗锡', '集成电路与 PCB', '中国出货量', '全球出货量', '半导体', '光伏', '镀锡板'] },
  { label: 'DECK 5 · 化工电池', labels: ['锡化工', '浮法玻璃', '铅蓄电池'] },
  { label: 'DECK 6 · 汽车库存', labels: ['汽车出口', '海外溢价', 'LME 持仓', '地区升水', '显性库存'] },
  { label: 'DECK 7 · 汽车平衡', labels: ['汽车产销', '平衡图表', '进出口盈亏', '美印尼日贸易', '日本泰国贸易', '泰国锡贸易'] }
];
let deckStart = id('ai-weekly-detail');
deckConfigs.forEach((config, deckIndex) => {
  const heading = deckIndex === 0 ? deckStart : (() => {
    let h = deckStart;
    for (let i = 0; i < deckIndex; i++) h = nextH2(h);
    return h;
  })();
  const end = nextH2(heading);
  const groups = splitOnMarkers(takeUntil(heading, end), node => node.nodeType === 1 && node.classList.contains('lead'));
  groups.forEach((nodes, topicIndex) => {
    const pageId = `deck-${deckIndex + 1}-${topicIndex + 1}`;
    register(pageId, config.labels[topicIndex] || `图表主题 ${topicIndex + 1}`, ['详细周报', config.label], nodes);
    config.children = config.children || [];
    config.children.push({ id: pageId, label: config.labels[topicIndex] || `图表主题 ${topicIndex + 1}` });
  });
});

/* Create independent report pages. */
const sourceFooter = $('footer', wrap);
registry.forEach(page => {
  const section = document.createElement('section');
  section.className = 'report-page';
  section.dataset.page = page.id;
  section.setAttribute('aria-labelledby', `heading-${page.id}`);
  const heading = document.createElement('div');
  heading.className = 'page-heading';
  heading.innerHTML = `<h2 id="heading-${page.id}"></h2><span></span>`;
  $('h2', heading).textContent = page.title;
  $('span', heading).textContent = page.trail.join(' / ').toUpperCase();
  const body = document.createElement('div');
  body.className = 'page-body';
  page.nodes.forEach(node => body.appendChild(node));
  section.append(heading, body);
  page.section = section;
  page.body = body;
  wrap.insertBefore(section, sourceFooter && sourceFooter.parentNode === wrap ? sourceFooter : null);
});
if (ppt) ppt.remove();
if (sourceFooter) sourceFooter.remove();
id('balance').open = true;
id('q4outlook').open = false;
id('framework').open = false;
id('datagap').open = false;
const roll = $('.roll', wrap);
if (roll) roll.textContent = '策略每日滚动更新：周报为周五存档，最新决策见日报页。使用顶部目录切换研究内容。';
$$('summary', wrap).forEach(summary => { summary.innerHTML = summary.innerHTML.replace('表格可编辑', '数据明细'); });

/* Navigation schema */
const page = (id, label) => ({ type: 'page', id, label });
const group = (label, children, open = false) => ({ type: 'group', label, children, open });
const NAV = [
  group('总览', [page('summary', '本周总结'), page('quarter', '季度展望'), page('framework', '产业框架')], true),
  group('重点关注', [
    group('供给', [page('supply-mine', '矿端与进口'), page('supply-smelt', '冶炼与精锡'), page('inventory', '显性库存'), page('cost', '矿山成本与边际')], true),
    group('需求', [
      group('锡焊料', [
        page('demand-solder', '焊料开工与成交'), page('demand-appliance', '三大白电'),
        page('demand-newenergy', '新能源汽车'), page('demand-solar', '光伏'), page('demand-semi', '半导体')
      ], true),
      group('锡化工', [page('demand-pvc', 'PVC'), page('demand-float', '浮法玻璃')], true),
      page('demand-tinplate', '马口铁'),
      page('demand-battery', '铅蓄电池')
    ], true)
  ], true),
  group('宏观与策略', [page('focus-sentiment', '锡市场情绪'), page('focus-macro', '宏观环境'), page('ai', 'AI 高频验证'), page('spot', '现货与进出口'), page('strategy', '策略与验证点')]),
  page('balance', '平衡表与全年情景'),
  group('AI 耗锡专题', aiIds.filter(pid => registry.has(pid)).map(pid => page(pid, aiLabels[aiIds.indexOf(pid)]))),
  page('lab', '图表工作区'),
  group('详细周报', deckConfigs.map(config => group(config.label, config.children.map(child => page(child.id, child.label))))),
  group('研究工作台', [
    { type: 'tool', id: 'daily', label: '锡研究日报' }, { type: 'tool', id: 'sheet', label: '数据日报' },
    { type: 'tool', id: 'archive', label: '周报留档' }, { type: 'tool', id: 'news', label: '市场信息和情绪' },
    { type: 'tool', id: 'db', label: '锡研究数据库' }, { type: 'tool', id: 'metals', label: '其他有色' },
    { type: 'tool', id: 'cu', label: '铜研究' }, { type: 'tool', id: 'cudb', label: '铜数据库' }
  ]),
  page('datagap', '数据缺口')
];

const treeNav = $('#treeNav');
function buildNav(items, parent, depth = 0) {
  items.forEach(item => {
    if (item.type === 'group') {
      const details = document.createElement('details');
      details.open = depth > 0 && item.open;
      const summary = document.createElement('summary'); summary.textContent = item.label;
      const children = document.createElement('div'); children.className = 'tree-children';
      details.append(summary, children); parent.appendChild(details);
      buildNav(item.children, children, depth + 1);
    } else {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'tree-link'; button.textContent = item.label;
      button.dataset[item.type === 'tool' ? 'tool' : 'page'] = item.id;
      parent.appendChild(button);
    }
  });
}
buildNav(NAV, treeNav);

/* Private technical analysis: original daily-report theory, external price snapshots. */
const technicalPage = registry.get('technical') || (() => {
  register('technical', '技术分析（私享）', ['技术分析'], []);
  const section = document.createElement('section'); section.className = 'report-page'; section.dataset.page = 'technical';
  section.innerHTML = '<div class="page-heading"><h2>技术分析（私享）</h2><span>DAILY METHODOLOGY · 15M / 60M / DAILY</span></div><div class="page-body"></div>';
  const record = { id: 'technical', title: '技术分析（私享）', trail: ['技术分析'], section, body: $('.page-body', section) };
  registry.set('technical', record); wrap.appendChild(section); return record;
})();
technicalPage.body.innerHTML = `
  <div class="tech-gate" id="techGate"><h3>技术分析（私享）</h3><p>采用锡研究日报原有技术理论。请输入访问密码，解锁仅在本次浏览器会话中有效。</p><form id="techForm"><input id="techPassword" type="password" inputmode="numeric" autocomplete="off" aria-label="技术分析访问密码" placeholder="访问密码" required><button type="submit">解锁技术分析</button></form><div class="tech-gate-error" id="techGateError" aria-live="polite"></div></div>
  <div class="tech-private" id="techPrivate" hidden>
    <button class="tech-lock" id="techLock" type="button">退出私享</button>
    <div class="tech-intro"><p>趋势 / 动能 / 量价 · 日线原引擎 · 多周期验证</p><span class="tag" id="privateTechUpdated">等待读取数据…</span></div>
    <div class="tech-score" id="privateTechScore"></div><div class="tech-grid" id="privateTechGrid"></div>
    <div class="tech-brief" id="privateTechBrief"></div>
    <div class="tech-note" id="privateTechMethod"><b>原日报指标体系：</b>趋势使用均线、MACD(12,26,9)、DMI、DMA、BOLL、缠论中枢与周线 MACD；动能使用 KDJ、RSI、WR、CCI、ROC；结构辅助使用数浪与背驰。当前快照无成交量和持仓量，量价维度不参与评分，也不补造数据。</div>
    <div class="kline-card"><h3>沪锡主连｜日 K 价格与均线</h3><div class="meta-line" id="privateTechMeta">MA5 / MA10 / MA20 / MA60 / MA288 · 红涨绿跌</div><div class="kline-chart"><canvas id="privateSnKline" aria-label="沪锡主连日 K 图"></canvas></div></div>
  </div>`;
let technicalData = null, technicalLoading = false, enginePromise = null, legacyPromise = null;
let techUnlocked = false;
try { techUnlocked = sessionStorage.getItem('tin-weekly-tech-private') === 'unlocked'; } catch (_) {}
const TECH_PASSWORD_HASH = '7f861bcee185de001377d79e08af62e94b1e7718e2470e08520c917f8d953602';
const fmt = (value, digits = 0) => value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const MA_COLORS = { MA5: '#a3760e', MA10: '#8b6cc1', MA20: '#1F4E79', MA60: '#188865', MA288: '#c44b5d' };
function syncTechGate() {
  id('techGate').hidden = techUnlocked; id('techPrivate').hidden = !techUnlocked;
  $('#techTop').textContent = techUnlocked ? '技术分析（已解锁）' : '技术分析（私享）';
}
async function sha256(text) {
  const bytes = new TextEncoder().encode(text), hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
id('techForm').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.target.querySelector('button'); button.disabled = true;
  try {
    if (await sha256(id('techPassword').value) !== TECH_PASSWORD_HASH) throw new Error('密码不正确，请重新输入。');
    techUnlocked = true; try { sessionStorage.setItem('tin-weekly-tech-private', 'unlocked'); } catch (_) {}
    id('techGateError').textContent = ''; id('techPassword').value = ''; syncTechGate(); initTechnical();
  } catch (error) { id('techGateError').textContent = error.message; }
  finally { button.disabled = false; }
});
id('techLock').addEventListener('click', () => {
  techUnlocked = false; try { sessionStorage.removeItem('tin-weekly-tech-private'); } catch (_) {}
  syncTechGate(); showPage('summary');
});
$('#techTop').addEventListener('click', () => showPage('technical'));

function loadDailyEngine() {
  if (window.TECH?.analyze) return Promise.resolve();
  if (enginePromise) return enginePromise;
  enginePromise = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = './daily_tech_engine.js';
    script.onload = () => window.TECH?.analyze ? resolve() : reject(new Error('日报技术引擎不可用'));
    script.onerror = () => reject(new Error('日报技术引擎加载失败')); document.head.appendChild(script);
  });
  return enginePromise;
}
function loadLegacyTechData() {
  if (window.TIN_LEGACY_TECH) return Promise.resolve(window.TIN_LEGACY_TECH);
  if (legacyPromise) return legacyPromise;
  legacyPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = './daily_volume_oi.js';
    script.onload = () => window.TIN_LEGACY_TECH ? resolve(window.TIN_LEGACY_TECH) : reject(new Error('旧日报量仓不可用'));
    script.onerror = () => reject(new Error('旧日报量仓加载失败')); document.head.appendChild(script);
  });
  return legacyPromise;
}
function mergeTechnicalData(data, legacy) {
  if (!legacy) return data;
  const volume = new Map(legacy.volume || []), oi = new Map(legacy.oi || []);
  data.kline.candles.forEach((candle, index) => {
    if (!candle) return;
    const date = data.kline.labels[index];
    if (!(Number(candle.v) > 0) && Number(volume.get(date)) > 0) candle.v = Number(volume.get(date));
    if (!(Number(candle.oi) > 0) && Number(oi.get(date)) > 0) candle.oi = Number(oi.get(date));
  });
  data.legacyTech = legacy;
  return data;
}
async function fetchJson(url) {
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
  try { const response = await fetch(url, { cache: 'no-store', signal: controller.signal }); if (!response.ok) throw new Error(String(response.status)); return await response.json(); }
  finally { clearTimeout(timer); }
}
async function fetchTechnicalSnapshot() {
  const sources = ['https://tin-insight-api.wangziquan-tin.workers.dev/api/technical', 'https://amiya866.github.io/tin-insight/technical.json', './technical.json'];
  let lastError;
  for (const source of sources) {
    try { const data = await fetchJson(source); if (Array.isArray(data.tech) && data.tech.length >= 3 && data.kline?.candles?.length) return data; }
    catch (error) { lastError = error; }
  }
  throw lastError || new Error('技术数据不可用');
}
function scoreSnapshot(item) {
  const text = item.detail || '';
  const number = pattern => { const match = text.match(pattern); return match ? Number(match[1].replace(/,/g, '')) : null; };
  const ma5 = number(/MA5\s*([\d,]+)/), ma20 = number(/MA20\s*([\d,]+)/), dif = number(/DIF\s*(-?[\d,]+)/), dea = number(/DEA\s*(-?[\d,]+)/), rsi = number(/RSI14\s*([\d.]+)/);
  const price = Number(item.price); let trend = 0;
  if (ma5 != null) trend += price >= ma5 ? 20 : -20;
  if (ma20 != null) trend += price >= ma20 ? 20 : -20;
  if (ma5 != null && ma20 != null) trend += ma5 >= ma20 ? 20 : -20;
  if (dif != null && dea != null) trend += dif >= dea ? 20 : -20;
  if (dif != null) trend += dif >= 0 ? 20 : -20;
  let momentum = dif == null || dea == null ? 0 : (dif >= dea ? 35 : -35);
  if (rsi != null) momentum += rsi >= 55 ? 35 : rsi <= 45 ? -35 : 0;
  if (momentum > 100) momentum = 100; if (momentum < -100) momentum = -100;
  const total = Math.round(trend * .6 + momentum * .4);
  return { trend: Math.round(trend), momentum: Math.round(momentum), total, ma5, ma20, dif, dea, rsi };
}
function rating(score) { return score >= 25 ? ['多头占优', 'up'] : score <= -25 ? ['空头占优', 'down'] : ['震荡平衡', 'neutral']; }
function renderTechnical(data) {
  const labels = data.kline.labels, candles = data.kline.candles;
  const series = key => labels.map((date, index) => [date, candles[index][key]]);
  const hasVolume = candles.some(candle => Number(candle.v) > 0), hasOi = candles.some(candle => Number(candle.oi) > 0);
  window.DB_DATA = [
    { k: 'd719', s: series('c') }, { k: 'd726', s: series('o') }, { k: 'd727', s: series('h') },
    { k: 'd728', s: series('l') }, { k: 'd729', s: labels.map((date, i) => [date, Number(candles[i].v) || 0]) },
    { k: 'd725', s: labels.map((date, i) => [date, Number(candles[i].oi) || 0]) }
  ];
  const analysis = window.TECH.analyze(), originalScore = window.TECH.score(), last = analysis.n - 1;
  const hasVolumeScore = hasVolume && hasOi;
  const total = hasVolumeScore ? originalScore.total : Math.round(originalScore.t * .6 + originalScore.m * .4);
  const [dailyRating, dailyTone] = rating(total);
  const ma = name => analysis.MA[name][last], macd = analysis.M.dif[last] - analysis.M.dea[last];
  const cards = data.tech.slice(0, 2).map(item => {
    const score = scoreSnapshot(item), [status, tone] = rating(score.total);
    return { frame: item.frame, status, tone, total: score.total, detail: `趋势 ${score.trend} / 动能 ${score.momentum}\nMA5 ${fmt(score.ma5)} · MA20 ${fmt(score.ma20)}\nMACD DIF ${fmt(score.dif)} · DEA ${fmt(score.dea)} · RSI14 ${fmt(score.rsi, 1)}\n${(item.detail.match(/缠论简化结构[^；]+/) || ['结构区间见快照'])[0]}\n量价：快照未提供，不参与评分` };
  });
  cards.push({ frame: '大级别｜日线', status: dailyRating, tone: dailyTone, total, detail: `趋势 ${originalScore.t} / 动能 ${originalScore.m}\nMA5 ${fmt(ma('m5'))} · MA20 ${fmt(ma('m20'))} · MA60 ${fmt(ma('m60'))}\nDIF ${fmt(analysis.M.dif[last])} · DEA ${fmt(analysis.M.dea[last])} · 柱 ${fmt(macd)}\nKDJ ${fmt(analysis.KD.k[last], 1)} / ${fmt(analysis.KD.d[last], 1)} · RSI14 ${fmt(analysis.RSI14[last], 1)}\n中枢 ${analysis.zs ? `${fmt(analysis.zs.ZD)}–${fmt(analysis.zs.ZG)}` : '结构不足'}${hasVolumeScore ? `\n量价 ${originalScore.v}：旧日报成交量与持仓量补齐` : '\n量价：源数据缺失，不参与评分'}` });
  id('privateTechGrid').innerHTML = cards.map(card => `<article class="tech-card ${card.tone}"><h3>${escapeHtml(card.frame)}<span class="score">${card.total} · ${card.status}</span></h3><p>${escapeHtml(card.detail)}</p></article>`).join('');
  id('privateTechScore').innerHTML = `<div><span>日线综合评分</span><strong>${total}</strong><small>${dailyRating}</small></div><div><span>趋势</span><strong>${originalScore.t}</strong><small>${hasVolumeScore ? '原日报权重 45%' : '可用维度权重 60%'}</small></div><div><span>动能</span><strong>${originalScore.m}</strong><small>${hasVolumeScore ? '原日报权重 30%' : '可用维度权重 40%'}</small></div><div><span>量价</span><strong>${hasVolumeScore ? originalScore.v : '—'}</strong><small>${hasVolumeScore ? `旧日报补齐 · 原日报权重 25%` : '源数据缺失，不参与评分'}</small></div>`;
  const recent = candles.slice(-20), support = Math.min(...recent.map(c => c.l)), resistance = Math.max(...recent.map(c => c.h));
  let strategy;
  if (total >= 25) strategy = `短期（2–3天）：上行方向占优，回踩不破支撑时顺势观察；中短期（2–3周）：关注 ${fmt(support)} 支撑与 ${fmt(resistance)} 前高，突破需动能同步配合；策略：多头思维，避免在动能背离时追高。`;
  else if (total <= -25) strategy = `短期（2–3天）：下行方向未改，反抽先按修复观察；中短期（2–3周）：${fmt(resistance)} 附近构成压力，下方观察 ${fmt(support)}；策略：控制仓位，跌破支撑按纪律处理，不盲目抄底。`;
  else strategy = `短期（2–3天）：无方向性优势，区间思维；中短期（2–3周）：${fmt(support)}～${fmt(resistance)} 区间震荡，边界附近反向观察；中期（2–3月）：等待结构突破再定方向；策略：区间高抛低吸，放量突破边界后跟随。`;
  id('privateTechBrief').innerHTML = `<b>技术面评分 ${total}（${dailyRating}）</b>。${strategy}<br><b>结构提示：</b>${escapeHtml(analysis.wave || '结构不足，暂不数浪')} 数浪与背驰仅供结构复核，以价格、MACD 和关键区间共同验证。`;
  id('privateTechUpdated').textContent = `快照 ${data.updated_at || '已更新'}`;
  id('privateTechMethod').innerHTML = `<b>原日报指标体系：</b>趋势使用均线、MACD(12,26,9)、DMI、DMA、BOLL、缠论中枢与周线 MACD；动能使用 KDJ、RSI、WR、CCI、ROC；结构辅助使用数浪与背驰。${hasVolumeScore ? `新快照缺少的成交量和持仓量已按日期使用旧日报数据补齐，量价按原权重参与评分；旧源量仓分别更新至 ${escapeHtml(data.legacyTech?.volumeUpdated || '—')} / ${escapeHtml(data.legacyTech?.oiUpdated || '—')}。` : '当前量仓数据仍缺失，量价维度不参与评分，也不补造数据。'}`;
  id('privateTechMeta').textContent = `${data.source || '外部技术快照'}${hasVolumeScore ? '＋旧日报量仓' : ''} · MA5 / MA10 / MA20 / MA60 / MA288`;
  requestAnimationFrame(drawKline);
}
function initTechnical() {
  syncTechGate(); if (!techUnlocked || technicalLoading) return;
  if (technicalData) { renderTechnical(technicalData); return; }
  technicalLoading = true; id('privateTechUpdated').textContent = '正在读取数据并运行日报引擎…';
  Promise.all([fetchTechnicalSnapshot(), loadDailyEngine(), loadLegacyTechData().catch(() => null)]).then(([data, , legacy]) => { technicalData = mergeTechnicalData(data, legacy); renderTechnical(technicalData); }).catch(() => {
    id('privateTechUpdated').textContent = '技术数据读取失败'; id('privateTechGrid').innerHTML = '<div class="tech-note">暂时无法读取技术数据或日报引擎，请稍后刷新重试。</div>';
  }).finally(() => { technicalLoading = false; });
}

function drawKline() {
  const canvas = id('privateSnKline');
  if (!canvas || !technicalData?.kline || !techUnlocked || !technicalPage.section.classList.contains('active')) return;
  const data = technicalData.kline, rect = canvas.getBoundingClientRect(); if (rect.width < 50 || rect.height < 50) return;
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1)); canvas.width = Math.round(rect.width * dpr); canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = rect.width, h = rect.height, pad = { l: 66, r: 18, t: 44, b: 30 }, pw = w - pad.l - pad.r, ph = h - pad.t - pad.b, nums = [];
  data.candles.forEach(c => { if (c) nums.push(c.h, c.l); }); Object.values(data.mas || {}).forEach(values => values.forEach(v => { if (v != null) nums.push(v); }));
  let lo = Math.min(...nums), hi = Math.max(...nums); const extra = (hi - lo) * .04 || 1; lo -= extra; hi += extra;
  const y = value => pad.t + (hi - value) / (hi - lo) * ph;
  ctx.clearRect(0, 0, w, h); ctx.font = '10px -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif'; ctx.lineWidth = 1;
  for (let j = 0; j <= 6; j++) { const yy = pad.t + ph * j / 6, value = hi - (hi - lo) * j / 6; ctx.strokeStyle = '#e3e6e8'; ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy); ctx.stroke(); ctx.fillStyle = '#777'; ctx.textAlign = 'right'; ctx.fillText(fmt(value), pad.l - 8, yy + 3); }
  const n = data.labels.length, step = pw / Math.max(n, 1), body = Math.max(1, Math.min(6, step * .66)); ctx.textAlign = 'center';
  for (let j = 0; j <= 6; j++) { const index = Math.min(n - 1, Math.round((n - 1) * j / 6)), xx = pad.l + step * (index + .5); ctx.fillStyle = '#777'; ctx.fillText(data.labels[index].slice(2, 7), xx, h - 8); }
  data.candles.forEach((candle, index) => { if (!candle) return; const xx = pad.l + step * (index + .5), up = candle.c >= candle.o, color = up ? '#c44b5d' : '#188865'; ctx.strokeStyle = color; ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(xx, y(candle.h)); ctx.lineTo(xx, y(candle.l)); ctx.stroke(); const top = y(Math.max(candle.o, candle.c)), bottom = y(Math.min(candle.o, candle.c)); ctx.fillRect(xx - body / 2, top, body, Math.max(1, bottom - top)); });
  Object.entries(data.mas || {}).forEach(([name, values]) => { ctx.strokeStyle = MA_COLORS[name] || '#333'; ctx.lineWidth = name === 'MA288' ? 1.8 : 1.2; ctx.beginPath(); let open = false; values.forEach((value, index) => { if (value == null) { open = false; return; } const xx = pad.l + step * (index + .5), yy = y(value); if (!open) { ctx.moveTo(xx, yy); open = true; } else ctx.lineTo(xx, yy); }); ctx.stroke(); });
  let lx = pad.l; ctx.textAlign = 'left'; ctx.font = '11px -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif'; Object.entries(data.mas || {}).forEach(([name, values]) => { const last = [...values].reverse().find(value => value != null), label = `${name} ${last == null ? '—' : fmt(last)}`; ctx.fillStyle = MA_COLORS[name] || '#333'; ctx.fillText(label, lx, 18); lx += ctx.measureText(label).width + 15; });
  const last = data.candles[data.candles.length - 1]; if (last) { ctx.fillStyle = last.c >= last.o ? '#c44b5d' : '#188865'; ctx.textAlign = 'right'; ctx.font = '600 12px -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif'; ctx.fillText(`收盘 ${fmt(last.c)}`, w - pad.r, 18); }
}

/* Annual balance scenario */
const scenario = document.createElement('section');
scenario.className = 'scenario-card';
scenario.innerHTML = `
  <h3>2026E 全球年度敏感性情景</h3><p>在基准平衡 +0.4 万吨上调整全年变量；正值为过剩，负值为短缺。</p>
  <div class="sliders">
    <label class="slider">缅甸矿变化 <b id="v-mm">0.0</b> 万吨<input id="s-mm" type="range" min="-1.5" max="1.5" step="0.1" value="0"></label>
    <label class="slider">印尼矿变化 <b id="v-id">0.0</b> 万吨<input id="s-id" type="range" min="-1.0" max="1.0" step="0.1" value="0"></label>
    <label class="slider">中国精锡变化 <b id="v-cn">0.0</b> 万吨<input id="s-cn" type="range" min="-1.5" max="1.5" step="0.1" value="0"></label>
    <label class="slider">全球需求变化 <b id="v-dem">0.0</b> 万吨<input id="s-dem" type="range" min="-2.0" max="2.0" step="0.1" value="0"></label>
  </div>
  <div class="balance-result"><div>情景下锡锭平衡<small>矿端变化按 80% 向冶炼端传导</small></div><strong id="balance-value">+0.4 万吨</strong></div>
  <div class="scenario-note">滑块用于全年敏感性分析，不是点预测；不构成投资建议。</div>`;
registry.get('balance').body.appendChild(scenario);
function updateBalance() {
  const values = {};
  ['mm', 'id', 'cn', 'dem'].forEach(key => {
    values[key] = Number(id(`s-${key}`).value);
    id(`v-${key}`).textContent = `${values[key] > 0 ? '+' : ''}${values[key].toFixed(1)}`;
  });
  const result = .4 + .8 * (values.mm + values.id) + values.cn - values.dem;
  const output = id('balance-value'); output.textContent = `${result >= 0 ? '+' : ''}${result.toFixed(1)} 万吨`;
  output.style.color = result < 0 ? '#c44b5d' : '#188865';
}
['mm', 'id', 'cn', 'dem'].forEach(key => id(`s-${key}`).addEventListener('input', updateBalance));
updateBalance();

/* Routing and external workbench */
let currentPage = 'summary';
const toolPage = $('#toolPage'), toolFrame = $('#toolFrame');
const toolUrls = {
  daily: ['锡研究日报', 'https://gsy1005.github.io/tin-research/daily_2026-10-26.html'],
  sheet: ['数据日报', 'https://gsy1005.github.io/tin-research/sheet.html'],
  archive: ['周报留档', 'https://gsy1005.github.io/tin-research/weekly_archive.html'],
  news: ['市场信息和情绪', 'https://gsy1005.github.io/tin-research/news.html'],
  db: ['锡研究数据库', 'https://gsy1005.github.io/tin-research/db.html'],
  metals: ['其他有色', 'https://gsy1005.github.io/tin-research/metals.html'],
  cu: ['铜研究', 'https://gsy1005.github.io/tin-research/cu.html'],
  cudb: ['铜数据库', 'https://gsy1005.github.io/tin-research/cu_db.html']
};
function resizeCharts() {
  requestAnimationFrame(() => {
    if (window.Chart?.instances) Object.values(window.Chart.instances).forEach(chart => { try { chart.resize(); } catch (_) {} });
    drawKline();
  });
}
function showPage(pageId, updateUrl = true) {
  const record = registry.get(pageId); if (!record) return;
  currentPage = pageId;
  toolPage.hidden = true; toolFrame.hidden = true; wrap.hidden = false;
  registry.forEach(page => page.section.classList.toggle('active', page.id === pageId));
  $$('.tree-link[data-page]', treeNav).forEach(button => {
    const active = button.dataset.page === pageId;
    button.classList.toggle('active', active); button.setAttribute('aria-current', active ? 'page' : 'false');
  });
  $$(':scope > details', treeNav).forEach(details => { details.open = false; });
  $('#techTop').classList.toggle('active', pageId === 'technical');
  $('#breadcrumb').innerHTML = record.trail.map(item => `<span>${item}</span>`).join('') + `<span>${record.title}</span>`;
  document.title = `${record.title} · 锡研究周报`;
  if (updateUrl) history.replaceState(null, '', `${location.pathname}?page=${encodeURIComponent(pageId)}`);
  window.scrollTo({ top: 0, behavior: 'instant' });
  updateMobilePager();
  if (pageId === 'technical') initTechnical();
  resizeCharts();
}
function showTool(toolId) {
  const tool = toolUrls[toolId]; if (!tool) return;
  wrap.hidden = true; toolPage.hidden = false; toolFrame.hidden = false;
  $('#toolTitle').textContent = tool[0]; $('#breadcrumb').innerHTML = `<span>研究工作台</span><span>${tool[0]}</span>`;
  if (toolFrame.dataset.tool !== toolId) { toolFrame.src = tool[1]; toolFrame.dataset.tool = toolId; }
  $$('.tree-link', treeNav).forEach(button => button.classList.remove('active'));
  $$(':scope > details', treeNav).forEach(details => { details.open = false; });
  $('#techTop').classList.remove('active'); $('#mobilePageTitle').textContent = tool[0];
  document.title = `${tool[0]} · 锡研究周报`; window.scrollTo({ top: 0, behavior: 'instant' });
}
treeNav.addEventListener('click', event => {
  const pageButton = event.target.closest('[data-page]'), toolButton = event.target.closest('[data-tool]');
  if (pageButton) showPage(pageButton.dataset.page);
  if (toolButton) showTool(toolButton.dataset.tool);
});
$('#closeTool').addEventListener('click', () => showPage(currentPage));

/* Keep only one dropdown open and return focus to the top navigation on small screens. */
treeNav.addEventListener('toggle', event => {
  const details = event.target;
  if (details.tagName !== 'DETAILS' || !details.open) return;
  [...details.parentElement.children].forEach(sibling => { if (sibling !== details && sibling.tagName === 'DETAILS') sibling.open = false; });
  if (innerWidth <= 1180 && details.parentElement === treeNav) $('#topNavigation').scrollIntoView({ block: 'start' });
}, true);
document.addEventListener('click', event => { if (!treeNav.contains(event.target)) $$(':scope > details', treeNav).forEach(details => { details.open = false; }); });

/* Fixed mobile previous/next controls; no need to scroll back to the top. */
const PAGE_ORDER = [];
function collectPages(items) { items.forEach(item => { if (item.type === 'page') PAGE_ORDER.push(item.id); else if (item.type === 'group') collectPages(item.children); }); }
collectPages(NAV); PAGE_ORDER.splice(PAGE_ORDER.indexOf('balance'), 0, 'technical');
function updateMobilePager() {
  const index = PAGE_ORDER.indexOf(currentPage), record = registry.get(currentPage);
  $('#mobilePageTitle').textContent = record?.title || '锡研究周报';
  $('#prevPage').disabled = index <= 0; $('#nextPage').disabled = index < 0 || index >= PAGE_ORDER.length - 1;
}
function stepPage(direction) {
  const index = PAGE_ORDER.indexOf(currentPage), target = PAGE_ORDER[index + direction];
  if (target) showPage(target);
}
$('#prevPage').addEventListener('click', () => stepPage(-1));
$('#nextPage').addEventListener('click', () => stepPage(1));

/* Legacy in-report anchors route to the corresponding independent page. */
const anchorRoutes = { '#sumsec': 'summary', '#q4outlook': 'quarter', '#framework': 'framework', '#focus': 'focus-sentiment', '#sentiment': 'focus-sentiment', '#ai': 'ai', '#supply': 'supply-mine', '#smelt': 'supply-smelt', '#invsec': 'inventory', '#balance': 'balance', '#demand': 'demand-solder', '#spot': 'spot', '#strategy': 'strategy', '#lab': 'lab', '#ai-detail': 'ai-core', '#minecost': 'cost', '#decks': 'deck-1-1' };
wrap.addEventListener('click', event => {
  const anchor = event.target.closest('a[href^="#"]'); if (!anchor) return;
  const hash = anchor.getAttribute('href');
  if (anchorRoutes[hash]) { event.preventDefault(); showPage(anchorRoutes[hash]); }
});

/* One responsive view control. */
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
window.addEventListener('resize', drawKline, { passive: true });

const hashRoutes = Object.fromEntries(Object.entries(anchorRoutes).map(([key, value]) => [key.slice(1), value]));
const requested = new URLSearchParams(location.search).get('page') || hashRoutes[location.hash.slice(1)] || 'summary';
applyView(viewMode);
showPage(registry.has(requested) ? requested : 'summary', false);
