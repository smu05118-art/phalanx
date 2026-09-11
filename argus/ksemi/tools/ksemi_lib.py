#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_lib — 한국반도체장비(argus/ksemi) 파이프라인 공용 유틸.

한국건설(argus/kce/tools)의 DART 수집·표 파서·KIND 모집단 도구를 **그대로 import** 한다
(COMMON.md §1). 복사하지 않는다 — DART 3단 경로·재시도·프로세스 간 요청 게이트·머리행
평탄화는 산업과 무관한 층이고, 두 벌로 갈라지면 한쪽만 고쳐지는 날이 온다.
산업 특성(수주잔고 롤포워드·매출인식 시점·고객 집중·공정 단계 분류)만 여기서 새로 만든다.

규약(AGENTS.md·COMMON.md): stdlib 전용 · fail-closed · 원자적 쓰기 · 정규화 출력.
"""
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))           # argus/ksemi/tools
KSEMI = os.path.dirname(HERE)                               # argus/ksemi
ARGUS = os.path.dirname(KSEMI)                              # argus
KCE_TOOLS = os.path.join(ARGUS, "kce", "tools")
ASSETS = os.path.join(HERE, "assets")

if KCE_TOOLS not in sys.path:
    sys.path.insert(0, KCE_TOOLS)

# 산업 무관 층 — kce에서 가져온다. 이 이름들로 ksemi 모듈 전체가 쓴다.
from kce_lib import (COL_ALIAS, atomic_write, json_for_html, latest_quarter,  # noqa: E402,F401
                     norm_col, num_of, q_next, q_of, q_range, report_kind)
from kce_fetch import (fetch_section, find_sections, pick_report,             # noqa: E402,F401
                       search_reports, toc, _get)
from kce_parse import parse_tables                                           # noqa: E402,F401
from kce_probe import report_window                                          # noqa: E402,F401
from kce_universe import KIND_URL, parse_kind                                # noqa: E402,F401

E = html.escape


def load_asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return json.load(f)


def has_asset(name):
    return os.path.exists(os.path.join(ASSETS, name))


def write_asset(name, data):
    """정규화 JSON(키 순서 보존·들여쓰기 1·개행 고정) — 같은 데이터는 같은 바이트."""
    os.makedirs(ASSETS, exist_ok=True)
    atomic_write(os.path.join(ASSETS, name),
                 json.dumps(data, ensure_ascii=False, indent=1) + "\n")


_PAL = None


def palette():
    global _PAL
    if _PAL is None:
        _PAL = load_asset("palette.json")
    return _PAL


def slot_color(slot):
    """공정 단계 시리즈 색. 슬롯은 단계에 고정된다(필터로 줄어도 재배색 금지)."""
    for s in palette()["categorical_order_fixed"]:
        if s["slot"] == slot:
            return s["hex"]
    raise KeyError(slot)


# ── 숫자 표기 ───────────────────────────────────────────────

def fmt_eok(v):
    """백만원 → 억원 문자열."""
    if v is None:
        return "—"
    return format(round(v / 100), ",d")


def fmt_musd(v):
    if v is None:
        return "—"
    return format(round(v), ",d")


def fmt_n(v):
    if v is None:
        return "—"
    return format(v, ",d") if float(v).is_integer() else format(v, ",.1f")


def fmt_x(v):
    """배수(잔고/매출) — 소수 한 자리."""
    if v is None:
        return "—"
    return "%.2f" % v


def pct(a, b):
    if not a or not b:
        return None
    return 100.0 * a / b


# ── 페이지 셸 ───────────────────────────────────────────────

def _rel(depth):
    return "../" * depth


def page(title, body, depth=0, head_extra="", scripts=(), h1=None, crumbs=(), tags=(),
         nav=(), lead=""):
    """공용 셸. depth=0 은 ksemi 루트, 1 은 회사 디렉터리.

    CSS는 assets/ksemi.css 하나를 링크한다(페이지마다 인라인 복제 금지).
    외부 스크립트(Chart.js)는 **본문보다 먼저** 둔다 — 본문의 인라인 차트 코드가 그 전역을
    즉시 쓰기 때문이다(kship에서 겪은 `Chart is not defined` 사고).
    """
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
            "<title>%s</title>\n<link rel=\"stylesheet\" href=\"%sassets/ksemi.css\">\n%s</head>\n"
            "<body>\n<header class=\"top\"><div class=\"hd\"><h1>%s</h1>%s<span class=\"sp\">%s</span></div>%s</header>\n%s"
            "<main>%s%s</main>\n"
            "<footer>출처 DART 정기보고서·수시공시, KRX KIND 상장법인목록. 금액 단위는 표마다 원문 캡션에서 읽어 "
            "백만원으로 정규화. 참고용 · 투자조언 아님.</footer>\n</body></html>\n"
            % (E(title), r, head_extra, E(h1 or title), tagh, navh, crumbh, sh,
               ('<p class="lead">%s</p>' % lead) if lead else "", body))


# Chart.js 공용 기본값 — dataviz 규격(kship과 같다).
CHART_DEFAULTS_JS = r"""
(function(){
  if(!window.Chart) return;
  var C=window.Chart, css=getComputedStyle(document.documentElement);
  var tx2=css.getPropertyValue('--tx2').trim()||'#98a1b0', grid=css.getPropertyValue('--grid').trim()||'#2a2f3a';
  C.defaults.color=tx2; C.defaults.font.family=css.getPropertyValue('--sans')||'sans-serif'; C.defaults.font.size=11;
  C.defaults.plugins.legend.labels.boxWidth=10; C.defaults.plugins.legend.labels.boxHeight=10;
  C.defaults.plugins.legend.labels.usePointStyle=false; C.defaults.plugins.legend.position='bottom';
  C.defaults.plugins.tooltip.backgroundColor='#0b0d12'; C.defaults.plugins.tooltip.borderColor='#343a47';
  C.defaults.plugins.tooltip.borderWidth=1; C.defaults.plugins.tooltip.titleColor='#e6e8ec'; C.defaults.plugins.tooltip.bodyColor='#e6e8ec';
  C.defaults.plugins.tooltip.padding=8; C.defaults.plugins.tooltip.displayColors=true; C.defaults.plugins.tooltip.boxWidth=10; C.defaults.plugins.tooltip.boxHeight=2;
  C.defaults.scale.grid.color=grid; C.defaults.scale.grid.lineWidth=1; C.defaults.scale.border.display=false;
  C.defaults.scale.ticks.color=tx2; C.defaults.scale.ticks.font={size:10.5};
  C.defaults.elements.bar.borderRadius=4; C.defaults.elements.bar.borderSkipped='bottom';
  C.defaults.elements.line.borderWidth=2; C.defaults.elements.line.tension=0.25; C.defaults.elements.point.radius=0; C.defaults.elements.point.hoverRadius=4;
  C.defaults.datasets.bar.maxBarThickness=24; C.defaults.datasets.bar.borderWidth=2; C.defaults.datasets.bar.borderColor='#171a21';
  C.defaults.animation.duration=matchMedia('(prefers-reduced-motion: reduce)').matches?0:350;
  C.defaults.interaction={mode:'index',intersect:false};
})();
"""

# 표 정렬·검색·툴팁 공용 JS. 값은 textContent 로만 넣는다(공시 텍스트는 신뢰할 수 없는 입력).
TABLE_JS = r"""
(function(){
  function num(s){var v=parseFloat(String(s).replace(/[^\d.\-]/g,''));return isNaN(v)?null:v;}
  document.querySelectorAll('table[data-sortable]').forEach(function(tb){
    var ths=tb.querySelectorAll('thead th'); var body=tb.tBodies[0]; if(!body) return;
    ths.forEach(function(th,i){
      th.classList.add('sort');
      th.addEventListener('click',function(){
        var dir=th.dataset.dir==='asc'?'desc':'asc'; ths.forEach(function(t){delete t.dataset.dir}); th.dataset.dir=dir;
        var rows=Array.prototype.slice.call(body.rows);
        rows.sort(function(a,b){
          var x=a.cells[i]?a.cells[i].dataset.v!==undefined?a.cells[i].dataset.v:a.cells[i].textContent:'';
          var y=b.cells[i]?b.cells[i].dataset.v!==undefined?b.cells[i].dataset.v:b.cells[i].textContent:'';
          var nx=num(x),ny=num(y);
          if(nx!==null&&ny!==null){ if(nx===ny) return 0; return (nx<ny?-1:1)*(dir==='asc'?1:-1); }
          if(x===y) return 0; return (x<y?-1:1)*(dir==='asc'?1:-1);
        });
        rows.forEach(function(r){body.appendChild(r)});
      });
    });
  });
  document.querySelectorAll('input[data-filter]').forEach(function(inp){
    var tb=document.querySelector(inp.dataset.filter); if(!tb) return;
    inp.addEventListener('input',function(){
      var q=inp.value.trim().toLowerCase();
      Array.prototype.forEach.call(tb.tBodies[0].rows,function(r){ r.hidden=q&&r.textContent.toLowerCase().indexOf(q)<0; });
    });
  });
})();
"""
