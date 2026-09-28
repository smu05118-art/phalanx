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
// Panoptes — 국제분쟁 지도 (독자 시스템, MapLibre GL)
const TYPES = {
  armed_clash:  {label:'무력 충돌', color:'#ff6b6b'},
  airstrike:    {label:'공습',      color:'#ff8a3d'},
  shelling:     {label:'포격',      color:'#ffab3d'},
  terrorism:    {label:'테러',      color:'#c45cff'},
  naval:        {label:'해상',      color:'#26c6da'},
  cyber:        {label:'사이버',    color:'#59d0a8'},
  protest:      {label:'시위·소요', color:'#ffd23d'},
  border_tension:{label:'국경 긴장',color:'#4ea1ff'},
  political:    {label:'정치·외교', color:'#8a93a3'},
};
const SEV = {1:'#4ea1ff',2:'#59d0a8',3:'#ffd23d',4:'#ff8a3d',5:'#ff4d5e'};
const ST = { typeOff:{}, sevOff:{}, q:'', timePct:0, sel:null };
let MAP=null, EVENTS=[], DATES=[];

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function daysAgo(d){const t=Date.parse(d); if(isNaN(t))return null; return Math.round((Date.now()-t)/864e5);}

async function boot(){
  const [world, events] = await Promise.all([
    fetch('data/world.min.geojson').then(r=>r.json()),
    fetch('data/events.json').then(r=>r.ok?r.json():[]).catch(()=>[])
  ]);
  EVENTS = (Array.isArray(events)?events:(events.events||[])).filter(e=>e.lat!=null&&e.lon!=null);
  EVENTS.forEach((e,i)=>{e._id=e.id||('ev'+i); e._sev=Math.max(1,Math.min(5,+e.severity||1));});
  window.EVENTS=EVENTS; // ProView 모듈(proview.js)에서 브리핑·레이더·TTS에 사용
  DATES = EVENTS.map(e=>Date.parse(e.date)).filter(x=>!isNaN(x)).sort((a,b)=>a-b);

  const CARTO=['a','b','c','d'].map(s=>`https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png`);
  MAP = new maplibregl.Map({
    container:'map',
    style:{version:8,
      sources:{
        carto:{type:'raster',tiles:CARTO,tileSize:256,attribution:'© OpenStreetMap · © CARTO'},
      },
      layers:[
        {id:'bg',type:'background',paint:{'background-color':'#080b12'}},
        {id:'carto',type:'raster',source:'carto',paint:{'raster-opacity':0.92,'raster-saturation':-0.25,'raster-contrast':0.05}},
      ]},
    center:[27,20], zoom:2.1, minZoom:1.3, maxZoom:12, renderWorldCopies:true, attributionControl:false
  });
  MAP.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right');
  MAP.addControl(new maplibregl.AttributionControl({compact:true}),'bottom-left');
  window.MAP=MAP; // ProView 뉴스 레이어 훅용

  MAP.on('load', ()=>{
    // 국가 상호작용용(투명 fill + 은은한 accent 경계 + hover 하이라이트)
    MAP.addSource('world',{type:'geojson',data:world,promoteId:'name'});
    MAP.addLayer({id:'country-hover',type:'fill',source:'world',
      paint:{'fill-color':'#2bc0d4','fill-opacity':['case',['boolean',['feature-state','hover'],false],0.10,0]}});
    MAP.addLayer({id:'country-line',type:'line',source:'world',paint:{'line-color':'#2b3a4d','line-width':0.4,'line-opacity':0.5}});
    let hov=null;
    MAP.on('mousemove','country-hover',e=>{const f=e.features[0];if(hov!==null)MAP.setFeatureState({source:'world',id:hov},{hover:false});hov=f.id;MAP.setFeatureState({source:'world',id:hov},{hover:true});});
    MAP.on('mouseleave','country-hover',()=>{if(hov!==null)MAP.setFeatureState({source:'world',id:hov},{hover:false});hov=null;});

    MAP.addSource('events',{type:'geojson',data:geo()});
    // 펄스(고심각도) → glow → dot → 코어 하이라이트
    MAP.addLayer({id:'ev-pulse',type:'circle',source:'events',filter:['>=',['get','sev'],4],paint:{
      'circle-radius':['*',['get','sev'],3],'circle-color':['get','color'],'circle-opacity':0.4,'circle-blur':0.6}});
    MAP.addLayer({id:'ev-glow',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],3],5],'circle-color':['get','color'],'circle-blur':1,'circle-opacity':0.28}});
    MAP.addLayer({id:'ev-dot',type:'circle',source:'events',paint:{
      'circle-radius':['+',['*',['get','sev'],1.7],3],'circle-color':['get','color'],
      'circle-stroke-color':'#fff','circle-stroke-width':1,'circle-stroke-opacity':0.5,'circle-opacity':0.95}});
    MAP.addLayer({id:'ev-core',type:'circle',source:'events',paint:{
      'circle-radius':1.6,'circle-color':'#fff','circle-opacity':0.9}});
    MAP.on('click','ev-dot',e=>{const id=e.features[0].properties.id; select(id,true);});
    MAP.on('mouseenter','ev-dot',()=>MAP.getCanvas().style.cursor='pointer');
    MAP.on('mouseleave','ev-dot',()=>MAP.getCanvas().style.cursor='');
    buildFilters(); buildRegions(); refresh(); pulse();
  });

  document.getElementById('search').oninput=e=>{ST.q=e.target.value.toLowerCase().trim();refresh();};
  const sl=document.getElementById('timeSlider');
  sl.oninput=e=>{ST.timePct=+e.target.value;refresh();};
  document.getElementById('stEvents').textContent=EVENTS.length;
  const latest=EVENTS.map(e=>e.date).filter(Boolean).sort().pop();
  document.getElementById('stUpdated').textContent=latest||'—';
  if(DATES.length){document.getElementById('tlMin').textContent=new Date(DATES[0]).toISOString().slice(0,10);}
}

