#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kchem_lib — 한국화학(argus/kchem) 파이프라인 공용 유틸.

이 탭은 DART 도, 외부 네트워크도 두드리지 않는다. 입력은 ARGUS 빌더 산출물
(`argus/data/argus_data.js`·`chunk_*.js`·`connections.js`, `argus/data_map.js`)뿐이며
**읽기 전용**이다(AGENTS.md "생성물 직접 수정 금지"). 여기서는 그 산출물을 파싱해
화학 스프레드만 다시 조립한다.

페이지 셸·표 JS 는 한국조선(kship_lib)의 것을 쓰되 CSS 경로·꼬리말만 kchem 으로 바꾼다
(COMMON.md §1 "새로 만들지 말 것"). 원자적 쓰기·HTML 안전 JSON 은 kce_lib 에서 가져온다.

규약: 표준 라이브러리만(3.9) · fail-closed · 원자적 쓰기 · 정규화 출력(같은 입력 → 같은 바이트).
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # argus/kchem/tools
KCHEM = os.path.dirname(HERE)                               # argus/kchem
ARGUS = os.path.dirname(KCHEM)                              # argus
REPO = os.path.dirname(ARGUS)                               # 레포 루트
ASSETS = os.path.join(HERE, "assets")                       # 사전·레지스트리·fingerprint (Pages 배포 제외)
DATA_DIR = os.path.join(KCHEM, "data")                      # 페이지가 읽는 런타임 데이터 (배포됨)
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
KSHIP_TOOLS = os.path.join(ARGUS, "kship", "tools")

for _p in (KCE_TOOLS, KSHIP_TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kce_lib import atomic_write, json_for_html   # noqa: E402,F401
from kship_lib import TABLE_JS                    # noqa: E402,F401

E = html.escape


def load_asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


def dump_json(data):
    """정규화 JSON — 키 정렬·들여쓰기 1·개행 고정. 같은 데이터는 같은 바이트."""
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_asset(name, data):
    os.makedirs(ASSETS, exist_ok=True)
    atomic_write(os.path.join(ASSETS, name), dump_json(data))


def fmt(v, digits=1):
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) >= 1000:
        return format(round(v), ",d")
    s = ("%%.%df" % digits) % v
    return s.replace("-", "−")


def fmt_k(k):
    """계수 표기 — 소수 2자리, 1.00 은 '1'."""
    if k is None:
        return "?"
    r = round(k, 2)
    if abs(r - round(r)) < 1e-9:
        return "%d" % round(r)
    return ("%.2f" % r).rstrip("0").rstrip(".")


# ── 페이지 셸 (kship_lib.page 를 복사 — CSS 경로·꼬리말만 다르다) ───────────

def _rel(depth):
    return "../" * depth


FOOTER = ("출처 ARGUS 원장(Weekly xlsm — Platts류 유료 스팟, 2026-08-24 주차 이후 미갱신)·페트로넷 일간·中 선물(quheqihuo) "
          "— 빌더 산출물(argus/data)을 읽기 전용으로 재조립. 단위 USD/MT. 계수는 전부 역산 추정. "
          "참고용 · 투자조언 아님.")


