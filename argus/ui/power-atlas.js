/* Physical equipment silhouettes and source-backed drill-downs. No external runtime. */
(function(){
  'use strict';
  const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const symbols={
    plant:`<path d="M7 99V65l24-14v14l25-14v48zM62 99V50a22 22 0 0 1 44 0v49z"/><path class="pa-solid" d="M62 51h44v48H62z"/><path d="M67 50h34M77 28V16h13v12M14 77h9v10h-9zm19 0h9v10h-9zM4 104h112"/><path class="pa-nofill" d="M76 8q9-10 18 0"/>`,
    reactor:`<path d="M14 105V45a46 46 0 0 1 92 0v60" stroke-dasharray="4 4" class="pa-nofill"/><path d="M41 40q19-13 38 0v52q-19 15-38 0z"/><ellipse cx="60" cy="40" rx="19" ry="7"/><path d="M46 101v8m28-8v8M36 51H23V38M84 51h16v31"/><path class="pa-solid" d="M46 63h28v23H46z"/><path d="M50 28v42m10-44v44m10-42v42M51 71v13m9-13v13m9-13v13"/><path d="M7 110h106"/>`,
    steamgen:`<path d="M34 30a26 18 0 0 1 52 0v64q0 14-26 14T34 94z"/><ellipse cx="60" cy="30" rx="26" ry="12"/><path class="pa-solid" d="M35 71h50v25q-26 18-50 0z"/><path d="M46 94V48q0-11 7 0v40m7 7V44q0-11 7 0v44m7 7V48q0-11 6 0v43M50 16V5h29M34 81H17V64M86 83h17v15"/><path d="M43 107v7m34-7v7"/>`,
    turbine:`<path d="M15 43l75-19v70L15 76z"/><ellipse cx="90" cy="59" rx="19" ry="35"/><ellipse cx="91" cy="59" rx="11" ry="23"/><path d="M6 60h108M29 40v38m15-42v46m15-49v53m15-57v61M30 80v22h13m29-6v6h15"/><path class="pa-solid" d="M16 61h61v24L16 74z"/><path d="M90 36v46m-9-42l18 38m0-38L81 78"/>`,
    generator:`<path d="M20 37h67q20 0 20 28T87 93H20z"/><ellipse cx="22" cy="65" rx="15" ry="28"/><ellipse cx="87" cy="65" rx="18" ry="28"/><ellipse cx="87" cy="65" rx="8" ry="14"/><path d="M87 65h30M11 65H0M31 39v51m10-51v51m10-51v51m10-51v51M28 94v11h17m27-11v11h17M42 37V22h24v15"/><path class="pa-solid" d="M25 67h38v23H25z"/><path class="pa-light" d="M51 45l-8 15h9l-5 16 15-22h-10l6-9z"/>`,
    transformer:`<path d="M28 44l59-6 19 12v49l-60 9-18-13zM28 44l18 12 60-6M46 56v52"/><path class="pa-solid" d="M47 57l58-6v47l-58 9z"/><path d="M17 54l21 10v36L17 90zM22 59v32m6-29v31m6-28v31M57 64v32m8-34v33m8-34v33m8-34v33m8-34v33M36 105v8m57-8v8"/><path d="M43 41V19m20 19V14m20 22V10M38 22h10m-10 5h10m-10 5h10m10-15h10m-10 5h10m-10 5h10m10-14h10m-10 5h10m-10 5h10"/><path d="M21 45V28h13M97 43V29h14"/>`,
    tower:`<path class="pa-nofill" d="M60 4L24 112M60 4l36 108M43 50h34M34 78h52M24 112h72M43 50l43 28H34l62 34M77 50L34 78l-10 34m36-93L27 33h66L60 19M43 50H13l30-15m34 0 30 15H77"/><path d="M17 50v14m8-14v14m70-14v14m8-14v14M13 56h8m0 4h8m62-4h8m0 4h8M27 33v11m66-11v11"/><path class="pa-nofill" d="M0 64q17 9 34 0m52 0q17 9 34 0"/>`,
    substation:`<path d="M7 24h106M14 24v83m91-83v83M7 17h106M24 17v-9m72 9V8"/><path d="M26 62h62v31H26zM36 61V39m23 22V34m21 27V39M31 43h10m13-5h10m11 5h10M35 48h5m17-5h5m16 5h5M32 72h13v14H32zm24 0h24v14H56z"/><path d="M27 92v15m60-15v15M6 112h110M100 72h11v23H100zM12 67h11v29H12z"/><path class="pa-solid" d="M26 62h62v7H26z"/>`,
    pole:`<path d="M55 14h8v100h-8zM15 26h87v5H15zM25 11v15m21-15v15m27-15v15m21-15v15M20 15h10m-10 5h10m11-5h10m-10 5h10m17-5h10m-10 5h10m11-5h10m-10 5h10"/><path d="M28 48h21v20H28zM35 31v17M49 54h6M63 78h24V55h20M53 111h13"/><path class="pa-nofill" d="M0 11q12 7 25 0m69 0q13 7 26 0"/>`,
    poletr:`<path d="M64 10h8v105h-8zM22 26h80v5H22zM27 11v15m23-15v15m23-15v15m23-15v15M22 15h10m13 0h10m13 0h10m13 0h10"/><path d="M22 48h32v45q-16 10-32 0z"/><ellipse cx="38" cy="48" rx="16" ry="6"/><path class="pa-solid" d="M23 69h30v24q-15 8-30 0z"/><path d="M31 46V32m15 15V34M54 58h10m-10 29h10M25 75h-9V62M72 82h31M31 34h5m-5 4h5M58 112h20"/>`,
    pad:`<path d="M15 43l75-14 20 13v60l-75 12-20-14zM15 43l20 14 75-15M35 57v57M72 51v56"/><path class="pa-solid" d="M15 44l20 13v56l-20-14z"/><path d="M43 71h19m-19 5h19m-19 5h19m-19 5h19M83 64h18m-18 5h18m-18 5h18M65 86v8m14-10v8M8 110l28 10 80-13"/>`,
    home:`<path d="M13 69l31-31 33 31v40H13zM6 70l38-40 40 40M30 109V83h18v26M55 78h13v13H55zM25 48V30h9v9"/><path d="M80 108V43h28v65M87 53h6v9h-6zm13 0h5v9h-5zM87 71h6v9h-6zm13 0h5v9h-5zM87 88h6v9h-6zm13 0h5v9h-5zM3 113h113"/><path class="pa-solid" d="M15 73h16v35H15z"/>`,
    factory:`<path d="M7 106V57l27-15v15l28-15v64zM72 107V32h39v75M12 104h94M18 69h11v11H18zm24 0h11v11H42zM82 41h18v12H82zm0 20h18v12H82zm0 20h18v12H82zM83 47h8m-8 20h8m-8 20h8M17 57V23h10v29"/><path class="pa-solid" d="M73 32h38v10H73z"/><circle cx="99" cy="47" r="1.5"/><circle cx="99" cy="67" r="1.5"/><circle cx="99" cy="87" r="1.5"/>`,
    converter:`<path d="M8 27h38v76H8zM74 27h38v76H74zM46 65h28M14 40h26m-26 12h26m-26 12h26m-26 12h26m-26 12h26M80 40h26m-26 12h26m-26 12h26m-26 12h26m-26 12h26M3 108h114"/><path class="pa-nofill" d="M14 16q7-12 14 0t14 0M80 16q7-12 14 0t14 0M51 61h18m-18 8h18"/>`,
    solar:`<path d="M5 54l53-12 14 37-54 11zM11 66l53-12M15 78l53-12M20 51l13 35m3-39l14 35m2-39l14 35M28 87v20m28-27v23M19 111h47M84 44h29v63H84zM90 36h17v8M90 54h17v18H90zM90 81h17m-17 8h17m-17 8h17"/><circle cx="37" cy="17" r="9"/><path d="M37 1v3m0 26v3M21 17h3m26 0h3M26 6l3 3m17 17 3 3M26 29l3-3M46 9l3-3"/>`,
    condenser:`<path d="M13 42h91v54H13z"/><path d="M7 47h102v44H7zM22 55h72M22 63h72M22 71h72M22 79h72M22 87h72M34 42V21h23M59 97v13H31M105 55h13M0 82h7"/><path class="pa-solid" d="M14 91h89v5H14z"/><circle cx="26" cy="110" r="6"/>`,
    control:`<path d="M6 34h108v62H6zM12 97v14m96-14v14M13 41h40v28H13zm51 0h40v28H64z"/><path class="pa-nofill" d="M17 61l7-9 8 7 7-12 10 8M68 57h7l5-9 7 14 5-9h9"/><path d="M14 80h9m6 0h9m6 0h9m15 0h9m6 0h9m6 0h9M14 86h38m17 0h36"/><path class="pa-solid" d="M7 90h106v7H7z"/>`,
    pump:`<circle cx="56" cy="69" r="25"/><circle cx="56" cy="69" r="10"/><path d="M32 60H7V48h36M65 47V22h14v47M56 95v12H38m42 0H60M94 34v64M86 44l16 18-16 18z"/><path class="pa-solid" d="M49 51l20 20-23 17z"/>`,
    fuel:`<path d="M16 39l28-15 61 15-28 17zM16 39v66l61 12 28-16V39M77 56v61"/><path d="M29 45V18m11 23V13m11 31V12m11 36V19M25 55v39m10-37v39m10-37v39m10-37v39m10-37v39"/><path class="pa-solid" d="M17 40l60 17v60l-60-12z"/>`,
    boiler:`<path d="M17 18h65v90H17zM25 27h49v59H25zM83 62h21V25h12v80H83M9 113h108"/><path d="M34 35h29v9H34v10h29v10H34v10h29M27 98h12m8 0h12m8 0h8M4 78h13M47 18V6h55"/><path class="pa-solid" d="M18 88h64v20H18z"/>`,
    stack:`<path d="M15 112V47h35v65M73 112l5-98h18l5 98M74 29h23M11 112h96M22 56h21v30H22zM50 69h25M80 8q9-10 18 0"/><path d="M25 62h15m-15 8h15m-15 8h15"/><path class="pa-solid" d="M17 93h31v19H17z"/>`
  };
  function start(P){
    document.body.classList.add('pa-page');
    const root=document.getElementById('power-atlas'),canvas=root.querySelector('.pa-diagram-wrap'),context=root.querySelector('.pa-context'),panel=root.querySelector('.pa-companies');
    const state={scene:P.scenes[0].id,node:null,child:null,playing:false};
    const scene=()=>P.scenes.find(s=>s.id===state.scene);
    const allNodes=()=>P.scenes.flatMap(s=>s.nodes);
    const unique=rows=>{
      const found=new Map();
      rows.forEach(c=>{const old=found.get(c.stock);if(!old)found.set(c.stock,{...c,proofs:[...c.proofs]});else{
        c.proofs.forEach(p=>{if(!old.proofs.some(q=>q.src===p.src&&q.text===p.text&&q.url===p.url))old.proofs.push(p);});
        if(!old.metric&&c.metric)old.metric=c.metric;
      }});return [...found.values()];
    };
    function rows(n){return unique(n.children.flatMap(c=>P.rows[c.id]||[]));}
    function draw(){
      const s=scene();
      let h=`<svg class="pa-svg" viewBox="0 0 ${s.width||1340} ${s.height||590}" role="group" aria-label="${esc(s.title)}"><defs>`;
      ['electric','steam','water','heat','shaft','control'].forEach((k,i)=>{const colors=['#e8bb72','#dc9879','#73b9dd','#d57e78','#a4b6c7','#7ebfae'];h+=`<marker id="pa-arrow-${k}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L8 4 0 8z" fill="${colors[i]}"/></marker>`;});
      h+='</defs>';
      (s.boundaries||[]).forEach(b=>{h+=`<rect class="pa-boundary" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="16"/><text class="pa-lane" x="${b.x+16}" y="${b.y+24}">${esc(b.label)}</text>`;});
      (s.labels||[]).forEach(l=>{h+=`<text class="pa-lane" x="${l.x}" y="${l.y}">${esc(l.text)}</text>`;});
      const colors={electric:'#e8bb72',steam:'#dc9879',water:'#73b9dd',heat:'#d57e78',shaft:'#a4b6c7',control:'#7ebfae'};
      s.edges.forEach(e=>{
        const color=colors[e.kind||'electric'];
        h+=`<path class="pa-edge" d="${e.d}" stroke="${color}" opacity="${e.branch?.55:.7}"${e.branch?' stroke-dasharray="4 5"':''} marker-end="url(#pa-arrow-${e.kind||'electric'})"${e.both?' marker-start="url(#pa-arrow-'+(e.kind||'electric')+')"':''}/>`;
        if(!e.branch&&e.kind!=='control')h+=`<path class="pa-pulse" d="${e.d}" stroke="${color}"/>`;
        if(e.label)h+=`<text class="pa-edge-label" x="${e.lx}" y="${e.ly}" text-anchor="middle" style="fill:${color}">${esc(e.label)}</text>`;
      });
      s.nodes.forEach((n,i)=>{
        const count=rows(n).length, selected=state.node===n.id;
        h+=`<g class="pa-node" data-node="${esc(n.id)}" tabindex="0" role="button" aria-label="${esc(n.label)} · 하위 장비 보기" aria-pressed="${selected}" aria-controls="pa-detail" style="color:${n.color||'#8ab5d1'}"><title>${esc(n.label+' — '+n.note)}</title><rect class="pa-hit" x="${n.x-83}" y="${n.y-91}" width="166" height="213" rx="13"/><ellipse class="pa-ground" cx="${n.x}" cy="${n.y+55}" rx="66" ry="12"/><text class="pa-num" x="${n.x}" y="${n.y-73}" text-anchor="middle">${esc(n.tag||String(i+1).padStart(2,'0'))}</text><g class="pa-icon" transform="translate(${n.x-55} ${n.y-53}) scale(.92)">${symbols[n.id==='POLE'&&state.child==='pad-transformer'?'pad':n.icon]||symbols.transformer}</g><text class="pa-label" x="${n.x}" y="${n.y+81}" text-anchor="middle">${esc(n.label)}</text><text class="pa-sub" x="${n.x}" y="${n.y+102}" text-anchor="middle">${esc(n.unit||'')}${count?' · '+count+'사':''}</text></g>`;
      });
      h+='</svg>';canvas.innerHTML=h;
      root.querySelectorAll('.pa-node').forEach(g=>{
        g.addEventListener('click',()=>select(g.dataset.node));
        g.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();select(g.dataset.node);const next=root.querySelector('[data-node="'+g.dataset.node+'"]');if(next)next.focus({preventScroll:true});}});
      });
      root.querySelector('.pa-legend').innerHTML=s.legend.map(l=>`<span><i style="--flow:${colors[l.kind]}"></i>${esc(l.label)}</span>`).join('')+`<span class="pa-caveat">${esc(s.caveat)}</span>`;
      root.querySelector('.pa-stepnav').innerHTML=s.nodes.map(n=>`<button type="button" data-jump="${esc(n.id)}" aria-pressed="${state.node===n.id}">${esc(n.label)}</button>`).join('');
      root.querySelectorAll('[data-jump]').forEach(b=>b.addEventListener('click',()=>select(b.dataset.jump)));
      root.querySelectorAll('[data-scene]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.scene===state.scene));
    }
    function select(id,child=null,hash=true){
      const s=P.scenes.find(s=>s.nodes.some(n=>n.id===id));if(!s)return;
      state.scene=s.id;state.node=id;state.child=child;draw();details();
      if(hash)history.replaceState(null,'','#'+encodeURIComponent(child||id));
      root.querySelector('[role="status"]').textContent=allNodes().find(n=>n.id===id).label+' 하위 장비와 기업을 표시했습니다.';
    }
    function details(){
      const n=scene().nodes.find(n=>n.id===state.node);if(!n)return;
      context.innerHTML=`<div class="pa-kicker">설비의 역할</div><h3>${esc(n.label)}</h3><div class="pa-unit">${esc(n.unit||'')}</div><p>${esc(n.note)}</p><div class="pa-children">${n.children.map(c=>`<button class="pa-child" type="button" data-child="${esc(c.id)}" aria-pressed="${state.child===c.id}"><span>${esc(c.label)}</span><small>${unique(P.rows[c.id]||[]).length||'미확인'}${(P.rows[c.id]||[]).length?'사':''}</small></button>`).join('')}</div><div class="pa-ref">${(n.refs||[]).map(k=>{const s=P.sources[k];return s?`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label)} ↗</a>`:'';}).join('')}</div>`;
      context.querySelectorAll('[data-child]').forEach(b=>b.addEventListener('click',()=>{
        state.child=b.dataset.child;draw();details();history.replaceState(null,'','#'+encodeURIComponent(state.child));context.querySelector('[data-child="'+state.child+'"]').focus({preventScroll:true});
      }));
      const child=n.children.find(c=>c.id===state.child), list=child?unique(P.rows[child.id]||[]):rows(n);
      panel.innerHTML=`<header><h3>${esc(child?child.label:'연결 기업')}</h3><span class="pa-count">${list.length}사</span></header><p class="pa-help">${esc(child&&child.note||P.company_note)}</p><label><span class="pa-sr">기업명 또는 종목코드 검색</span><input class="pa-search" type="search" placeholder="기업명 · 종목코드 검색"></label><div class="pa-co-list"></div>`;
      const out=panel.querySelector('.pa-co-list');
      function fill(query){
        const filtered=list.filter(c=>(c.nm+' '+c.stock).toLowerCase().includes(query.trim().toLowerCase()));
        out.innerHTML=filtered.map(c=>`<article class="pa-co"><div class="pa-co-head">${P.pages.includes(c.stock)?`<a href="${esc(c.stock)}/index.html">${esc(c.nm)}</a>`:`<strong>${esc(c.nm)}</strong>`}<small>${esc(c.stock)}</small></div>${c.metric?`<p class="pa-metric">${esc(c.metric)}</p>`:''}<details><summary>분류 근거</summary>${c.proofs.map(p=>`<span class="pa-proof-src">${esc(p.src)}${p.url?` · <a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">공식 자료 ↗</a>`:''}</span><blockquote>${esc(p.text)}</blockquote>`).join('')}${(c.primes||[]).map(p=>`<p class="pa-help">납품처 언급 · ${esc(p.nm)} · ${esc(p.basis||'')}</p>`).join('')}</details></article>`).join('')||`<p class="pa-empty">${query?'검색 결과가 없습니다.':'이 세부 장비를 만드는 상장사를 현재 원문에서 확인하지 못했습니다.'}${n.link?`<br><a href="${esc(n.link.url)}">${esc(n.link.label)} ↗</a>`:''}</p>`;
      }
      panel.querySelector('.pa-search').addEventListener('input',e=>fill(e.target.value));fill('');
    }
    function fromHash(){
      let id;try{id=decodeURIComponent(location.hash.slice(1));}catch(_){return false;}
      id=(P.aliases||{})[id]||id;
      const n=allNodes().find(n=>n.id===id||n.children.some(c=>c.id===id));
      if(!n)return false;select(n.id,n.id===id?null:id,false);return true;
    }
    root.querySelectorAll('[data-scene]').forEach(b=>b.addEventListener('click',()=>{const s=P.scenes.find(s=>s.id===b.dataset.scene);select(s.nodes[0].id);}));
    root.querySelector('[data-reset]').addEventListener('click',()=>select(scene().nodes[0].id));
    const motion=root.querySelector('[data-motion]'),reduced=matchMedia('(prefers-reduced-motion: reduce)');
    function stopMotion(){state.playing=false;root.classList.remove('pa-playing');motion.setAttribute('aria-pressed','false');motion.textContent='흐름 재생';}
    motion.addEventListener('click',()=>{if(reduced.matches){stopMotion();return;}state.playing=!state.playing;root.classList.toggle('pa-playing',state.playing);motion.setAttribute('aria-pressed',state.playing);motion.textContent=state.playing?'흐름 정지':'흐름 재생';});
    reduced.addEventListener('change',stopMotion);window.addEventListener('hashchange',fromHash);
    if(!fromHash())select(P.default_node||scene().nodes[0].id,null,false);
  }
  window.PowerAtlas={start};
})();
