/* W01_VIZ_STANDALONE_BEGIN */
(function(){
if(typeof window!=="undefined"&&!window.VIZ_CONTRACT){
/* W01_VIZ_CONTRACT_v1 */
(function(r){r.VIZ_CONTRACT={
  "schema_version": "1.0.0",
  "lane": "W01_VIZ",
  "purpose": "투자판단 참고용. 축·스타일 정책이며 재무 추정 정확성을 보증하지 않음.",
  "numeric_domain": {
    "finite_only": true,
    "max_abs": 1e+200,
    "min_nonzero_span": 1e-200,
    "null_policy": "gap",
    "strings_and_booleans": "reject",
    "rounding": "눈금: 정수 mantissa×10진 지수 문자열을 IEEE754로 변환; 요약값:12유효자리",
    "precision_guard": "span>0에서 pad>=abs(median)*1e-12, NUMERIC_PRECISION_GUARD 경고; 작은 지수 값은 eN 접미사"
  },
  "classes": {
    "zero_anchored": {
      "use": [
        "bar",
        "stacked",
        "composition"
      ],
      "zero_required": true,
      "signed_stack": "positive_negative_sums_separate"
    },
    "range_focus": {
      "use": [
        "level",
        "capacity",
        "price",
        "index"
      ],
      "near_flat": "span/abs(median)<0.08; median=0이면 span=0",
      "pad": "span*0.12; span=0이면 abs(median)*0.02; 모두0이면0.02",
      "zero_required": false
    },
    "symmetric": {
      "use": [
        "yoy",
        "qoq",
        "growth",
        "change"
      ],
      "rule": "max(abs(min),abs(max))*1.12 양쪽 동일; 0 중심"
    },
    "ratio": {
      "use": [
        "utilization",
        "margin",
        "supply_demand"
      ],
      "domain": "0~ratioMax(1 또는100), 음수·초과관측과 reference 모두 포함. 명시적 null이면 상한미지정(data+0)",
      "clamp": false
    },
    "log_candidate": {
      "rule": "모든 값>0 및 max/min>=1000",
      "automatic_transform": false,
      "reason": "배율 축은 의미 변경이므로 후보만 제시; 선형 전체 범위를 유지"
    },
    "unknown": {
      "rule": "분류 근거 없음 표시; 렌더러 숫자 축은 range_focus fallback, 상태를 실적으로 승격하지 않음"
    }
  },
  "scale_policy": {
    "version": "1",
    "near_flat_threshold": 0.08,
    "pad_fraction": 0.12,
    "constant_pad_fraction": 0.02,
    "ticks": {
      "min": 4,
      "target": 5,
      "max": 6,
      "mantissas": [
        1,
        2,
        2.5,
        5
      ],
      "rule": "범위를 덮는 후보 중 abs(n-5)+추가폭/원폭 최소; tie step/min/max 순"
    },
    "truncation_note": "축 시작 ≠ 0",
    "outlier": {
      "minimum_n": 100,
      "quantiles": [
        0.01,
        0.99
      ],
      "tail_to_core": 3,
      "automatic_clipping": false,
      "clip_hint": "삼각형+실제값, 사용자가 범위 축소 선택할 때만 적용"
    },
    "zero_anchored_precedence": "stacked/composition/bar 우선; 사용자 range_focus라도 막대 절단 금지"
  },
  "multi_axis": {
    "same_unit": "single shared domain",
    "different_units": "dual axes with explicit unit labels",
    "more_than_two_units": "separate panels required",
    "zero_alignment": "두 축 모두 zero_anchored일 때만 0정렬; 다른 축은 강제 정렬하지 않고 양축 기준 표시",
    "grid": "primary only"
  },
  "legend": {
    "up_to_3": "inline",
    "4_to_8": "bottom_wrap",
    "over_8": "scroll_group",
    "label": "name [unit · status]",
    "palette_rotation": "metric_index modulo8; actual/forecast metric_index 동일",
    "distinguishers": [
      "color",
      "dash or marker shape"
    ]
  },
  "tokens": {
    "palette": {
      "light": [
        "#005b8f",
        "#924500",
        "#00694d",
        "#743487",
        "#a33048",
        "#37519b",
        "#665b00",
        "#454d56"
      ],
      "dark": [
        "#56b4e9",
        "#e69f00",
        "#55c9a5",
        "#d995e4",
        "#ff9daa",
        "#9baef5",
        "#e3ce64",
        "#bec9d4"
      ]
    },
    "background": {
      "light": "#ffffff",
      "dark": "#101721"
    },
    "text": {
      "light": "#202735",
      "dark": "#e9eef5"
    },
    "markers": [
      "circle",
      "rect",
      "triangle",
      "rectRot"
    ],
    "roles": {
      "actual": {
        "label": "실적",
        "width": 1.8,
        "dash": [],
        "hollow": false,
        "opacity": 1
      },
      "derived": {
        "label": "산출",
        "width": 1.8,
        "dash": [],
        "hollow": false,
        "markerBorderWidth": 2.5,
        "opacity": 1
      },
      "forecast": {
        "label": "전망(est)",
        "width": 2.8,
        "dash": [
          7,
          4
        ],
        "hollow": true,
        "opacity": 1
      },
      "unknown": {
        "label": "NOT FOUND",
        "width": 0,
        "dash": [],
        "hollow": true,
        "opacity": 0
      }
    },
    "band": {
      "opacity": 0.14,
      "default_label": "시나리오 lo~hi (확률 미보정)",
      "probability_label_gate": "80% 범위는 coverage calibration 증거가 있을 때만",
      "requires": [
        "lo",
        "base",
        "hi",
        "basis"
      ]
    },
    "divider": {
      "label": "전망 시작",
      "dash": [
        3,
        3
      ]
    },
    "minimum_contrast": 4.5
  },
  "status_aliases": {
    "reported": "actual",
    "calculated": "derived",
    "estimate": "forecast",
    "est": "forecast",
    "NOT FOUND": "unknown"
  },
  "safety": [
    "공시 없는 과거값도 est 유지",
    "NOT FOUND를0으로대체금지",
    "결측구간 연결금지",
    "시나리오를확률구간으로라벨금지",
    "밴드가없으면창작금지",
    "주식가격추천아님"
  ],
  "validation": {
    "minimum_parity_cases": 30,
    "holdout": "별도 난수 seed 입력과 다른 ref 회사 시계열",
    "model_fit": "범위 계산 검증이며 예측모델 성과와 별개; SHINETSU holdout n=0 게이트 미검증"
  }
};})(typeof window!=="undefined"?window:globalThis);

}
if(typeof window!=="undefined"&&!window.VizSeries){
/* W01 series semantics and shared SVG/Chart.js style, ES5. */
(function(root){
 'use strict';
 function cp(x){var y={},k;for(k in x){if(Object.prototype.hasOwnProperty.call(x,k)){y[k]=x[k];}}return y;}
 function esc(x){return String(x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
 function roleOf(r){if(r==='actual'||r==='reported'){return 'actual';}if(r==='derived'||r==='calculated'){return 'derived';}if(r==='forecast'||r==='est'||r==='estimate'){return 'forecast';}return 'unknown';}
 function finite(v){return typeof v==='number'&&isFinite(v);}
 function readTheme(){if(!root.document){return 'light';}var e=root.document.documentElement,t=e.getAttribute('data-theme');if(t==='light'||t==='dark'){return t;}if(root.getComputedStyle){var bg=root.getComputedStyle(e).getPropertyValue('--bg').replace(/\s/g,'');if(/^#[0-9a-f]{6}$/i.test(bg)){return (parseInt(bg.slice(1,3),16)*.2126+parseInt(bg.slice(3,5),16)*.7152+parseInt(bg.slice(5,7),16)*.0722)>128?'light':'dark';}}return root.matchMedia&&root.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
 function getTokens(t){var v=t||root.VIZ_CONTRACT;if(!v){throw new Error('VIZ_CONTRACT_REQUIRED');}return v.tokens||v;}
 function applySeriesStyle(series,role,tokens){
   var s=cp(series||{}),t=getTokens(tokens),r=roleOf(role),theme=s.theme==='light'?'light':'dark',pal=t.palette[theme],i=s.metric_index===undefined?(s.index||0):s.metric_index,color=pal[((i%pal.length)+pal.length)%pal.length],st=t.roles[r],marker=t.markers[(((i+Math.floor(i/8))%t.markers.length)+t.markers.length)%t.markers.length];
   s.role=r;s.statusLabel=st.label;s.borderColor=color;s.stroke=color;s.borderWidth=st.width;s.width=st.width;s.borderDash=st.dash.slice();s.dash=st.dash.slice();s.pointStyle=marker;s.marker=marker;s.hollow=st.hollow;s.pointRadius=r==='forecast'?3.4:2.4;s.pointBorderWidth=r==='derived'?2.5:1.5;s.pointBackgroundColor=st.hollow?t.background[theme]:color;s.backgroundColor=s.pointBackgroundColor;s.fill=s.backgroundColor;s.opacity=1;s.spanGaps=false;s.tension=0;
   s.label=(s.name||s.label||'계열')+' ['+(s.unit||s.vizUnit||'단위 미확인')+' · '+st.label+']';
   if(s.data){s.data=s.data.map(function(p){if(r==='unknown'){return null;}if(p===null||p===undefined){return null;}if(typeof p==='object'){var pr=roleOf(p.role||p.status||(p.est?'est':r));return pr==='unknown'?null:p;}return finite(p)?p:null;});}
   return s;
 }
 function normalizePoint(p,defaultRole){
   if(p===null||p===undefined){return {value:null,role:'unknown'};}
   if(Array.isArray(p)){return {value:finite(p[1])?p[1]:null,role:roleOf(defaultRole)};}
   if(typeof p==='object'){var r=roleOf(p.role||p.status||(p.est?'est':defaultRole)),v=finite(p.y)?p.y:(finite(p.value)?p.value:null);return {value:r==='unknown'?null:v,role:r,lo:finite(p.lo)?p.lo:null,hi:finite(p.hi)?p.hi:null};}
   if(Array.isArray(p)){return {value:finite(p[1])?p[1]:null,role:roleOf(defaultRole)};}return {value:finite(p)?p:null,role:roleOf(defaultRole)};
 }
 function splitSeries(series,tokens){
   var roles=['actual','derived','forecast'],out=[],raw=series.data||[],pts=raw.map(function(p){return normalizePoint(p,series.role||series.vizRole||'unknown');});
   roles.forEach(function(r){if(!pts.some(function(p){return p.role===r&&p.value!==null;})){return;}var s=cp(series),first=null;s.data=pts.map(function(p,i){var take=p.role===r;if(take&&p.value!==null&&first===null){first=i;}if(!take&&series.type!=='bar'&&r==='forecast'&&i+1<pts.length&&pts[i+1].role==='forecast'&&p.role!=='unknown'){take=true;}if(!take||p.value===null){return null;}if(raw[i]&&typeof raw[i]==='object'){if(Array.isArray(raw[i])){return raw[i].slice();}var q=cp(raw[i]);q.y=p.value;return q;}return p.value;});s=applySeriesStyle(s,r,tokens);s.vizForecastStartIndex=r==='forecast'?first:null;s.role=r;out.push(s);});return out;
 }
 function svgBand(points,opts){
   var o=opts||{},segments=[],seg=[],paths=[],x=o.x||function(i){return i;},y=o.y||function(v){return v;},meaning=o.meaning||'시나리오 lo~hi (확률 미보정)';
   points.forEach(function(p,i){var lo=p&&p[o.loKey||'lo'],hi=p&&p[o.hiKey||'hi'];var base=p&&(finite(p.base)?p.base:(finite(p.value)?p.value:p.y));if(!finite(lo)||!finite(hi)||!finite(base)||lo>base||base>hi||p.status==='unknown'||p.status==='NOT FOUND'){if(seg.length){segments.push(seg);}seg=[];return;}seg.push({x:x(i),lo:y(lo),hi:y(hi)});});if(seg.length){segments.push(seg);}
   segments.forEach(function(a){if(a.length<2){return;}if(!o.basis){throw new Error('BAND_BASIS_REQUIRED');}if(/%/.test(meaning)&&!(o.calibration&&o.calibration.validated===true)){throw new Error('BAND_PROBABILITY_UNVERIFIED');}var d='M'+a.map(function(p){return p.x+','+p.lo;}).join(' L')+' L'+a.slice().reverse().map(function(p){return p.x+','+p.hi;}).join(' L')+' Z';paths.push('<path data-viz-band="true" aria-label="'+esc(meaning)+'" d="'+d+'" fill="'+esc(o.color||getTokens(o.tokens).palette[o.theme==='dark'?'dark':'light'][0])+'" fill-opacity="0.14" stroke="'+esc(o.color||getTokens(o.tokens).palette[o.theme==='dark'?'dark':'light'][0])+'" stroke-width="1" stroke-dasharray="3 3"><title>'+esc(meaning)+'</title></path>');});return paths.join('');
 }
 function svgDivider(x,y1,y2,label,tokens){var t=getTokens(tokens),color=t.text[readTheme()];return '<g data-viz-forecast-start="true"><line x1="'+x+'" x2="'+x+'" y1="'+y1+'" y2="'+y2+'" stroke="'+color+'" stroke-dasharray="3 3"/><text x="'+(x+4)+'" y="'+(y1+12)+'" fill="'+color+'" font-size="11">'+esc(label||'전망 시작')+'</text></g>';}
 function makeForecastBand(series,opts){
   var o=opts||{},lo=[],hi=[],base=[],meaning=o.meaning||'시나리오 lo~hi (확률 미보정)';if(!(o.basis||series.basis)){throw new Error('BAND_BASIS_REQUIRED');}if(/%/.test(meaning)&&!(o.calibration&&o.calibration.validated===true)){throw new Error('BAND_PROBABILITY_UNVERIFIED');}
   (series.data||[]).forEach(function(p){var valid=p&&finite(p.lo)&&finite(p.hi)&&finite(p.base)&&p.lo<=p.base&&p.base<=p.hi&&p.status!=='unknown'&&p.status!=='NOT FOUND';lo.push(valid?p.lo:null);hi.push(valid?p.hi:null);base.push(p&&finite(p.base)?p.base:null);});
   var source=cp(series);source.theme=source.theme||readTheme();var lower=applySeriesStyle(source,'forecast',o.tokens),upper=applySeriesStyle(source,'forecast',o.tokens);lower.data=lo;upper.data=hi;lower.label=meaning+' 하단';upper.label=meaning;lower.pointRadius=0;upper.pointRadius=0;lower.borderWidth=1;upper.borderWidth=1;lower.fill=false;upper.fill='-1';upper.backgroundColor=hexAlpha(upper.borderColor,.14);lower.vizBand=true;upper.vizBand=true;lower.vizBandPart='lo';upper.vizBandPart='hi';return [lower,upper];
 }
 function hexAlpha(h,a){return 'rgba('+parseInt(h.slice(1,3),16)+','+parseInt(h.slice(3,5),16)+','+parseInt(h.slice(5,7),16)+','+a+')';}
 function styleDatasets(chart){
   var theme=readTheme(),names=[],expanded=[];
   chart.data.datasets.forEach(function(ds){var def=roleOf(ds.vizRole||ds.role||ds.status),rs=[];(ds.data||[]).forEach(function(p){if(p&&typeof p==='object'&&!Array.isArray(p)){var pr=roleOf(p.role||p.status||(p.est?'est':def));if(pr!=='unknown'&&rs.indexOf(pr)<0){rs.push(pr);}}});if(!ds._vizSplit&&rs.some(function(r){return r!==def;})){var src=cp(ds);src.type=ds.type||chart.config.type;src.role=def;src.name=ds._vizOriginalLabel||ds.label;splitSeries(src).forEach(function(s){s.vizRole=s.role;s.vizMetric=ds.vizMetric||ds.label;s._vizOriginalLabel=ds._vizOriginalLabel||ds.label;s._vizSplit=true;expanded.push(s);});}else{expanded.push(ds);}});chart.data.datasets=expanded;
   chart.data.datasets.forEach(function(ds,i){
     if(ds.vizBand){var bandStyle=applySeriesStyle({theme:theme,metric_index:ds.metric_index||0},'forecast');ds.borderColor=bandStyle.borderColor;ds.backgroundColor=ds.vizBandPart==='hi'?hexAlpha(bandStyle.borderColor,.14):bandStyle.backgroundColor;return;}var hasRole=ds.vizRole||ds.role||ds.status;if(!hasRole){return;}
     if(!ds._vizOriginalLabel){ds._vizOriginalLabel=ds.label||'계열';}var metric=ds.vizMetric||ds._vizOriginalLabel;if(names.indexOf(metric)<0){names.push(metric);}
     var s=applySeriesStyle({name:ds._vizOriginalLabel,unit:ds.vizUnit||ds.unit,metric_index:ds.metric_index===undefined?names.indexOf(metric):ds.metric_index,theme:theme},hasRole);
     ['borderColor','borderWidth','borderDash','pointStyle','pointRadius','pointBorderWidth','pointBackgroundColor','backgroundColor','spanGaps','label'].forEach(function(k){ds[k]=s[k];});
     if(roleOf(hasRole)==='unknown'){ds.data=(ds.data||[]).map(function(){return null;});}
     else {ds.data=(ds.data||[]).map(function(p){if(p&&typeof p==='object'&&(p.status==='NOT FOUND'||p.status==='unknown')){return null;}return p;});}
   });
   var labels=chart.data.datasets.filter(function(s){return !s.vizBand;}).map(function(s){return {label:s._vizOriginalLabel||s.label,unit:s.vizUnit||s.unit,role:s.vizRole||s.role||'unknown'};});
   chart.$vizLegend=root.VizScale.legendPlan(labels);
   var raw=(chart.config&&chart.config.options)||chart.options;if(!raw.plugins){raw.plugins={};}var cfg=raw.plugins;if(!cfg.legend){cfg.legend={};}cfg.legend.position='bottom';if(!cfg.legend.labels){cfg.legend.labels={};}cfg.legend.labels.usePointStyle=true;cfg.legend.display=false;
 }
 function drawForecastDividers(chart){
   if(chart.options&&chart.options.plugins&&chart.options.plugins.vizScale&&chart.options.plugins.vizScale.forecastDivider===false){return;}
   var start=null,labels=chart.data.labels||[],ctx=chart.ctx,a=chart.chartArea;
   chart.data.datasets.forEach(function(ds){if(roleOf(ds.vizRole||ds.role)!=='forecast'||ds.vizBand){return;}if(ds.vizForecastStartIndex!==undefined&&ds.vizForecastStartIndex!==null){start=start===null?ds.vizForecastStartIndex:Math.min(start,ds.vizForecastStartIndex);return;}(ds.data||[]).some(function(p,i){if(finite(p)||(p&&typeof p==='object'&&finite(p.y))){start=start===null?i:Math.min(start,i);return true;}return false;});});
   if(start===null||!chart.scales.x||!a){return;}var x=chart.scales.x.getPixelForValue(labels[start]===undefined?start:labels[start],start);ctx.save();ctx.strokeStyle='#9aa7b8';ctx.fillStyle=getTokens().text[readTheme()];ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x,a.top);ctx.lineTo(x,a.bottom);ctx.stroke();ctx.setLineDash([]);var config=(chart.options.plugins||{}).vizScale||{},caption=config.forecastDivider===true?'전망 시작':'추정 시작 (시점 미확인)';ctx.fillText(caption,Math.min(x+4,a.right-130),a.top+12);ctx.restore();
 }
 function renderLegend(chart){
   if(!root.document||!chart.canvas||!chart.canvas.parentNode||!chart.$vizLegend){return;}
   var plan=chart.$vizLegend,host=chart.$vizLegendElement,t=getTokens(),theme=readTheme();
   if(!host){host=root.document.createElement('div');host.setAttribute('data-viz-legend','');host.setAttribute('aria-label','차트 범례; 버튼으로 계열 표시 전환');var parent=chart.canvas.parentNode;if(parent.parentNode&&parent.tagName!=='BODY'){parent.parentNode.insertBefore(host,parent.nextSibling);}else{parent.insertBefore(host,chart.canvas.nextSibling);}chart.$vizLegendElement=host;}
   host.style.cssText='display:flex;gap:8px;max-width:100%;padding:6px 0;font:12px sans-serif;'+(plan.placement==='scroll_group'?'overflow-x:auto;flex-wrap:nowrap;':'flex-wrap:wrap;');host.setAttribute('data-placement',plan.placement);while(host.firstChild){host.removeChild(host.firstChild);}
   chart.data.datasets.forEach(function(ds,i){
     if(ds.vizBand&&ds.vizBandPart==='lo'){return;}var b=root.document.createElement('button'),sw=root.document.createElement('span');b.type='button';b.style.cssText='display:inline-flex;align-items:center;gap:5px;flex-shrink:0;cursor:pointer;border:1px solid '+t.text[theme]+';border-radius:3px;padding:3px 5px;background:'+t.background[theme]+';color:'+t.text[theme]+';font:inherit;';b.setAttribute('aria-pressed',chart.isDatasetVisible?String(chart.isDatasetVisible(i)):'true');sw.textContent=(ds.pointStyle==='triangle'?'△':ds.pointStyle==='rect'||ds.pointStyle==='rectRot'?'□':'○');sw.style.color=ds.borderColor||t.text[theme];sw.style.borderBottom=(ds.borderWidth||2)+'px '+((ds.borderDash||[]).length?'dashed':'solid')+' '+(ds.borderColor||t.text[theme]);b.appendChild(sw);b.appendChild(root.document.createTextNode(ds.label||'계열'));b.onclick=function(){if(chart.setDatasetVisibility){chart.setDatasetVisibility(i,!chart.isDatasetVisible(i));chart.update();}};host.appendChild(b);
   });
   var raw=(chart.config&&chart.config.options)||chart.options;if(raw.plugins&&raw.plugins.legend){raw.plugins.legend.display=false;}
 }
 function clearUnitPanels(chart){
   (chart.$vizPanelCharts||[]).forEach(function(c){c.destroy();});chart.$vizPanelCharts=[];
   var host=chart.$vizPanelHost;if(host&&host.parentNode){host.parentNode.removeChild(host);}chart.$vizPanelHost=null;
   if(chart.$vizHiddenContainer){chart.$vizHiddenContainer.style.display=chart.$vizOldDisplay||'';chart.$vizHiddenContainer=null;}
 }
 function renderUnitPanels(chart){
   if(!root.document||!root.Chart||chart.$vizIsPanel||!chart.canvas||!chart.canvas.parentNode){return false;}
   var raw=(chart.config&&chart.config.options)||chart.options,cfg=(raw.plugins||{}).vizScale||{},axes=cfg.axes||{},units=[],selected=[];
   if(chart.config.type==='scatter'||raw.indexAxis==='y'){return false;}
   chart.data.datasets.forEach(function(ds,i){if(chart.isDatasetVisible&&!chart.isDatasetVisible(i)){return;}var axis=ds.yAxisID||'y',unit=ds.vizUnit||ds.unit||(axes[axis]||{}).unit;if(!unit){return;}if(units.indexOf(unit)<0){units.push(unit);}selected.push({dataset:ds,unit:unit,axis:axis});});
   if(units.length<=2){if(chart.$vizPanelHost){clearUnitPanels(chart);}return false;}
   clearUnitPanels(chart);
   if(chart.$vizLegendElement){chart.$vizLegendElement.remove();chart.$vizLegendElement=null;}
   var parent=chart.canvas.parentNode,hidden=parent.children.length===1?parent:chart.canvas,host=root.document.createElement('div');host.setAttribute('data-viz-unit-panels',String(units.length));host.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;';parent.parentNode.insertBefore(host,parent.nextSibling);chart.$vizPanelHost=host;chart.$vizHiddenContainer=hidden;chart.$vizOldDisplay=hidden.style.display;hidden.style.display='none';chart.$vizPanelCharts=[];
   for(var i=0;i<units.length;i+=2){
     var group=units.slice(i,i+2),box=root.document.createElement('div'),heading=root.document.createElement('div'),plot=root.document.createElement('div'),canvas=root.document.createElement('canvas'),scales={},meta={},datasets=[];
     heading.textContent=group.join(' / ')+' · 단위별 분리';heading.style.cssText='font:12px sans-serif;margin-bottom:5px;color:'+getTokens().text[readTheme()]+';';plot.style.cssText='position:relative;height:240px;';plot.appendChild(canvas);box.appendChild(heading);box.appendChild(plot);host.appendChild(box);
     selected.forEach(function(item){var j=group.indexOf(item.unit);if(j<0){return;}var key=j?'y2':'y',ds=cp(item.dataset);ds.data=(item.dataset.data||[]).slice();ds.yAxisID=key;datasets.push(ds);if(!scales[key]){scales[key]=cp((raw.scales||{})[item.axis]||{});scales[key].position=j?'right':'left';scales[key].axis='y';if(scales[key].ticks){scales[key].ticks=cp(scales[key].ticks);}if(scales[key].grid){scales[key].grid=cp(scales[key].grid);}meta[key]=cp(axes[item.axis]||{});meta[key].unit=item.unit;}});
     if(raw.scales&&raw.scales.x){scales.x=cp(raw.scales.x);}
     var childConfig={type:chart.config.type||'line',data:{labels:(chart.data.labels||[]).slice(),datasets:datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,scales:scales,plugins:{legend:{display:false},vizScale:{axes:meta,forecastDivider:cfg.forecastDivider}}}};
     var child=new root.Chart(canvas,childConfig);child.$vizIsPanel=true;chart.$vizPanelCharts.push(child);
   }
   chart.$vizMultiAxisStatus={status:'SPLIT_INTO_PANELS',units:units,panels:chart.$vizPanelCharts.length};return true;
 }
 var api={applySeriesStyle:applySeriesStyle,roleOf:roleOf,splitSeries:splitSeries,svgBand:svgBand,svgDivider:svgDivider,makeForecastBand:makeForecastBand,styleDatasets:styleDatasets,drawForecastDividers:drawForecastDividers,renderLegend:renderLegend,readTheme:readTheme,renderUnitPanels:renderUnitPanels,clearUnitPanels:clearUnitPanels};root.VizSeries=api;if(typeof module!=='undefined'&&module.exports){module.exports=api;}
}(typeof window!=='undefined'?window:(typeof global!=='undefined'?global:this)));

}
if(typeof window!=="undefined"&&!window.VizScale){
/* W01 VIZ scale engine: ES5, no dependency, JSON contract. */
(function (root) {
  'use strict';
  function finite(x) { return typeof x === 'number' && isFinite(x); }
  function clean(x) { return x === 0 ? 0 : Number(x.toPrecision(12)); }
  function copy(o) { var r = {}, k; for (k in o) { if (Object.prototype.hasOwnProperty.call(o,k)) { r[k]=o[k]; } } return r; }
  function classifySeries(m) {
    m=m||{};
    if(m.stacked || m.composition || m.type==='bar') { return 'zero_anchored'; }
    var c=m['class']||m.scale_class, kind=m.kind||m.metric_type||'';
    if(['zero_anchored','range_focus','symmetric','ratio','log_candidate','unknown'].indexOf(c)>=0) { return c; }
    if(['yoy','qoq','change','growth','return','spread_change'].indexOf(kind)>=0) { return 'symmetric'; }
    if(['utilization','margin','ratio','supply_demand'].indexOf(kind)>=0) { return 'ratio'; }
    if(['capacity','price','index','level','revenue','profit','volume'].indexOf(kind)>=0) { return 'range_focus'; }
    return 'unknown';
  }
  function axisNote(r) { return r.min!==null && (r.min>0 || r.max<0) ? '축 시작 ≠ 0' : ''; }
  function quantile(a,p) { var z=(a.length-1)*p,i=Math.floor(z); return a[i]+(a[Math.min(i+1,a.length-1)]-a[i])*(z-i); }
  function niceScale(values,opts) {
    var o=opts||{},a=values.filter(finite).sort(function(x,y){return x-y;}),c=classifySeries(o),mn,mx,med,span,near,log,warnings=[],pad,lo,hi,refs=[],cap,width,exp,cands=[],e,m,mult,decExp,step,li,hiidx,n,score,ticks=[],i,magnitude,suffix='',divisor=1,units,ss,decimals=0,hint=null,q1,q99,core,result;
    if(c==='unknown'){c='range_focus';}
    if(!a.length){return {status:'NOT FOUND',scale_class:c,min:null,max:null,step:null,ticks:[],decimals:0,suffix:'',divisor:1,axis_note:'',clip_hint:null,near_flat:false,log_candidate:false,references:[],warnings:['NO_FINITE_DATA']};}
    mn=a[0];mx=a[a.length-1];med=quantile(a,.5);span=mx-mn;
    if(!isFinite(span)||Math.max(Math.abs(mn),Math.abs(mx))>1e200||(span&&span<1e-200)){throw new Error('UNSUPPORTED_NUMERIC_MAGNITUDE');}
    near=med ? span/Math.abs(med)<.08 : span===0;log=mn>0&&mx/mn>=1000;
    if(c==='log_candidate'&&!log){warnings.push('LOG_REQUIRES_POSITIVE_1000X_RANGE');}
    if(log){warnings.push('LOG_SUGGESTION_ONLY_LINEAR_RETAINED');}
    pad=span ? span*.12 : (Math.abs(med)*.02||.02);if(span&&pad<Math.abs(med)*1e-12){pad=Math.abs(med)*1e-12;warnings.push('NUMERIC_PRECISION_GUARD');}lo=mn-pad;hi=mx+pad;
    if(c==='zero_anchored'){lo=mn>=0?0:lo;hi=mx<=0&&mn<0?0:hi;}
    else if(c==='symmetric'){hi=Math.max(Math.abs(mn),Math.abs(mx))*1.12||.02;lo=-hi;refs=[0];}
    else if(c==='ratio'){
      cap=o.ratioMax===undefined?(['%','pct'].indexOf(o.unit)>=0?100:1):o.ratioMax;
      if(cap!==null&&(!finite(cap)||cap<=0)){throw new Error('INVALID_RATIO_MAX');}if(cap===null){cap=Math.max(0,mx);}
      lo=Math.min(0,mn<0?lo:0);hi=Math.max(cap,mx>cap?hi:cap);refs=[0,cap];
      if(finite(o.reference)){refs.push(o.reference);lo=Math.min(lo,o.reference);hi=Math.max(hi,o.reference);}
    }
    if(finite(o.reference)&&c!=='ratio'){refs.push(o.reference);lo=Math.min(lo,o.reference);hi=Math.max(hi,o.reference);}
    if(hi<=lo){hi=lo+.02;}width=hi-lo;exp=Math.floor(Math.log(width/4)/Math.LN10);
    for(e=exp-2;e<exp+4;e+=1){
      for(m=0;m<4;m+=1){
        mult=m===2?25:[1,2,2.5,5][m];decExp=m===2?e-1:e;step=Number(mult+'e'+decExp);li=Math.floor(lo/step+1e-10);hiidx=Math.ceil(hi/step-1e-10);
        if(c==='symmetric'){hiidx=Math.max(Math.abs(li),Math.abs(hiidx),2);li=-hiidx;}
        while(hiidx-li+1<4){
          if(c==='zero_anchored'&&mn>=0){hiidx+=1;}
          else if(c==='zero_anchored'&&mx<=0){li-=1;}
          else if(lo-li*step<=hiidx*step-hi){li-=1;}else{hiidx+=1;}
        }
        n=hiidx-li+1;
        if(n>=4&&n<=6){score=Math.abs(n-5)+((hiidx-li)*step-width)/width;cands.push([score,step,li,hiidx,mult,decExp]);}
      }
    }
    if(!cands.length){throw new Error('NO_NICE_SCALE');}
    cands.sort(function(a,b){return a[0]-b[0]||a[1]-b[1]||a[2]-b[2]||a[3]-b[3];});
    step=cands[0][1];li=cands[0][2];hiidx=cands[0][3];mult=cands[0][4];decExp=cands[0][5];for(i=0;i<=hiidx-li;i+=1){ticks.push(Number(((li+i)*mult)+'e'+decExp));}
    magnitude=Math.max(Math.abs(ticks[0]),Math.abs(ticks[ticks.length-1]));
    units=o.locale==='ko'?[[1e12,'조'],[1e8,'억'],[1e4,'만']]:[[1e12,'T'],[1e9,'B'],[1e6,'M'],[1e3,'K']];
    for(i=0;i<units.length;i+=1){if(magnitude>=units[i][0]){divisor=units[i][0];suffix=units[i][1];break;}}
    if(magnitude>0&&magnitude<1e-6){var sci=Math.floor(Math.log(magnitude)/Math.LN10);divisor=Number('1e'+sci);suffix='e'+sci;}ss=step/divisor;decimals=Math.max(0,Math.min(12,Math.ceil(-Math.log(ss)/Math.LN10)));while(decimals<12&&Math.abs(ss*Math.pow(10,decimals)-Math.floor(ss*Math.pow(10,decimals)+.5))>1e-7){decimals+=1;}
    if(a.length>=100){q1=quantile(a,.01);q99=quantile(a,.99);core=q99-q1;
      if((core>0&&Math.max(q1-mn,mx-q99)>3*core)||(core===0&&(mn<q1||mx>q99))){hint={suggested_min:clean(q1),suggested_max:clean(q99),below:a.filter(function(x){return x<q1;}).length,above:a.filter(function(x){return x>q99;}).length,applied:false,marker:'triangle+value',reason:'1% 꼬리가 중앙 98% 폭의 3배 초과; 사용자 선택 전 전체 범위 유지'};}
    }
    refs=refs.sort(function(a,b){return a-b;}).filter(function(x,i,a){return i===0||x!==a[i-1];});
    result={status:'ok',scale_class:c,min:ticks[0],max:ticks[ticks.length-1],step:clean(step),ticks:ticks,decimals:decimals,suffix:suffix,divisor:divisor,axis_note:'',clip_hint:hint,near_flat:near,log_candidate:log,references:refs,warnings:warnings};result.axis_note=axisNote(result);return result;
  }
  function legendPlan(series){
    var names={actual:'실적',reported:'실적',derived:'산출',calculated:'산출',forecast:'전망(est)',est:'전망(est)',estimate:'전망(est)',unknown:'NOT FOUND','NOT FOUND':'NOT FOUND'},n=series.length;
    return {placement:n<=3?'inline':(n<=8?'bottom_wrap':'scroll_group'),labels:series.map(function(s,i){var role=s.role||s.status||'unknown',idx=s.metric_index===undefined?i:s.metric_index;return {label:(s.label||s.name||('계열 '+(i+1)))+' ['+(s.unit||'단위 미확인')+' · '+(names[role]||'NOT FOUND')+']',palette_index:idx%8,marker_index:(idx+Math.floor(idx/8))%4,role:role};}),max_visible:8,min_distinguishers:2};
  }
  function axisPlan(series){
    var units=[],mapping=[],i,u;
    for(i=0;i<series.length;i+=1){u=series[i].unit||'단위 미확인';if(units.indexOf(u)<0){units.push(u);}mapping.push(units.indexOf(u)===0?'y':'y'+(units.indexOf(u)+1));}
    return {status:units.length>2?'SEPARATE_PANELS_REQUIRED':'ok',units:units,dataset_axes:mapping,zero_alignment:'both_zero_anchored_only',grid_primary_only:true};
  }
  function alignZero(ranges){
    var keys=Object.keys(ranges),negative=false,positive=false,out={};
    keys.forEach(function(k){out[k]=ranges[k];if(ranges[k].status==='ok'){negative=negative||ranges[k].min<0;positive=positive||ranges[k].max>0;}});
    if(keys.length<2||!negative||!positive||!keys.every(function(k){return ranges[k].status==='ok'&&ranges[k].scale_class==='zero_anchored';})){return out;}
    keys.forEach(function(k){var r=ranges[k],m=Math.max(Math.abs(r.min),Math.abs(r.max)),a=niceScale([-m,m],{'class':'symmetric'});a.scale_class='zero_anchored';a.zero_alignment='center';out[k]=a;});return out;
  }
  function dataValue(p){if(Array.isArray(p)){return finite(p[1])?p[1]:null;}if(p&&typeof p==='object'){if(p.status==='NOT FOUND'||p.status==='unknown'){return null;}return finite(p.y)?p.y:(finite(p.value)?p.value:null);}return finite(p)?p:null;}
  var vizScalePlugin={
    id:'vizScale',
    beforeUpdate:function(chart,args,pluginOptions){
      var op=(chart.config&&chart.config.options)||chart.options||{},cfg=pluginOptions||{},scales=op.scales||{},axes=cfg.axes||{},datasets=chart.data.datasets||[],keys=Object.keys(scales),results={},idx;
      if(cfg.enabled===false){return;}
      if(!keys.length){scales.y={};op.scales=scales;keys=['y'];}
      keys.forEach(function(key){
        var axis=scales[key],horizontal=op.indexAxis==='y',isValue=axis.axis?(axis.axis===(horizontal?'x':'y')):(horizontal?key.charAt(0)==='x':key.charAt(0)==='y'),vals=[],meta=copy(axes[key]||cfg),stacks={},hasBar=false;
        if(!isValue&&!axes[key]){return;}
        datasets.forEach(function(ds,di){
          var axisId=key.charAt(0)==='x'?(ds.xAxisID||'x'):(ds.yAxisID||'y'),typ=ds.type||chart.config.type,arr=ds.data||[];
          if(axisId!==key||(chart.isDatasetVisible&&!chart.isDatasetVisible(di))){return;}
          if(typ==='bar'){hasBar=true;}
          arr.forEach(function(p,i){var v=key.charAt(0)==='x'?(Array.isArray(p)?p[0]:(p&&typeof p==='object'&&finite(p.x)?p.x:dataValue(p))):dataValue(p);if(v===null){return;}vals.push(v);if(axis.stacked){var pointKey=(Array.isArray(p)?p[0]:(p&&typeof p==='object'?(horizontal?p.y:p.x):undefined));var group=(ds.stack||'default')+':'+(pointKey===undefined?i:typeof pointKey+':'+pointKey);if(!stacks[group]){stacks[group]=[0,0];}stacks[group][v<0?0:1]+=v;}});
        });
        Object.keys(stacks).forEach(function(k){vals.push(stacks[k][0],stacks[k][1]);});
        if(axis.stacked){meta.stacked=true;}if(hasBar){meta.type='bar';}
        var r=niceScale(vals,meta);results[key]=r;if(r.status!=='ok'){return;}
        axis.type='linear';axis.min=r.min;axis.max=r.max;axis.beginAtZero=r.scale_class==='zero_anchored';if(!axis.ticks){axis.ticks={};}axis.ticks.stepSize=r.step;axis.ticks.maxTicksLimit=6;axis.ticks.autoSkip=false;
        if(!axis.ticks.callback){axis.ticks.callback=function(v){return (v/r.divisor).toFixed(r.decimals)+r.suffix;};}
        if(!axis.title){axis.title={};}if(meta.unit){axis.title.display=true;axis.title.text=meta.unit;}
        if(root.VIZ_CONTRACT){var theme=root.VizSeries&&root.VizSeries.readTheme?root.VizSeries.readTheme():'light';axis.ticks.color=root.VIZ_CONTRACT.tokens.text[theme];axis.title.color=root.VIZ_CONTRACT.tokens.text[theme];}
        if(!axis.grid){axis.grid={};}axis.grid.drawOnChartArea=key===keys.filter(function(k){return k.charAt(0)===(horizontal?'x':'y');})[0];
      });
      results=alignZero(results);Object.keys(results).forEach(function(k){var r=results[k];if(r.zero_alignment){scales[k].min=r.min;scales[k].max=r.max;scales[k].ticks.stepSize=r.step;}});chart.$vizScales=results;
      if(root.VizSeries&&root.VizSeries.styleDatasets){root.VizSeries.styleDatasets(chart);}
      if(chart.options&&chart.options.plugins&&chart.options.plugins.legend){chart.options.plugins.legend.display=false;}
      if(chart.legend&&chart.legend.options){chart.legend.options.display=false;}
    },
    afterDataLimits:function(chart,args){var scale=args.scale,r=(chart.$vizScales||{})[scale.id];if(r&&r.status==='ok'){scale.min=r.min;scale.max=r.max;}},
    afterBuildTicks:function(chart,args){var scale=args.scale,r=(chart.$vizScales||{})[scale.id];if(r&&r.status==='ok'){scale.ticks=r.ticks.map(function(v){return {value:v};});}},
    afterUpdate:function(chart){if(root.VizSeries&&root.VizSeries.renderUnitPanels&&root.VizSeries.renderUnitPanels(chart)){return;}if(root.VizSeries&&root.VizSeries.renderLegend){root.VizSeries.renderLegend(chart);}},
    afterDestroy:function(chart){var e=chart.$vizLegendElement;if(e&&e.parentNode){e.parentNode.removeChild(e);}if(root.VizSeries&&root.VizSeries.clearUnitPanels){root.VizSeries.clearUnitPanels(chart);}},
    afterDraw:function(chart){
      var ctx=chart.ctx,area=chart.chartArea;if(!ctx||!area){return;}ctx.save();ctx.fillStyle=root.VizSeries&&root.VizSeries.readTheme&&root.VizSeries.readTheme()==='light'?'#202735':'#e9eef5';ctx.font='11px sans-serif';
      var notes=[];Object.keys(chart.$vizScales||{}).forEach(function(k){var r=chart.$vizScales[k],s=chart.scales[k];if(r.axis_note){notes.push(k+': '+r.axis_note);}if(s&&s.getPixelForValue){r.references.forEach(function(v){var pos=s.getPixelForValue(v),isX=s.axis==='x';if(pos>=(isX?area.left:area.top)&&pos<=(isX?area.right:area.bottom)){ctx.beginPath();ctx.setLineDash([2,3]);ctx.strokeStyle='#818994';if(isX){ctx.moveTo(pos,area.top);ctx.lineTo(pos,area.bottom);}else{ctx.moveTo(area.left,pos);ctx.lineTo(area.right,pos);}ctx.stroke();}});}});
      if(notes.length){ctx.setLineDash([]);ctx.fillText(notes.join(' / '),area.left+5,area.bottom-5);}
      ctx.restore();if(root.VizSeries&&root.VizSeries.drawForecastDividers){root.VizSeries.drawForecastDividers(chart);}
    }
  };
  var api={niceScale:niceScale,classifySeries:classifySeries,legendPlan:legendPlan,axisNote:axisNote,axisPlan:axisPlan,alignZero:alignZero,dataValue:dataValue,vizScalePlugin:vizScalePlugin};
  root.VizScale=api;if(typeof module!=='undefined'&&module.exports){module.exports=api;}
  if(root.Chart&&root.Chart.register){root.Chart.register(vizScalePlugin);}
}(typeof window!=='undefined'?window:(typeof global!=='undefined'?global:this)));

}
}());
/* W01_VIZ_PHALANX_HELPERS_v1: 명시된 축 의미만 사용. 단위/상태 미확인은 표기. */
function vizPhalanxTheme(){return window.document&&document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';}
function vizPhalanxConfig(config,id,context){
  context=context||{};
  var op=config.options||(config.options={}), scales=op.scales||(op.scales={}), ds=(config.data||{}).datasets||[];
  var axes={}, role='actual', unit='단위 미확인';
  function axis(key,cl,u,extra){axes[key]={class:cl,unit:u||'단위 미확인'};if(extra)Object.keys(extra).forEach(function(k){axes[key][k]=extra[k];});}
  function hasBar(key){return ds.some(function(d){return (d.yAxisID||'y')===key&&(d.type||config.type)==='bar';});}
  function generic(){Object.keys(scales).forEach(function(k){if(k.charAt(0)==='y')axis(k,scales[k].stacked||hasBar(k)?'zero_anchored':'range_focus',unit);});}
  if(id==='company_month'){axis('y','zero_anchored','표시통화');axis('y1','symmetric','비율 (1=100%)');}
  else if(id==='company_yoy_year'){axis('y','symmetric','비율 (1=100%)');role='derived';}
  else if(id==='detail_port'){
    axis('yV',scales.yV&&scales.yV.stacked||hasBar('yV')?'zero_anchored':'range_focus','표시통화');
    axis('yW',hasBar('yW')?'zero_anchored':'range_focus','kg');axis('yU','range_focus','표시통화/kg');axis('yP','symmetric','비율 (1=100%)');
  }
  else if(id==='pc_fin'||id==='kr_fin'){
    ds.forEach(function(d){d.yAxisID='y';d.label=(d.label||'').replace('(우)','');});delete scales.y2;axis('y','zero_anchored','기업 보고통화·동일단위');
  }
  else if(id==='pc_backlog'||id==='kr_backlog'){axis('y','zero_anchored','기업 보고통화');axis('y2','ratio','배',{ratioMax:null,reference:1});}
  else if(id==='pc_util'||id==='kr_util'){axis('y','zero_anchored','보고 생산단위');axis('y2','ratio','%',{ratioMax:100,reference:100});}
  else if(id==='pc_asp'||id==='kr_asp'||id==='platform_compare'){axis('y','range_focus','기준=100');role='derived';}
  else if(id==='pc_product'||id==='kr_product'){axis('y','zero_anchored','기업 보고통화');}
  else if(id==='pc_global'){axis('y','zero_anchored','기업 보고통화');axis('y2','range_focus','프록시 원단위');}
  else if(id==='pc_segments'){axis('y','zero_anchored','기업 보고통화');axis('y2','ratio','%',{ratioMax:100});}
  else if(id==='pc_ebitda'){axis('y','zero_anchored','EUR M');axis('y2','ratio','%',{ratioMax:null,reference:0});}
  else if(id==='ppi'){axis('y',ST.ppiMode==='level'?'range_focus':'symmetric',ST.ppiMode==='level'?'지수':'%');role=ST.ppiMode==='level'?'actual':'derived';}
  else if(id==='country_hero'||id==='country_card'){
    var cm=ST.cmetric||'value', key=id==='country_hero'?'yV':'y';
    axis(key,cm==='yoy'?'symmetric':cm==='unit'?'range_focus':'zero_anchored',cm==='share'||cm==='yoy'?'비율 (1=100%)':cm==='unit'?'표시통화/kg':'표시통화');
    if(cm==='share'){axes[key].reference=1;} role=cm==='value'?'actual':'derived';
  }
  else if(id==='nowcast_scatter'){axis('x','ratio','R²',{ratioMax:1});axis('y','symmetric','YoY %');role='forecast';}
  else if(id.indexOf('dc_')===0){axis('y','zero_anchored',id==='dc_tam'?'USD B':id==='dc_grid_net'||id==='dc_grid_status'||id==='dc_grid_tech'?'화면 선택 MW/GW':'MW');role=id==='dc_grid_net'?'derived':'forecast';}
  else{generic();if(id==='preview'||id==='game_generic'||id==='kpi_generic'||id==='platform_single')role='unknown';}
  if(id==='platform_multi'){role='forecast';axis('y','range_focus','億G · 제3자 추정');}
  if(id==='platform_single'&&context.kind==='gi'){role='forecast';axis('y','range_focus','億G · 제3자 추정');}
  if(id==='game_generic'&&(context.canvas==='gPcbangAll'||/^pcbang_share_/.test(context.source||''))){role='derived';axis('y',scales.y.stacked?'zero_anchored':'ratio','%',{ratioMax:100});}
  if(id==='game_generic'&&(context.canvas==='gDmmAll'||/^dmm_rev_/.test(context.source||''))){role='forecast';axis('y','range_focus','億 · 제3자 추정');}
  ds.forEach(function(d,i){
    var label=d.label||'',key=d.yAxisID||'y';if(role!=='unknown')d.vizRole=d.vizRole||role;else d.vizProvenance='NOT FOUND: 상태 메타 미제공';d.vizUnit=d.vizUnit||((axes[key]||{}).unit)||unit;
    if(/YoY|MoM|잔고÷|프록시|비중|마진/.test(label))d.vizRole='derived';
    if(/잠정|(?:^|\s)est(?:\s|$)|전망|예측/.test(label))d.vizRole='forecast';
    if(id==='company_month'&&(label==='Revenue'||label==='잠정')){d.vizMetric='Revenue';d.metric_index=0;}
    if(id==='dc_energy'){d.vizRole=/ est$/.test(label)?'forecast':'actual';d.vizMetric=label.replace(/ (확정|est)$/,'');d.metric_index=Math.floor(i/2);}
    if(id==='preview'){delete d.vizRole;if(/%/.test(label)){axes[key]={class:'ratio',unit:'%',ratioMax:null,reference:0};}}
    d.spanGaps=false;
  });
  op.plugins=op.plugins||{};op.plugins.vizScale=Object.assign({},op.plugins.vizScale||{},{axes:axes,surface:id,forecastDivider:['nowcast_scatter','platform_multi','platform_single','game_generic'].indexOf(id)<0});
  return config;
}
function vizPhalanxSpark(values,w,h,color,opts){
  opts=opts||{};var rg=VizScale.niceScale(values,{class:opts.class||'range_focus',unit:opts.unit||'',ratioMax:opts.ratioMax,reference:opts.reference});
  if(rg.status!=='ok')return '<span>NOT FOUND</span>';
  var st=window.VizSeries?VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),color:color,metric_index:opts.metric_index||0},opts.role||'actual'):{};
  var col=st.borderColor||color, width=st.borderWidth||1.8, dash=(st.borderDash||[]).join(' '),path='',pen=false;
  values.forEach(function(v,i){if(typeof v!=='number'||!isFinite(v)){pen=false;return;}var x=2+i/Math.max(1,values.length-1)*(w-4),y=2+(h-4)*(1-(v-rg.min)/(rg.max-rg.min));path+=(pen?'L':'M')+x.toFixed(2)+' '+y.toFixed(2)+' ';pen=true;});
  var note=rg.axis_note?'<span style="display:block;font-size:9px;color:var(--ink,#e6edf3)">'+rg.axis_note+'</span>':'';
  return '<svg role="img" aria-label="'+(opts.role==='derived'?'산출':'실적')+' '+(opts.unit||'단위 미확인')+'" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" data-viz-min="'+rg.min+'" data-viz-max="'+rg.max+'" data-viz-ticks="'+rg.ticks.join(',')+'"><title>범위 '+rg.min+' ~ '+rg.max+'; 눈금 '+rg.ticks.join(', ')+'</title><path d="'+path+'" fill="none" stroke="'+col+'" stroke-width="'+width+'"'+(dash?' stroke-dasharray="'+dash+'"':'')+'/></svg>'+note;
}
function vizPhalanxSvgMarker(x,y,st,r){
  r=r||2.8;var col=st.borderColor,fill=st.hollow?(vizPhalanxTheme()==='light'?'#ffffff':'#0b111b'):col,attrs=' fill="'+fill+'" stroke="'+col+'" stroke-width="'+(st.pointBorderWidth||1.5)+'"';
  if(st.pointStyle==='rect')return '<rect x="'+(x-r)+'" y="'+(y-r)+'" width="'+(2*r)+'" height="'+(2*r)+'"'+attrs+'/>';
  if(st.pointStyle==='triangle')return '<path d="M'+x+' '+(y-r)+' L'+(x+r)+' '+(y+r)+' L'+(x-r)+' '+(y+r)+' Z"'+attrs+'/>';
  if(st.pointStyle==='rectRot')return '<path d="M'+x+' '+(y-r)+' L'+(x+r)+' '+y+' L'+x+' '+(y+r)+' L'+(x-r)+' '+y+' Z"'+attrs+'/>';
  return '<circle cx="'+x+'" cy="'+y+'" r="'+r+'"'+attrs+'/>';
}
function vizPhalanxLegend(series){
  function e(x){return String(x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  var plan=VizScale.legendPlan(series),html='<div data-viz-legend="'+plan.placement+'" style="display:flex;gap:8px;padding:5px 0;font-size:11px;color:var(--ink,#e9eef5);'+(plan.placement==='scroll_group'?'overflow-x:auto;flex-wrap:nowrap':'flex-wrap:wrap')+'">';
  series.forEach(function(s,i){var st=VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),metric_index:i},s.role||'actual');html+='<span style="display:inline-flex;align-items:center;gap:4px;white-space:nowrap"><svg width="12" height="12" aria-hidden="true">'+vizPhalanxSvgMarker(6,6,st,3)+'</svg>'+e(plan.labels[i].label)+'</span>';});return html+'</div>';
}

/* W01_VIZ_STANDALONE_END */
/* argus_charts.js — ARGUS 대시보드 렌더러 (의존성 0, 순수 SVG, IIFE)
 * 전역: window.renderARGUS(el, data)   data = data/argus_data.js 의 window.ARGUS
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 섹션: ①체인 스코어보드 ②사냥 시그널 ③스프레드 차트 ④태양광 밸류체인 ⑤유가 데크
 */
(function () {
  'use strict';

  var DIM = '#8a93a3', ACC = '#2bc0d4', UP = '#59d0a8', DOWN = '#ff5e6c', WARN = '#f6c85f';
  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var PAL = ['#4ea1ff', '#59d0a8', '#f6c85f', '#e07a5f', '#b892ff', '#2bc0d4', '#ff8a3d', '#7ec8e3', '#ff6b9d', '#9ccc65'];

  var CSS = [
    '.ag-wrap{display:flex;flex-direction:column;gap:20px}',
    /* 히어로 */
    '.ag-hero{position:relative;overflow:hidden;background:linear-gradient(135deg,rgba(43,192,212,.13),rgba(78,161,255,.06) 45%,rgba(89,208,168,.09));border:1px solid rgba(43,192,212,.3);border-radius:16px;padding:18px 22px}',
    '.ag-hero h2{font-size:19px;font-weight:850;letter-spacing:-.02em}',
    '.ag-hero .sub{font-size:12px;color:' + DIM + ';margin-top:5px;line-height:1.65}',
    '.ag-hero .sub b{color:var(--ink,#e6edf3)}',
    /* 내비 */
    '.ag-nav{position:sticky;top:46px;z-index:12;display:flex;gap:6px;flex-wrap:wrap;background:rgba(10,14,20,.9);backdrop-filter:blur(8px);padding:8px 2px;border-bottom:1px solid var(--line,#1f2937);margin:0 -2px}',
    '.ag-nav a{font-size:11.5px;font-weight:650;color:' + DIM + ';text-decoration:none;padding:4px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;transition:.12s;white-space:nowrap}',
    '.ag-nav a:hover{color:' + ACC + ';border-color:rgba(43,192,212,.5)}',
    '.ag-nav a:focus-visible,.ag-chip:focus-visible,summary:focus-visible,.ag-plot:focus-visible{outline:3px solid ' + ACC + ';outline-offset:3px}',
    /* KPI */
    '.ag-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}',
    '@media(max-width:980px){.ag-kpis{grid-template-columns:repeat(3,1fr)}}',
    '@media(max-width:620px){.ag-kpis{grid-template-columns:repeat(2,1fr)}}',
    '.ag-kpi{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:11px 14px;min-width:0;position:relative;overflow:hidden}',
    '.ag-kpi:after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--kc,' + ACC + ')}',
    '.ag-kpi .lab{font-size:10.5px;color:' + DIM + ';font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.ag-kpi .val{font-family:' + MONO + ';font-size:19px;font-weight:800;margin-top:3px;letter-spacing:-.02em}',
    '.ag-kpi .sub{font-size:10.5px;color:' + DIM + ';margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    /* 섹션 */
    '.ag-sec{scroll-margin-top:96px}',
    '.ag-sech{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap}',
    '.ag-sech h3{font-size:15px;font-weight:800;margin:0;letter-spacing:-.01em}',
    '.ag-sech .hint{font-size:11px;color:' + DIM + '}',
    '.ag-sech .sp{flex:1}',
    '.ag-card{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:14px;padding:15px 17px;min-width:0}',
    /* 체인 스코어보드 */
    '.ag-chains{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}',
    '.ag-chain{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:14px;padding:13px 15px;min-width:0}',
    '.ag-chain .top{display:flex;align-items:center;gap:12px}',
    '.ag-chain .lb{font-size:13px;font-weight:750}',
    '.ag-chain .nn{font-size:10px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-gauge{flex:0 0 92px}',
    '.ag-momrow{display:flex;gap:5px;margin-top:10px}',
    '.ag-mom{flex:1;border-radius:7px;padding:4px 2px;text-align:center;min-width:0}',
    '.ag-mom .h{font-size:8.5px;color:' + DIM + ';letter-spacing:.05em}',
    '.ag-mom .v{font-family:' + MONO + ';font-size:10.5px;font-weight:750;margin-top:1px}',
    '.ag-hbadges{display:flex;gap:5px;margin-top:9px;flex-wrap:wrap;min-height:18px}',
    '.ag-hb{font-size:9.5px;font-weight:800;border-radius:999px;padding:2px 8px;letter-spacing:.03em}',
    '.ag-hb.bt{color:' + UP + ';border:1px solid rgba(89,208,168,.45)}',
    '.ag-hb.pw{color:' + DOWN + ';border:1px solid rgba(255,94,108,.45)}',
    '.ag-hb.ac{color:' + WARN + ';border:1px solid rgba(246,200,95,.45)}',
    '.ag-stocks{display:flex;gap:4px;flex-wrap:wrap;margin-top:9px}',
    '.ag-stk{font-size:10px;color:' + DIM + ';border:1px solid var(--line,#1f2937);border-radius:999px;padding:2px 8px;cursor:default}',
    '.ag-stk b{color:var(--ink,#e6edf3);font-weight:650}',
    '.ag-members{margin-top:9px;border-top:1px solid rgba(31,41,55,.65);padding-top:7px}',
    '.ag-members summary{cursor:pointer;color:' + DIM + ';font-size:10.5px;border-radius:4px}',
    '.ag-member{display:grid;grid-template-columns:minmax(100px,1fr) auto;gap:3px 8px;padding:6px 0;border-bottom:1px solid rgba(31,41,55,.4);font-size:10px;color:' + DIM + '}',
    '.ag-member b{color:var(--ink,#e6edf3);font-weight:650}',
    /* 데이터 건강 */
    '.ag-health{display:grid;grid-template-columns:repeat(4,minmax(110px,1fr));gap:10px}',
    '@media(max-width:700px){.ag-health{grid-template-columns:repeat(2,1fr)}}',
    '.ag-health .metric{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:10px;padding:10px 12px}',
    '.ag-health .metric b{display:block;font-family:' + MONO + ';font-size:19px;margin-top:2px}',
    '.ag-health .metric span{font-size:10px;color:' + DIM + '}',
    '.ag-health-lists{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}',
    '@media(max-width:800px){.ag-health-lists{grid-template-columns:1fr}}',
    '.ag-health details{border:1px solid var(--line,#1f2937);border-radius:10px;padding:8px 10px}',
    '.ag-health details summary{cursor:pointer;font-size:11px;font-weight:700}',
    '.ag-quality-list{margin:7px 0 0 17px;color:' + DIM + ';font-size:10.5px;line-height:1.7}',
    /* 테이블 */
    '.ag-scroll{overflow-x:auto}',
    '.ag-tbl{width:100%;border-collapse:collapse;font-size:12.5px;min-width:760px}',
    '.ag-tbl th{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:' + DIM + ';font-weight:700;text-align:right;padding:7px 10px;border-bottom:1px solid var(--line,#1f2937);white-space:nowrap}',
    '.ag-tbl th.l,.ag-tbl td.l{text-align:left}',
    '.ag-tbl td{padding:7px 10px;border-bottom:1px solid rgba(31,41,55,.55);text-align:right;font-family:' + MONO + ';font-size:12px;white-space:nowrap}',
    '.ag-tbl tr:hover td{background:rgba(43,192,212,.05)}',
    '.ag-tbl td.nm{font-family:inherit;font-weight:700;font-size:12.5px}',
    '.ag-tbl td.nm .c{font-size:10px;color:' + DIM + ';font-weight:500;margin-left:6px}',
    '.ag-posbar{position:relative;width:76px;height:8px;background:rgba(31,41,55,.6);border-radius:4px;display:inline-block;vertical-align:middle;margin-right:7px}',
    '.ag-posbar i{position:absolute;top:-2px;width:4px;height:12px;border-radius:2px}',
    '.ag-empty{font-size:11.5px;color:' + DIM + ';padding:12px 0}',
    /* 칩 */
    '.ag-chips{display:flex;gap:6px;flex-wrap:wrap}',
    '.ag-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 11px;border:1px solid var(--line,#1f2937);border-radius:999px;background:transparent;color:' + DIM + ';cursor:pointer;transition:.12s}',
    '.ag-chip:hover{border-color:rgba(43,192,212,.5);color:' + ACC + '}',
    '.ag-chip.on{background:rgba(43,192,212,.14);color:' + ACC + ';border-color:rgba(43,192,212,.45);font-weight:700}',
    /* 차트 그리드 */
    '.ag-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}',
    '.ag-ccard{background:var(--panel,#111721);border:1px solid var(--line,#1f2937);border-radius:13px;padding:11px 13px;min-width:0}',
    '.ag-ccard .h{display:flex;align-items:baseline;gap:7px;flex-wrap:wrap;margin-bottom:5px}',
    '.ag-ccard .t{font-size:12px;font-weight:750;line-height:1.3}',
    '.ag-ccard .u{font-size:9.5px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-ccard .lv{margin-left:auto;font-family:' + MONO + ';font-size:12px;font-weight:800}',
    '.ag-badge{font-size:9px;font-weight:800;border-radius:999px;padding:1px 7px}',
    '.ag-more{text-align:center;margin-top:12px}',
    /* 플롯 공통 */
    '.ag-plot{position:relative}',
    '.ag-plot[tabindex]{border-radius:8px}',
    '.ag-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.ag-tip{position:absolute;pointer-events:none;opacity:0;background:rgba(8,11,17,.94);border:1px solid var(--line,#1f2937);border-radius:8px;padding:6px 9px;font-family:' + MONO + ';font-size:10.5px;line-height:1.7;color:#e6edf3;white-space:nowrap;z-index:4;transition:opacity .1s;transform:translate(-50%,0)}',
    '.ag-plot.on .ag-tip{opacity:1}',
    '.ag-chart-summary{font-size:10px;color:' + DIM + ';line-height:1.5;margin-top:4px}',
    '.ag-data{margin-top:6px;border-top:1px solid rgba(31,41,55,.6);padding-top:5px}',
    '.ag-data summary{cursor:pointer;color:' + DIM + ';font-size:10px;border-radius:4px;width:max-content;max-width:100%}',
    '.ag-data .ag-scroll{max-height:320px;margin-top:6px}',
    '.ag-data .ag-tbl{min-width:520px;font-size:10px}',
    '.ag-data .ag-tbl caption{text-align:left;color:' + DIM + ';padding:4px 0;font-size:10px}',
    '.ag-progress{width:92px;height:8px;accent-color:' + ACC + ';vertical-align:middle}',
    '.ag-load{font-size:11px;color:' + DIM + ';padding:14px 0}',
    '.ag-meta{font-size:10px;color:' + DIM + ';line-height:1.55;white-space:normal;min-width:210px}',
    '.ag-status{display:inline-block;border:1px solid var(--line,#1f2937);border-radius:999px;padding:1px 6px;font-size:9px;font-weight:750}',
    '.ag-status.low{color:' + WARN + ';border-color:rgba(246,200,95,.45)}',
    '.ag-lgd{display:flex;gap:5px 12px;flex-wrap:wrap;margin-top:8px}',
    '.ag-lgd span{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;color:' + DIM + '}',
    '.ag-lgd i{width:9px;height:9px;border-radius:3px;flex:0 0 auto}',
    /* 태양광 플로우 */
    '.ag-flow{display:flex;align-items:stretch;gap:0;flex-wrap:wrap}',
    '.ag-stage{flex:1 1 170px;background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:12px;padding:11px 13px;min-width:150px}',
    '.ag-stage .sn{font-size:10px;color:' + ACC + ';font-weight:800;letter-spacing:.09em}',
    '.ag-stage .pn{font-size:11.5px;font-weight:700;margin-top:2px;line-height:1.3}',
    '.ag-stage .pv{font-family:' + MONO + ';font-size:17px;font-weight:800;margin-top:5px}',
    '.ag-stage .pu{font-size:9.5px;color:' + DIM + ';font-family:' + MONO + '}',
    '.ag-stage .pm{font-family:' + MONO + ';font-size:10.5px;margin-top:3px}',
    '.ag-arrow{flex:0 0 26px;display:flex;align-items:center;justify-content:center;color:' + DIM + ';font-size:15px}',
    '@media(max-width:700px){.ag-flow{flex-direction:column}.ag-arrow{transform:rotate(90deg);flex-basis:20px}}',
    '.ag-grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media(max-width:980px){.ag-grid2{grid-template-columns:1fr}}',
    /* 유가 KPI */
    '.ag-oilkpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}',
    '.ag-oilk{background:var(--panel2,#0d131c);border:1px solid var(--line,#1f2937);border-radius:11px;padding:9px 14px;min-width:120px}',
    '.ag-oilk .l{font-size:10.5px;color:' + DIM + ';font-weight:650}',
    '.ag-oilk .v{font-family:' + MONO + ';font-size:16px;font-weight:800;margin-top:2px}',
    '.ag-oilk .w{font-family:' + MONO + ';font-size:10.5px;margin-top:1px}',
    '.ag-foot{font-size:10.5px;color:' + DIM + ';line-height:1.7;border-top:1px solid var(--line,#1f2937);padding-top:12px}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('agChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'agChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ───────── helpers ───────── */
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fin(v) { return v != null && isFinite(v); }
  function fmt(v) {
    if (!fin(v)) return '—';
    var a = Math.abs(v);
    if (a >= 1000) return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    if (a >= 100) return v.toFixed(1);
    if (a >= 1) return v.toFixed(2);
    return v.toFixed(3);
  }
  function fmtPct(v, dp) {
    if (!fin(v)) return '<span style="color:' + DIM + '">—</span>';
    var c = v >= 0 ? UP : DOWN, s = v >= 0 ? '↑ +' : '↓ −';
    return '<span style="color:' + c + ';font-weight:700">' + s + Math.abs(v).toFixed(dp == null ? 1 : dp) + '%</span>';
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function hex2rgb(h) { var n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
  function mix(c1, c2, t) {
    var a = hex2rgb(c1), b = hex2rgb(c2);
    return 'rgb(' + Math.round(lerp(a[0], b[0], t)) + ',' + Math.round(lerp(a[1], b[1], t)) + ',' + Math.round(lerp(a[2], b[2], t)) + ')';
  }
  function posColor(p) {
    if (!fin(p)) return DIM;
    return p <= 50 ? mix(UP, WARN, p / 50) : mix(WARN, DOWN, (p - 50) / 50);
  }
  function momCell(lab, v) {
    var bg = 'rgba(31,41,55,.4)', col = DIM;
    if (fin(v)) {
      var t = Math.min(1, Math.abs(v) / 8);
      bg = v >= 0 ? 'rgba(89,208,168,' + (0.08 + 0.3 * t).toFixed(2) + ')' : 'rgba(255,94,108,' + (0.08 + 0.3 * t).toFixed(2) + ')';
      col = v >= 0 ? UP : DOWN;
    }
    return '<div class="ag-mom" style="background:' + bg + '"><div class="h">' + lab + '</div><div class="v" style="color:' + col + '">' +
      (fin(v) ? (v >= 0 ? '↑ +' : '↓ −') + Math.abs(v).toFixed(1) : '—') + '</div></div>';
  }
  function huntBadges(hunt) {
    var M = { bottom_turn: ['bt', '🎯 바닥반등'], peak_warn: ['pw', '⚠ 고점경계'], accel: ['ac', '⤴ 가속'] };
    return (hunt || []).map(function (h) { var m = M[h]; return m ? '<span class="ag-hb ' + m[0] + '">' + m[1] + '</span>' : ''; }).join('');
  }
  function stockChips(stocks) {
    return (stocks || []).map(function (s) {
      return '<span class="ag-stk" title="' + esc(s.note || '') + '"><b>' + esc(s.n) + '</b> ' + esc(s.t || '') + '</span>';
    }).join('');
  }
  function spark(v,w,h,color){return vizPhalanxSpark(v,w||90,h||24,color||ACC,{class:'range_focus',role:'actual'});}
  function gauge(pos) {
    var W = 92, H = 58, cx = 46, cy = 50, r = 38;
    function pt(frac) { var th = Math.PI * (1 - frac); return [cx + r * Math.cos(th), cy - r * Math.sin(th)]; }
    var col = posColor(pos), f = fin(pos) ? pos / 100 : 0;
    var a = pt(0), b = pt(f);
    var arc = fin(pos) && pos > 0.5
      ? '<path d="M' + a[0].toFixed(1) + ' ' + a[1].toFixed(1) + ' A' + r + ' ' + r + ' 0 ' + (f > 0.5 ? 1 : 0) + ' 1 ' + b[0].toFixed(1) + ' ' + b[1].toFixed(1) + '" fill="none" stroke="' + col + '" stroke-width="7" stroke-linecap="round"/>' : '';
    var e = pt(1);
    var summary = fin(pos) ? '사이클 위치 ' + Math.round(pos) + ' 퍼센타일' : '사이클 위치 데이터 없음';
    return '<svg class="ag-gauge" role="img" aria-label="' + esc(summary) + '" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '"><title>' + esc(summary) + '</title><desc>0은 역사적 저점, 100은 역사적 고점입니다.</desc>' +
      '<path d="M' + a[0] + ' ' + a[1] + ' A' + r + ' ' + r + ' 0 0 1 ' + e[0] + ' ' + e[1] + '" fill="none" stroke="rgba(31,41,55,.8)" stroke-width="7" stroke-linecap="round"/>' + arc +
      '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="17" font-weight="800" fill="' + col + '" font-family="ui-monospace,Menlo,monospace">' + (fin(pos) ? Math.round(pos) : '—') + '</text>' +
      '<text x="' + cx + '" y="' + (cy + 7) + '" text-anchor="middle" font-size="7.5" fill="' + DIM + '">POS</text></svg>';
  }
  function posBarCell(pos) {
    if (!fin(pos)) return '—';
    return '<span class="ag-posbar"><i style="left:' + Math.min(96, Math.max(0, pos)).toFixed(0) + '%;background:' + posColor(pos) + '"></i></span><b style="color:' + posColor(pos) + '">' + pos.toFixed(0) + '</b>';
  }

  /* ───────── 라인차트 (호버 툴팁 + 사냥 마커) ───────── */
  var CH = new WeakMap();
  var PENDING = {};
  var chSeq = 0;
  function chart(dates, rows, o) {
    // rows: [{name, v, col, hunt}], o: {h, unit, from, idx(100지수화), ymin0}
    var DIM=VIZ_CONTRACT.tokens.text[vizPhalanxTheme()];
    o = o || {};
    var from = o.from || 0;
    var ds = dates.slice(from);
    var W = 900, H = o.h || 170, PL = 8, PR = 54, PT = 10, PB = 20;
    var n = ds.length;
    if (!n || !rows.length) return '<div class="ag-empty">데이터 없음</div>';
    var view = rows.map(function (r) {
      var v = r.v.slice(from);
      if (o.idx) {
        var b = null;
        for (var i = 0; i < v.length; i++) if (fin(v[i]) && v[i] !== 0) { b = v[i]; break; }
        v = v.map(function (x) { return fin(x) && b ? x / b * 100 : null; });
      }
      return {rawName:r.name,name:r.name+' ['+(o.idx?'지수':(o.unit||'단위 미확인'))+' · '+(o.idx?'산출':'실적')+']',v:v,col:r.col,hunt:r.hunt};
    });
    var all = [];
    view.forEach(function (r) { r.v.forEach(function (x) { if (fin(x)) all.push(x); }); });
    if (!all.length) return '<div class="ag-empty">데이터 없음</div>';
    var vr=VizScale.niceScale(all,{class:o.ymin0?'zero_anchored':'range_focus',unit:o.idx?'지수':o.unit}),mn=vr.min,mx=vr.max;
    var x = function (i) { return PL + (W - PL - PR) * (n === 1 ? 0.5 : i / (n - 1)); };
    var y = function (v) { return PT + (H - PT - PB) * (1 - (v - mn) / (mx - mn)); };
    var g = '';
    for (var t = 0; t < vr.ticks.length; t++) {
      var tv=vr.ticks[t],ty=y(tv);
      g += '<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (W - PR) + '" y2="' + ty.toFixed(1) + '" stroke="#1f2937" stroke-width="0.6" stroke-dasharray="3 4"/>' +
        '<text x="' + (W - PR + 5) + '" y="' + (ty + 3.5).toFixed(1) + '" font-size="9.5" fill="' + DIM + '" font-family="ui-monospace,Menlo,monospace">' + fmt(tv) + '</text>';
    }
    if (mn < 0 && mx > 0) {
      g += '<line x1="' + PL + '" y1="' + y(0).toFixed(1) + '" x2="' + (W - PR) + '" y2="' + y(0).toFixed(1) + '" stroke="' + DIM + '" stroke-width="0.7" stroke-opacity="0.55"/>';
    }
    var xl = '';
    for (var xi = 0; xi < 5; xi++) {
      var idx = Math.round((n - 1) * xi / 4);
      var anchor = xi === 0 ? 'start' : (xi === 4 ? 'end' : 'middle');
      xl += '<text x="' + x(idx).toFixed(1) + '" y="' + (H - 5) + '" font-size="9.5" fill="' + DIM + '" text-anchor="' + anchor + '" font-family="ui-monospace,Menlo,monospace">' + esc(String(ds[idx]).slice(2, 7)) + '</text>';
    }
    var paths = '', marks = '';
    view.forEach(function (r, rowIndex) {
      var d = '', started = false, li = -1;
      for (var i = 0; i < n; i++) {
        if (!fin(r.v[i])) { started = false; continue; }
        d += (started ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r.v[i]).toFixed(1) + ' ';
        started = true; li = i;
      }
      var vst=VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),color:r.col,metric_index:rowIndex},o.idx?'derived':'actual'),dash=(vst.borderDash||[]).join(' ');r.col=vst.borderColor;
      paths += '<path d="' + d + '" fill="none" stroke="' + r.col + '" stroke-width="'+vst.borderWidth+'"' +
        (dash ? ' stroke-dasharray="' + dash + '"' : '') + ' stroke-linejoin="round"/>';
      if(li>=0)marks+=vizPhalanxSvgMarker(x(li),y(r.v[li]),vst,3.2);
      if (li >= 0 && r.hunt && r.hunt.length) {
        var hc = r.hunt.indexOf('bottom_turn') >= 0 ? UP : (r.hunt.indexOf('peak_warn') >= 0 ? DOWN : WARN);
        marks += '<circle cx="' + x(li).toFixed(1) + '" cy="' + y(r.v[li]).toFixed(1) + '" r="5.5" fill="none" stroke="' + hc + '" stroke-width="2"/>' +
          '<circle cx="' + x(li).toFixed(1) + '" cy="' + y(r.v[li]).toFixed(1) + '" r="2" fill="' + hc + '"/>';
      }
    });
    var id = 'ag' + (++chSeq);
    var latest = view.map(function (r) {
      for (var j = r.v.length - 1; j >= 0; j--) if (fin(r.v[j])) return r.name + ' ' + fmt(r.v[j]);
      return r.name + ' —';
    }).join(', ');
    var summary = '기간 ' + ds[0] + '부터 ' + ds[ds.length - 1] + ', 최신 ' + latest + ', 전체 최저 ' + fmt(Math.min.apply(null, all)) + ', 전체 최고 ' + fmt(Math.max.apply(null, all));
    if(vr.axis_note)summary+=' · '+vr.axis_note;
    PENDING[id] = { ds: ds, rows: view, W: W, PL: PL, PR: PR,
      unit: o.idx ? 'idx' : (o.unit || ''), summary: summary, index: n - 1 };
    return '<div class="ag-plot" data-ch="' + id + '" tabindex="0" aria-describedby="' + id + '-summary" aria-label="차트. 좌우 화살표로 날짜별 값을 탐색합니다."><svg role="img" focusable="false" aria-labelledby="' + id + '-title ' + id + '-desc" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none"><title id="' + id + '-title">' + esc(o.title || view.map(function (r) { return r.name; }).join(', ')) + '</title><desc id="' + id + '-desc">' + esc(summary) + '</desc>' + g + paths + marks +
      '<line class="ag-guide" x1="0" y1="' + PT + '" x2="0" y2="' + (H - PB) + '" stroke="#e6edf3" stroke-opacity="0" stroke-width="1"/>' + xl +
      '</svg>'+vizPhalanxLegend(view.map(function(r){return {name:r.rawName,unit:o.idx?'지수':o.unit,role:o.idx?'derived':'actual'};}))+'<div class="ag-tip" role="status" aria-live="polite"></div><div class="ag-chart-summary" id="' + id + '-summary">' + esc(summary) + '</div>' +
      '<details class="ag-data"><summary>접근 가능한 표 대체 데이터</summary><div data-table></div></details></div>';
  }
  function chartTable(st) {
    var head = '<th scope="col" class="l">날짜</th>' + st.rows.map(function (r) {
      return '<th scope="col">' + esc(r.name) + '</th>';
    }).join('');
    var rows = st.ds.map(function (date, i) {
      return '<tr><th scope="row" class="l">' + esc(date) + '</th>' + st.rows.map(function (r) {
        return '<td>' + fmt(r.v[i]) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    return '<div class="ag-scroll"><table class="ag-tbl"><caption>' + esc(st.summary) + '</caption><thead><tr>' +
      head + '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }
  function bindHover(root) {
    root.querySelectorAll('.ag-plot[data-ch]').forEach(function (plot) {
      if (plot.dataset.bound) return;
      plot.dataset.bound = '1';
      var st = PENDING[plot.dataset.ch] || CH.get(plot); if (!st) return;
      CH.set(plot, st);
      delete PENDING[plot.dataset.ch];
      var svg = plot.querySelector('svg'), tip = plot.querySelector('.ag-tip'), guide = plot.querySelector('.ag-guide');
      function showAt(i) {
        var r = svg.getBoundingClientRect();
        i = Math.min(st.ds.length - 1, Math.max(0, i));
        st.index = i;
        var frac = st.ds.length === 1 ? 0 : i / (st.ds.length - 1);
        var fx = st.PL + frac * (st.W - st.PL - st.PR);
        var lines = st.rows.map(function (rw) {
          return '<span aria-hidden="true" style="color:' + rw.col + '">◆</span> ' + esc(rw.name) + ' <b>' + fmt(rw.v[i]) + '</b>';
        });
        tip.innerHTML = '<b>' + esc(st.ds[i]) + '</b>' + (st.unit && st.unit !== 'idx' ? ' · ' + esc(st.unit) : (st.unit === 'idx' ? ' · 지수(=100)' : '')) + '<br>' + lines.join('<br>');
        var px = (st.PL + frac * (st.W - st.PL - st.PR)) / st.W * r.width;
        tip.style.left = Math.min(r.width - 100, Math.max(100, px)) + 'px';
        tip.style.top = '4px';
        guide.setAttribute('x1', fx.toFixed(1)); guide.setAttribute('x2', fx.toFixed(1));
        guide.setAttribute('stroke-opacity', '0.35');
        plot.classList.add('on');
      }
      plot.addEventListener('mousemove', function (ev) {
        var r = svg.getBoundingClientRect();
        var fx = (ev.clientX - r.left) / r.width * st.W;
        var frac = Math.min(1, Math.max(0, (fx - st.PL) / (st.W - st.PL - st.PR)));
        showAt(Math.round(frac * (st.ds.length - 1)));
      });
      plot.addEventListener('mouseleave', function () { plot.classList.remove('on'); guide.setAttribute('stroke-opacity', '0'); });
      plot.addEventListener('focus', function () { showAt(st.index); });
      plot.addEventListener('blur', function () { plot.classList.remove('on'); guide.setAttribute('stroke-opacity', '0'); });
      plot.addEventListener('keydown', function (ev) {
        var next = st.index;
        if (ev.key === 'ArrowLeft') next -= 1;
        else if (ev.key === 'ArrowRight') next += 1;
        else if (ev.key === 'Home') next = 0;
        else if (ev.key === 'End') next = st.ds.length - 1;
        else if (ev.key === 'Escape') { plot.blur(); return; }
        else return;
        ev.preventDefault(); showAt(next);
      });
      var details = plot.querySelector('.ag-data');
      details.addEventListener('toggle', function () {
        var holder = details.querySelector('[data-table]');
        if (details.open && !holder.dataset.ready) {
          holder.innerHTML = chartTable(st); holder.dataset.ready = '1';
        }
      });
    });
  }

  /* ───────── 메인 ───────── */
  window.renderARGUS = function (el, data) {
    ensureCss(el.ownerDocument);
    PENDING = {}; // 이전 렌더에서 DOM에 연결되지 못한 임시 차트 상태 제거
    data = data || {};
    data.kpi = data.kpi || {};
    data.axes = data.axes || { wk: [], sol: [], oil: [] };
    data.chains = data.chains || [];
    data.signals = data.signals || { bt: [], pw: [] };
    data.health = data.health || { total: data.kpi.n_series || 0, active: data.kpi.n_series || 0,
      stale: 0, low_confidence: 0, stale_series: [], low_confidence_series: [] };
    data.spread = data.spread || { cats: [], series: [] };
    data.solar = data.solar || { series: [] };
    data.oil = data.oil || { series: [] };

    var doc = el.ownerDocument, win = doc.defaultView || window;
    var chunkCache = {}, chunkWait = {}, fallbackWait = [], fallbackLoading = false;
    function directChunk(kind, key, source) {
      source = source || data;
      if (kind === 'spread') {
        var sp = (source.spread && source.spread.series || []).filter(function (r) { return r.cat === key && Array.isArray(r.v); });
        return sp.length ? { kind: kind, key: key, axis: (source.axes || {}).wk || [], series: sp } : null;
      }
      var rows = (source[kind] && source[kind].series || []).filter(function (r) { return Array.isArray(r.v); });
      var axisKey = kind === 'solar' ? 'sol' : 'oil';
      return rows.length ? { kind: kind, key: key, axis: (source.axes || {})[axisKey] || [], series: rows } : null;
    }
    function finishChunk(ref, chunk, error, source) {
      if (chunk) chunkCache[ref] = chunk;
      var waiting = chunkWait[ref] || [];
      delete chunkWait[ref];
      waiting.forEach(function (cb) { cb(chunk, error, source); });
    }
    function loadScript(url, done) {
      var script = doc.createElement('script');
      script.src = url; script.async = true; script.dataset.argusChunk = url;
      script.onload = function () { done(null); };
      script.onerror = function () { script.remove(); done(new Error('load failed: ' + url)); };
      (doc.head || doc.documentElement).appendChild(script);
    }
    function loadFallback(done) {
      if (win.ARGUS_FULL) { done(null, win.ARGUS_FULL); return; }
      fallbackWait.push(done);
      if (fallbackLoading) return;
      fallbackLoading = true;
      var url = (data.chunks || {}).fallback || 'data/argus_data_full.js';
      loadScript(url, function (error) {
        fallbackLoading = false;
        var full = win.ARGUS_FULL;
        var waiting = fallbackWait.slice(); fallbackWait = [];
        waiting.forEach(function (cb) { cb(error || (!full ? new Error('fallback payload missing') : null), full); });
      });
    }
    function loadChunk(kind, key, done) {
      var ref = kind + ':' + key;
      var direct = directChunk(kind, key);
      if (direct) { done(direct, null, 'inline'); return; }
      if (chunkCache[ref]) { done(chunkCache[ref], null, 'cache'); return; }
      if (win.ARGUS_CHUNKS && win.ARGUS_CHUNKS[ref]) {
        chunkCache[ref] = win.ARGUS_CHUNKS[ref]; done(chunkCache[ref], null, 'chunk'); return;
      }
      if (chunkWait[ref]) { chunkWait[ref].push(done); return; }
      chunkWait[ref] = [done];
      var manifest = data.chunks || {};
      var url = kind === 'spread' ? (manifest.spread || {})[key] : manifest[kind];
      if (!url) {
        finishChunk(ref, null, new Error('chunk manifest missing: ' + ref), null); return;
      }
      loadScript(url, function (error) {
        var loaded = win.ARGUS_CHUNKS && win.ARGUS_CHUNKS[ref];
        if (!error && loaded) { finishChunk(ref, loaded, null, 'chunk'); return; }
        loadFallback(function (fallbackError, full) {
          var fallbackChunk = full ? directChunk(kind, key, full) : null;
          finishChunk(ref, fallbackChunk, fallbackChunk ? null : (fallbackError || error),
            fallbackChunk ? 'fallback' : null);
        });
      });
    }

    var defCat = (function () {
      var withHunt = data.spread.series.filter(function (r) { return r.hunt && r.hunt.length; });
      if (withHunt.length) return withHunt[0].cat;
      return data.spread.cats[0] || null;
    })();
    var ST = { cat: defCat, spLimit: 24, oilRange: '5y' };

    el.innerHTML = '<div class="ag-wrap">' + hero() + nav() + kpis() +
      sec('hunt', '🎯 신규·확인 시그널', '상태·확인일과 데이터 신뢰도를 함께 확인') +
      sec('health', '🩺 데이터 건강상태', 'stale 및 표본 부족 시리즈는 별도 확인') +
      sec('board', '🏔 체인 스코어보드', '게이지 = 사이클 위치 percentile(전 이력) · 셀 = 모멘텀 중앙값 %') +
      sec('spread', '📉 스프레드 차트', '주간 5년 · 마커 = 현재 사냥 시그널', chips()) +
      sec('solar', '☀️ 태양광 밸류체인', '폴리 → 웨이퍼 → 셀 → 모듈 · PVInsights 주간') +
      sec('oil', '🛢 유가 데크', 'petronet 일간 → 주간 다운샘플 · 스프레드 = 제품-두바이', oilChips()) +
      footer() + '</div>';

    var W = el.querySelector('.ag-wrap');
    function body(id) { return W.querySelector('[data-body="' + id + '"]'); }
    function sec(id, title, hint, right) {
      return '<div class="ag-sec" id="ag-' + id + '"><div class="ag-sech"><h3>' + title + '</h3><span class="hint">' + esc(hint || '') + '</span><span class="sp"></span>' + (right || '') + '</div><div data-body="' + id + '"></div></div>';
    }
    function hero() {
      var k = data.kpi;
      return '<div class="ag-hero"><h2>👁 ARGUS — 시클리컬 사이클 관제</h2>' +
        '<div class="sub">정유·화학·태양광 <b>' + (k.n_series || 0) + '개</b> 가격·스프레드 시리즈의 사이클 위치를 상시 감시 — ' +
        '바닥 반등 <b style="color:' + UP + '">' + (k.n_bt || 0) + '건</b> · 고점 경계 <b style="color:' + DOWN + '">' + (k.n_pw || 0) + '건</b> · ' +
        '기준일 <b>' + esc(data.asof || '—') + '</b> · 주간 갱신' + (data.mock ? ' · <b style="color:' + WARN + '">MOCK 데이터</b>' : '') +
        ' · 참고용, 투자조언 아님</div></div>';
    }
    function nav() {
      var items = [['hunt', '🎯 시그널'], ['health', '🩺 건강상태'], ['board', '🏔 스코어보드'], ['spread', '📉 스프레드'], ['solar', '☀️ 태양광'], ['oil', '🛢 유가']];
      return '<div class="ag-nav">' + items.map(function (it) { return '<a href="#ag-' + it[0] + '">' + it[1] + '</a>'; }).join('') + '</div>';
    }
    function kpis() {
      var k = data.kpi;
      var low = data.chains.filter(function (c) { return fin(c.pos); }).sort(function (a, b) { return a.pos - b.pos; })[0];
      var high = data.chains.filter(function (c) { return fin(c.pos); }).sort(function (a, b) { return b.pos - a.pos; })[0];
      function kpi(color, lab, val, sub) { return '<div class="ag-kpi" style="--kc:' + color + '"><div class="lab">' + lab + '</div><div class="val">' + val + '</div><div class="sub">' + sub + '</div></div>'; }
      return '<div class="ag-kpis">' +
        kpi(ACC, '감시 시리즈', String(k.n_series || 0), '가격·스프레드·태양광·유가') +
        kpi(UP, '🎯 바닥 반등', String(k.n_bt || 0), 'bottom_turn 시그널') +
        kpi(DOWN, '⚠ 고점 경계', String(k.n_pw || 0), 'peak_warn 시그널') +
        kpi(WARN, '⤴ 가속', String(k.n_ac || 0), '모멘텀 가속(accel)') +
        kpi('#b892ff', '최저 사이클 체인', low ? esc(low.label) : '—',
          (low ? 'pos ' + low.pos : '') + (high ? ' · 최고 ' + esc(high.label) + ' ' + high.pos : '')) +
        '</div>';
    }
    function chips() {
      return '<div class="ag-chips" data-ck="cat">' + data.spread.cats.map(function (c) {
        var n = data.spread.series.filter(function (r) { return r.cat === c && r.hunt && r.hunt.length; }).length;
        return '<button type="button" aria-pressed="' + (c === ST.cat ? 'true' : 'false') + '" class="ag-chip' + (c === ST.cat ? ' on' : '') + '" data-cv="' + esc(c) + '">' + esc(c) + (n ? ' <b style="color:' + UP + '">●' + n + '</b>' : '') + '</button>';
      }).join('') + '</div>';
    }
    function oilChips() {
      return '<div class="ag-chips" data-ck="oilRange">' + [['all', '전체'], ['10y', '10년'], ['5y', '5년'], ['1y', '1년']].map(function (p) {
        return '<button type="button" aria-pressed="' + (p[0] === ST.oilRange ? 'true' : 'false') + '" class="ag-chip' + (p[0] === ST.oilRange ? ' on' : '') + '" data-cv="' + p[0] + '">' + p[1] + '</button>';
      }).join('') + '</div>';
    }
    function footer() {
      return '<div class="ag-foot">ARGUS — 주간 시황 원장(xlsm) 기반 시클리컬 사이클 계량 · pos = 전 이력 percentile(0=역사적 바닥, 100=역사적 고점) · ' +
        'mom = 1/4/13/26주 변화율 · 종목 매핑은 사업 익스포저 큐레이션(참고용 라벨) · <b>투자조언 아님</b> · 기준일 ' + esc(data.asof || '—') +
        (data.mock ? ' · <span style="color:' + WARN + '">본 화면은 MOCK 데이터 렌더 검증본</span>' : '') + '</div>';
    }

    /* ── 데이터 건강상태 ── */
    function qualityList(rows, empty) {
      if (!rows || !rows.length) return '<div class="ag-empty">' + empty + '</div>';
      return '<ul class="ag-quality-list">' + rows.map(function (r) {
        return '<li><b>' + esc(r.name || r.sid) + '</b> · ' + esc(r.last_date || '날짜 없음') +
          ' · ' + esc(r.freq || '빈도 미상') + ' · n=' + esc(r.n_obs == null ? '—' : r.n_obs) +
          (r.source ? ' · ' + esc(r.source) : '') + '</li>';
      }).join('') + '</ul>';
    }
    function rHealth() {
      var h = data.health || {};
      body('health').innerHTML = '<p><a href="connections.html">데이터 연결 현황 · 품목별 원문·실제 관측 그래프 →</a></p><div class="ag-card ag-health"><div class="metric"><span>총 시리즈</span><b>' + (h.total || 0) + '</b></div>' +
        '<div class="metric"><span>활성(신호 적격)</span><b style="color:' + UP + '">' + (h.active || 0) + '</b></div>' +
        '<div class="metric"><span>stale</span><b style="color:' + DOWN + '">' + (h.stale || 0) + '</b></div>' +
        '<div class="metric"><span>저신뢰(표본 부족)</span><b style="color:' + WARN + '">' + (h.low_confidence || 0) + '</b></div>' +
        '<div class="ag-health-lists" style="grid-column:1/-1"><details><summary>stale 목록 ' + (h.stale || 0) + '개</summary>' +
        qualityList(h.stale_series, 'stale 시리즈 없음') + '</details><details><summary>저신뢰 목록 ' + (h.low_confidence || 0) + '개</summary>' +
        qualityList(h.low_confidence_series, '표본 부족 시리즈 없음') + '</details></div></div>';
    }

    /* ── ① 스코어보드 ── */
    function rBoard() {
      if (!data.chains.length) { body('board').innerHTML = '<div class="ag-empty">체인 데이터 없음</div>'; return; }
      body('board').innerHTML = '<div class="ag-chains">' + data.chains.map(function (c) {
        var h = c.hunts || {};
        var badges = (h.bt ? '<span class="ag-hb bt">🎯 바닥반등 ' + h.bt + '</span>' : '') +
          (h.pw ? '<span class="ag-hb pw">⚠ 고점 ' + h.pw + '</span>' : '') +
          (h.ac ? '<span class="ag-hb ac">⤴ 가속 ' + h.ac + '</span>' : '');
        var m = c.mom || {};
        var members = (c.members || []).map(function (r) {
          return '<div class="ag-member"><b>' + esc(r.name || r.sid) + '</b><span>' + esc(r.freq || '—') + ' · n=' + esc(r.n_obs == null ? '—' : r.n_obs) + '</span>' +
            '<span>' + esc(r.last_date || '날짜 없음') + ' · ' + esc(r.freshness || '미상') + (r.low_confidence ? ' · 표본부족' : '') + '</span>' +
            '<span>' + esc(r.basis_id || r.source || 'source 미상') + '</span></div>';
        }).join('');
        return '<div class="ag-chain"><div class="top">' + gauge(c.pos) +
          '<div><div class="lb">' + esc(c.label) + '</div><div class="nn">' + (c.n || 0) + ' series</div></div></div>' +
          '<div class="ag-momrow">' + momCell('1W', m.w1) + momCell('4W', m.w4) + momCell('13W', m.w13) + momCell('26W', m.w26) + '</div>' +
          '<div class="ag-hbadges">' + badges + '</div>' +
          '<div class="ag-stocks">' + stockChips(c.stocks) + '</div>' +
          '<details class="ag-members"><summary>구성 시리즈 ' + (c.members || []).length + '개 펼치기</summary>' + members + '</details></div>';
      }).join('') + '</div>';
    }

    /* ── ② 사냥 시그널 ── */
    function sigTable(rows, kind) {
      if (!rows.length) return '<div class="ag-empty">현재 ' + (kind === 'bt' ? 'bottom_turn' : 'peak_warn') + ' 시그널 없음</div>';
      return '<div class="ag-scroll"><table class="ag-tbl"><thead><tr>' +
        '<th class="l">시리즈</th><th class="l">상태</th><th>pos</th><th>pos5y</th><th>1W%</th><th>4W%</th><th>z26</th><th>현재값</th><th>26주</th><th class="l">데이터 근거</th><th class="l">연관 종목</th>' +
        '</tr></thead><tbody>' + rows.map(function (r) {
          var state = esc(r.state || 'active');
          var metaLines = [], metaA = [], metaB = [];
          metaA.push('last ' + esc(r.last_date || '미상'));
          metaA.push('freq ' + esc(r.freq || '미상'));
          metaA.push('freshness ' + esc(r.freshness || '미상'));
          metaB.push('n_obs ' + esc(r.n_obs == null ? '미상' : r.n_obs));
          metaB.push('pos ' + esc(r.pos_window || '미상'));
          metaB.push('mom ' + esc(r.mom_method || '미상'));
          if (metaA.length) metaLines.push(metaA.join(' · '));
          if (metaB.length) metaLines.push(metaB.join(' · '));
          metaLines.push('source ' + esc(r.source || '미상') + (r.basis_id ? ' · basis ' + esc(r.basis_id) : ''));
          if (r.fut && r.fut.state && r.fut.state !== 'no_data') {
            var fu = r.fut.state === 'diverge';
            metaLines.push('<span style="color:' + (fu ? DOWN : UP) + ';font-weight:700">'
              + (fu ? '↓ 선물 괴리' : (r.fut.state === 'confirm_strong' ? '↑↑ 선물 2주 연속 확인' : '↑ 선물 확인'))
              + '</span> ' + (r.fut.chg != null ? (r.fut.chg > 0 ? '+' : '') + r.fut.chg + '%' : '')
              + ' <span class="ag-meta">(' + esc(r.fut.proxy) + ' 1주 선행 · 참고정보, 시그널 조건 아님)</span>');
          }
          var stateMeta = [];
          if (r.on_date) stateMeta.push('on ' + esc(r.on_date));
          if (r.confirmed_on) stateMeta.push('confirmed ' + esc(r.confirmed_on));
          stateMeta.push('rule ' + esc(r.rule_version || '미상'));
          if (state === 'candidate') {
            var held = Math.min(Number(r.bars_required || 2), Number(r.bars_held || 0));
            var required = Number(r.bars_required || 2);
            stateMeta.push('<progress class="ag-progress" max="' + required + '" value="' + held + '" aria-label="확인 진행도 ' + held + '/' + required + ' bar"></progress> ' + held + '/' + required + ' bar');
            stateMeta.push('다음 ' + esc(r.freq || '') + ' 관측에서도 반전 조건 유지 시 확정');
          }
          if (r.low_confidence) stateMeta.push('⚠ 표본 부족');
          return '<tr><td class="nm l">' + esc(r.name) + '<span class="c">' + esc(r.cat || '') + '</span></td>' +
            '<td class="l" style="font-family:inherit"><span class="ag-status' + (r.low_confidence ? ' low' : '') + '">' + state + '</span>' +
            (stateMeta.length ? '<div class="ag-meta">' + stateMeta.join('<br>') + '</div>' : '') + '</td>' +
            '<td>' + posBarCell(r.pos) + '</td>' +
            '<td style="color:' + DIM + '">' + (fin(r.pos5y) ? r.pos5y.toFixed(0) : '—') + '</td>' +
            '<td>' + fmtPct(r.m1) + '</td><td>' + fmtPct(r.m4) + '</td>' +
            '<td style="color:' + DIM + '">' + (fin(r.z26) ? r.z26.toFixed(1) : '—') + '</td>' +
            '<td><b>' + fmt(r.last) + '</b> <span style="color:' + DIM + ';font-size:10px">' + esc(r.unit || '') + '</span></td>' +
            '<td>' + spark(r.spark || [], 90, 24, kind === 'bt' ? UP : DOWN) + '</td>' +
            '<td class="l ag-meta">' + metaLines.join('<br>') + '</td>' +
            '<td class="l" style="font-family:inherit">' + stockChips(r.stocks) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    function rHunt() {
      var btc = data.signals.btc || [], pwc = data.signals.pwc || [];
      var cand = '';
      if (btc.length || pwc.length) {
        cand = '<div class="ag-card" style="margin-top:12px">' +
          '<div style="font-size:12.5px;font-weight:800;margin-bottom:4px">👀 관찰 중 (candidate — 확인 대기)</div>' +
          '<div class="ag-meta" style="margin-bottom:8px">사이클 위치·추세 조건은 충족했으나 확인(2개 관측 연속 반전)이 남은 후보. 확인되면 위 확정 시그널로 승격된다.</div>' +
          (btc.length ? '<div style="font-size:12px;font-weight:700;margin:6px 0 4px;color:' + UP + '">🎯 바닥 후보 ' + btc.length + '건</div>' + sigTable(btc, 'btc') : '') +
          (pwc.length ? '<div style="font-size:12px;font-weight:700;margin:10px 0 4px;color:' + DOWN + '">⚠ 고점 후보 ' + pwc.length + '건</div>' + sigTable(pwc, 'pwc') : '') +
          '</div>';
      }
      body('hunt').innerHTML =
        '<div class="ag-card" style="margin-bottom:12px"><div style="font-size:12.5px;font-weight:800;margin-bottom:8px;color:' + UP + '">🎯 bottom_turn — 역사적 바닥권에서 반등 시작(확정)</div>' + sigTable(data.signals.bt || [], 'bt') + '</div>' +
        '<div class="ag-card"><div style="font-size:12.5px;font-weight:800;margin-bottom:8px;color:' + DOWN + '">⚠ peak_warn — 역사적 고점권에서 하락 전환(확정)</div>' + sigTable(data.signals.pw || [], 'pw') + '</div>' +
        cand;
    }

    /* ── ③ 스프레드 차트 ── */
    var spreadPanels = {};
    function renderSpreadPanel(panel, chunk) {
      var rows = (chunk.series || []).slice().sort(function (a, b) {
        var ha = a.hunt && a.hunt.length ? 1 : 0, hb = b.hunt && b.hunt.length ? 1 : 0;
        return hb - ha;
      });
      if (!rows.length) { panel.innerHTML = '<div class="ag-empty">카테고리 데이터 없음</div>'; return; }
      var shown = rows.slice(0, ST.spLimit);
      panel.innerHTML = '<div class="ag-grid">' + shown.map(function (r, i) {
        var col = r.hunt && r.hunt.indexOf('bottom_turn') >= 0 ? UP : (r.hunt && r.hunt.indexOf('peak_warn') >= 0 ? DOWN : PAL[i % PAL.length]);
        return '<div class="ag-ccard"><div class="h"><span class="t">' + esc(r.name) + '</span><span class="u">' + esc(r.unit || '') + '</span>' +
          (fin(r.pos) ? '<span class="ag-badge" style="color:' + posColor(r.pos) + ';border:1px solid ' + posColor(r.pos) + '">pos ' + r.pos.toFixed(0) + '</span>' : '') +
          huntBadges(r.hunt) +
          '<span class="lv">' + fmt(r.last) + ' <span style="font-weight:500;color:' + DIM + '">' + (fin(r.m4) ? '' : '') + '</span></span></div>' +
          '<div class="ag-meta">관측 ' + esc(r.last_date || '미확인') + ' · ' + esc(r.freshness || '') + ' · <a href="connections.html#' + encodeURIComponent(r.sid) + '">갱신 경로·원문</a></div>' +
          chart(chunk.axis, [{ name: r.name, v: r.v, col: col, hunt: r.hunt }], { h: 150, unit: r.unit, title: r.name }) + '</div>';
      }).join('') + '</div>' +
        (rows.length > ST.spLimit ? '<div class="ag-more"><button type="button" class="ag-chip" data-act="spmore">▼ ' + (rows.length - ST.spLimit) + '개 더 보기</button></div>' :
          (ST.spLimit > 24 ? '<div class="ag-more"><button type="button" class="ag-chip" data-act="spless">▲ 접기</button></div>' : ''));
      bindHover(panel);
      var mb = panel.querySelector('[data-act]');
      if (mb) mb.onclick = function () {
        ST.spLimit = mb.dataset.act === 'spmore' ? 999 : 24; renderSpreadPanel(panel, chunk);
      };
    }
    function rSpread() {
      var host = body('spread');
      Object.keys(spreadPanels).forEach(function (cat) {
        spreadPanels[cat].hidden = cat !== ST.cat;
      });
      if (spreadPanels[ST.cat]) return;
      var panel = doc.createElement('div');
      panel.dataset.categoryPanel = ST.cat || '';
      panel.innerHTML = '<div class="ag-load" role="status">선택 카테고리 시계열 로딩…</div>';
      host.appendChild(panel); spreadPanels[ST.cat] = panel;
      loadChunk('spread', ST.cat, function (chunk, error, source) {
        panel.dataset.payloadSource = source || 'error';
        if (error || !chunk) {
          panel.innerHTML = '<div class="ag-empty" role="alert">시계열 chunk와 단일 파일 폴백을 모두 불러오지 못했습니다.</div>'; return;
        }
        renderSpreadPanel(panel, chunk);
      });
    }

    /* ── ④ 태양광 ── */
    function renderSolar(chunk) {
      var ss = chunk.series || [];
      if (!ss.length) { body('solar').innerHTML = '<div class="ag-empty">태양광 데이터 없음</div>'; return; }
      var ORDER = [['poly', '폴리실리콘'], ['wafer', '웨이퍼'], ['cell', '셀'], ['module', '모듈']];
      var mains = ORDER.map(function (o) {
        return (ss.filter(function (r) { return r.stage === o[0] && r.main; })[0]) || null;
      });
      var flow = '<div class="ag-flow">' + ORDER.map(function (o, i) {
        var r = mains[i];
        var cell = r ? '<div class="ag-stage"><div class="sn">' + o[1].toUpperCase() + '</div><div class="pn">' + esc(r.name) + '</div>' +
          '<div class="pv" style="color:' + posColor(r.pos) + '">' + fmt(r.last) + ' <span class="pu">' + esc(r.unit || '') + '</span></div>' +
          '<div class="ag-meta">관측 ' + esc(r.last_date || '미확인') + ' · <a href="connections.html#' + encodeURIComponent(r.sid) + '">가격 기준·원문</a></div><div class="pm">WoW ' + fmtPct(r.m1) + ' · 4W ' + fmtPct(r.m4) + (fin(r.pos) ? ' · pos <b style="color:' + posColor(r.pos) + '">' + r.pos.toFixed(0) + '</b>' : '') + '</div>' +
          '<div style="margin-top:6px">' + spark((r.v || []).slice(-104).filter(function (_, j) { return true; }), 150, 30, posColor(r.pos)) + '</div>' +
          '<div class="ag-hbadges" style="margin-top:6px">' + huntBadges(r.hunt) + '</div></div>'
          : '<div class="ag-stage"><div class="sn">' + o[1] + '</div><div class="ag-empty">—</div></div>';
        return cell + (i < ORDER.length - 1 ? '<div class="ag-arrow">➜</div>' : '');
      }).join('') + '</div>';
      var mainRows = mains.filter(Boolean).map(function (r, i) {
        return { name: r.name, v: r.v, col: PAL[i], hunt: r.hunt };
      });
      var modRows = ss.filter(function (r) { return r.stage === 'module' && r.unit === 'USD/W'; }).slice(0, 6).map(function (r, i) {
        return { name: r.name, v: r.v, col: PAL[(i + 4) % PAL.length], hunt: r.hunt };
      });
      body('solar').innerHTML = '<p class="ag-meta">공개 현물과 원장 가격은 규격·지역에 따라 다릅니다. <a href="connections.html#sol_pvi_module_182_perc">전체 태양광 연결·신규 현물 보기 →</a></p>' + flow +
        '<div class="ag-grid2" style="margin-top:12px">' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">단계별 가격 지수 (5년, 시작=100)</div>' +
        chart(chunk.axis, mainRows, { h: 200, idx: true, title: '태양광 단계별 가격 지수' }) +
        '<div class="ag-lgd">' + mainRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div>' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">모듈 가격 (USD/W)</div>' +
        chart(chunk.axis, modRows, { h: 200, unit: 'USD/W', title: '태양광 모듈 가격' }) +
        '<div class="ag-lgd">' + modRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div></div>';
      bindHover(body('solar'));
    }
    function rSolar() {
      body('solar').innerHTML = '<div class="ag-load" role="status">태양광 시계열 로딩…</div>';
      loadChunk('solar', 'solar', function (chunk, error, source) {
        body('solar').dataset.payloadSource = source || 'error';
        if (error || !chunk) {
          body('solar').innerHTML = '<div class="ag-empty" role="alert">태양광 chunk와 단일 파일 폴백을 모두 불러오지 못했습니다.</div>'; return;
        }
        renderSolar(chunk);
      });
    }

    /* ── ⑤ 유가 데크 ── */
    function oilFrom(axis) {
      var n = axis.length;
      if (ST.oilRange === 'all') return 0;
      var yrs = ST.oilRange === '10y' ? 10 : ST.oilRange === '5y' ? 5 : 1;
      return Math.max(0, n - yrs * 52 - 1);
    }
    var oilChunk = null;
    function renderOil(chunk) {
      var ss = chunk.series || [];
      if (!ss.length) { body('oil').innerHTML = '<div class="ag-empty">유가 데이터 없음</div>'; return; }
      var crude = ss.filter(function (r) { return r.grp === 'crude'; });
      var crack = ss.filter(function (r) { return r.grp === 'crack'; });
      var from = oilFrom(chunk.axis);
      var kpi = '<div class="ag-oilkpis">' + crude.concat(crack.slice(0, 2)).map(function (r) {
        return '<div class="ag-oilk"><div class="l">' + esc(r.name) + '</div><div class="v">' + fmt(r.last) +
          ' <span style="font-size:10px;color:' + DIM + '">' + esc(r.unit || '') + '</span></div><div class="w">WoW ' + fmtPct(r.wow) +
          (fin(r.pos) ? ' · pos <b style="color:' + posColor(r.pos) + '">' + r.pos.toFixed(0) + '</b>' : '') + '</div></div>';
      }).join('') + '</div>';
      var crudeRows = crude.map(function (r, i) { return { name: r.name, v: r.v, col: [ACC, '#4ea1ff', '#f6c85f', '#b892ff'][i % 4], hunt: r.hunt }; });
      var crackRows = crack.map(function (r, i) { return { name: r.name, v: r.v, col: PAL[i % PAL.length], hunt: r.hunt }; });
      body('oil').innerHTML = kpi +
        '<div class="ag-grid2">' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">원유 ($/bbl)</div>' +
        chart(chunk.axis, crudeRows, { h: 210, unit: '$/bbl', from: from, title: '원유 가격' }) +
        '<div class="ag-lgd">' + crudeRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div>' +
        '<div class="ag-card"><div style="font-size:12px;font-weight:750;margin-bottom:6px">정제 스프레드 — 제품-두바이 ($/bbl)</div>' +
        chart(chunk.axis, crackRows, { h: 210, unit: '$/bbl', from: from, title: '정제 스프레드' }) +
        '<div class="ag-lgd">' + crackRows.map(function (r) { return '<span><i style="background:' + r.col + '"></i>' + esc(r.name) + '</span>'; }).join('') + '</div></div></div>';
      bindHover(body('oil'));
    }
    function rOil() {
      if (oilChunk) { renderOil(oilChunk); return; }
      body('oil').innerHTML = '<div class="ag-load" role="status">유가 시계열 로딩…</div>';
      loadChunk('oil', 'oil', function (chunk, error, source) {
        body('oil').dataset.payloadSource = source || 'error';
        if (error || !chunk) {
          body('oil').innerHTML = '<div class="ag-empty" role="alert">유가 chunk와 단일 파일 폴백을 모두 불러오지 못했습니다.</div>'; return;
        }
        oilChunk = chunk; renderOil(chunk);
      });
    }

    /* 칩 이벤트 (위임) */
    W.addEventListener('click', function (ev) {
      var b = ev.target.closest('.ag-chip'); if (!b) return;
      var row = b.closest('[data-ck]'); if (!row) return;
      var key = row.dataset.ck, val = b.dataset.cv;
      if (val == null || ST[key] === val) return;
      ST[key] = val;
      row.querySelectorAll('.ag-chip').forEach(function (c) {
        var selected = c === b;
        c.classList.toggle('on', selected);
        c.setAttribute('aria-pressed', selected ? 'true' : 'false');
      });
      if (key === 'cat') { ST.spLimit = 24; rSpread(); }
      else if (key === 'oilRange') rOil();
    });

    function lazySection(id, render) {
      if (!win.IntersectionObserver) { render(); return; }
      body(id).innerHTML = '<div class="ag-load" role="status">화면에 가까워지면 시계열을 불러옵니다.</div>';
      var target = W.querySelector('#ag-' + id);
      var observer = new win.IntersectionObserver(function (entries) {
        if (entries.some(function (entry) { return entry.isIntersecting; })) {
          observer.disconnect(); render();
        }
      }, { rootMargin: '240px' });
      observer.observe(target);
    }

    rHunt(); rHealth(); rBoard(); rSpread();
    lazySection('solar', rSolar); lazySection('oil', rOil);
  };
})();
