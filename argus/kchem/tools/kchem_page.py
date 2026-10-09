#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kchem_page — 한국화학(argus/kchem) 페이지 생성기.

입력: tools/assets/registry.json(kchem_registry) + 빌더 청크(스프레드 255주 축·값) + connections(中선물 관측).
출력(전부 `argus/kchem/` 안):
  data/kchem_data.js   window.KCHEM = {axes, series, rows, derived, chains, summary, fingerprint}
  index.html           허브 — KPI·원장 정지 고지·카테고리 칩·체인 카드
  spreads.html         표 — 242행 정렬·필터, 산식·k·지역·신선도·中선물·종목
  matrix.html          제품×지역 매트릭스 → 셀 클릭 6선 비교
  chains.html          밸류체인 다이어그램(원료→제품 그래프, 레지스트리에서 자동 생성)
  coverage.html        모집단 전수(242) + chain 미배정·dead·미재현·결함
  <종목코드>/index.html 종목 → 스프레드 역참조(체인 단위 라벨)

규칙: 화면에 실리는 수치는 전부 registry/청크 값이고 추정은 '추정' 으로 표시한다(COMMON.md §0-1).
빌드 시각을 쓰지 않는다 — 같은 입력이면 같은 바이트(fingerprint 만 표기).
"""
import json
import os
import sys

from kchem_lib import (ASSETS, DATA_DIR, E, KCHEM, KCHEM_JS, TABLE_JS, atomic_write, fmt, fmt_k,
                       json_for_html, load_asset, page)
import kchem_inputs
import kchem_registry

CHEM_CATS = None
LAYER_KO = {"integrated": "통합(−나프타)", "step": "단계(−직접원료)", "composite": "복합", "crack": "크랙(−원유)",
            "price": "가격", "proxy": "中선물", "index": "PPI", "unknown": "미상"}
FLAG_KO = {
    "composite_extra_feed": ("이름에 없는 원료 추가", "est"),
    "feed_mismatch": ("이름과 다른 원료로 재현", "bad"),
    "feed_unspecified": ("원료 미표기 → 탐침", "est"),
    "formula_changed": ("창 안에서 산식 변경", "est"),
    "missing_product_as_zero": ("제품 결측을 0으로 계산(결함 의심)", "bad"),
    "unreproduced": ("미재현", "bad"),
    "insufficient_overlap": ("관측 겹침 부족", ""),
    "product_series_missing": ("제품 가격 시리즈 없음", ""),
    "unit_conversion_unverified": ("단위 환산 미확인", ""),
    "derived_estimate": ("파생(공개 관행 계수·추정)", "est"),
    "constituent_missing": ("구성 시리즈 없음", "bad"),
    "name_unparsed": ("이름 미해석", ""),
    "product_alias_missing": ("제품 별칭 없음", ""),
}
REGION_ORDER = ["한국", "대만", "일본", "동남아", "동북아", "중국", "중국 Huadong", "중국 Huanan", "인도", "싱가포르", "미국", "유럽",
                "ARA", "Rdam", "MED", "Genoa", "USGC", "Arab Gulf"]
NAV = (("← ARGUS", "../index.html"), ("표", "spreads.html"), ("매트릭스", "matrix.html"), ("밸류체인", "chains.html"), ("커버리지", "coverage.html"))


def fr_chip(f):
    f = f or "none"
    ko = {"fresh": "정상", "late": "지연", "stale": "오래됨", "dead": "장기 미갱신", "none": "—"}[f if f in ("fresh", "late", "stale", "dead") else "none"]
    return '<span class="fr %s">%s</span>' % (E(f), ko)


def flags_html(flags):
    out = []
    for f in flags:
        ko, cls = FLAG_KO.get(f, (f, ""))
        out.append('<span class="flag %s" title="%s">%s</span>' % (cls, E(f), E(ko)))
    return "".join(out)


def pos_html(pos):
    if pos is None:
        return '<span class="mut">—</span>'
    cls = "lo" if pos <= 20 else ("hi" if pos >= 80 else "")
    return '<span class="posbar %s"><i><b style="width:%d%%"></b></i>%d</span>' % (cls, max(0, min(100, round(pos))), round(pos))


def stocks_html(stocks, depth=0):
    r = "../" * depth
    return '<span class="stocks">%s</span>' % "".join(
        '<a class="%s" href="%s%s/index.html" title="%s">%s</a>' % ("est" if s.get("est") else "", r, E(s["t"]), E(s.get("note", "")), E(s["n"]))
        for s in stocks)


def link_html(sid, depth=0):
    r = "../" * (depth + 1)
    return ('<a href="%sconnections.html#%s" title="데이터 연결·관측일·원문">연결</a> · '
            '<a href="%smap.html#series=argus:%s" title="전상품 맵">맵</a>' % (r, E(sid), r, E(sid)))


def sort_region(r):
    return (REGION_ORDER.index(r) if r in REGION_ORDER else 99, r or "")


# ── 데이터 JS ───────────────────────────────────────────────

def build_data_js(reg, inputs):
    chunks = inputs["chunks"]
    conn = {r["sid"]: r for r in inputs["connections"]["rows"]}
    axis_wk = None
    series = {}
    for cat, ch in chunks.items():
        if axis_wk is None:
            axis_wk = ch["axis"]
        elif ch["axis"] != axis_wk:
            raise kchem_inputs.InputError("청크 축이 카테고리마다 다름: %s" % cat)
        for s in ch["series"]:
            if s["sid"].startswith(("cf_", "ppim_")):
                # 자동 소스는 청크 축이 2026-08-24 에 고정돼 최근 주가 잘린다 — connections 관측으로 그린다(R25)
                obs = conn.get(s["sid"], {}).get("observations") or []
                series[s["sid"]] = {"name": s["name"], "unit": s["unit"], "axis": None,
                                    "dates": [o[0] for o in obs], "v": [o[1] for o in obs]}
            else:
                series[s["sid"]] = {"name": s["name"], "unit": s["unit"], "axis": "wk", "v": s["v"]}
    for d in reg["derived"]:
        if d["values"] is not None:
            series[d["sid"]] = {"name": d["name"], "unit": d["unit"], "axis": "wk2y", "v": d["values"]}
    # 中선물 프록시(표·매트릭스의 참고 열) — 관측 그대로, 자기 축
    for r in reg["rows"]:
        cf = r.get("cnfut")
        if cf and cf["sid"] not in series and cf["sid"] in conn:
            obs = conn[cf["sid"]]["observations"]
            series[cf["sid"]] = {"name": conn[cf["sid"]]["name"], "unit": conn[cf["sid"]]["unit"], "axis": None,
                                 "dates": [o[0] for o in obs], "v": [o[1] for o in obs]}
    slim_rows = [{k: r.get(k) for k in ("sid", "name", "cat", "chain", "chain_est", "unit", "kind", "layer", "product", "region",
                                        "formula", "feeds", "reproduced", "flags", "freshness", "last_date", "last", "pos", "m4",
                                        "weeks_since", "stocks", "cnfut", "product_sid")} for r in reg["rows"] + reg["derived"]]
    data = {"fingerprint": reg["fingerprint"], "argus_asof": reg["argus_asof"],
            "axes": {"wk": axis_wk, "wk2y": reg["axis2y"]}, "series": series, "rows": slim_rows,
            "chains": reg["chains"], "summary": reg["summary"], "rules": reg["rules"]}
    return "window.KCHEM=" + json_for_html(data) + ";\n"


# ── 공통 조각 ───────────────────────────────────────────────

def notice_html(reg):
    s = reg["summary"]
    wk = s.get("ledger_stale_weeks")
    if wk is None:
        return ""
    if wk > 2:
        return ('<div class="notice"><div class="sym">⛔</div><div><p><b>원장 정지 %d주</b> — 화학 스프레드 원장(Weekly xlsm)의 마지막 관측은 %s, '
                'ARGUS 평가일은 %s 입니다. 아래 주간 스프레드는 전부 이 날짜에 멈춰 있으며(살아 있는 스프레드 0), '
                '값은 그대로 보이되 신선도 배지가 <span class="fr stale">오래됨</span>/<span class="fr dead">장기 미갱신</span> 으로 표시됩니다. '
                '살아 있는 화학 입력은 中 선물(일간)·PPI(월)뿐입니다.</p></div></div>'
                % (wk, E(s["ledger_last"]), E(reg["argus_asof"])))
    return ('<div class="notice info"><div class="sym">ℹ</div><div><p>원장 마지막 관측 %s · 평가일 %s.</p></div></div>'
            % (E(s["ledger_last"]), E(reg["argus_asof"])))


def kpi_html(reg):
    s = reg["summary"]
    sf = s["spread_freshness"]
    return ('<div class="kpi">'
            '<div><b>%d</b><span>화학 시리즈(청크 13 카테고리) · 스프레드 %d</span></div>'
            '<div><b>%d<small>/%d</small></b><span>산식 역산 재현(최소제곱, |잔차|≤%s)</span></div>'
            '<div><b>%d</b><span>살아 있는 스프레드 — 오래됨 %d · 장기 미갱신 %d</span></div>'
            '<div><b>%s주</b><span>원장 정지(마지막 %s)</span></div>'
            '<div><b>%d</b><span>파생 스프레드(공개 관행 계수·추정)</span></div>'
            '<div><b>%d</b><span>결함 의심·산식 변경·원료 불일치 플래그</span></div>'
            '</div>' % (s["rows"], s["spreads"], s["reproduced"], s["spreads"], fmt_k(reg["rules"]["tol_abs"]),
                        sf.get("fresh", 0), sf.get("stale", 0), sf.get("dead", 0),
                        s.get("ledger_stale_weeks", "—"), E(s.get("ledger_last") or "—"), s["derived_ok"],
                        sum(s["flags"].get(f, 0) for f in ("missing_product_as_zero", "formula_changed", "feed_mismatch"))))


def cat_chips(reg, cur=None):
    by = reg["summary"]["by_cat"]
    out = []
    for cat in CHEM_CATS:
        n = by.get(cat, 0)
        out.append('<a href="spreads.html#cat=%s"%s><b>%s</b>%d</a>' % (E(cat), ' aria-current="true"' if cat == cur else "", E(cat), n))
    out.append('<a href="spreads.html#cat=파생"><b>파생</b>%d</a>' % reg["summary"]["derived_ok"])
    return '<div class="catchips">%s</div>' % "".join(out)


def chain_cards(reg):
    chem = ["refining", "ncc", "aromatics", "butadiene", "vinyls", "urethane", "solvents"]
    cards = []
    rows_by_chain = {}
    for r in reg["rows"]:
        if r["kind"] == "spread":
            rows_by_chain.setdefault(r["chain"] or r["chain_est"], []).append(r)
    for cid in chem:
        c = reg["chains"].get(cid)
        if not c:
            continue
        mom = c.get("mom") or {}
        n_sp = len(rows_by_chain.get(cid, []))
        pos = c.get("pos")
        cards.append(
            '<div class="cardlink" style="cursor:default"><div class="t"><b>%s</b><span class="code">%s</span></div>'
            '<p class="mut">허브 체인 사이클 위치(자동 프록시 %s개 기준 — 원장 스프레드는 집계에 들어가지 않음) · 이 탭의 스프레드 %d개</p>'
            '<div class="stat"><div><b>%s</b><span>체인 pos</span></div><div><b>%s</b><span>1W %%</span></div><div><b>%s</b><span>4W %%</span></div><div><b>%s</b><span>13W %%</span></div></div>'
            '<div style="margin-top:8px">%s</div></div>'
            % (E(c["label"]), E(cid), c.get("n", 0), n_sp,
               ("%d" % round(pos)) if pos is not None else "—", fmt(mom.get("w1")), fmt(mom.get("w4")), fmt(mom.get("w13")),
               stocks_html([dict(s, est=False) for s in c.get("stocks", [])])))
    return '<div class="cards">%s</div>' % "".join(cards)


# ── 페이지들 ────────────────────────────────────────────────

def index_html(reg):
    s = reg["summary"]
    body = notice_html(reg) + kpi_html(reg)
    body += '<h2 class="sec">카테고리<span>청크 13 + 파생 · 누르면 표에서 필터</span></h2>' + cat_chips(reg)
    body += ('<div class="cards">'
             '<a class="cardlink" href="spreads.html"><div class="t"><b>📋 스프레드 표</b></div><p>%d행 정렬·검색. 산식(역산 k·참조 지역)·사이클 위치·4주 변화·신선도·中선물 참고·종목.</p><div class="go">표 →</div></a>'
             '<a class="cardlink" href="matrix.html"><div class="t"><b>🧮 제품 × 지역 매트릭스</b></div><p>같은 제품의 지역별 스프레드를 한 줄에. 셀을 누르면 6선 비교 차트.</p><div class="go">매트릭스 →</div></a>'
             '<a class="cardlink" href="chains.html"><div class="t"><b>🔗 밸류체인</b></div><p>레지스트리의 원료→제품 관계로 자동 생성한 다이어그램. 노드를 누르면 스프레드·종목.</p><div class="go">밸류체인 →</div></a>'
             '<a class="cardlink" href="coverage.html"><div class="t"><b>🧾 커버리지</b></div><p>모집단 전수 %d — 미재현 %d · 체인 미배정 %d · 결함 의심 · 축 잘림 자동 소스.</p><div class="go">커버리지 →</div></a>'
             '</div>' % (s["rows"] + s["derived_ok"], s["rows"], s["unreproduced"], s["chain_missing"]))
    body += '<h2 class="sec">체인<span>허브(argus_data.chains) 값을 읽기 전용으로 표시 · 종목은 체인 단위 참고 라벨</span></h2>' + chain_cards(reg)
    body += ('<section class="card"><h2>이 탭이 하는 일과 하지 않는 일</h2><ul class="note">'
             '<li>원장 스프레드의 산식은 데이터에 없다. 이름(<code>제품-원료 스프레드(지역)</code>)과 주간 관측으로 <b>계수를 역산</b>해 병기한다 — 전부 추정이며 원장 수식을 본 것이 아니다.</li>'
             '<li>원장 값은 수정하지 않는다. 결함으로 보이는 것(BR−BD 결측 0 계산, 산식 변경, 이름과 다른 원료)은 배지로만 표시한다.</li>'
             '<li>中 선물·PPI 는 기준(통화·세금·스팟/선물)이 달라 같은 산식에 넣지 않는다 — 방향 참고 열.</li>'
             '<li>파생 스프레드(PE/PP/PX−납사 통합, 카프로락탐−벤젠, PVC−0.5에틸렌)는 공개 관행 계수로 이 탭이 계산한 것이다(원장에 없음).</li>'
             '<li>wj-stock 등 회원 전용 화면의 값·산식은 쓰지 않는다. 입력 fingerprint <code>%s</code>.</li></ul></section>' % E(reg["fingerprint"][:16]))
    body += '<script src="data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    return page("한국화학 — 스프레드 원장·산식·사이클", body, depth=0, h1="🧪 한국화학", nav=NAV[:1] + NAV[1:],
                lead="ARGUS 원장의 석유화학 스프레드 %d개를 산식·지역·신선도 축으로 다시 조립합니다. 계수는 역산 추정, 원장 값은 불가침, wj-stock 등 비공개 자료는 입력이 아닙니다." % s["spreads"])


def spreads_html(reg):
    rows = reg["rows"] + [d for d in reg["derived"] if d["values"] is not None]
    trs = []
    for r in rows:
        feeds = r.get("feeds") or []
        feed_txt = ", ".join("%s×%s" % (fmt_k(f["k"]), f["name"]) for f in feeds if f.get("name")) if feeds else "—"
        cf = r.get("cnfut")
        cf_txt = ('<span title="%s · %s %s">%s</span>' % (E(cf["name"]), E(cf["last_date"] or ""), E(cf["unit"] or ""), fmt(cf["last"], 0))) if cf else '<span class="mut">—</span>'
        rep = r.get("reproduced")
        rep_txt = ('<span class="flag ok">재현</span>' if rep else ('<span class="flag bad">미재현</span>' if rep is False else '<span class="flag est">추정</span>'))
        trs.append(
            '<tr data-cat="%s" data-layer="%s" data-region="%s" data-chain="%s">'
            '<td class="l">%s</td><td class="l"><b>%s</b><div class="fm">%s</div></td><td class="l">%s</td>'
            '<td class="l">%s</td><td class="l fm">%s</td><td class="l">%s</td>'
            '<td data-v="%s">%s</td><td class="l">%s</td><td data-v="%s">%s</td><td data-v="%s">%s</td>'
            '<td class="l">%s</td><td><svg class="spk" data-sid="%s" aria-label="%s 추이"></svg></td>'
            '<td data-v="%s">%s</td><td class="l">%s</td><td class="l">%s</td></tr>'
            % (E(r["cat"]), E(r.get("layer") or ""), E(r.get("region") or ""), E(r.get("chain") or r.get("chain_est") or ""),
               E(r["cat"]), E(r["name"]), E(r.get("formula") or ""), E(LAYER_KO.get(r.get("layer"), r.get("layer") or "")),
               E(r.get("product") or "—"), E(feed_txt), E(r.get("region") or "—"),
               r.get("last") if r.get("last") is not None else "", fmt(r.get("last")), E(r.get("last_date") or "—"),
               r.get("m4") if r.get("m4") is not None else "", fmt(r.get("m4")),
               r.get("pos") if r.get("pos") is not None else "", pos_html(r.get("pos")),
               fr_chip(r.get("freshness")) + (' <small class="mut">%s주</small>' % r["weeks_since"] if r.get("weeks_since") not in (None, 0) else ""),
               E(r["sid"]), E(r["name"]),
               cf["last"] if cf and cf.get("last") is not None else "", cf_txt,
               rep_txt + flags_html([f for f in r.get("flags", []) if f != "unreproduced"]) + stocks_html(r.get("stocks") or []),
               link_html(r["sid"]) if not r["sid"].startswith("derived:") else '<span class="mut">파생</span>'))
    body = notice_html(reg) + cat_chips(reg)
    body += ('<div class="ctl"><input id="q" data-filter="#sp" type="search" placeholder="제품·원료·지역·카테고리·종목 검색 (예: 에틸렌 한국)">'
             '<label>레이어 <select id="layer"><option value="">전체</option>%s</select></label>'
             '<label>지역 <select id="region"><option value="">전체</option>%s</select></label>'
             '<label>카테고리 <select id="cat"><option value="">전체</option>%s</select></label></div>'
             % ("".join('<option value="%s">%s</option>' % (E(k), E(v)) for k, v in LAYER_KO.items()),
                "".join('<option value="%s">%s</option>' % (E(x), E(x)) for x in sorted(reg["summary"]["regions"], key=sort_region)),
                "".join('<option value="%s">%s</option>' % (E(c), E(c)) for c in CHEM_CATS + ["파생"])))
    body += ('<div class="wrap tall"><table id="sp" data-sortable><thead><tr><th class="l">카테고리</th><th class="l">시리즈 · 역산 산식</th><th class="l">레이어</th>'
             '<th class="l">제품</th><th class="l">원료(k·참조)</th><th class="l">지역</th><th>최신</th><th class="l">관측일</th><th>4W%%</th><th>사이클 위치</th>'
             '<th class="l">신선도</th><th>5년 추이</th><th>中선물</th><th class="l">판정·플래그·종목</th><th class="l">링크</th></tr></thead><tbody>%s</tbody></table></div>'
             % "".join(trs))
    body += ('<p class="note">사이클 위치 = ARGUS 허브의 전 이력 백분위(pos). 4W% = 허브 m4(카드에서는 렌더되지 않는 값을 여기서 표시). '
             '추이는 청크 255주(파생은 104주, 中선물은 자기 관측). 계수 k 는 최소제곱 역산 — <code>k_2pt</code>·잔차·이상치 주는 tools/assets/registry.json.</p>')
    body += '<script src="data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    body += r"""<script>
