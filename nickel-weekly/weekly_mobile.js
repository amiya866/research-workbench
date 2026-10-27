/* 周报版本二 · 原生手机网页模式。保留 MobilePDF 接口兼容旧链接，但不再生成 A4 缩略页。 */
(function(){
  'use strict';
  function ensureTableScroll(){
    document.querySelectorAll('table.bal,table.ita').forEach(function(tb){
      if(tb.parentNode.classList.contains('tablewrap'))return;
      var wrap=document.createElement('div');
      wrap.className='tablewrap';
      tb.parentNode.insertBefore(wrap,tb);
      wrap.appendChild(tb);
    });
  }
  function apply(){
    var phone=window.innerWidth<=760;
    document.documentElement.classList.toggle('pgxmobileweb',phone);
    document.documentElement.classList.remove('pgxmobile','pgxa4','pgxppt','pgxmeasure');
    ensureTableScroll();
  }
  apply();
  window.addEventListener('resize',apply,{passive:true});
  window.MobilePDF={
    open:apply,
    close:apply,
    fit:apply,
    isActive:function(){return window.innerWidth<=760;}
  };
})();
