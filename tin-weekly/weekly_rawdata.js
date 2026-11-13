/* W45 source-workbook browser: lazy worksheet loading, filtering and pagination. */
(function () {
  'use strict';
  const panel = document.getElementById('rawDataPanel');
  if (!panel) return;
  const fileEl = document.getElementById('rawFile');
  const sheetEl = document.getElementById('rawSheet');
  const searchEl = document.getElementById('rawSearch');
  const sizeEl = document.getElementById('rawPageSize');
  const statusEl = document.getElementById('rawStatus');
  const table = document.getElementById('rawTable');
  const prev = document.getElementById('rawPrev');
  const next = document.getElementById('rawNext');
  const pageInfo = document.getElementById('rawPageInfo');
  const cache = new Map();
  let manifest = [];
  let payload = null;
  let filtered = [];
  let page = 0;
  let requestId = 0;

  function option(value, label) {
    const el = document.createElement('option');
    el.value = value;
    el.textContent = label;
    return el;
  }
  function currentEntry() {
    return manifest.find(item => item.key === sheetEl.value);
  }
  function applyFilter() {
    page = 0;
    if (!payload) { filtered = []; render(); return; }
    const query = searchEl.value.trim().toLocaleLowerCase('zh-CN');
    filtered = [];
    payload.rows.forEach((values, index) => {
      if (!query || values.some(value => String(value ?? '').toLocaleLowerCase('zh-CN').includes(query))) {
        filtered.push({ sourceRow: index + 1, values });
      }
    });
    render();
  }
  function cell(tag, text) {
    const el = document.createElement(tag);
    el.textContent = text;
    el.title = text;
    return el;
  }
  function render() {
    table.replaceChildren();
    const size = Number(sizeEl.value) || 50;
    const pages = Math.max(1, Math.ceil(filtered.length / size));
    page = Math.max(0, Math.min(page, pages - 1));
    const start = page * size;
    const visible = filtered.slice(start, start + size);
    const thead = document.createElement('thead');
    const head = document.createElement('tr');
    head.appendChild(cell('th', '行'));
    (payload?.columns || []).forEach(letter => head.appendChild(cell('th', letter)));
    thead.appendChild(head);
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    visible.forEach(row => {
      const tr = document.createElement('tr');
      tr.appendChild(cell('th', String(row.sourceRow)));
      (payload?.columns || []).forEach((_, index) => {
        const value = row.values[index];
        tr.appendChild(cell('td', value == null ? '' : String(value)));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    pageInfo.textContent = `${page + 1} / ${pages} 页`;
    prev.disabled = page <= 0;
    next.disabled = page >= pages - 1;
    const entry = currentEntry();
    if (entry && payload) {
      statusEl.textContent = `${entry.file} · ${entry.sheet}｜原表 ${entry.rows} 行 × ${entry.columns} 列｜筛选后 ${filtered.length} 行｜非空单元格 ${entry.nonempty.toLocaleString('zh-CN')}`;
    }
  }
  async function loadSheet() {
    const entry = currentEntry();
    if (!entry) return;
    const id = ++requestId;
    statusEl.textContent = `正在读取 ${entry.sheet}…`;
    table.replaceChildren();
    try {
      if (!cache.has(entry.key)) {
        const response = await fetch(`weekly_data/w45/${entry.key}.json`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        cache.set(entry.key, await response.json());
      }
      if (id !== requestId) return;
      payload = cache.get(entry.key);
      searchEl.value = '';
      applyFilter();
    } catch (error) {
      if (id !== requestId) return;
      payload = null;
      filtered = [];
      statusEl.textContent = `工作表读取失败：${error.message}。源文件仍保留在 weekly_data/w45/，未用空表替代。`;
      pageInfo.textContent = '';
      prev.disabled = next.disabled = true;
    }
  }
  function fillSheets() {
    const selectedFile = fileEl.value;
    sheetEl.replaceChildren();
    manifest.filter(item => item.file === selectedFile).forEach(item => {
      sheetEl.appendChild(option(item.key, `${item.sheet}（${item.rows} 行）`));
    });
    loadSheet();
  }
  async function init() {
    try {
      const response = await fetch('weekly_data/w45/manifest.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      manifest = await response.json();
      const files = [...new Set(manifest.map(item => item.file))];
      fileEl.replaceChildren();
      files.forEach(file => fileEl.appendChild(option(file, file)));
      fillSheets();
    } catch (error) {
      statusEl.textContent = `原始数据目录读取失败：${error.message}`;
    }
  }
  fileEl.addEventListener('change', fillSheets);
  sheetEl.addEventListener('change', loadSheet);
  searchEl.addEventListener('input', applyFilter);
  sizeEl.addEventListener('change', () => { page = 0; render(); });
  prev.addEventListener('click', () => { page -= 1; render(); });
  next.addEventListener('click', () => { page += 1; render(); });
  init();
})();