(function(){
  var tb=document.getElementById('sp'), sel={layer:document.getElementById('layer'),region:document.getElementById('region'),cat:document.getElementById('cat')}, q=document.getElementById('q');
  function apply(){var f={layer:sel.layer.value,region:sel.region.value,cat:sel.cat.value}; var s=q.value.trim().toLowerCase();
    Array.prototype.forEach.call(tb.tBodies[0].rows,function(r){var ok=true; for(var k in f){ if(f[k]&&r.dataset[k]!==f[k]) ok=false; }
      if(ok&&s&&r.textContent.toLowerCase().indexOf(s)<0) ok=false; r.hidden=!ok;});}
  for(var k in sel){ sel[k].addEventListener('change',apply); }
  q.addEventListener('input',apply);
  var m=location.hash.match(/cat=([^&]+)/); if(m){ sel.cat.value=decodeURIComponent(m[1]); apply(); }
  window.addEventListener('hashchange',function(){var m=location.hash.match(/cat=([^&]+)/); sel.cat.value=m?decodeURIComponent(m[1]):''; apply();});
})();
</script>"""
    return page("한국화학 — 스프레드 표", body, depth=0, h1="📋 스프레드 표", nav=NAV, crumbs=(("한국화학", "index.html"), ("표", "")),
                lead="원장 스프레드 %d + 파생 %d. 열 머리를 누르면 정렬, 위 검색·선택으로 필터. 산식은 이름과 관측으로 역산한 추정입니다." % (reg["summary"]["rows"], reg["summary"]["derived_ok"]))


def matrix_html(reg):
    rows = [r for r in reg["rows"] if r["kind"] == "spread"] + [d for d in reg["derived"] if d["values"] is not None]
    # 행 = (레이어, 제품 + 원료 토큰 묶음) ; 열 = 지역
    groups = {}
    for r in rows:
        feeds = r.get("feeds") or []
        key_feed = "&".join(f["token"] for f in feeds) if feeds else "?"
        base = r["name"].split(" 스프레드(")[0] if " 스프레드(" in r["name"] else r["name"].rsplit("(", 1)[0]
        gk = (r.get("layer") or "", base)
        g = groups.setdefault(gk, {"label": base, "layer": r.get("layer"), "cells": {}, "feed": key_feed, "derived": r["sid"].startswith("derived:")})
        g["cells"][r.get("region") or "—"] = r
    regions = sorted({r.get("region") or "—" for r in rows}, key=sort_region)
    order = ["crack", "integrated", "step", "composite", "unknown"]
    keys = sorted(groups, key=lambda k: (order.index(k[0]) if k[0] in order else 9, k[1]))
    trs = []
    for k in keys:
        g = groups[k]
        tds = []
        for reg_name in regions:
            r = g["cells"].get(reg_name)
            if not r:
                tds.append('<td><span class="empty">·</span></td>')
                continue
            pos = r.get("pos")
            pcls = "" if pos is None else ("p0" if pos <= 10 else "p1" if pos <= 25 else "p4" if pos >= 90 else "p3" if pos >= 75 else "")
            tds.append('<td><button type="button" class="cell %s %s" data-sid="%s" data-row="%s" title="%s · %s · pos %s">%s<small>%s</small></button></td>'
                       % (pcls, "dead" if r.get("freshness") == "dead" else "", E(r["sid"]), E(g["label"]), E(r["name"]), E(r.get("last_date") or ""),
                          "—" if pos is None else round(pos), fmt(r.get("last")), E((r.get("last_date") or "")[2:7])))
        trs.append('<tr><td class="rh">%s<small>%s%s</small></td>%s</tr>'
                   % (E(g["label"]), E(LAYER_KO.get(g["layer"], g["layer"] or "")), " · 파생" if g["derived"] else "", "".join(tds)))
    body = notice_html(reg)
    body += ('<div class="wrap tall"><table class="mx"><thead><tr><th style="text-align:left">제품 − 원료 <small class="mut">(레이어)</small></th>%s</tr></thead><tbody>%s</tbody></table></div>'
             % ("".join("<th>%s</th>" % E(x) for x in regions), "".join(trs)))
    body += ('<p class="note">셀 = 최신 스프레드(USD/MT)와 관측 연월. 바탕색은 사이클 위치(≤10% 진한 초록 · ≤25% 초록 · ≥75% 붉음 · ≥90% 진한 붉음). '
             '흐린 셀은 장기 미갱신. 셀을 누르면 그 제품의 지역별 스프레드를 겹쳐 그립니다. 지역은 시리즈 이름의 접미사에서 파생한 것이며 '
             '원료 참조 지역(모든 −납사는 Naphtha 일본, 중국 제품은 한국 원료)은 표의 원료 열에 적혀 있습니다.</p>')
    body += '<div id="det" class="detail" hidden><h3 id="detTitle"></h3><div id="detFormula"></div><div class="kchart-box" id="detChart"></div></div>'
    body += '<script src="data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    body += r"""<script>