let _pt=0;
function pulse(){
  _pt=(_pt+1)%90; const p=_pt/90;
  if(MAP&&MAP.getLayer('ev-pulse')){
    MAP.setPaintProperty('ev-pulse','circle-radius',['*',['get','sev'],3+p*6]);
    MAP.setPaintProperty('ev-pulse','circle-opacity',0.45*(1-p));
  }
  requestAnimationFrame(pulse);
}
const REGIONS=[
  ['전체',[27,20],1.9],['우크라이나',[33,48.5],4.3],['중동·가자',[37,31],4.2],
  ['수단·사헬',[20,14],3.4],['홍해',[42,15],4.2],['동아시아',[122,26],3.6],['미얀마',[96,21],4.3]
];
function buildRegions(){
  const el=document.getElementById('regionJump'); if(!el)return;
  el.innerHTML=REGIONS.map((r,i)=>`<span class="rchip" data-i="${i}">${r[0]}</span>`).join('');
  el.querySelectorAll('.rchip').forEach(c=>c.onclick=()=>{const r=REGIONS[+c.dataset.i];MAP.flyTo({center:r[1],zoom:r[2],speed:0.9});});
}
function geo(){
  return {type:'FeatureCollection',features:visible().map(e=>({
    type:'Feature',geometry:{type:'Point',coordinates:[+e.lon,+e.lat]},
    properties:{id:e._id,sev:e._sev,color:(TYPES[e.type]||{}).color||'#8a93a3'}}))};
}
function passType(e){return !ST.typeOff[e.type];}
function passSev(e){return !ST.sevOff[e._sev];}
function passTime(e){ if(!ST.timePct||!DATES.length)return true; const cut=DATES[0]+(DATES[DATES.length-1]-DATES[0])*(ST.timePct/100); const t=Date.parse(e.date); return isNaN(t)||t>=cut; }
function passQ(e){ if(!ST.q)return true; return ((e.title||'')+(e.country||'')+(e.region||'')+(e.summary||'')).toLowerCase().includes(ST.q); }
function visible(){return EVENTS.filter(e=>passType(e)&&passSev(e)&&passTime(e)&&passQ(e));}

function refresh(){
  if(MAP&&MAP.getSource('events'))MAP.getSource('events').setData(geo());
  const vis=visible();
  document.getElementById('stActive').textContent=vis.length;
  if(ST.timePct&&DATES.length){const cut=DATES[0]+(DATES[DATES.length-1]-DATES[0])*(ST.timePct/100);document.getElementById('tlCur').textContent='이후: '+new Date(cut).toISOString().slice(0,10);}
  else document.getElementById('tlCur').textContent='전체 기간';
  const list=document.getElementById('evlist');
  list.innerHTML=vis.slice().sort((a,b)=>(b.date||'').localeCompare(a.date||'')).slice(0,60).map(e=>{
    const c=(TYPES[e.type]||{}).color||'#8a93a3';const da=daysAgo(e.date);
    return `<div class="evcard" style="border-left-color:${c}" data-id="${e._id}">
      <div class="et">${esc(e.title)}</div>
      <div class="em"><span>${esc(e.country||e.region||'')}</span><span>${(TYPES[e.type]||{}).label||e.type}</span><span>S${e._sev}</span>${da!=null?`<span>${da==0?'오늘':da+'일 전'}</span>`:''}</div>
    </div>`;}).join('')||'<p class="hint">표시할 이벤트가 없습니다.</p>';
  list.querySelectorAll('.evcard').forEach(el=>el.onclick=()=>select(el.dataset.id,true));
}

function buildFilters(){
  const tc={};EVENTS.forEach(e=>tc[e.type]=(tc[e.type]||0)+1);
  document.getElementById('typeFilters').innerHTML=Object.entries(TYPES).filter(([k])=>tc[k]).map(([k,t])=>
    `<div class="frow" data-t="${k}"><span class="dot" style="background:${t.color}"></span>${t.label}<span class="n">${tc[k]||0}</span></div>`).join('');
  const sc={};EVENTS.forEach(e=>sc[e._sev]=(sc[e._sev]||0)+1);
  document.getElementById('sevFilters').innerHTML=[1,2,3,4,5].map(s=>
    `<div class="frow" data-s="${s}"><span class="dot" style="background:${SEV[s]}"></span>심각도 ${s}<span class="n">${sc[s]||0}</span></div>`).join('');
  document.querySelectorAll('[data-t]').forEach(el=>el.onclick=()=>{ST.typeOff[el.dataset.t]=!ST.typeOff[el.dataset.t];el.classList.toggle('off');refresh();});
  document.querySelectorAll('[data-s]').forEach(el=>el.onclick=()=>{const s=+el.dataset.s;ST.sevOff[s]=!ST.sevOff[s];el.classList.toggle('off');refresh();});
}

function select(id,fly){
  const e=EVENTS.find(x=>x._id===id);if(!e)return;ST.sel=id;
  const t=TYPES[e.type]||{};const da=daysAgo(e.date);
  document.getElementById('detail').innerHTML=`
    <div class="dt">${esc(e.title)}</div>
    <span class="badge" style="background:${t.color}22;color:${t.color}">${t.label||e.type}</span>
    <span class="badge" style="background:${SEV[e._sev]}22;color:${SEV[e._sev]}">심각도 ${e._sev}</span>
    <div class="meta"><b>${esc(e.country||'')}</b>${e.region?' · '+esc(e.region):''}<br>${esc(e.date||'')}${da!=null?` (${da==0?'오늘':da+'일 전'})`:''}<br>좌표 ${(+e.lat).toFixed(2)}, ${(+e.lon).toFixed(2)}</div>
    ${e.summary?`<p class="sum">${esc(e.summary)}</p>`:''}
    ${(e.actors&&e.actors.length)?`<div class="actors">${e.actors.map(a=>`<span>${esc(a)}</span>`).join('')}</div>`:''}
    ${e.source_url?`<a class="src" href="${esc(e.source_url)}" target="_blank" rel="noopener">출처: ${esc(e.source_name||'link')} ↗</a>`:''}
    ${window.PV?`<div style="margin-top:10px"><button class="ttsbtn" onclick="PV.speakEvent('${e._id}')">🔊 듣기</button></div>`:''}`;
  if(fly&&MAP){MAP.flyTo({center:[+e.lon,+e.lat],zoom:Math.max(MAP.getZoom(),4),speed:0.8});
    new maplibregl.Popup({closeButton:false,offset:12}).setLngLat([+e.lon,+e.lat]).setHTML(`<b>${esc(e.title)}</b>`).addTo(MAP);}
}

