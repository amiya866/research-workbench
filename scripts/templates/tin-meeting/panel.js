(function(){
'use strict';
const data=window.SN_MEETING_PANEL;
const table=document.getElementById('meetingTable');
const strategyTable=document.getElementById('strategyTable');
const opinionTable=document.getElementById('opinionTable');
const storageKey='tin-meeting-panel-overrides-v1';
const empty={values:{},auto_reset:[]};
let editing=false,dirty=false;
function clean(value){return value&&typeof value==='object'?value:{}}
function localState(){
  try{const x=JSON.parse(localStorage.getItem(storageKey)||'null');return {values:clean(x&&x.values),auto_reset:Array.isArray(x&&x.auto_reset)?x.auto_reset:[]}}
  catch(e){return {values:{},auto_reset:[]}}
}
let local=localState();
const persistent=data.manual||empty;
function has(obj,key){return Object.prototype.hasOwnProperty.call(obj,key)}
function auto(key){return has(data.auto,key)?String(data.auto[key]):''}
function value(key){
  if(has(local.values,key))return String(local.values[key]);
  if(local.auto_reset.includes(key))return auto(key);
  if(has(persistent.values,key)&&!(persistent.auto_reset||[]).includes(key))return String(persistent.values[key]);
  return auto(key);
}
function origin(key){
  if(has(local.values,key))return '本机手动';
  if(local.auto_reset.includes(key))return '自动';
  if(has(persistent.values,key)&&!(persistent.auto_reset||[]).includes(key))return '手动默认';
  return (data.origins&&data.origins[key])||'auto';
}
function originLabel(kind){return {auto:'自动',manual:'手动',minutes:'纪要',pending:'待纪要'}[kind]||kind}
function esc(text){return String(text).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function field(key,cls){
  const kind=origin(key);
  return '<div class="field-wrap '+(cls||'')+'"><button type="button" class="reset-field" data-reset="'+esc(key)+'" title="解除手动锁定">恢复自动</button><div class="field" data-key="'+esc(key)+'" contenteditable="false">'+esc(value(key))+'</div><span class="origin '+esc(kind)+'">'+esc(originLabel(kind))+'</span></div>';
}
function opinionRow(person){
  return '<tr><td class="row-label person">'+field('name.'+person)+'</td><td class="content opinion-content">'+field('opinion.'+person)+'</td></tr>';
}
function render(){
  const rows=[];
  rows.push('<colgroup><col style="width:65px"><col style="width:105px"><col><col style="width:115px"><col></colgroup>');
  rows.push('<tr><th class="corner">周会记录<br>自动更新 · 可手改</th><th class="head" colspan="2">'+field('week')+'</th><th class="head strategy" colspan="2">'+field('strategyTitle')+'</th></tr>');
  rows.push('<tr><td class="commodity" rowspan="4">SN</td><td class="row-label auto-label">平衡</td><td class="content">'+field('balance')+'</td><td class="side-label" rowspan="4">主要矛盾方向</td><td class="content" rowspan="4">'+field('contradiction')+'</td></tr>');
  rows.push('<tr><td class="row-label auto-label">现货</td><td class="content">'+field('spot')+'</td></tr>');
  rows.push('<tr><td class="row-label auto-label">持仓</td><td class="content">'+field('positions')+'</td></tr>');
  rows.push('<tr><td class="row-label auto-label">关注</td><td class="content">'+field('watch')+'</td></tr>');
  table.innerHTML=rows.join('');
  strategyTable.innerHTML='<colgroup><col style="width:140px"><col></colgroup><tr><th class="strategy-heading">会议应对方向</th><td class="content strategy-content">'+field('strategy')+'</td></tr>';
  opinionTable.innerHTML='<colgroup><col style="width:90px"><col></colgroup><thead><tr><th>参会人</th><th>核心观点与交易判断</th></tr></thead><tbody>'+data.people.map(opinionRow).join('')+'</tbody>';
  document.querySelectorAll('.field').forEach(function(el){
    el.contentEditable=editing?'true':'false';
    el.addEventListener('input',function(){el.dataset.changed='1';dirty=true;showNotice('有未保存修改。点击“保存到本机”后生效。')})
  });
  document.querySelectorAll('[data-reset]').forEach(function(btn){btn.addEventListener('click',function(){resetField(btn.dataset.reset)})});
  document.body.classList.toggle('editing',editing);
  document.getElementById('editBtn').textContent=editing?'退出编辑':'编辑面板';
  document.getElementById('saveBtn').hidden=!editing;
  renderMeta();
}
function renderMeta(){
  const meta=data.meta||{};
  document.getElementById('meta').textContent='数据截至 '+(meta.asof||'—')+' · 构建 '+(meta.built_at||'—')+' · 纪要：'+(meta.minutes_status||'未接入');
  document.getElementById('minutesHelp').textContent=meta.minutes_help||'';
  const sources=data.sources||[];
  document.getElementById('sourceList').innerHTML='<ul>'+sources.map(function(s){return '<li><b>'+esc(s.label)+'</b>：'+esc(s.value)+'（'+esc(s.date||'—')+'）｜'+esc(s.source)+'</li>'}).join('')+'</ul><p>'+esc(meta.balance_note||'缺数不补零。')+'</p>';
}
function showNotice(text){const n=document.getElementById('notice');n.textContent=text;n.classList.add('show')}
function save(){
  document.querySelectorAll('.field[data-changed="1"]').forEach(function(el){
    const key=el.dataset.key;local.values[key]=el.innerText.replace(/\u00a0/g,' ').trim();local.auto_reset=local.auto_reset.filter(function(k){return k!==key});
  });
  localStorage.setItem(storageKey,JSON.stringify(local));dirty=false;render();showNotice('已保存到本机。导出配置后可设为线上默认值。');
}
function resetField(key){
  delete local.values[key];
  if(!local.auto_reset.includes(key))local.auto_reset.push(key);
  localStorage.setItem(storageKey,JSON.stringify(local));dirty=false;render();showNotice('已恢复自动：'+key);
}
function effectiveManual(){
  const values={},reset=new Set(local.auto_reset);
  Object.keys(persistent.values||{}).forEach(function(key){if(!(persistent.auto_reset||[]).includes(key)&&!reset.has(key))values[key]=persistent.values[key]});
  Object.keys(local.values).forEach(function(key){values[key]=local.values[key];reset.delete(key)});
  return {values:values,auto_reset:Array.from(reset).sort()};
}
function exportManual(){
  const blob=new Blob([JSON.stringify(effectiveManual(),null,2)],{type:'application/json;charset=utf-8'});
  const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='tin_meeting_overrides.json';a.click();setTimeout(function(){URL.revokeObjectURL(url)},1000);
  showNotice('配置已导出。将其替换 data/tin_meeting_overrides.json 后，下次构建即成为线上默认值。');
}
function importManual(file){
  const reader=new FileReader();reader.onload=function(){
    try{const x=JSON.parse(reader.result);if(!x||typeof x.values!=='object'||!Array.isArray(x.auto_reset||[]))throw new Error('配置结构不正确');
      local={values:clean(x.values),auto_reset:Array.isArray(x.auto_reset)?x.auto_reset:[]};localStorage.setItem(storageKey,JSON.stringify(local));dirty=false;render();showNotice('配置已导入并保存到本机。');
    }catch(e){showNotice('导入失败：'+e.message)}
  };reader.readAsText(file,'utf-8');
}
document.getElementById('editBtn').addEventListener('click',function(){if(editing&&dirty&&!confirm('有未保存修改，确定退出编辑吗？'))return;editing=!editing;dirty=false;render()});
document.getElementById('saveBtn').addEventListener('click',save);
document.getElementById('exportBtn').addEventListener('click',exportManual);
document.getElementById('importBtn').addEventListener('click',function(){document.getElementById('importFile').click()});
document.getElementById('importFile').addEventListener('change',function(e){if(e.target.files[0])importManual(e.target.files[0]);e.target.value=''});
document.getElementById('printBtn').addEventListener('click',function(){window.print()});
render();
})();