(function(){
  var D=window.KCHEM, rows={}; D.rows.forEach(function(r){rows[r.sid]=r;});
  var det=document.getElementById('det'), tt=document.getElementById('detTitle'), fo=document.getElementById('detFormula'), box=document.getElementById('detChart');
  document.querySelectorAll('.mx .cell').forEach(function(b){ b.addEventListener('click',function(){
    document.querySelectorAll('.mx .cell.sel').forEach(function(x){x.classList.remove('sel');});
    var label=b.dataset.row, sids=[]; document.querySelectorAll('.mx .cell[data-row]').forEach(function(x){ if(x.dataset.row===label){ sids.push(x.dataset.sid); x.classList.add('sel'); } });
    var r=rows[b.dataset.sid]; tt.textContent=label+' — 지역별 비교 ('+sids.length+'선)';
    fo.textContent=''; if(r&&r.formula){var s=document.createElement('span');s.className='formula';s.textContent=r.formula+(r.reproduced===false?'  (미재현)':r.reproduced===true?'  (역산 재현)':'  (추정)');fo.appendChild(s);}
    box.dataset.sids=sids.join(','); det.hidden=false; window.KCHEMUI.chart(box); det.scrollIntoView({behavior:'smooth',block:'nearest'});
  });});
})();
</script>"""
    return page("한국화학 — 제품×지역 매트릭스", body, depth=0, h1="🧮 제품 × 지역", nav=NAV, crumbs=(("한국화학", "index.html"), ("매트릭스", "")),
                lead="같은 제품-원료 스프레드를 지역별로 한 줄에 놓습니다. 표준 6지역(한국·대만·일본·동남아·미국·유럽)과 중국 Huadong/Huanan·동북아·인도·나프타 허브.")


def _stage_of(reg):
    """원료→제품 그래프에서 단계 번호를 유도한다(뿌리: 원유 0·나프타 1, 나머지는 원료 단계+1; 모르면 사전값)."""
    al = load_asset("aliases.json")
    roots = dict(al["stage_roots"])
    prod_of = {}            # 제품 이름(영문 토큰) → 원료 이름 토큰 집합
    name_of = {}            # 영문 토큰 → 표시명(한글 토큰)
    for r in reg["rows"]:
        if r["kind"] not in ("spread",) or not r.get("product"):
            continue
        ptok = al["product_alias"].get(r["product"], r["product"])
        name_of.setdefault(ptok, r["product"])
        for f in r.get("feeds") or []:
            ftok = f["name"].rsplit(" ", 1)[0] if f.get("name") else f["token"]
            if f["sid"] == "sp_dubai_유가":
                ftok = "sp_dubai_유가"
            prod_of.setdefault(ptok, set()).add(ftok)
            name_of.setdefault(ftok, f["token"])
    for r in reg["rows"]:
        if r["kind"] == "price" and r.get("product"):
            ptok = al["product_alias"].get(r["product"], r["product"])
            name_of.setdefault(ptok, r["product"])
            prod_of.setdefault(ptok, set())
    stage = dict(roots)

    def st(tok, seen=()):
        if tok in stage:
            return stage[tok]
        if tok in seen:
            return None
        feeds = prod_of.get(tok)
        if not feeds:
            return None
        vals = [st(f, seen + (tok,)) for f in feeds]
        vals = [v for v in vals if v is not None]
        if not vals:
            return None
        stage[tok] = max(vals) + 1
        return stage[tok]
    for tok in list(prod_of):
        st(tok)
    name_of["sp_dubai_유가"] = "Dubai(원유)"
    return stage, prod_of, name_of


def chains_html(reg):
    stage, prod_of, name_of = _stage_of(reg)
    rows_by_prod = {}
    for r in reg["rows"] + [d for d in reg["derived"] if d["values"] is not None]:
        if r.get("product"):
            al_tok = r["product"]
            rows_by_prod.setdefault(al_tok, []).append(r)
    al = load_asset("aliases.json")
    inv = {v: k for k, v in al["product_alias"].items()}
    nodes = sorted(set(list(prod_of) + [f for fs in prod_of.values() for f in fs]), key=lambda t: (stage.get(t) if stage.get(t) is not None else 9, t))
    cols = {}
    for t in nodes:
        cols.setdefault(stage.get(t) if stage.get(t) is not None else 9, []).append(t)
    # SVG 배치 — 열 = 단계, 행 = 열 안 순서
    CW, RH, PADX, PADY, BW, BH = 190, 30, 40, 40, 150, 22
    col_keys = sorted(cols)
    W = PADX * 2 + CW * len(col_keys)
    H = PADY * 2 + RH * max(len(v) for v in cols.values()) + 10
    xy = {}
    svg = ['<svg class="chaindiag" viewBox="0 0 %d %d" role="img" aria-label="석유화학 밸류체인(레지스트리 원료→제품 관계)"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#5d6675"/></marker></defs>' % (W, H)]
    stage_label = {0: "0 · 원유", 1: "1 · 나프타·기초", 2: "2 · NCC/BTX", 3: "3 · 1차 다운스트림", 4: "4 · 2차 다운스트림", 5: "5 · 3차", 6: "6", 9: "단계 미상"}
    for ci, c in enumerate(col_keys):
        x = PADX + ci * CW
        svg.append('<text class="stg" x="%d" y="%d">%s</text>' % (x, PADY - 14, E(stage_label.get(c, str(c)))))
        for ri, t in enumerate(cols[c]):
            y = PADY + ri * RH
            xy[t] = (x, y)
    for t in sorted(prod_of):
        for f in sorted(prod_of[t]):
            if t in xy and f in xy:
                x1, y1 = xy[f][0] + BW, xy[f][1] + BH / 2
                x2, y2 = xy[t][0], xy[t][1] + BH / 2
                mx = (x1 + x2) / 2
                svg.append('<path class="edge" data-from="%s" data-to="%s" d="M%d %d C%d %d %d %d %d %d"/>' % (E(f), E(t), x1, y1, mx, y1, mx, y2, x2, y2))
    for t in nodes:
        x, y = xy[t]
        ko = inv.get(t, name_of.get(t, t))
        n_sp = len([r for r in rows_by_prod.get(ko, []) if r["kind"] in ("spread", "derived")])
        svg.append('<g class="node" data-tok="%s" data-ko="%s" tabindex="0" role="button"><rect x="%d" y="%d" width="%d" height="%d"/>'
                   '<text x="%d" y="%d">%s</text><text class="sm" x="%d" y="%d" text-anchor="end">%s</text></g>'
                   % (E(t), E(ko), x, y, BW, BH, x + 8, y + 15, E(ko if len(ko) <= 14 else ko[:13] + "…"), x + BW - 6, y + 15, ("%d" % n_sp) if n_sp else ""))
    svg.append("</svg>")
    # 노드별 상세 데이터
    detail = {}
    for ko, rs in rows_by_prod.items():
        detail[ko] = [{"sid": r["sid"], "name": r["name"], "formula": r.get("formula"), "reproduced": r.get("reproduced"), "last": r.get("last"),
                       "last_date": r.get("last_date"), "pos": r.get("pos"), "freshness": r.get("freshness"), "kind": r["kind"],
                       "stocks": r.get("stocks") or [], "flags": r.get("flags") or []} for r in rs]
    body = notice_html(reg)
    body += '<div class="wrap">%s</div>' % "".join(svg)
    body += '<p class="note">노드 = 레지스트리에 제품 또는 원료로 등장하는 품목, 화살표 = 역산된 원료→제품 관계(이름에 없던 원료 포함). 숫자 = 그 제품의 스프레드 수. 단계는 그래프에서 유도(원유 0·나프타 1), 모르면 "단계 미상". 노드를 누르면 스프레드·종목.</p>'
    body += '<div id="det" class="detail" hidden><h3 id="detTitle"></h3><div id="detBody"></div><div class="kchart-box" id="detChart" hidden></div></div>'
    body += '<script src="data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    body += '<script>window.KCHEM_NODES=%s;</script>' % json_for_html(detail)
    body += r"""<script>