// ===== 탭 전환 =====
let _liqLoaded=false, _mapInit=false;
// nav: 'push'=사용자 클릭(뒤로가기로 이전 탭에 돌아가야 함) · 'none'=popstate(해시 재기록 금지) · 그 외=프로그램 호출(replace)
function switchTab(tab,nav){
  document.querySelectorAll('.ptab').forEach(t=>{
    const selected=t.dataset.tab===tab;
    t.classList.toggle('on',selected); t.setAttribute('aria-selected',String(selected)); t.tabIndex=selected?0:-1;
  });
  const isMap=tab==='map';
  document.getElementById('mapview').hidden=!isMap;
  document.getElementById('sigview').hidden=(tab!=='sig');
  document.getElementById('liqview').hidden=(tab!=='liq');
  document.getElementById('techview').hidden=(tab!=='tech');
  document.getElementById('shipview').hidden=(tab!=='ship');
  document.getElementById('humanview').hidden=(tab!=='human');
  document.getElementById('llmview').hidden=(tab!=='llm');
  document.getElementById('fedview').hidden=(tab!=='fed');
  document.getElementById('headStat').style.display=isMap?'':'none';
  if(isMap && MAP){setTimeout(()=>MAP.resize(),50);}
  if(tab==='sig' && window.PV){ PV.loadSignals(); }
  if(tab==='liq' && !_liqLoaded){ _liqLoaded=true; loadLiq(); }
  if(tab==='tech'){ loadTech2(); }
  if(tab==='ship'){ loadShip(); }
  if(tab==='human'){ loadHuman(); }
  if(tab==='llm'){ loadLLM(); }
  if(tab==='fed'){ loadFed(); }
  routeWrite(tab,nav);
}

