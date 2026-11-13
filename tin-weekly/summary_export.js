(function(){
  'use strict';
  var sum=document.getElementById('sumsec');
  if(!sum)return;
  var bar=document.createElement('div');bar.className='summary-export-bar';
  var button=document.createElement('button');button.type='button';button.id='exportSummaryPNG';button.textContent='导出总结图片 PNG';
  var hint=document.createElement('span');hint.textContent='含本周定调、三期判断与完整供需表';
  bar.appendChild(hint);bar.appendChild(button);sum.insertBefore(bar,sum.children[1]||null);
  var style=document.createElement('style');style.textContent='.summary-export-bar{display:flex;align-items:center;justify-content:flex-end;gap:12px;margin:-4px 0 10px}.summary-export-bar span{color:var(--faint);font-size:12px}.summary-export-bar button{border:1px solid var(--red);background:transparent;color:var(--red);border-radius:6px;padding:6px 13px;cursor:pointer;font:600 13px var(--ui-font,"Microsoft YaHei",sans-serif)}.summary-export-bar button:hover{background:var(--red);color:#fff}.summary-export-bar button:disabled{opacity:.55;cursor:wait}@media(max-width:520px){.summary-export-bar{align-items:flex-end;flex-direction:column;gap:5px}.summary-export-bar span{font-size:11px}}@media print{.summary-export-bar{display:none!important}}';document.head.appendChild(style);

  function exportPNG(){
    if(button.disabled)return;
    button.disabled=true;var oldText=button.textContent;button.textContent='正在生成…';
    try{
      var width=1600,date=document.querySelector('.research-stamp b')?.textContent.trim()||'2026-11-06';
      var tone=document.querySelector('.report-page[data-page="summary"] .tone')||document.querySelector('.tone');
      var exportRoot=document.createElement('div');exportRoot.className='export-root';
      var title=document.createElement('div');title.className='export-title';
      title.innerHTML='<div><p>TIN WEEKLY RESEARCH · 2026 W45</p><h1>锡研究周报 · 本周总结</h1></div><div class="export-meta"><b>中哲金属 · 甘思雨</b><span>数据截至　'+date+'</span></div>';
      exportRoot.appendChild(title);
      if(tone){var toneClone=tone.cloneNode(true);toneClone.removeAttribute('contenteditable');exportRoot.appendChild(toneClone);}
      var clone=sum.cloneNode(true);clone.querySelectorAll('.summary-export-bar').forEach(function(el){el.remove();});clone.querySelectorAll('[contenteditable]').forEach(function(el){el.removeAttribute('contenteditable');});exportRoot.appendChild(clone);
      var foot=document.createElement('div');foot.className='export-foot';foot.innerHTML='<span>周度研究 · 技术分析 · 供需平衡 · 全年情景</span><span>内部研究材料，仅供参考，不构成投资建议</span>';exportRoot.appendChild(foot);
      var css='*{box-sizing:border-box;margin:0;padding:0}body{background:#fff}.export-root{width:1600px;padding:38px 42px 26px;background:#fff;color:#1a1a1a;font-family:"KaiTi","楷体","STKaiti","Microsoft YaHei",serif;font-size:16px;line-height:1.8}.export-title{display:flex;align-items:flex-end;justify-content:space-between;gap:28px;padding-bottom:17px;margin-bottom:20px;border-bottom:4px solid #C00000}.export-title p{font:12px Arial,sans-serif;letter-spacing:2.5px;color:#7a828c;margin-bottom:6px}.export-title h1{font-size:34px;line-height:1.35;letter-spacing:1px}.export-meta{display:flex;flex-direction:column;align-items:flex-end;gap:7px;white-space:nowrap;font-size:14px}.export-meta b{color:#C00000;font-size:16px}.export-meta span{color:#59636f}.tone{border:1.5px solid #C00000;background:#FDF6F6;padding:14px 18px;margin:0 0 20px;font-size:16px;line-height:1.9}.tone b,.rd{color:#C00000;font-weight:700}#sumsec h2{display:flex;align-items:baseline;border-left:5px solid #C00000;padding-left:12px;margin:0 0 14px;font-size:25px;line-height:1.4}#sumsec h2 .en{font:12px Arial,sans-serif;color:#777;letter-spacing:2px;margin-left:10px}.verdict{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:10px 0 20px}.verdict .v{border:1px solid #e3e3e3;border-top:3px solid #C00000;padding:13px 16px;background:#fff}.verdict .t{font-size:14px;color:#777}.verdict .d{font-size:20px;font-weight:700;color:#C00000;margin:4px 0 7px}.verdict p{font-size:15px;color:#555;line-height:1.8}table.sum{width:100%;border-collapse:collapse;table-layout:fixed;margin-top:10px;font-size:15px;line-height:1.65}table.sum th{background:#F2F2F2;color:#1a1a1a;border:1px solid #D9D9D9;padding:9px 11px;text-align:left;font-size:15px}table.sum td{border:1px solid #D9D9D9;padding:9px 11px;vertical-align:top;line-height:1.7;overflow-wrap:break-word}table.sum td.c{background:#F2F2F2;font-weight:700;text-align:center;vertical-align:middle}.dir{display:inline-block;font-weight:700;font-size:13px;padding:0 8px;border-radius:3px;white-space:nowrap}.dir.up{color:#C00000;border:1px solid #C00000}.dir.dn{color:#1F7A33;border:1px solid #1F7A33}.dir.nt{color:#777;border:1px solid #999}tr.final td{border:1.5px solid #C00000;background:#FDF6F6}.export-foot{display:flex;justify-content:space-between;gap:20px;border-top:1px solid #D9D9D9;padding-top:14px;margin-top:22px;color:#777;font-size:12px}';
      var measure=document.createElement('div');measure.style.cssText='position:fixed;left:-100000px;top:0;width:'+width+'px;background:#fff;visibility:hidden;';
      var exportStyle=document.createElement('style');exportStyle.textContent=css;measure.appendChild(exportStyle);measure.appendChild(exportRoot);document.body.appendChild(measure);
      var height=Math.ceil(exportRoot.getBoundingClientRect().height)+2;
      var markup=new XMLSerializer().serializeToString(exportRoot);measure.parentNode.removeChild(measure);
      var svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+width+'" height="'+height+'"><foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml"><style>'+css+'</style>'+markup+'</div></foreignObject></svg>';
      var img=new Image();
      img.onload=function(){
        try{
          var canvas=document.createElement('canvas');canvas.width=width*2;canvas.height=height*2;
          var ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
          var a=document.createElement('a');a.download='锡研究周报_本周总结_'+date+'.png';document.body.appendChild(a);a.href=canvas.toDataURL('image/png');a.click();a.remove();
          button.disabled=false;button.textContent=oldText;
        }catch(e){button.disabled=false;button.textContent=oldText;alert('总结图片导出失败，请刷新后重试。');}
      };
      img.onerror=function(){button.disabled=false;button.textContent=oldText;alert('总结图片导出失败，请刷新后重试。');};
      img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);
    }catch(e){button.disabled=false;button.textContent=oldText;alert('总结图片导出失败，请刷新后重试。');}
  }
  button.addEventListener('click',exportPNG);
  window.TIN_SUMMARY_EXPORT={exportPNG:exportPNG};
})();