def page(title, body, depth=0, head_extra="", scripts=(), h1=None, crumbs=(), tags=(), nav=(), lead=""):
    """공용 셸. depth=0 은 kchem 루트, 1 은 종목 디렉터리. CSS 는 assets/kchem.css 하나."""
    r = _rel(depth)
    tagh = "".join('<span class="tag">%s</span>' % E(t) for t in tags if t)
    navh = "".join('<a href="%s"%s>%s</a>' % (E(href), (' target="_blank" rel="noopener noreferrer"' if href.startswith("http") else ""), E(label))
                   for label, href in nav)
    crumbh = ""
    if crumbs:
        parts = []
        for label, href in crumbs:
            parts.append('<a href="%s">%s</a>' % (E(href), E(label)) if href else "<span>%s</span>" % E(label))
        crumbh = '<div class="crumb">%s</div>' % " › ".join(parts)
    sh = "".join('<script src="%s"></script>' % E(s) for s in scripts)
    return ("<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/kchem.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>%s</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body, E(FOOTER)))


# ── 공용 JS (의존성 0 — Chart.js 를 쓰지 않는다. ARGUS 허브와 같은 인라인 SVG) ─────
# 값은 textContent 로만 넣는다. window.KCHEM 은 data/kchem_data.js 가 정의한다.
KCHEM_JS = r"""
(function(){
  var D=window.KCHEM; if(!D){return;}
  function el(t,a){var e=document.createElementNS('http://www.w3.org/2000/svg',t);for(var k in a){e.setAttribute(k,a[k]);}return e;}
  function fin(v){return typeof v==='number'&&isFinite(v);}
  function fmt(v){if(!fin(v))return '—';var a=Math.abs(v);var s=a>=1000?Math.round(v).toLocaleString('en-US'):(a>=100?v.toFixed(0):v.toFixed(1));return s.replace('-','−');}
  function series(sid){var s=D.series[sid];if(!s)return null;var ax=s.axis?D.axes[s.axis]:D.axes.wk;return {axis:ax,v:s.v,unit:s.unit,name:s.name};}
  function extent(vs){var lo=Infinity,hi=-Infinity;vs.forEach(function(v){if(fin(v)){if(v<lo)lo=v;if(v>hi)hi=v;}});if(lo===Infinity){lo=0;hi=1;}if(hi===lo){hi=lo+1;}return [lo,hi];}
  /* 스파크라인: <svg class="spk" data-sid> 를 채운다. 끝점 강조·0선 */
  function spark(svg){
    var s=series(svg.dataset.sid); if(!s){svg.remove();return;}
    var W=120,H=28,p=2; svg.setAttribute('viewBox','0 0 '+W+' '+H); svg.setAttribute('preserveAspectRatio','none');
    var vs=s.v, n=vs.length, ex=extent(vs), lo=ex[0], hi=ex[1];
    var x=function(i){return p+(W-2*p)*i/Math.max(1,n-1);}, y=function(v){return H-p-(H-2*p)*(v-lo)/(hi-lo);};
    if(lo<0&&hi>0){svg.appendChild(el('line',{x1:0,x2:W,y1:y(0),y2:y(0),'class':'zero'}));}
    var d='',last=null,li=-1; for(var i=0;i<n;i++){if(!fin(vs[i]))continue;d+=(d?'L':'M')+x(i).toFixed(1)+' '+y(vs[i]).toFixed(1);last=vs[i];li=i;}
    if(!d){return;} svg.appendChild(el('path',{d:d,'class':'ln'}));
    if(li>=0){svg.appendChild(el('circle',{cx:x(li).toFixed(1),cy:y(last).toFixed(1),r:2,'class':'end'}));}
  }
  /* 다중 선 차트: container.dataset.sids = 'sid1,sid2,...' */
  var COLORS=['#3987e5','#d95926','#199e70','#c98500','#d55181','#9085e9','#e66767','#008300'];
  function chart(box){
    var sids=(box.dataset.sids||'').split(',').filter(Boolean); box.textContent='';
    var W=Math.max(320,box.clientWidth||640),H=240,L=56,R=12,T=14,B=28;
    var svg=el('svg',{viewBox:'0 0 '+W+' '+H,'class':'kchart',role:'img'}); box.appendChild(svg);
    var rows=[],allv=[],axis=null;
    sids.forEach(function(sid,i){var s=series(sid);if(!s)return;axis=axis||s.axis;rows.push({sid:sid,s:s,c:COLORS[i%COLORS.length]});s.v.forEach(function(v){if(fin(v))allv.push(v);});});
    if(!rows.length){box.textContent='데이터 없음';return;}
    var ex=extent(allv),lo=ex[0],hi=ex[1],pad=(hi-lo)*0.06;lo-=pad;hi+=pad; var n=axis.length;
    var x=function(i){return L+(W-L-R)*i/Math.max(1,n-1);}, y=function(v){return T+(H-T-B)*(1-(v-lo)/(hi-lo));};
    var ticks=5; for(var t=0;t<=ticks;t++){var v=lo+(hi-lo)*t/ticks;svg.appendChild(el('line',{x1:L,x2:W-R,y1:y(v),y2:y(v),'class':'grid'}));var tx=el('text',{x:L-6,y:y(v)+3.5,'class':'tk','text-anchor':'end'});tx.textContent=fmt(v);svg.appendChild(tx);}
    if(lo<0&&hi>0){svg.appendChild(el('line',{x1:L,x2:W-R,y1:y(0),y2:y(0),'class':'zero'}));}
    var step=Math.max(1,Math.floor(n/6)); for(var i=0;i<n;i+=step){var tt=el('text',{x:x(i),y:H-8,'class':'tk','text-anchor':'middle'});tt.textContent=axis[i].slice(0,7);svg.appendChild(tt);}
    rows.forEach(function(r){var d='';for(var i=0;i<n;i++){var v=r.s.v[i];if(!fin(v)){continue;}d+=(d?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);}
      if(d){svg.appendChild(el('path',{d:d,'class':'ln',stroke:r.c}));}});
    var cursor=el('line',{x1:0,x2:0,y1:T,y2:H-B,'class':'cur'});cursor.setAttribute('visibility','hidden');svg.appendChild(cursor);
    var lg=document.createElement('div');lg.className='legend';rows.forEach(function(r){var i=document.createElement('i');i.style.background=r.c;var sp=document.createElement('span');sp.appendChild(i);sp.appendChild(document.createTextNode(' '+r.s.name));lg.appendChild(sp);});box.appendChild(lg);
    svg.addEventListener('mousemove',function(ev){var rect=svg.getBoundingClientRect();var px=(ev.clientX-rect.left)*W/rect.width;var i=Math.round((px-L)/(W-L-R)*(n-1));if(i<0||i>=n){return;}
      cursor.setAttribute('x1',x(i));cursor.setAttribute('x2',x(i));cursor.setAttribute('visibility','visible');
      var lines=[{label:axis[i],value:''}];rows.forEach(function(r){lines.push({label:r.s.name,value:fmt(r.s.v[i])+(r.s.unit?' '+r.s.unit:''),color:r.c});});
      if(window.KSTIP){window.KSTIP.show(ev.clientX,ev.clientY,lines);}});
    svg.addEventListener('mouseleave',function(){cursor.setAttribute('visibility','hidden');if(window.KSTIP){window.KSTIP.hide();}});
  }
  function boot(){document.querySelectorAll('svg.spk[data-sid]').forEach(spark);document.querySelectorAll('.kchart-box[data-sids]').forEach(chart);}
  if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}
  window.KCHEMUI={chart:chart,spark:spark,series:series,fmt:fmt};
})();
"""