// ===== 해시 라우팅 (#<data-tab>) =====
// 탭 목록을 하드코딩하지 않고 DOM 에서 뽑는다 — 나중에 .ptab 이 늘어도 이 코드는 안 고쳐도 되게.
const HASH_DEFAULT_TAB='map';
function tabIds(){ return Array.from(document.querySelectorAll('.ptab[data-tab]'),t=>t.dataset.tab); }
function hashTab(){
  let h=(location.hash||'').replace(/^#/,'');
  try{ h=decodeURIComponent(h); }catch(e){}      // 깨진 퍼센트 인코딩 — 던지지 말고 원문 그대로
  return tabIds().indexOf(h)>=0?h:null;          // 모르는 해시는 null → 호출부가 조용히 무시한다
}
function routeWrite(tab,nav){
  if(nav==='none') return;                       // popstate 로 들어온 전환 — 다시 쓰면 루프가 된다
  if(tabIds().indexOf(tab)<0) return;            // 알 수 없는 탭은 주소창에 남기지 않는다
  const want=tab===HASH_DEFAULT_TAB?'':'#'+tab;  // 기본 탭은 해시를 비운다('#' 쓰레기 금지)
  if(location.hash===want) return;               // 같은 탭 반복 클릭으로 뒤로가기 스택을 늘리지 않는다
  try{
    history[nav==='push'?'pushState':'replaceState'](null,'',location.pathname+location.search+want);
  }catch(e){
    // file:// 등 history API 가 막히는 환경 폴백. 기본 탭이면 '#' 한 글자가 남지만
    // 리로드 없이 지울 방법이 없어 감수한다(동작에는 영향 없음).
    location.hash=want;
  }
}
function applyHashRoute(){
  const t=hashTab();
  if(t) switchTab(t);                            // 유효한 #탭만 반영(replace). 모르는 해시는 손대지 않고 기본 탭 유지
}
// ===== /해시 라우팅 =====
// ===== 🏛 연준 =====
const FED_FILES=['fed_roster.json','fed_positions.json','fed_statements.json','fed_calendar.json','fed_reaction.json','taco.json','portraits.json'];
let _fedHandle=null, _fedTs=0, _fedTimer=null, _fedBusy=false;
function fedTabOn(){ const b=document.getElementById('fedview'); return !!(b && !b.hidden); }
async function fedFetchAll(){
  const bust='?t='+Math.floor(Date.now()/6e5);   // proview 관례 10분 버킷
  const J=p=>fetch('data/fed/'+p+bust).then(r=>r.ok?r.json():null).catch(()=>null);
  const values=await Promise.all(FED_FILES.map(J));
  const data={};
  ['roster','positions','statements','calendar','reaction','taco','photos'].forEach((key,i)=>{ if(values[i]) data[key]=values[i]; });
  return data; // 일시 실패한 파일은 기존 렌더 데이터로 유지
}
async function fedAutoRefresh(){
  // 열린 탭 자동 갱신: 문서가 보이고 fed 탭이 활성일 때만 재fetch(아니면 요청 0)
  if(document.visibilityState!=='visible') return;
  if(!fedTabOn() || !_fedHandle || _fedBusy) return;
  const m=document.querySelector('.fd-modal'); if(m && !m.hidden) return;   // 모달 열려 있으면 재렌더 보류
  _fedBusy=true;
  try{ const d=await fedFetchAll(); if(d.roster||d.positions){ _fedHandle.refresh(d); _fedTs=Date.now(); } }
  catch(e){ console.warn('fed auto', e); }
  finally{ _fedBusy=false; }
}
async function loadFed(){
  const box=document.getElementById('fedview'); if(!box) return;
  if(!_fedTimer){ _fedTimer=setInterval(fedAutoRefresh, 5*60*1000); }   // 인터벌은 1개만
  if(_fedBusy) return;                                                  // 진행 중이면 중복 fetch 금지
  if(box.dataset.loaded){
    if(Date.now()-_fedTs>=6e5) fedAutoRefresh();                        // 재진입 + 10분 경과 → 재fetch 후 refresh()
    // 최신 데이터로 재진입할 때 기존 DOM과 스크롤을 그대로 유지한다.
    return;
  }
  _fedBusy=true;
  box.innerHTML='<p class="hint" style="padding:20px">연준 데이터 로딩…</p>';
  try{
    const d=await fedFetchAll();
    if(!d.roster && !d.positions) throw new Error('core missing');
    box.innerHTML=''; _fedHandle=renderFed(box,d); _fedTs=Date.now(); box.dataset.loaded='1';
  }catch(e){ console.warn('fed', e); box.innerHTML='<p class="hint" style="padding:20px">연준 데이터 준비 중…</p>'; }
  finally{ _fedBusy=false; }
}
// ===== /연준 =====
async function loadLLM(){
  const box=document.getElementById('llmview');
  if(box.dataset.loaded){ if(box.__orResize) box.__orResize(); return; } // 숨긴 동안 바뀐 화면 폭 반영
  box.innerHTML='<p class="hint" style="padding:20px">LLM 랭킹 데이터 로딩…</p>';
  try{ const d=await fetch('data/llm_rankings.json').then(r=>r.json());
    box.innerHTML=''; renderLLM(box, d); box.dataset.loaded='1';
  }catch(e){ console.warn('llm', e); box.innerHTML='<p class="hint" style="padding:20px">LLM 랭킹 데이터 준비 중…</p>'; }
}
async function loadShip(){
  const box=document.getElementById('shipview');
  if(box.dataset.loaded) return; 
  box.innerHTML='<p class="hint" style="padding:20px">해운 데이터 로딩…</p>';
  try{ const d=await fetch('data/shipping.json').then(r=>r.json());
    box.innerHTML=''; renderShipping(box, d); box.dataset.loaded='1';
  }catch(e){ box.innerHTML='<p class="hint" style="padding:20px">해운 데이터 준비 중…</p>'; }
}
async function loadTech2(){
  const box=document.getElementById('techview');
  let d; try{ d=await fetch('data/tech_indicators.json').then(r=>r.json()); }
  catch(e){ box.innerHTML='<p class="hint" style="padding:20px">기술적 지표 수집 중…</p>'; return; }
  const IN={'^KS11':'KOSPI','^KQ11':'KOSDAQ','^GSPC':'S&P 500','^IXIC':'NASDAQ','kospi':'KOSPI','kosdaq':'KOSDAQ','sp500':'S&P 500','nasdaq':'NASDAQ'};
  const ORD=['kospi','nasdaq','kosdaq','sp500'];
  const keys=ORD.filter(k=>d[k]).concat(Object.keys(d).filter(k=>!k.startsWith('_')&&!ORD.includes(k)));
  const cards=keys.map(k=>[k,d[k]]).map(([k,v])=>{
    const nm=IN[k]||v.name||k; const disp=v.disparity||{};
    const rows=Object.entries(disp).map(([ma,o])=>{
      const now=o.now, pct=o.pct;
      const col=pct==null?'#8a93a3':pct>=90?'#ff4d5e':pct>=75?'#ff8a3d':pct<=10?'#4ea1ff':pct<=25?'#59d0a8':'#8a93a3';
      const w=pct==null?0:Math.max(0,Math.min(100,pct));
      return `<div style="margin:7px 0"><div style="display:flex;justify-content:space-between;font-size:11.5px"><span style="color:var(--dim)">${ma.toUpperCase()} 이격도</span><b style="font-family:var(--mono)">${now!=null?now.toFixed(1):'—'} <span style="color:${col}">(${pct!=null?pct.toFixed(0):'—'}%ile)</span></b></div>
      <div style="height:5px;background:var(--panel2);border-radius:3px;margin-top:3px"><div style="width:${w}%;height:100%;border-radius:3px;background:${col}"></div></div></div>`;}).join('');
    const mddo=v.mdd; const mdd=(mddo&&typeof mddo==='object')?mddo.from_peak_pct:mddo;
    const VDK={overheat:'과열',depressed:'침체',oversold:'침체',neutral:'중립'};
    const vd=VDK[String(v.verdict||'').toLowerCase()]||v.verdict||'';
    return `<div style="background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:16px 18px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:14px">${nm}</b>
      <span style="font-size:11px;font-weight:700;color:${/과열/.test(vd)?'#ff4d5e':/침체/.test(vd)?'#4ea1ff':'var(--dim)'}">${vd}</span></div>
      ${rows}
      ${mdd!=null?`<div style="font-size:11px;color:var(--dim);margin-top:8px">전고점 대비 <b style="font-family:var(--mono);color:${mdd<-10?'#ff8a3d':'var(--ink)'}">${Number(mdd).toFixed(1)}%</b>${(mddo&&mddo.peak_date)?` <span style="opacity:.7">(고점 ${mddo.peak_date})</span>`:''} · 10년 최악 ${mddo&&mddo.worst_10y_pct!=null?mddo.worst_10y_pct.toFixed(0)+'%':'—'}</div>`:''}
    </div>`;}).join('');
  box.innerHTML=`<p style="font-size:18px;font-weight:800;margin:0 0 4px">📐 기술적 — 이격도·MDD</p>
  <p class="hint" style="margin:0 0 16px">이격도 = 종가/이동평균×100 · %ile = 10년 백분위(90+ 과열 · 10- 침체) · 일간 자동갱신 ${String(d._updated||'').slice(0,10)}</p>
  <div id="techCharts" style="max-width:1180px;margin:0 0 18px"></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px;max-width:1180px">${cards}</div>`;
  if(window.renderTechCharts){ try{ renderTechCharts(document.getElementById('techCharts'), d); }catch(e){ console.warn('techCharts', e); } }
  try{ const dv=await fetch('data/deriv_kr.json').then(r=>r.ok?r.json():null);
    if(dv && window.renderDeriv){ const el=document.createElement('div'); el.style.marginTop='20px'; box.appendChild(el); renderDeriv(el, dv); } }catch(e){ console.warn('deriv', e); }
}
const mainTabs=Array.from(document.querySelectorAll('.ptab'));
mainTabs.forEach((t,i)=>{
  const panel=document.getElementById(t.dataset.tab+'view');
  if(panel){ panel.setAttribute('role','tabpanel'); panel.setAttribute('aria-labelledby',t.id); }
  t.onclick=()=>switchTab(t.dataset.tab,'push');   // 사용자 클릭만 push — 뒤로가기가 이전 탭으로 돌아가게
  t.addEventListener('keydown',e=>{
    let next=i;
    if(e.key==='ArrowRight') next=(i+1)%mainTabs.length;
    else if(e.key==='ArrowLeft') next=(i+mainTabs.length-1)%mainTabs.length;
    else if(e.key==='Home') next=0;
    else if(e.key==='End') next=mainTabs.length-1;
    else return;
    e.preventDefault(); mainTabs[next].focus(); mainTabs[next].click();
    mainTabs[next].scrollIntoView({block:'nearest',inline:'nearest'});
  });
});
// 뒤로/앞으로 — 해시가 가리키는 탭으로만 전환하고 해시는 다시 쓰지 않는다
window.addEventListener('popstate',()=>{ switchTab(hashTab()||HASH_DEFAULT_TAB,'none'); });

// ===== 💧 유동성 =====
const LIQC={green:'#59d0a8',yellow:'#ffd23d',orange:'#ff8a3d',red:'#ff4d5e',gray:'#8a93a3'};
const LIQLABEL={green:'초록',yellow:'노랑',orange:'주황',red:'빨강',gray:'—'};
function validTgaTarget(raw,asOf){
  return window.PanoptesTgaTarget
    ? window.PanoptesTgaTarget.validateConfig(raw,asOf)
    : null;
}
async function loadTgaTarget(){
  try{
    return await fetch('data/tga_target.json',{cache:'no-store'}).then(r=>r.ok?r.json():null);
  }catch(e){ console.warn('tgaTarget',e); return null; }
}
function attachTgaTarget(d,raw){
  if(!d) return d;
  const model=validTgaTarget(raw,d.updated);
  if(!model) return d;
  d.tga_targets=model; // 구형 fallback 렌더러도 같은 검증 모델 사용
  if(d.sections&&d.sections.funding){
    d.sections.funding.references=d.sections.funding.references||{};
    d.sections.funding.references.treasury_cash_balance_assumptions=model;
  }
  return d;
}
async function loadLiq(){
  const box=document.getElementById('liqview');
  box.innerHTML='<p class="hint" style="padding:20px">유동성 데이터 로딩…</p>';
  const tgaTarget=await loadTgaTarget();
  try{ const d2=await fetch('data/liquidity2.json').then(r=>r.ok?r.json():null);
    if(d2 && window.renderLiq2){ attachTgaTarget(d2,tgaTarget); renderLiq2(box, d2); liqHistStrip(box, d2); return; } }catch(e){ console.warn('liq2', e); }
  let d; try{ d=await fetch('data/liquidity.json').then(r=>r.json()); }
  catch(e){ box.innerHTML='<p class="hint" style="padding:20px">유동성 데이터 준비 중입니다.</p>'; return; }
  attachTgaTarget(d,tgaTarget);
  renderLiq(d);
}
function liqHistStrip(box, d){
  const H=d.hist||{}; const days=Object.keys(H).sort(); if(days.length<2) return;
  const LC={green:'#59d0a8',yellow:'#ffd23d',orange:'#ff8a3d',red:'#ff4d5e'};
  const keys=['repo','bank','tga','rrp','netliq','hy','curve','vix','dxy4w'];
  const rows=keys.map(k=>`<div style="display:flex;align-items:center;gap:6px"><span style="font-size:9.5px;color:var(--dim);width:44px;text-align:right">${k}</span>${days.map(dd=>`<span title="${dd} ${((H[dd]||{}).lights||{})[k]||''}" style="width:7px;height:7px;border-radius:2px;background:${LC[((H[dd]||{}).lights||{})[k]]||'#2a3140'}"></span>`).join('')}</div>`).join('');
  const ov=`<div style="display:flex;align-items:center;gap:6px;margin-top:3px"><span style="font-size:9.5px;font-weight:800;width:44px;text-align:right">종합</span>${days.map(dd=>`<span title="${dd} ${(H[dd]||{}).overall||''}" style="width:7px;height:9px;border-radius:2px;background:${LC[(H[dd]||{}).overall]||'#2a3140'}"></span>`).join('')}</div>`;
  const el=document.createElement('div');
  el.className='comment'; el.style.marginTop='14px';
  el.innerHTML=`<div style="font-size:12px;font-weight:700;margin-bottom:8px">🚦 신호등 히스토리 <span style="color:var(--dim);font-weight:400;font-size:10px">(${days[0]} ~ ${days[days.length-1]} · 일별 축적 중)</span></div><div style="display:flex;flex-direction:column;gap:3px;overflow-x:auto">${rows}${ov}</div>`;
  box.appendChild(el);
}
function liqSpark(series, opts){
  opts=opts||{}; const keys=Object.keys(series).sort(); const vals=keys.map(k=>series[k]);
  if(vals.length<2) return '<div class="hint">데이터 부족</div>';
  const W=opts.w||560,H=opts.h||120,pad=opts.pad||4;
  const refs=(opts.refs||[]).filter(r=>r&&Number.isFinite(Number(r.v)));
  if(opts.ref!=null&&Number.isFinite(Number(opts.ref))) refs.push({v:Number(opts.ref),c:opts.refColor||'#8a93a3'});
  const domain=vals.concat(refs.filter(r=>r.domain).map(r=>Number(r.v)));
  const vr=VizScale.niceScale(domain,{class:'range_focus',unit:opts.unit}),mn=vr.min,mx=vr.max,rg=mx-mn;
  const x=i=>pad+(W-2*pad)*i/(vals.length-1), y=v=>pad+(H-2*pad)*(1-(v-mn)/rg);
  let pts='',pen=false;vals.forEach((v,i)=>{if(typeof v!=='number'||!isFinite(v)){pen=false;return;}pts+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)+' ';pen=true;});
  const vst=VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),color:opts.color||'#2bc0d4',metric_index:opts.metric_index||0},opts.role||'actual'),col=vst.borderColor;
  const ref=refs.filter(r=>r.v>=mn&&r.v<=mx).map(r=>{const ry=y(r.v);return `<line x1="${pad}" y1="${ry}" x2="${W-pad}" y2="${ry}" stroke="${r.c||'#8a93a3'}" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/>`;}).join('');
  const last=vals[vals.length-1];
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px">
    ${ref}<path d="${pts}" fill="none" stroke="${col}" stroke-width="${vst.borderWidth}" stroke-dasharray="${(vst.borderDash||[]).join(' ')}"/>
    ${last!=null?`<circle cx="${x(vals.length-1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="3" fill="${col}"/>`:""}</svg>${vr.axis_note?`<div style="font-size:10px;color:var(--ink,#e9eef5)">${vr.axis_note}</div>`:""}`;
}
function renderLiq(d){
  const box=document.getElementById('liqview');
  const L=d.latest||{}, C=d.computed||{}, lights=d.lights||{}, ov=d.overall||'gray';
  const V=n=>((L[n]||{}).value);
  const tgaModel=d.tga_targets&&d.tga_targets.release?d.tga_targets:null;
  const tgaDisplays=tgaModel&&window.PanoptesTgaTarget
    ? window.PanoptesTgaTarget.displayModels(tgaModel)
    : [];
  const tgaRefs=[{v:900,c:'#e0a24a'}];   // TGA 데이터선(주황 #ff8a3d)과 구분되는 호박색
  if(tgaModel&&tgaModel.next&&tgaDisplays[1]) tgaRefs.unshift({v:Number(tgaModel.next.value),c:'#8793a3',domain:true});
  if(tgaModel&&tgaModel.current&&tgaDisplays[0]) tgaRefs.unshift({v:Number(tgaModel.current.value),c:'#c6cfda',domain:true});
  const tgaRefLabel=tgaDisplays.length
    ? `${tgaDisplays.map(v=>v.legendLabel).join(' / ')} / 호박색 점선 = Panoptes 내부 경계 900B`
    : '미 재무부 공식 분기말 가정 업데이트 대기 / 호박색 점선 = Panoptes 내부 경계 900B';
  const card=(title,val,sub,light)=>`<div class="liqcard" style="border-top:3px solid ${LIQC[light||'gray']}">
    <div class="lqt">${title} ${light?`<span class="lqdot" style="background:${LIQC[light]}"></span>`:''}</div>
    <div class="lqv">${val}</div><div class="lqs">${sub||''}</div></div>`;
  const iorb=V('IORB');   // IORB 결측 시 폴백 렌더러 전체가 죽지 않도록 가드
  const charts=[
    ['NETLIQ','Net Liquidity','#2bc0d4',[],'$'+(C.net_liquidity/1000).toFixed(2)+'T',''],
    ['TGA','TGA (재무부 현금)','#ff8a3d',tgaRefs,V('TGA').toFixed(0)+'B',tgaRefLabel],
    ['RRP','RRP (역레포)','#ffd23d',[],V('RRP').toFixed(1)+'B',''],
    ['SOFR','SOFR vs IORB','#ff4d5e',iorb!=null?[{v:iorb,c:'#8a93a3'}]:[],V('SOFR').toFixed(2)+'%',iorb!=null?`IORB ${iorb.toFixed(2)}`:''],
    ['EFFR','EFFR vs IORB','#4ea1ff',iorb!=null?[{v:iorb,c:'#8a93a3'}]:[],V('EFFR').toFixed(2)+'%',iorb!=null?`IORB ${iorb.toFixed(2)}`:''],
    ['RESERVES','지급준비금','#59d0a8',[],(V('RESERVES')/1000).toFixed(2)+'T',''],
  ].map(([k,t,c,refs,cur,refLabel])=>`<div class="liqchart"><div class="lct"><span>${t}</span><b style="color:${c}">${cur}</b>${refLabel?`<span class="lcref">— ${esc(refLabel)}</span>`:''}</div>
    ${liqSpark(d.series[k]||{},{color:c,refs:refs,unit:k==='SOFR'||k==='EFFR'?'%':'USD B',role:k==='NETLIQ'?'derived':'actual',metric_index:['NETLIQ','TGA','RRP','SOFR','EFFR','RESERVES'].indexOf(k)})}</div>`).join('');
  box.innerHTML=`<style>
    .liqhead{display:flex;align-items:center;gap:14px;margin-bottom:6px}
    .liqhead h2{font-size:20px;font-weight:800}
    .ovbadge{font-size:12px;font-weight:700;padding:4px 12px;border-radius:999px}
    .liqsub{color:var(--dim);font-size:12.5px;margin-bottom:20px}
    .lights{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}
    .liqcard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 16px;min-width:150px;flex:1}
    .lqt{font-size:11px;color:var(--dim);font-weight:600;display:flex;align-items:center;gap:6px}
    .lqdot{width:9px;height:9px;border-radius:50%;display:inline-block}
    .lqv{font-family:var(--mono);font-size:21px;font-weight:750;margin-top:4px}
    .lqs{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:2px}
    .liqgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-bottom:26px}
    .liqchart{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
    .lct{display:flex;align-items:baseline;gap:8px;font-size:12.5px;font-weight:650;margin-bottom:8px;flex-wrap:wrap}
    .lct b{font-family:var(--mono);font-size:14px}
    .lcref{font-family:var(--mono);font-size:10px;color:var(--dim);margin-left:auto;text-align:right;overflow-wrap:anywhere}
    @media(max-width:600px){.lcref{flex-basis:100%;margin-left:0;text-align:left}}
    .comment{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 24px;max-width:900px}
    .comment pre{font-family:var(--sans);font-size:13.5px;line-height:1.85;white-space:pre-wrap;color:#cdd6de;margin:0}
    .comment .cmeta{font-family:var(--mono);font-size:11px;color:var(--dim);margin-top:14px;border-top:1px solid var(--line);padding-top:10px}
  </style>
  <div class="liqhead"><h2>💧 유동성 대시보드</h2>
    <span class="ovbadge" style="background:${LIQC[ov]}22;color:${LIQC[ov]}">종합 ${LIQLABEL[ov]}불</span></div>
  <p class="liqsub">Net Liquidity = 연준 총자산 − TGA − RRP · FRED 실시간 · 매일 자동 갱신 · 업데이트 ${d.updated||'—'}</p>
  <div class="lights">
    ${card('레포 (SOFR−IORB)',(C.sofr_iorb>=0?'+':'')+C.sofr_iorb+'%p',C.sofr_iorb>0?'IORB 위 = 스트레스':'IORB 아래 = 안정',lights.repo)}
    ${card('은행 (EFFR−IORB)',(C.effr_iorb>=0?'+':'')+C.effr_iorb+'%p',C.effr_iorb<0?'IORB 아래 = 정상':'경계',lights.bank)}
    ${card('TGA 흡수압력',V('TGA').toFixed(0)+'B',lights.tga==='green'?'내부 기준 900B 미만':'내부 경계 초과·재축적 압력',lights.tga)}
    ${card('RRP 완충재',V('RRP').toFixed(1)+'B',V('RRP')<20?'사실상 고갈':'남아있음',lights.rrp)}
    ${card('Net Liq 방향','$'+(C.net_liquidity/1000).toFixed(2)+'T',(C.net_liquidity_chg_1w>=0?'+':'')+C.net_liquidity_chg_1w+'B / 1주',lights.netliq)}
  </div>
  <div class="liqgrid">${charts}</div>
  <div class="comment"><pre>${(d.commentary||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}</pre>
    <div class="cmeta">자동 생성 해석 — 실시간 FRED 수치 기반. 투자 조언 아님. #TGA #RRP #SOFR #IORB #EFFR #NetLiquidity</div></div>`;
}

// ===== 👥 인간지표 (human signals — 한국인/외인·기관이 실제로 사고판 것) =====
const HSD={buy:{l:'순매수',c:'#59d0a8'},sell:{l:'순매도',c:'#ff4d5e'},hold:{l:'보관잔액',c:'#4ea1ff'}};
const HAX=[['total_pct','① 전체대비'],['stock_pct','② 종목대비'],['mcap_pct','③ 시총대비']];
const HST={scope:'overseas',inv:'foreign',side:'buy',sort:'value'};
function hUsd(v){if(v==null)return '—';const a=Math.abs(v);const t=a>=1e9?(a/1e9).toFixed(2)+'B':a>=1e6?(a/1e6).toFixed(1)+'M':(a/1e3).toFixed(0)+'K';return (v<0?'-$':'$')+t;}
function hKrw(mn){if(mn==null)return '—';const a=Math.abs(mn);const t=a>=1e6?(a/1e6).toFixed(2)+'조':a>=100?(a/100).toFixed(0)+'억':a+'백만';return (mn<0?'-':'')+t;}
function hPct(p){return p==null?'—':(p>=10?p.toFixed(1):p>=1?p.toFixed(2):p.toFixed(3))+'%';}
function hYmd(s){return s&&/^\d{8}$/.test(s)?s.slice(0,4)+'-'+s.slice(4,6)+'-'+s.slice(6):(s||'—');}
function hRows(d,st){
  const src=st.scope==='overseas'?(d.overseas||{}):((d.domestic||{})[st.inv]||{});
  const rows=(src[st.side]||[]).slice();
  if(st.sort!=='value')rows.sort((a,b)=>(((b.axes||{})[st.sort])||-1)-(((a.axes||{})[st.sort])||-1));
  return rows;
}
function humanHTML(d,st){
  const ovs=st.scope==='overseas', src=ovs?(d.overseas||{}):(d.domestic||{});
  const rows=hRows(d,st), sc=HSD[st.side].c;
  const maxA={};HAX.forEach(([k])=>maxA[k]=Math.max.apply(null,rows.map(r=>((r.axes||{})[k])||0).concat(0)));
  const chip=(k,v,l,on)=>`<span class="hchip${on?' on':''}" data-hk="${k}" data-hv="${v}">${l}</span>`;
  const sides=ovs?['buy','sell','hold']:['buy','sell'];
  const tr=rows.map(r=>{
    const val=ovs?(st.side==='hold'?r.hold_usd:st.side==='sell'?-(r.sell_usd||0):r.net_buy_usd):r.value_mn;
    const sub=ovs?`${esc(r.nation||'')}${st.side==='sell'?' · 순 '+hUsd(r.net_buy_usd):''}`
                 :`${esc(r.market||'')} ${esc(r.code||'')}`;
    const cells=HAX.map(([k])=>{const p=(r.axes||{})[k];const w=p&&maxA[k]?Math.max(0,100*p/maxA[k]):0;
      return `<td class="hx"><span class="hxv">${hPct(p)}</span><div class="hxb"><div style="width:${w}%;background:${sc}"></div></div></td>`;}).join('');
    return `<tr><td class="hr">${r.rank||''}</td><td class="hn">${esc(r.name)}<span class="hs">${sub}</span></td>
      <td class="hv" style="color:${val<0?'#ff4d5e':val>0?'#59d0a8':'var(--dim)'}">${ovs?hUsd(val):hKrw(val)}</td>${cells}</tr>`;
  }).join('')||`<tr><td colspan="6"><p class="hint" style="padding:14px">데이터 없음 — 다음 배치에서 재시도</p></td></tr>`;
  const meta=ovs
    ?`SEIBRO 예탁결제 ${hYmd(src.date)}${st.side==='hold'?` · 보관 ${hYmd(src.hold_date)}`:''} · USD · ${esc(src.basis||'')}`
    :`네이버 투자자별 ${esc(src.date||'—')} · 단위 백만원 · ${esc(src.note||'')}`;
  const AXD=d.axes||{};
  return `<style>
    .hchips{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
    .hchips .hl{font-size:10.5px;color:var(--dim);font-weight:700;margin-right:2px}
    .hchip{font-size:11.5px;padding:4px 11px;border:1px solid var(--line);border-radius:999px;cursor:pointer;color:var(--dim);transition:.13s}
    .hchip:hover{border-color:var(--accent);color:var(--accent)}
    .hchip.on{background:rgba(43,192,212,.14);border-color:var(--accent);color:var(--accent);font-weight:700}
    .hwrap{max-width:1180px;background:var(--panel);border:1px solid var(--line);border-radius:13px;overflow:hidden;margin-top:14px}
    .htable{width:100%;border-collapse:collapse;font-size:12.5px}
    .htable th{font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim);text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--panel2)}
    .htable td{padding:7px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
    .htable tr:last-child td{border-bottom:none}
    .htable tr:hover td{background:rgba(127,150,170,.05)}
    .hr{font-family:var(--mono);font-size:11px;color:var(--dim);width:34px}
    .hn{font-weight:650;line-height:1.25}
    .hn .hs{display:block;font-family:var(--mono);font-size:10px;font-weight:400;color:var(--dim);margin-top:1px}
    .hv{font-family:var(--mono);font-weight:700;white-space:nowrap;text-align:right}
    .hx{width:118px}.hxv{font-family:var(--mono);font-size:10.5px;color:var(--ink)}
    .hxb{height:4px;background:var(--panel2);border-radius:2px;margin-top:3px}.hxb div{height:100%;border-radius:2px}
    .hmeta{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:10px}
  </style>
  <p style="font-size:18px;font-weight:800;margin:0 0 4px">👥 인간지표 — 사람들이 실제로 산/판 종목</p>
  <p class="hint" style="margin:0 0 14px">해외=한국인 해외주식 결제·보관 TOP(SEIBRO) · 국내=외국인/기관 순매매 상위(네이버, 개인은 무인증 소스 부재) · 3축 = ①전체 거래대금 대비 ②종목 거래대금 대비 ③시총 대비</p>
  <div class="hchips" style="margin-bottom:8px">${chip('scope','overseas','🌎 해외 (한국인)',ovs)}${chip('scope','domestic','🇰🇷 국내 (외인·기관)',!ovs)}
    <span style="width:10px"></span>${sides.map(s=>chip('side',s,HSD[s].l,st.side===s)).join('')}
    ${ovs?'':`<span style="width:10px"></span>${[['foreign','외국인'],['institution','기관']].map(([v,l])=>chip('inv',v,l,st.inv===v)).join('')}`}</div>
  <div class="hchips"><span class="hl">정렬</span>${[['value','금액순']].concat(HAX.map(([k,l])=>[k,l+'순'])).map(([v,l])=>chip('sort',v,l,st.sort===v)).join('')}</div>
  <div class="hwrap"><table class="htable">
    <tr><th>#</th><th>종목</th><th style="text-align:right">${ovs&&st.side==='hold'?'보관금액':'순매매금액'}</th>${HAX.map(([k,l])=>`<th title="${esc(AXD[k]||'')}">${l}</th>`).join('')}</tr>
    ${tr}</table></div>
  <div class="hmeta">${meta} · 갱신 ${esc(String(d.updated||'—'))}${ovs?'':` · 시장 전체 거래대금 ${hKrw((src.market_trade_total_mn||0))}`}</div>`;
}
function renderHuman(box,d){
  box.innerHTML=humanHTML(d,HST);
  box.querySelectorAll('.hchip').forEach(el=>el.onclick=()=>{
    const k=el.dataset.hk,v=el.dataset.hv;
    HST[k]=v;
    if(k==='scope'&&v==='domestic'&&HST.side==='hold')HST.side='buy';
    if(k==='scope'&&v==='overseas'&&HST.sort==='mcap_pct')HST.sort='value'; // 해외는 ③시총 없음
    renderHuman(box,d);
  });
}
async function loadHuman(){
  const box=document.getElementById('humanview');
  if(box.dataset.loaded) return;
  box.innerHTML='<p class="hint" style="padding:20px">인간지표 데이터 로딩…</p>';
  try{ const d=await fetch('data/human.json').then(r=>r.json());
    renderHuman(box,d); box.dataset.loaded='1';
  }catch(e){ console.warn('human', e); box.innerHTML='<p class="hint" style="padding:20px">인간지표 데이터 준비 중…</p>'; }
}
// ===== /인간지표 =====

// 초기 해시 적용은 boot() 의 데이터 준비가 끝난 뒤. 로드 직후 #탭 으로 들어오면
// 지연 렌더 차트가 빈 데이터로 굳을 수 있어서다. boot() 가 실패해도 라우팅은 살아야 하므로 finally.
boot().finally(applyHashRoute);
