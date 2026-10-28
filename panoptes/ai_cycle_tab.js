/* Isolated style scope: the report cannot restyle other Panoptes tabs. */
(function(){
  'use strict';
  window.PHXAiCycle={mount:function(panel){
    if(panel.dataset.mounted)return;
    panel.dataset.mounted='1';
    const fallback=document.createElement('p');
    fallback.style.cssText='padding:8px 20px;color:#a9bdd6;font-size:12px;margin:0';
    const link=document.createElement('a');link.href='ai-cycle/index.html';
    link.target='_blank';link.rel='noopener';link.textContent='AI Cycle 독립 화면 열기';link.style.color='#6ee7b7';
    fallback.append(link,' · 숫자와 해석은 같은 검증 데이터로 갱신됩니다. 미연결·권한 미확인 자료는 별도 표시합니다.');
    const frame=document.createElement('iframe');frame.title='AI 투자 사이클 공개 데이터 보고서';
    frame.src='ai-cycle/index.html';frame.style.cssText='display:block;width:100%;height:calc(100% - 38px);min-height:650px;border:0';
    frame.loading='lazy';frame.referrerPolicy='same-origin';
    panel.append(fallback,frame);
  }};
})();
