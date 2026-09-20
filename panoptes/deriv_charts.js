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
/* deriv_charts.js — 파생·수급 지표 차트 (의존성 0, 순수 SVG)
 * 전역: window.renderDeriv(el, data)
 *   data = deriv_kr.json 전체 객체
 *   { _src:{...}, vkospi:{"YYYY-MM-DD":62.41},
 *     opt_net:{"YYYY-MM-DD":{"<투자자>":{"call":억원,"put":억원}}},
 *     fut_net:{"YYYY-MM-DD":{"<투자자>":억원}}, oi:{...}, asof:"..." }
 * 로드 시 부작용 없음(함수 정의만). 외부 라이브러리·fetch 사용 안 함.
 * 스타일 문법은 tech_charts.js(파놉테스 기존 렌더러)와 동일.
 */
(function () {
  'use strict';

  var PERIODS = [
    { k: '1M', n: 21 }, { k: '3M', n: 63 }, { k: '6M', n: 126 },
    { k: '1Y', n: 252 }, { k: '3Y', n: 756 }
  ];
  var DEFAULT_PERIOD = '6M';
  var FLOW_MAX = 120;   // 수급 차트는 최대 120거래일(가독성)
  var CUM_N = 20;       // "최근 N일 누적" 기준

  var VK_STABLE = 60;   // 안정화 임계
  var VK_HI = 75;       // 극단 공포
  var VK_LO = 40;       // 정상권 복귀

  var C = {
    vk: '#ffb545',
    call: '#ff4d5e',
    put: '#3d63d6',
    frgn: '#ff4d5e',
    trust: '#59d0a8',
    fin: '#4ea1ff',
    alt: ['#c58aff', '#f0a6c0', '#7ad0e6', '#e0c15a', '#8a93a3']
  };

  var MONO = 'var(--mono,ui-monospace,SFMono-Regular,Menlo,monospace)';
  var DIM = '#8a93a3';

  var CSS = [
    '.dv-wrap{display:flex;flex-direction:column;gap:12px}',
    '.dv-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}',
    '.dv-title{font-size:14px;font-weight:750;letter-spacing:-.01em}',
    '.dv-asof{font-family:' + MONO + ';font-size:10.5px;color:var(--dim,#8a93a3);font-weight:600}',
    '.dv-chips{display:flex;gap:6px}',
    '.dv-chip{font:inherit;font-size:11.5px;line-height:1.5;padding:3px 9px;border:1px solid var(--line,#2a2f3a);',
    'border-radius:999px;background:transparent;color:var(--dim,#8a93a3);cursor:pointer;transition:all .12s}',
    '.dv-chip:hover{border-color:rgba(43,192,212,.5);color:#2bc0d4}',
    '.dv-chip.on{background:rgba(43,192,212,.14);color:#2bc0d4;border-color:rgba(43,192,212,.45)}',
    '.dv-card{background:var(--panel,#12161d);border:1px solid var(--line,#2a2f3a);border-radius:13px;padding:14px 16px}',
    '.dv-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}',
    '@media (max-width:920px){.dv-grid{grid-template-columns:1fr}}',
    '.dv-cardhead{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px}',
    '.dv-t{font-size:12px;font-weight:650}',
    '.dv-t em{font-style:normal;color:var(--dim,#8a93a3);font-weight:550}',
    '.dv-v{font-family:' + MONO + ';font-size:12.5px;font-weight:700;white-space:nowrap}',
    '.dv-plot{position:relative}',
    '.dv-plot svg{display:block;width:100%;height:auto;overflow:visible}',
    '.dv-guide{opacity:0}',
    '.dv-plot.on .dv-guide{opacity:1}',
    '.dv-tip{position:absolute;top:2px;transform:translateX(-50%);pointer-events:none;opacity:0;',
    'background:rgba(10,12,16,.92);border:1px solid var(--line,#2a2f3a);border-radius:6px;padding:3px 7px;',
    'font-family:' + MONO + ';font-size:10.5px;color:#e6e9ef;white-space:nowrap;z-index:3;transition:opacity .1s}',
    '.dv-plot.on .dv-tip{opacity:1}',
    '.dv-empty{font-size:11.5px;color:var(--dim,#8a93a3);padding:10px 0}',
    '.dv-legend{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}',
    '.dv-lg{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--dim,#8a93a3)}',
    '.dv-lgd{width:11px;height:2.5px;border-radius:2px;flex:none}',
    '.dv-lg b{font-family:' + MONO + ';font-weight:700;font-size:10.5px}',
    '.dv-badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}',
    '.dv-badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;border:1px solid;line-height:1.5}',
    '.dv-note{font-size:11.5px;line-height:1.75;color:#cfd5e0;margin-top:8px}',
    '.dv-note b{color:#e6e9ef}',
    '.dv-foot{font-size:10.5px;line-height:1.7;color:var(--dim,#8a93a3);margin-top:8px;',
    'border-top:1px dashed var(--line,#2a2f3a);padding-top:8px}',
    '.dv-key{background:var(--panel,#12161d);border:1px solid rgba(43,192,212,.35);border-radius:13px;padding:13px 16px}',
    '.dv-keyt{font-size:12.5px;font-weight:750;color:#2bc0d4;margin-bottom:8px}',
    '.dv-keyrow{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
    '@media (max-width:760px){.dv-keyrow{grid-template-columns:1fr}}',
    '.dv-keyitem{border:1px solid var(--line,#2a2f3a);border-radius:10px;padding:9px 11px;display:flex;gap:9px;align-items:flex-start}',
    '.dv-ox{font-family:' + MONO + ';font-size:17px;font-weight:800;line-height:1.15;flex:none}',
    '.dv-kq{font-size:11.5px;font-weight:700;color:#e6e9ef}',
    '.dv-kr{font-family:' + MONO + ';font-size:10.5px;color:var(--dim,#8a93a3);margin-top:2px;line-height:1.6}',
    '.dv-src{font-size:10px;color:var(--dim,#8a93a3);font-family:' + MONO + '}'
  ].join('');

  function ensureCss(doc) {
    if (!doc || doc.getElementById('derivChartsCss')) return;
    var s = doc.createElement('style');
    s.id = 'derivChartsCss';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  /* ── 포맷/유틸 ─────────────────────────────────────────── */
  function mnum(v) { return String(v).replace('-', '−'); }
  function fx(v, d) { return mnum(v.toFixed(d)); }
  function tickTxt(v) { return mnum(Math.abs(v % 1) < 0.05 ? v.toFixed(0) : v.toFixed(1)); }
  function tail(a, n) { return a.length > n ? a.slice(a.length - n) : a.slice(); }
  function comma(v) {
    var s = String(Math.abs(Math.round(v))), o = '', c = 0;
    for (var i = s.length - 1; i >= 0; i--) {
      o = s.charAt(i) + o;
      if (++c % 3 === 0 && i > 0) o = ',' + o;
    }
    return (v < 0 ? '−' : '') + o;
  }
  function signed(v) { return (v > 0 ? '+' : '') + comma(v); }
  function sum(a) { var t = 0; for (var i = 0; i < a.length; i++) t += a[i] || 0; return t; }
  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  function niceTicks(lo, hi, count) {
    var span = hi - lo;
    if (!(span > 0)) return [lo];
    for (var c = count; c >= 2; c--) {
      var raw = span / c;
      var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
      var nrm = raw / mag;
      var step = (nrm <= 1 ? 1 : nrm <= 2 ? 2 : nrm <= 2.5 ? 2.5 : nrm <= 5 ? 5 : 10) * mag;
      var out = [];
      for (var v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
        out.push(Math.round(v * 1e6) / 1e6);
      }
      if (out.length <= 5) return out;
    }
    return [];
  }

  /* ── 투자자명 정규화 ────────────────────────────────────── */
  var ALIAS = {
    '외국인투자자': '외국인', '외국인계': '외국인', '외인': '외국인',
    '기타외국인': '기타외국인',
    '기관': '기관계', '기관합계': '기관계', '기관투자자': '기관계',
    '투자신탁': '투신', '자산운용': '투신', '집합투자': '투신',
    '증권': '금융투자', '금융투자업': '금융투자',
    '연기금등': '연기금', '연기금 등': '연기금',
    '개인투자자': '개인'
  };
  // 합산(중복 집계) 항목 — 카운터파티 랭킹에서 제외
  var AGG = { '기관계': 1, '전체': 1, '합계': 1, '기타계': 1, '전체합계': 1 };

  function canon(k) {
    var s = String(k).replace(/\s+/g, '');
    return ALIAS[s] || s;
  }

  /* ── 범용 라인 플롯 ─────────────────────────────────────── */
  /* spec: {w,h,dates,series:[{name,color,vals}],refs:[{v,c,txt}],base,unit,dec,lastLabel} */
  function buildPlot(doc, spec) {
    var DIM=VIZ_CONTRACT.tokens.text[vizPhalanxTheme()];
    var W = spec.w || 520, H = spec.h || 176;
    var PL = 10, PR = spec.pr || 46, PT = 16, PB = 22;
    var PW = W - PL - PR, PH = H - PT - PB;
    var dates = spec.dates, n = dates.length;
    var ser=spec.series.map(function(r,i){var v=Object.assign({},r),st=VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),color:r.color,metric_index:i},'actual');v.color=st.borderColor;v.w=st.borderWidth;v.dash=(st.borderDash||[]).join(' ');v.name=r.name+' ['+(spec.unit||'지수')+' · 실적]';return v;}),dec=spec.dec==null?1:spec.dec;

    var plot = doc.createElement('div');
    plot.className = 'dv-plot';
    if (n < 2) {
      var e = doc.createElement('div');
      e.className = 'dv-empty';
      e.textContent = '표시할 데이터가 없습니다.';
      plot.appendChild(e);
      return plot;
    }

    var dmin = Infinity, dmax = -Infinity, si, i;
    for (si = 0; si < ser.length; si++) {
      for (i = 0; i < ser[si].vals.length; i++) {
        var v = ser[si].vals[i];
        if (!isNum(v)) continue;
        if (v < dmin) dmin = v;
        if (v > dmax) dmax = v;
      }
    }
    if (!isFinite(dmin)) { dmin = 0; dmax = 1; }
    var lo = dmin, hi = dmax;
    var refs = spec.refs || [];
    for (i = 0; i < refs.length; i++) {
      if (refs[i].force) { lo = Math.min(lo, refs[i].v); hi = Math.max(hi, refs[i].v); }
    }
    if (spec.base != null) { lo = Math.min(lo, spec.base); hi = Math.max(hi, spec.base); }
    var all=[];ser.forEach(function(r){r.vals.forEach(function(v){if(isNum(v))all.push(v);});});all.push(lo,hi);
    var vr=VizScale.niceScale(all,{class:spec.base===0?'symmetric':'range_focus',unit:spec.unit,reference:spec.base});lo=vr.min;hi=vr.max;

    function Y(val) { return PT + (1 - (val - lo) / (hi - lo)) * PH; }
    function X(idx) { return n < 2 ? PL + PW : PL + (idx / (n - 1)) * PW; }

    var s = [];
    s.push('<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + (spec.aria || '차트') + '">');

    var lastY = [];
    for (si = 0; si < ser.length; si++) {
      var lv = null;
      for (i = ser[si].vals.length - 1; i >= 0; i--) { if (isNum(ser[si].vals[i])) { lv = ser[si].vals[i]; break; } }
      lastY.push(lv == null ? null : Y(lv));
    }
    function nearLast(y) {
      for (var q = 0; q < lastY.length; q++) if (lastY[q] != null && Math.abs(lastY[q] - y) < 9) return true;
      return false;
    }

    // 가로 그리드 + 우측 y 라벨
    var ticks = vr.ticks;
    for (var ti = 0; ti < ticks.length; ti++) {
      var ty = Y(ticks[ti]);
      s.push('<line x1="' + PL + '" y1="' + ty.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ty.toFixed(1) +
        '" stroke="var(--line,#2a2f3a)" stroke-width="1" opacity=".55"/>');
      if (!nearLast(ty)) {
        s.push('<text x="' + (PL + PW + 5) + '" y="' + (ty + 3.2).toFixed(1) + '" fill="' + DIM +
          '" font-size="10" style="font-family:' + MONO + '">' + tickTxt(ticks[ti]) + '</text>');
      }
    }

    // 기준선(0선 등)
    if (spec.base != null && spec.base > lo && spec.base < hi) {
      s.push('<line x1="' + PL + '" y1="' + Y(spec.base).toFixed(1) + '" x2="' + (PL + PW) + '" y2="' +
        Y(spec.base).toFixed(1) + '" stroke="' + DIM + '" stroke-width="1.1" opacity=".45"/>');
    }

    // 점선 기준선 + 우측끝 라벨
    for (var ri = 0; ri < refs.length; ri++) {
      var rf = refs[ri];
      if (rf.v <= lo || rf.v >= hi) continue;
      var ry = Y(rf.v);
      s.push('<line x1="' + PL + '" y1="' + ry.toFixed(1) + '" x2="' + (PL + PW) + '" y2="' + ry.toFixed(1) +
        '" stroke="' + rf.c + '" stroke-width="' + (rf.w || 1) + '" stroke-dasharray="' + (rf.dash || '3 3') +
        '" opacity="' + (rf.o || 0.8) + '"/>');
      if (rf.txt) {
        s.push('<text x="' + (PL + PW - 4) + '" y="' + (ry - 3.5).toFixed(1) + '" text-anchor="end" fill="' +
          rf.c + '" font-size="9.5" opacity=".95">' + rf.txt + '</text>');
      }
    }

    // 라인
    for (si = 0; si < ser.length; si++) {
      var vals = ser[si].vals, d = '', pen = false;
      for (i = 0; i < n; i++) {
        var vv = vals[i];
        if (!isNum(vv)) { pen = false; continue; }
        d += (pen ? 'L' : 'M') + X(i).toFixed(2) + ' ' + Y(vv).toFixed(2);
        pen = true;
      }
      if (d) {
        s.push('<path d="' + d + '" fill="none" stroke="' + ser[si].color +
          '" stroke-width="' + (ser[si].w || 1.6) + '" stroke-dasharray="'+ser[si].dash+'" stroke-linejoin="round" stroke-linecap="round"/>');
      }
    }

    // x축 라벨 — 3개월 이하 구간은 MM-DD, 그 이상은 YYYY-MM
    var xn = n >= 5 ? 5 : 4;
    var short = n <= 70;
    for (var xi = 0; xi < xn; xi++) {
      var idx = Math.round(xi * (n - 1) / (xn - 1));
      var anc = xi === 0 ? 'start' : (xi === xn - 1 ? 'end' : 'middle');
      s.push('<text x="' + X(idx).toFixed(1) + '" y="' + (H - 5) + '" text-anchor="' + anc + '" fill="' + DIM +
        '" font-size="10" style="font-family:' + MONO + '">' +
        (short ? dates[idx].slice(5) : dates[idx].slice(0, 7)) + '</text>');
    }

    // 마지막 점 + 값 라벨
    for (si = 0; si < ser.length; si++) {
      if (lastY[si] == null) continue;
      var lval = null;
      for (i = ser[si].vals.length - 1; i >= 0; i--) { if (isNum(ser[si].vals[i])) { lval = ser[si].vals[i]; break; } }
      s.push(vizPhalanxSvgMarker(X(n-1),lastY[si],VizSeries.applySeriesStyle({theme:vizPhalanxTheme(),metric_index:si},'actual'),3));
      if (spec.lastLabel !== false) {
        s.push('<text x="' + (X(n - 1) + 5).toFixed(1) + '" y="' + (lastY[si] + 3.4).toFixed(1) + '" fill="' +
          ser[si].color + '" font-size="9.5" font-weight="700" style="font-family:' + MONO + '">' +
          (spec.money ? signed(lval) : fx(lval, dec)) + '</text>');
      }
    }

    // 호버 가이드
    var g = ['<g class="dv-guide"><line class="dv-gl" x1="0" y1="' + PT + '" x2="0" y2="' + (PT + PH) +
      '" stroke="' + DIM + '" stroke-width="1" stroke-dasharray="2 2" opacity=".7"/>'];
    for (si = 0; si < ser.length; si++) {
      g.push('<circle class="dv-gd" cx="0" cy="0" r="2.8" fill="' + ser[si].color +
        '" stroke="var(--panel,#12161d)" stroke-width="1.2"/>');
    }
    g.push('</g>');
    s.push(g.join(''));
    s.push('</svg>');

    plot.innerHTML=s.join('')+(vr.axis_note?'<div style="font-size:10px;color:var(--ink,#e9eef5)">'+vr.axis_note+'</div>':'');
    var tip = doc.createElement('div');
    tip.className = 'dv-tip';
    plot.appendChild(tip);

    var svg = plot.querySelector('svg');
    var gl = plot.querySelector('.dv-gl');
    var gds = plot.querySelectorAll('.dv-gd');

    function move(ev) {
      var r = svg.getBoundingClientRect();
      if (!r.width) return;
      var px = (ev.clientX - r.left) / r.width * W;
      var idx = Math.round((px - PL) / PW * (n - 1));
      if (idx < 0) idx = 0; else if (idx > n - 1) idx = n - 1;
      var gx = X(idx);
      gl.setAttribute('x1', gx); gl.setAttribute('x2', gx);
      var txt = dates[idx];
      for (var q = 0; q < ser.length; q++) {
        var val = ser[q].vals[idx];
        if (isNum(val)) {
          gds[q].setAttribute('cx', gx);
          gds[q].setAttribute('cy', Y(val));
          gds[q].setAttribute('opacity', '1');
          txt += ' · ' + (ser.length > 1 ? ser[q].name + ' ' : '') +
            (spec.money ? signed(val) : fx(val, dec)) + (spec.unit || '');
        } else {
          gds[q].setAttribute('opacity', '0');
        }
      }
      tip.textContent = txt;
      var lp = gx / W * r.width;
      tip.style.left = Math.max(60, Math.min(r.width - 60, lp)) + 'px';
      plot.className = 'dv-plot on';
    }
    function leave() { plot.className = 'dv-plot'; }
    svg.addEventListener('mousemove', move);
    svg.addEventListener('mouseleave', leave);
    plot.addEventListener('mouseleave', leave);

    return plot;
  }

  /* ── 데이터 정리 ────────────────────────────────────────── */
  function seriesFromMap(map) {
    var dates = [], vals = [], k;
    if (!map) return { dates: dates, vals: vals };
    var keys = [];
    for (k in map) if (Object.prototype.hasOwnProperty.call(map, k)) keys.push(k);
    keys.sort();
    for (var i = 0; i < keys.length; i++) {
      var v = map[keys[i]];
      if (typeof v === 'string') v = parseFloat(v);
      if (!isNum(v)) continue;
      dates.push(keys[i]);
      vals.push(v);
    }
    return { dates: dates, vals: vals };
  }

  /* opt_net → {dates, inv:{name:{call:[],put:[]}}, names:[]} */
  function collectOpt(optNet) {
    var dates = [], k, i, j;
    if (!optNet) return { dates: [], inv: {}, names: [] };
    for (k in optNet) if (Object.prototype.hasOwnProperty.call(optNet, k)) dates.push(k);
    dates.sort();
    var inv = {}, names = [];
    for (i = 0; i < dates.length; i++) {
      var row = optNet[dates[i]] || {};
      for (k in row) {
        if (!Object.prototype.hasOwnProperty.call(row, k)) continue;
        var nm = canon(k);
        if (!inv[nm]) {
          inv[nm] = { call: [], put: [] };
          for (j = 0; j < i; j++) { inv[nm].call.push(null); inv[nm].put.push(null); }
          names.push(nm);
        }
      }
      for (j = 0; j < names.length; j++) {
        var cell = null, kk;
        for (kk in row) {
          if (Object.prototype.hasOwnProperty.call(row, kk) && canon(kk) === names[j]) { cell = row[kk]; break; }
        }
        inv[names[j]].call.push(cell && isNum(+cell.call) ? +cell.call : null);
        inv[names[j]].put.push(cell && isNum(+cell.put) ? +cell.put : null);
      }
    }
    return { dates: dates, inv: inv, names: names };
  }

  /* fut_net → {dates, inv:{name:[]}} */
  function collectFut(futNet) {
    var dates = [], k, i, j;
    if (!futNet) return { dates: [], inv: {}, names: [] };
    for (k in futNet) if (Object.prototype.hasOwnProperty.call(futNet, k)) dates.push(k);
    dates.sort();
    var inv = {}, names = [];
    for (i = 0; i < dates.length; i++) {
      var row = futNet[dates[i]] || {};
      for (k in row) {
        if (!Object.prototype.hasOwnProperty.call(row, k)) continue;
        var nm = canon(k);
        if (!inv[nm]) {
          inv[nm] = [];
          for (j = 0; j < i; j++) inv[nm].push(null);
          names.push(nm);
        }
      }
      for (j = 0; j < names.length; j++) {
        var cell = null, kk;
        for (kk in row) {
          if (Object.prototype.hasOwnProperty.call(row, kk) && canon(kk) === names[j]) { cell = row[kk]; break; }
        }
        inv[names[j]].push(isNum(+cell) ? +cell : null);
      }
    }
    return { dates: dates, inv: inv, names: names };
  }

  /* ── 해석 엔진 ──────────────────────────────────────────── */
  function analyzeVk(dates, vals) {
    var n = vals.length;
    if (!n) return null;
    var last = vals[n - 1], lastDate = dates[n - 1];
    var w = tail(vals, 20), wd = tail(dates, 20);
    var mx = -Infinity, mxi = 0;
    for (var i = 0; i < w.length; i++) if (w[i] > mx) { mx = w[i]; mxi = i; }
    var drop = mx > 0 ? (last - mx) / mx * 100 : 0;
    // 5일 하락추세: 5거래일 전 대비 하락 + 최근 5일 변화 중 하락일 3일 이상
    var dn = 0, cmp5 = n > 5 ? vals[n - 6] : vals[0];
    for (var j = Math.max(1, n - 5); j < n; j++) if (vals[j] < vals[j - 1]) dn++;
    var trendDown = last < cmp5 && dn >= 3;
    var peakout = drop <= -15 && trendDown;
    return {
      last: last, lastDate: lastDate,
      max20: mx, max20Date: wd[mxi] || lastDate,
      drop: drop, dn5: dn, cmp5: cmp5, trendDown: trendDown,
      peakout: peakout,
      stable: last <= VK_STABLE,
      daily: last / Math.sqrt(252)
    };
  }

  function analyzeFlow(opt, cumN) {
    if (!opt.dates.length || !opt.inv['외국인']) return null;
    var f = opt.inv['외국인'];
    var call = sum(tail(f.call, cumN)), put = sum(tail(f.put, cumN));
    var lastCall = null, lastPut = null, i;
    for (i = f.call.length - 1; i >= 0; i--) if (isNum(f.call[i])) { lastCall = f.call[i]; break; }
    for (i = f.put.length - 1; i >= 0; i--) if (isNum(f.put[i])) { lastPut = f.put[i]; break; }

    // 카운터파티: 같은 기간 콜 순매도 1위(합산 항목 제외)
    var cp = null, cpVal = 0;
    for (var q = 0; q < opt.names.length; q++) {
      var nm = opt.names[q];
      if (nm === '외국인' || AGG[nm]) continue;
      var v = sum(tail(opt.inv[nm].call, cumN));
      if (v < cpVal) { cpVal = v; cp = nm; }
    }
    return {
      n: Math.min(cumN, opt.dates.length),
      call: call, put: put,
      lastCall: lastCall, lastPut: lastPut,
      longVol: call > 0 && put > 0,
      cp: cp, cpVal: cpVal,
      from: tail(opt.dates, cumN)[0], to: opt.dates[opt.dates.length - 1]
    };
  }

  function analyzeFut(fut, cumN) {
    if (!fut.dates.length || !fut.inv['외국인']) return null;
    var arr = tail(fut.inv['외국인'], cumN);
    return { n: arr.length, sum: sum(arr), to: fut.dates[fut.dates.length - 1] };
  }

  /* ── 조립 블록 ──────────────────────────────────────────── */
  function el(doc, cls, txt) {
    var d = doc.createElement('div');
    if (cls) d.className = cls;
    if (txt != null) d.textContent = txt;
    return d;
  }

  function badge(doc, txt, color) {
    var b = doc.createElement('span');
    b.className = 'dv-badge';
    b.textContent = txt;
    b.style.color = color;
    b.style.borderColor = color;
    b.style.background = 'transparent';
    return b;
  }

  function legend(doc,items){var w=el(doc,'dv-legend');w.innerHTML=vizPhalanxLegend(items.map(function(it){return {name:it.name+(it.note?' '+it.note:''),unit:'억원',role:'actual'};}));return w;}

  function cardHead(doc, titleHtml, valueTxt, valueColor) {
    var h = el(doc, 'dv-cardhead');
    var t = doc.createElement('span');
    t.className = 'dv-t';
    t.innerHTML = titleHtml;
    h.appendChild(t);
    var v = doc.createElement('span');
    v.className = 'dv-v';
    v.textContent = valueTxt;
    if (valueColor) v.style.color = valueColor;
    h.appendChild(v);
    return h;
  }

  /* ① 지금 가장 중요한 2가지 */
  function buildKeyBox(doc, a) {
    var box = el(doc, 'dv-key');
    box.appendChild(el(doc, 'dv-keyt', '🎯 지금 가장 중요한 2가지'));
    var row = el(doc, 'dv-keyrow');

    function item(q, ok, reason) {
      var it = el(doc, 'dv-keyitem');
      var ox = el(doc, 'dv-ox', ok ? 'O' : 'X');
      ox.style.color = ok ? '#59d0a8' : '#ff4d5e';
      it.appendChild(ox);
      var body = el(doc, '');
      body.appendChild(el(doc, 'dv-kq', q));
      body.appendChild(el(doc, 'dv-kr', reason));
      it.appendChild(body);
      return it;
    }

    if (!a) {
      box.appendChild(el(doc, 'dv-empty', 'VKOSPI 데이터가 없어 판정할 수 없습니다.'));
      return box;
    }
    row.appendChild(item(
      '① VKOSPI 피크아웃 진행 중인가?',
      a.peakout,
      '20일 최고 ' + fx(a.max20, 2) + '(' + a.max20Date + ') → 현재 ' + fx(a.last, 2) +
      ' · ' + fx(a.drop, 1) + '% (기준 −15%) · 최근 5일 하락 ' + a.dn5 + '/5, 5일전 ' + fx(a.cmp5, 2)
    ));
    row.appendChild(item(
      '② VKOSPI 60 이하 안정화됐나?',
      a.stable,
      '현재 ' + fx(a.last, 2) + ' vs 임계 60 · ' +
      (a.stable ? '60 아래 진입' : '임계 상회 ' + fx(a.last - VK_STABLE, 2) + 'p') +
      ' · 기준일 ' + a.lastDate
    ));
    box.appendChild(row);
    return box;
  }

  /* ② VKOSPI 추이 카드 */
  function buildVkCard(doc, dates, vals, a) {
    var card = el(doc, 'dv-card');
    card.appendChild(cardHead(doc,
      'VKOSPI 추이 <em>· 코스피200 변동성지수 · 기준선 60(안정화 임계)</em>',
      vals.length ? fx(vals[vals.length - 1], 2) : '—', C.vk));
    card.appendChild(buildPlot(doc, {
      w: 1060, h: 230, pr: 54, dates: dates, dec: 2, aria: 'VKOSPI 추이',
      series: [{ name: 'VKOSPI', color: C.vk, vals: vals, w: 1.8 }],
      refs: [
        { v: VK_HI, c: '#ff4d5e', txt: '75 극단 공포' },
        { v: VK_STABLE, c: '#2bc0d4', txt: '60 안정화 임계', w: 1.4, dash: '5 3', o: 0.95, force: true },
        { v: VK_LO, c: '#59d0a8', txt: '40 정상권' }
      ]
    }));

    var bs = el(doc, 'dv-badges');
    if (a) {
      if (a.peakout) bs.appendChild(badge(doc, '⤵ 피크아웃 진행', '#59d0a8'));
      if (a.stable) bs.appendChild(badge(doc, '✅ 60 이하 안정화', '#2bc0d4'));
      if (!a.peakout && !a.stable) bs.appendChild(badge(doc, '⚠ 고변동성 지속', '#ff8a3d'));
      card.appendChild(bs);

      var note = el(doc, 'dv-note');
      note.innerHTML =
        'VKOSPI <b>' + fx(a.last, 2) + '</b> = 향후 30일 예상 변동성 <b>연 ' + fx(a.last, 1) + '%</b> ≈ ' +
        '하루 <b>±' + fx(a.daily, 2) + '%</b> (연 ' + fx(a.last, 1) + '% ÷ √252). ' +
        '20일 최고 ' + fx(a.max20, 2) + ' 대비 <b>' + fx(a.drop, 1) + '%</b>' +
        (a.peakout ? ' — −15% 이상 하락 + 5일 하락추세 조건 충족(피크아웃).'
          : ' — 피크아웃 기준(−15% 하락 & 5일 하락추세) 미충족.');
      card.appendChild(note);
    }
    return card;
  }

  /* ③ 외국인 옵션 순매수(콜 vs 풋) */
  function buildFrgnOptCard(doc, opt, take, fa) {
    var card = el(doc, 'dv-card');
    var f = opt.inv['외국인'];
    var dates = tail(opt.dates, take);
    var head = cardHead(doc,
      '외국인 옵션 순매수 <em>· 콜 vs 풋 (억원)</em>',
      fa ? '최근 ' + fa.n + '일 누적 콜 ' + signed(fa.call) + ' / 풋 ' + signed(fa.put) : '—');
    card.appendChild(head);
    if (!f) {
      card.appendChild(el(doc, 'dv-empty', '투자자별 옵션 순매수 데이터가 없습니다.'));
      return card;
    }
    card.appendChild(buildPlot(doc, {
      w: 520, h: 186, dates: dates, money: true, unit: '억', base: 0, aria: '외국인 옵션 순매수',
      series: [
        { name: '콜', color: C.call, vals: tail(f.call, take) },
        { name: '풋', color: C.put, vals: tail(f.put, take) }
      ]
    }));
    card.appendChild(legend(doc, [
      { name: '콜옵션', color: C.call, note: fa ? signed(fa.call) + '억' : '' },
      { name: '풋옵션', color: C.put, note: fa ? signed(fa.put) + '억' : '' }
    ]));
    var bs = el(doc, 'dv-badges');
    if (fa && fa.longVol) bs.appendChild(badge(doc, '외국인 양매수 = Long Vol', '#c58aff'));
    if (bs.childNodes.length) card.appendChild(bs);
    var note = el(doc, 'dv-note');
    if (fa && fa.longVol) {
      note.innerHTML = '외국인이 최근 ' + fa.n + '거래일 콜(<b>' + signed(fa.call) + '억</b>)·풋(<b>' +
        signed(fa.put) + '억</b>)을 <b>동시 순매수</b> — <b>변동성 확대에 베팅</b>하는 포지션입니다.';
    } else if (fa) {
      note.innerHTML = '최근 ' + fa.n + '거래일 외국인 콜 <b>' + signed(fa.call) + '억</b>, 풋 <b>' +
        signed(fa.put) + '억</b> — 콜·풋 동시 순매수(양매수) 아님, 방향성 베팅 우위.';
    }
    card.appendChild(note);
    return card;
  }

  /* ④ 콜옵션 순매수 주체별 */
  function buildCallByInvCard(doc, opt, take, fa) {
    var card = el(doc, 'dv-card');
    var want = ['외국인', '투신', '금융투자'];
    var cols = { '외국인': C.frgn, '투신': C.trust, '금융투자': C.fin };
    var picked = [], i;
    for (i = 0; i < want.length; i++) if (opt.inv[want[i]]) picked.push(want[i]);
    if (fa && fa.cp && picked.indexOf(fa.cp) < 0) picked.push(fa.cp);
    if (picked.length < 2) {
      for (i = 0; i < opt.names.length && picked.length < 3; i++) {
        if (AGG[opt.names[i]] || picked.indexOf(opt.names[i]) >= 0) continue;
        picked.push(opt.names[i]);
      }
    }
    var dates = tail(opt.dates, take);
    // 색 배정을 먼저 확정해 카드 헤드(카운터파티)와 라인 색을 일치시킨다
    var cmap = {}, ai = 0;
    for (i = 0; i < picked.length; i++) {
      cmap[picked[i]] = cols[picked[i]] || C.alt[ai++ % C.alt.length];
    }
    card.appendChild(cardHead(doc,
      '콜옵션 순매수 주체별 <em>· 카운터파티 관계 (억원)</em>',
      fa && fa.cp ? '카운터파티: ' + fa.cp : '—', fa && fa.cp ? cmap[fa.cp] || C.alt[0] : null));
    if (!picked.length) {
      card.appendChild(el(doc, 'dv-empty', '투자자별 옵션 순매수 데이터가 없습니다.'));
      return card;
    }
    var series = [], lgd = [];
    for (i = 0; i < picked.length; i++) {
      var nm = picked[i];
      var color = cmap[nm];
      var vals = tail(opt.inv[nm].call, take);
      series.push({ name: nm, color: color, vals: vals });
      lgd.push({ name: nm, color: color, note: signed(sum(tail(opt.inv[nm].call, fa ? fa.n : CUM_N))) + '억' });
    }
    card.appendChild(buildPlot(doc, {
      w: 520, h: 186, dates: dates, money: true, unit: '억', base: 0,
      aria: '콜옵션 순매수 주체별', lastLabel: false, series: series
    }));
    card.appendChild(legend(doc, lgd));
    var note = el(doc, 'dv-note');
    if (fa && fa.cp) {
      note.innerHTML = '외국인 콜 순매수의 <b>최대 반대편 주체</b>는 <b>' + fa.cp + '</b> — 같은 기간(' +
        fa.n + '거래일) 콜 <b>' + signed(fa.cpVal) + '억</b>으로 순매도 1위. ' +
        '외국인이 산 콜을 ' + fa.cp + '이(가) 받아낸 구조(합산 항목 제외).';
    } else {
      note.innerHTML = '같은 기간 콜옵션 순매도 우위 주체가 확인되지 않습니다.';
    }
    card.appendChild(note);
    return card;
  }

  function buildFoot(doc, a, fa, fu, src) {
    var f = el(doc, 'dv-foot');
    var lines = [];
    lines.push('※ <b>과거 패턴(고정 각주)</b> — VKOSPI 피크아웃이 확인된 국면에서는 외국인의 <b>선물 매도 포지션 청산</b>이 ' +
      '동반되며 지수 반등이 뒤따르는 경우가 많았습니다(3월말~4월 사례). ' +
      '변동성 피크아웃 → 숏커버 → 현·선물 동반 반등의 순서를 확인하세요.');
    if (fu) {
      lines.push('· 외국인 KOSPI200 선물 최근 ' + fu.n + '거래일 누적 순매수 <b>' + signed(fu.sum) +
        '억</b> (기준일 ' + fu.to + ') — 음수 축소/양전환이 매도 청산 신호.');
    }
    if (a) {
      lines.push('· 변동성 환산: 연 ' + fx(a.last, 1) + '% ≈ 하루 ±' + fx(a.daily, 2) + '% (= ' +
        fx(a.last, 1) + ' ÷ √252). 60 위는 하루 ±' + fx(VK_STABLE / Math.sqrt(252), 2) + '% 이상을 시장이 가격에 반영 중임을 뜻합니다.');
    }
    if (src) lines.push('· 출처: ' + src);
    f.innerHTML = lines.join('<br>');
    return f;
  }

  /* ── 엔트리 ─────────────────────────────────────────────── */
  function renderDeriv(el0, data) {
    if (!el0 || !el0.ownerDocument) return el0;
    var doc = el0.ownerDocument;
    ensureCss(doc);
    while (el0.firstChild) el0.removeChild(el0.firstChild);
    data = data || {};

    var vk = seriesFromMap(data.vkospi);
    var opt = collectOpt(data.opt_net);
    var fut = collectFut(data.fut_net);

    var wrap = el(doc, 'dv-wrap');
    var head = el(doc, 'dv-head');
    var titleBox = el(doc, '');
    var title = el(doc, 'dv-title', '⚡ 파생·수급 — VKOSPI & 투자자별 옵션 순매수');
    titleBox.appendChild(title);
    if (data.asof) titleBox.appendChild(el(doc, 'dv-asof', 'asof ' + String(data.asof).slice(0, 19).replace('T', ' ')));
    head.appendChild(titleBox);

    var chips = el(doc, 'dv-chips');
    var body = el(doc, '');
    body.style.display = 'flex';
    body.style.flexDirection = 'column';
    body.style.gap = '12px';

    var btns = [];
    function render(k) {
      var take = 252, i;
      for (i = 0; i < PERIODS.length; i++) if (PERIODS[i].k === k) take = PERIODS[i].n;
      for (i = 0; i < btns.length; i++) {
        btns[i].className = btns[i].getAttribute('data-k') === k ? 'dv-chip on' : 'dv-chip';
      }
      while (body.firstChild) body.removeChild(body.firstChild);

      var vDates = tail(vk.dates, take), vVals = tail(vk.vals, take);
      var a = analyzeVk(vk.dates, vk.vals);           // 판정은 항상 전체 시계열 기준
      var flowTake = Math.min(take, FLOW_MAX);
      var fa = analyzeFlow(opt, CUM_N);
      var fu = analyzeFut(fut, CUM_N);

      body.appendChild(buildKeyBox(doc, a));
      if (vDates.length) body.appendChild(buildVkCard(doc, vDates, vVals, a));
      else {
        var c0 = el(doc, 'dv-card');
        c0.appendChild(cardHead(doc, 'VKOSPI 추이', '—'));
        c0.appendChild(el(doc, 'dv-empty', 'VKOSPI 데이터가 없습니다.'));
        body.appendChild(c0);
      }

      var grid = el(doc, 'dv-grid');
      grid.appendChild(buildFrgnOptCard(doc, opt, flowTake, fa));
      grid.appendChild(buildCallByInvCard(doc, opt, flowTake, fa));
      body.appendChild(grid);

      var srcTxt = '';
      if (data._src) {
        var parts = [], kk;
        for (kk in data._src) {
          if (!Object.prototype.hasOwnProperty.call(data._src, kk)) continue;
          var sv = data._src[kk];
          parts.push(kk + '=' + (typeof sv === 'string' ? sv : (sv && (sv.name || sv.url || sv.bld)) || 'json'));
        }
        srcTxt = parts.join(' · ');
      }
      body.appendChild(buildFoot(doc, a, fa, fu, srcTxt));
    }

    for (var p = 0; p < PERIODS.length; p++) {
      (function (key) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'dv-chip';
        b.setAttribute('data-k', key);
        b.textContent = key;
        b.addEventListener('click', function () { render(key); });
        chips.appendChild(b);
        btns.push(b);
      })(PERIODS[p].k);
    }
    head.appendChild(chips);
    wrap.appendChild(head);
    wrap.appendChild(body);
    el0.appendChild(wrap);

    render(DEFAULT_PERIOD);
    return el0;
  }

  if (typeof window !== 'undefined') window.renderDeriv = renderDeriv;
  else if (typeof globalThis !== 'undefined') globalThis.renderDeriv = renderDeriv;
  if (typeof module !== 'undefined' && module.exports) module.exports = renderDeriv;
})();