(function(){
  var det=document.getElementById('det'), tt=document.getElementById('detTitle'), bd=document.getElementById('detBody'), box=document.getElementById('detChart');
  var nodes=document.querySelectorAll('.chaindiag .node'), edges=document.querySelectorAll('.chaindiag .edge');
  function fr(f){var s=document.createElement('span');s.className='fr '+(f||'none');s.textContent={fresh:'정상',late:'지연',stale:'오래됨',dead:'장기 미갱신'}[f]||'—';return s;}
  function show(g){
    var tok=g.dataset.tok, ko=g.dataset.ko, rel={}; rel[tok]=1;
    edges.forEach(function(e){ var on=(e.dataset.from===tok||e.dataset.to===tok); e.classList.toggle('rel',on); e.classList.toggle('dim',!on); if(on){rel[e.dataset.from]=1;rel[e.dataset.to]=1;} });
    nodes.forEach(function(n){ n.classList.toggle('sel',n===g); n.classList.toggle('rel',n!==g&&!!rel[n.dataset.tok]); n.classList.toggle('dim',!rel[n.dataset.tok]); });
    var list=window.KCHEM_NODES[ko]||[]; tt.textContent=ko+' — 스프레드 '+list.filter(function(r){return r.kind!=='price';}).length+'개';
    bd.textContent=''; var ul=document.createElement('ul'); ul.style.listStyle='none';
    var sids=[]; var seen={};
    list.forEach(function(r){ var li=document.createElement('li'); li.style.padding='3px 0';
      var b=document.createElement('b'); b.textContent=r.name; li.appendChild(b); li.appendChild(document.createTextNode(' '));
      li.appendChild(fr(r.freshness)); li.appendChild(document.createTextNode(' '+(r.last==null?'—':window.KCHEMUI.fmt(r.last))+' USD/MT · '+(r.last_date||'')+(r.pos==null?'':' · pos '+Math.round(r.pos))));
      if(r.formula){ var f=document.createElement('div'); f.className='fm'; f.textContent=r.formula+(r.reproduced===false?' (미재현)':r.reproduced===true?' (재현)':' (추정)'); li.appendChild(f); }
      if(r.stocks&&r.stocks.length&&!seen.st){ seen.st=1; var st=document.createElement('div'); st.className='stocks'; r.stocks.forEach(function(s){var a=document.createElement('a');a.href=s.t+'/index.html';a.textContent=s.n;if(s.est)a.className='est';st.appendChild(a);}); li.appendChild(st); }
      ul.appendChild(li); if(r.kind!=='price'&&sids.length<8) sids.push(r.sid); });
    bd.appendChild(ul); det.hidden=false;
    if(sids.length){ box.hidden=false; box.dataset.sids=sids.join(','); window.KCHEMUI.chart(box); } else { box.hidden=true; }
    det.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  nodes.forEach(function(g){ g.addEventListener('click',function(){show(g);}); g.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); show(g);} }); });
})();
</script>"""
    return page("한국화학 — 밸류체인", body, depth=0, h1="🔗 밸류체인", nav=NAV, crumbs=(("한국화학", "index.html"), ("밸류체인", "")),
                lead="원유 → 나프타 → NCC/BTX → 다운스트림. 그림은 외부 지식이 아니라 레지스트리가 역산한 원료→제품 관계에서 자동으로 그려집니다.")


def coverage_html(reg):
    s = reg["summary"]
    rows = reg["rows"]

    def table(rs, extra_cols=()):
        trs = []
        for r in rs:
            trs.append('<tr><td class="l">%s</td><td class="l">%s<div class="fm">%s</div></td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td>'
                       '<td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td></tr>'
                       % (E(r["cat"]), E(r["name"]), E(r["sid"]), E(r.get("kind") or ""), E(LAYER_KO.get(r.get("layer"), r.get("layer") or "")),
                          E(r.get("chain") or ("%s (추정)" % r["chain_est"] if r.get("chain_est") else "—")), E(r.get("region") or "—"),
                          fr_chip(r.get("freshness")) + " " + E(r.get("last_date") or ""), E(r.get("lane") or "—"),
                          ('<span class="flag ok">재현</span>' if r.get("reproduced") else ('<span class="flag bad">미재현</span>' if r.get("reproduced") is False else "—")) + flags_html([f for f in r.get("flags", []) if f != "unreproduced"]),
                          E(r.get("k_source") or r.get("reason") or "")))
        return ('<div class="wrap tall"><table data-sortable><thead><tr><th class="l">카테고리</th><th class="l">시리즈</th><th class="l">종류</th><th class="l">레이어</th><th class="l">체인</th>'
                '<th class="l">지역</th><th class="l">신선도 · 관측일</th><th class="l">lane</th><th class="l">판정·플래그</th><th class="l">근거</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))

    body = notice_html(reg)
    body += ('<div class="kpi"><div><b>%d</b><span>모집단 = 스프레드 패널의 화학 13 카테고리 전수</span></div><div><b>%d</b><span>스프레드(sp=true)</span></div>'
             '<div><b>%d</b><span>미재현(산식 역산 실패·겹침 부족·시리즈 없음)</span></div><div><b>%d</b><span>체인 미배정 → 추정 배정 %d</span></div>'
             '<div><b>%d</b><span>장기 미갱신(dead)</span></div></div>'
             % (s["rows"], s["spreads"], s["unreproduced"], s["chain_missing"], s["chain_est_assigned"], s["freshness"].get("dead", 0)))
    body += '<h2 class="sec">판정 규칙<span>registry.json rules</span></h2><dl class="kv">%s</dl>' % "".join(
        "<dt>%s</dt><dd>%s</dd>" % (E(k), E(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)) for k, v in reg["rules"].items())
    bad = [r for r in rows if r["kind"] == "spread" and any(f in r.get("flags", []) for f in ("missing_product_as_zero", "feed_mismatch", "formula_changed"))]
    body += '<h2 class="sec">결함 의심·산식 변경·원료 불일치 %d<span>원장 값은 수정하지 않는다 — 운영자 보고용</span></h2>%s' % (len(bad), table(bad))
    unrep = [r for r in rows if r["kind"] == "spread" and not r.get("reproduced")]
    body += '<h2 class="sec">미재현 %d<span>2시점 k 와 잔차는 registry.json fit 참조</span></h2>%s' % (len(unrep), table(unrep))
    nochain = [r for r in rows if not r.get("chain")]
    body += '<h2 class="sec">체인 미배정 %d<span>chain_est 는 aliases.json 의 추정 배정 — 빌더 chains.json 반영은 diff 제안</span></h2>%s' % (len(nochain), table(nochain))
    dead = [r for r in rows if r.get("freshness") == "dead"]
    body += '<h2 class="sec">장기 미갱신 %d<span>원장 열 종료</span></h2>%s' % (len(dead), table(dead))
    auto = [r for r in rows if r["kind"] in ("proxy_cnfut", "index")]
    body += '<h2 class="sec">자동 소스(청크 축 잘림 우회) %d<span>표·차트는 connections 관측으로 그린다</span></h2>%s' % (len(auto), table(auto))
    body += '<h2 class="sec">전수 %d<span>모든 행</span></h2>%s' % (len(rows), table(rows))
    body += '<script>%s</script>' % TABLE_JS
    return page("한국화학 — 커버리지", body, depth=0, h1="🧾 커버리지", nav=NAV, crumbs=(("한국화학", "index.html"), ("커버리지", "")),
                lead="이 탭의 모집단은 상장사가 아니라 스프레드 시리즈입니다. 빠진 것·못 푼 것도 이유와 함께 보입니다.")


def stock_html(reg, t, name, chains_of):
    rows = [r for r in reg["rows"] + [d for d in reg["derived"] if d["values"] is not None]
            if r.get("kind") in ("spread", "derived") and (r.get("chain") or r.get("chain_est")) in chains_of]
    rows.sort(key=lambda r: ((r.get("chain") or r.get("chain_est") or ""), r["cat"], r["name"]))
    trs = []
    for r in rows:
        trs.append('<tr><td class="l">%s%s</td><td class="l">%s</td><td class="l"><b>%s</b><div class="fm">%s</div></td><td data-v="%s">%s</td><td class="l">%s</td>'
                   '<td data-v="%s">%s</td><td><svg class="spk" data-sid="%s"></svg></td><td class="l">%s</td></tr>'
                   % (E(reg["chains"].get(r.get("chain") or r.get("chain_est"), {}).get("label", "")), " (추정)" if not r.get("chain") else "",
                      E(r["cat"]), E(r["name"]), E(r.get("formula") or ""), r.get("last") if r.get("last") is not None else "", fmt(r.get("last")),
                      E(r.get("last_date") or ""), r.get("pos") if r.get("pos") is not None else "", pos_html(r.get("pos")), E(r["sid"]),
                      fr_chip(r.get("freshness")) + flags_html([f for f in r.get("flags", []) if f not in ("unreproduced",)])))
    notes = []
    for cid in chains_of:
        for st in reg["chains"].get(cid, {}).get("stocks", []):
            if st["t"] == t and st.get("note"):
                notes.append("%s: %s" % (reg["chains"][cid]["label"], st["note"]))
    body = notice_html(reg)
    body += ('<div class="notice info"><div class="sym">ℹ</div><div><p>종목 연결은 ARGUS 허브의 <b>체인 단위 참고 라벨</b>입니다(스프레드별 감도·매출 비중 아님). '
             '%s</p></div></div>' % E(" · ".join(notes)))
    body += ('<div class="wrap tall"><table data-sortable><thead><tr><th class="l">체인</th><th class="l">카테고리</th><th class="l">스프레드 · 산식</th><th>최신</th><th class="l">관측일</th>'
             '<th>사이클 위치</th><th>5년 추이</th><th class="l">신선도·플래그</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))
    body += '<script src="../data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    return page("%s — 화학 스프레드 역참조" % name, body, depth=1, h1=name, tags=(t,),
                nav=(("← 한국화학", "../index.html"), ("표", "../spreads.html"), ("매트릭스", "../matrix.html")),
                crumbs=(("한국화학", "../index.html"), (name, "")),
                lead="이 종목이 매핑된 체인(%s)의 스프레드 %d개." % (", ".join(reg["chains"][c]["label"] for c in chains_of), len(rows)))


# ── 빌드 ────────────────────────────────────────────────────

def build(write=True):
    global CHEM_CATS
    inputs, fp = kchem_inputs.load_all()
    CHEM_CATS = list(inputs["chem_cats"])
    reg = kchem_registry.Registry(inputs, fp).build()
    outputs = {
        os.path.join(DATA_DIR, "kchem_data.js"): build_data_js(reg, inputs),
        os.path.join(KCHEM, "index.html"): index_html(reg),
        os.path.join(KCHEM, "spreads.html"): spreads_html(reg),
        os.path.join(KCHEM, "matrix.html"): matrix_html(reg),
        os.path.join(KCHEM, "chains.html"): chains_html(reg),
        os.path.join(KCHEM, "coverage.html"): coverage_html(reg),
    }
    stocks = {}
    for cid, c in reg["chains"].items():
        for st in c.get("stocks", []):
            stocks.setdefault(st["t"], {"name": st["n"], "chains": []})["chains"].append(cid)
    for t, info in sorted(stocks.items()):
        outputs[os.path.join(KCHEM, t, "index.html")] = stock_html(reg, t, info["name"], info["chains"])
    for path, text in outputs.items():
        if len(text.encode("utf-8")) > 5 * 1024 * 1024:
            raise kchem_inputs.InputError("산출물 5MB 초과: %s" % path)
    if write:
        from kchem_lib import write_asset
        write_asset("registry.json", reg)
        write_asset("fingerprint.json", {"fingerprint": fp["fingerprint"], "inputs": fp["inputs"], "argus_asof": fp["argus_asof"]})
        for path, text in outputs.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, text)
    return reg, outputs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    reg, outputs = build(write="--dry-run" not in argv)
    s = reg["summary"]
    print("kchem: rows %d · reproduced %d/%d · derived %d · pages %d · fingerprint %s%s"
          % (s["rows"], s["reproduced"], s["spreads"], s["derived_ok"], len(outputs), reg["fingerprint"][:12], " (dry-run)" if "--dry-run" in argv else ""))


if __name__ == "__main__":
    main()
