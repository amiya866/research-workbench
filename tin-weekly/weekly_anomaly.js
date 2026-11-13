/* Weekly data-anomaly monitor: fixed thresholds, full filterable audit trail. */
(function () {
  'use strict';
  const panel = document.getElementById('anomalyPanel');
  const data = window.WEEKLY_ANOMALIES;
  if (!panel || !data) return;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const labels = { low: '五年低位', wow: '周环比', yoy: '年同比' };
  let filter = 'featured', shown = 30;
  panel.innerHTML = `
    <div class="anomaly-solar"><b>光伏排产更新</b><span>11 月全球组件总产出预计 <strong>48GW</strong>，较 10 月 49GW 下降 <strong>1GW</strong>（约 -2.0%）。来源为用户提供的 11 月上游材料综述；与 SMM 组件产量序列口径不同，不直接拼接。</span></div>
    <div class="anomaly-summary">
      <button type="button" data-filter="low"><span>近五年低位</span><b>${data.alerts.filter(x=>x.type==='low').length}</b><small>20% 分位</small></button>
      <button type="button" data-filter="wow"><span>周环比异动</span><b>${data.alerts.filter(x=>x.type==='wow').length}</b><small>10% + 历史 P80</small></button>
      <button type="button" data-filter="yoy"><span>年同比异动</span><b>${data.alerts.filter(x=>x.type==='yoy').length}</b><small>20% + 历史 P80</small></button>
      <div><span>本周监测</span><b>${data.scanned}</b><small>条有效最新序列</small></div>
    </div>
    <div class="anomaly-rules">
      <div><b>低位</b>${escape(data.rules.low)}</div>
      <div><b>周环比</b>${escape(data.rules.wow)}</div>
      <div><b>年同比</b>${escape(data.rules.yoy)}</div>
    </div>
    <div class="anomaly-toolbar"><div><button class="on" type="button" data-filter="featured">精选异动</button><button type="button" data-filter="all">全部 ${data.totalTriggers} 条</button></div><span>数据截至 ${escape(data.asOf)}｜每周重算，不插值、不补造</span></div>
    <div class="tablewrap anomaly-tablewrap"><table class="ita anomaly-table"><thead><tr><th>类型</th><th>指标／序列</th><th>日期</th><th>最新值</th><th>触发变化</th><th>触发阈值</th><th>原图</th></tr></thead><tbody id="anomalyRows"></tbody></table></div>
    <div class="anomaly-foot"><span id="anomalyCount"></span><button id="anomalyMore" type="button">再显示 30 条</button></div>`;
  const rows = panel.querySelector('#anomalyRows'), count = panel.querySelector('#anomalyCount'), more = panel.querySelector('#anomalyMore');
  function currentRows() { return filter === 'featured' ? data.featured : filter === 'all' ? data.alerts : data.alerts.filter(item => item.type === filter); }
  function render() {
    const all = currentRows(), visible = filter === 'featured' ? all : all.slice(0, shown);
    rows.innerHTML = visible.map(item => `<tr><td><span class="anomaly-tag ${item.type}">${labels[item.type]}</span></td><td><b>${escape(item.title)}</b><small>${escape(item.series)}</small></td><td>${escape(item.date)}</td><td class="num">${escape(item.latestText)}</td><td>${escape(item.changeText)}</td><td>${escape(item.thresholdText)}</td><td><a href="${encodeURI('charts_full/' + item.fn)}" target="_blank" rel="noopener">查看</a></td></tr>`).join('') || '<tr><td colspan="7">本类暂无触发记录。</td></tr>';
    count.textContent = `显示 ${visible.length} / ${all.length} 条`;
    more.hidden = filter === 'featured' || visible.length >= all.length;
    panel.querySelectorAll('[data-filter]').forEach(button => button.classList.toggle('on', button.dataset.filter === filter));
  }
  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-filter]');
    if (!button) return;
    filter = button.dataset.filter; shown = 30; render();
  });
  more.addEventListener('click', () => { shown += 30; render(); });
  render();
})();
