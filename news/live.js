(() => {
  const SOURCE_KEYS = ['jin10', 'cs', 'eastmoney', 'sina', 'ah'];
  const SOURCE_NAMES = {jin10:'金十', cs:'CS财经', eastmoney:'东方财富', sina:'新浪财经', ah:'先讯'};
  const CATEGORIES = [
    {id:'commodity', name:'商品·产业', color:'#2e7d4f', re:/(铜|铝|锡|镍|锌|铅|锂|硅|焦煤|焦炭|螺纹|铁矿|钢铁|原油|石油|天然气|燃料油|黄金|白银|贵金属|欧佩克|OPEC|库存|升贴水|加工费|矿山|冶炼|光伏|电池|新能源|农产品|棕榈油|大豆|玉米|小麦|白糖|棉花|橡胶|化工|纯碱|玻璃|烧碱)/i},
    {id:'macro', name:'宏观·政策', color:'#a3760e', re:/(美联储|央行|加息|降息|利率|美债|美元|财政部|赤字|非农|CPI|PPI|PMI|通胀|GDP|就业|零售|消费信心|国务院|发改委|工信部|财政部|政策|关税|选举| IMF |世界银行)/i},
    {id:'geo', name:'地缘', color:'#b23a2e', re:/(伊朗|美伊|霍尔木兹|伊拉克|俄罗斯|乌克兰|特朗普|委内瑞拉|以色列|中东|红海|战争|冲突|袭击|制裁|停火|谈判|导弹|无人机)/i},
    {id:'equity', name:'股市·科技', color:'#39769e', re:/(美股|科技股|人工智能|AI|机器人|存储|英伟达|芯片|半导体|港股|A股|恒生|纳斯达克|标普|道琼斯|创业板|科创|上市公司|股价|涨停|跌停|苹果|微软|谷歌|特斯拉)/i}
  ];
  const state = {data:window.NEWS_SNAP || {}, category:'all', source:'all', query:'', important:false, expanded:false, loading:false, seconds:60};
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  const clean = value => String(value || '').replace(/<[^>]*>/g,'').replace(/[​‌‍⁠﻿­︀-️]/g,'').replace(/\s+/g,' ').trim();
  const parseTime = value => {
    const text = String(value || '').trim();
    if (!/^\d{4}-\d{2}-\d{2}/.test(text)) return NaN;
    const normalized = text.replace(' ','T');
    return Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/.test(normalized) ? normalized : normalized + '+08:00');
  };
  const shortTime = value => {
    const text = String(value || '');
    return text.length >= 16 ? text.slice(5,16) : text || '时间未知';
  };
  const categoriesFor = text => CATEGORIES.filter(cat => cat.re.test(text)).map(cat => cat.id);

  function allItems() {
    const rows = [];
    SOURCE_KEYS.forEach(source => {
      (state.data[source] || []).forEach(item => {
        const content = clean(item.content || item.title || item.title_cn);
        if (!content) return;
        const time = item.time || item.ts || '';
        rows.push({source, content, time, timestamp:parseTime(time), id:String(item.id || ''), important:Boolean(item.important) || Number(item.importance || 0) >= 80, categories:categoriesFor(content)});
      });
    });
    rows.sort((a,b) => (b.timestamp || 0) - (a.timestamp || 0));
    const seen = new Set();
    return rows.filter(item => {
      const key = item.id ? item.source + ':' + item.id : item.content.replace(/[【】\s]/g,'').slice(0,100);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function itemHtml(item, focused=false) {
    const catNames = item.categories.map(id => (CATEGORIES.find(cat => cat.id === id) || {}).name).filter(Boolean);
    return `<article class="${focused ? 'focus' : 'item'}">${focused ? '' : `<div class="time">${esc(shortTime(item.time))}</div>`}<div><div class="meta">${focused ? esc(shortTime(item.time)) : ''}${item.important ? '<span class="star">★</span>' : ''}<span class="src">${esc(SOURCE_NAMES[item.source])}</span>${catNames.map(name => `<span class="tag">${esc(name)}</span>`).join('')}</div><div class="content">${esc(item.content)}</div></div></article>`;
  }

  function filteredItems(items) {
    const query = state.query.toLowerCase();
    return items.filter(item => (state.category === 'all' || item.categories.includes(state.category)) && (state.source === 'all' || item.source === state.source) && (!state.important || item.important) && (!query || item.content.toLowerCase().includes(query)));
  }

  function renderSources() {
    const sources = state.data.sources || [];
    $('sourceCount').textContent = sources.filter(source => source.ok).length + '/' + sources.length;
    $('sourceList').innerHTML = sources.map(source => `<div class="source ${source.ok ? '' : 'bad'}"><div class="name">${source.ok ? '<span class="ok">●</span>' : '<span class="bad-text">●</span>'} ${esc(source.name)}</div><div class="detail">${source.ok ? `正常 · 本次 ${esc(source.n ?? 0)} 条${source.mode ? ' · ' + esc(source.mode) : ''}` : `异常 · ${esc(source.err || '未返回数据')}`}</div></div>`).join('') || '<div class="empty">暂无数据源状态</div>';
  }

  function renderFreshness() {
    const asof = state.data.asof || '';
    const timestamp = parseTime(asof);
    const ageMinutes = Number.isFinite(timestamp) ? Math.max(0, Math.floor((Date.now() - timestamp) / 60000)) : Infinity;
    const level = ageMinutes <= 20 ? 'live' : ageMinutes <= 60 ? 'warn' : 'bad';
    $('liveDot').className = 'live-dot' + (level === 'live' ? '' : ' ' + level);
    $('healthText').textContent = level === 'live' ? '快照正常' : level === 'warn' ? `快照延迟 ${ageMinutes} 分钟` : '快照严重延迟';
    $('asof').textContent = '快照 ' + (asof || '未知') + ' BJT';
    const stale = $('stale');
    if (level !== 'live') {
      stale.style.display = 'block';
      stale.textContent = Number.isFinite(ageMinutes) ? `当前展示最后成功快照，已延迟 ${ageMinutes} 分钟。云端任务恢复后会自动补更，无需手动改页面。` : '快照时间无法识别，请检查云端抓取任务。';
    } else stale.style.display = 'none';
  }

  function render() {
    const items = allItems();
    $('totalCount').textContent = items.length;
    $('importantCount').textContent = items.filter(item => item.important).length;
    $('latestTime').textContent = shortTime(items[0] && items[0].time);
    const cards = [{id:'all',name:'全部快讯',color:'#16140f'}, ...CATEGORIES];
    $('categoryCards').innerHTML = cards.map(cat => {
      const count = cat.id === 'all' ? items.length : items.filter(item => item.categories.includes(cat.id)).length;
      return `<button class="cat ${state.category === cat.id ? 'active' : ''}" data-cat="${cat.id}"><i style="background:${cat.color}"></i>${cat.name}<b>${count}</b></button>`;
    }).join('');
    const filtered = filteredItems(items);
    const focus = filtered.filter(item => item.important).slice(0,6);
    const focusItems = focus.length ? focus : filtered.slice(0,6);
    $('focusGrid').innerHTML = focusItems.map(item => itemHtml(item,true)).join('') || '<div class="empty" style="grid-column:1/-1">当前筛选条件下暂无快讯</div>';
    const visible = state.expanded ? filtered : filtered.slice(0,80);
    $('feed').innerHTML = visible.map(item => itemHtml(item)).join('') || '<div class="empty">没有匹配的快讯，请调整筛选条件</div>';
    $('moreBtn').style.display = filtered.length > 80 ? 'block' : 'none';
    $('moreBtn').textContent = state.expanded ? '收起为最新 80 条' : `展开全部 ${filtered.length} 条`;
    $('filterNote').textContent = `匹配 ${filtered.length} 条 · 按时间倒序`;
    renderSources();
    renderFreshness();
  }

  async function load(manual=false) {
    if (state.loading) return;
    state.loading = true;
    $('refreshBtn').disabled = true;
    $('refreshBtn').textContent = '刷新中…';
    try {
      const response = await fetch('../data/news_latest.json?v=' + Date.now(), {cache:'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (!data || !data.asof) throw new Error('快照格式异常');
      state.data = data;
      state.seconds = 60;
      render();
      if (manual) $('healthText').textContent = '已刷新 · ' + $('healthText').textContent;
    } catch (error) {
      $('healthText').textContent = '刷新失败，保留当前快照';
      $('liveDot').className = 'live-dot warn';
    } finally {
      state.loading = false;
      $('refreshBtn').disabled = false;
      $('refreshBtn').textContent = '立即刷新';
    }
  }

  $('categoryCards').addEventListener('click', event => {
    const button = event.target.closest('[data-cat]');
    if (!button) return;
    state.category = button.dataset.cat;
    state.expanded = false;
    render();
  });
  $('sourceFilter').addEventListener('change', event => {state.source = event.target.value; state.expanded = false; render();});
  $('importantOnly').addEventListener('change', event => {state.important = event.target.checked; state.expanded = false; render();});
  $('search').addEventListener('input', event => {state.query = event.target.value.trim(); state.expanded = false; render();});
  $('moreBtn').addEventListener('click', () => {state.expanded = !state.expanded; render();});
  $('refreshBtn').addEventListener('click', () => load(true));
  setInterval(() => {
    state.seconds -= 1;
    if (state.seconds <= 0) {state.seconds = 60; load();}
    $('nextRefresh').textContent = state.seconds + ' 秒后自动刷新';
  },1000);
  setInterval(renderFreshness,60000);
  render();
  load();
})();
