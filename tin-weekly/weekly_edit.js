/* Weekly report presentation editing. Source workbooks and chart series remain unchanged. */
(function () {
  'use strict';
  const storageKey = 'tin-weekly-text-edits-v2:' + location.pathname;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}') || {}; } catch (_) {}
  const selector = '#reportWrap .tone,#reportWrap .note,#reportWrap .lead,#reportWrap .cap,#reportWrap .stats,#reportWrap td';
  const nodes = [...document.querySelectorAll(selector)].filter(node => !node.closest('#rawDataPanel') && !node.querySelector('td'));
  let timer = 0;
  function persist() {
    const values = {};
    nodes.forEach(node => { if (node.dataset.editOriginal !== node.innerHTML) values[node.dataset.editKey] = node.innerHTML; });
    try { localStorage.setItem(storageKey, JSON.stringify(values)); } catch (_) {}
  }
  nodes.forEach((node, index) => {
    const key = node.dataset.editKey || `w45-text-${index}`;
    node.dataset.editKey = key;
    node.dataset.editOriginal = node.innerHTML;
    if (Object.prototype.hasOwnProperty.call(saved, key)) node.innerHTML = saved[key];
    node.contentEditable = 'true';
    node.spellcheck = false;
    node.setAttribute('title', '可直接编辑；内容自动保存在本机浏览器');
    node.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(persist, 250); });
    node.addEventListener('blur', persist);
  });
})();
