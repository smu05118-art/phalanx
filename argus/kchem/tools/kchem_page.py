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
import datetime
import json
import os
import sys

from kchem_lib import (ASSETS, DATA_DIR, E, KCHEM, KCHEM_JS, TABLE_JS, atomic_write, dump_json, fmt, fmt_k,
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
    "crack_usd_bbl": ("USD/bbl 크랙(나프타/9.26 − Dubai)", "est"),
    "carry_forward": ("원장 이월 주 — 실제 정지가 더 이르다", "bad"),
    "formula_episode": ("일시 이탈 후 복귀", "est"),
}
HUNT_NOTE = ("허브 사냥 신호(bt 바닥 반전·pw·ac) 개수. 2026-08-31 검증: bottom_turn 4주 적중 63.0% ≈ 바닥권 base rate 63.9% "
             "— 부가가치 없음. 신호로 쓰지 말 것.")
REGION_ORDER = ["한국", "대만", "일본", "동남아", "동북아", "중국", "중국 Huadong", "중국 Huanan", "인도", "싱가포르", "미국", "유럽",
                "ARA", "Rdam", "MED", "Genoa", "USGC", "Arab Gulf"]
NAV = (("← ARGUS", "../index.html"), ("표", "spreads.html"), ("가격", "prices.html"), ("매트릭스", "matrix.html"),
       ("밸류체인", "chains.html"), ("커버리지", "coverage.html"))


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
                                        "weeks_since", "stocks", "cnfut", "product_sid", "grade", "unit_hint", "dup_of",
                                        "effective_last")} for r in reg["rows"] + reg["derived"]]
    data = {"fingerprint": reg["fingerprint"], "argus_asof": reg["argus_asof"],
            "axes": {"wk": axis_wk, "wk2y": reg["axis2y"]}, "series": series, "rows": slim_rows,
            "chains": reg["chains"], "chain_view": reg["chain_view"], "summary": reg["summary"], "rules": reg["rules"],
            "proxies": [{k: p.get(k) for k in ("sid", "name", "unit", "freq", "product", "chain", "ledger_name", "check", "post_halt", "lag",
                                               "last", "last_date", "freshness")} for p in reg["proxies"]]}
    return "window.KCHEM=" + json_for_html(data) + ";\n"


# ── 공통 조각 ───────────────────────────────────────────────

def supp_notice(reg):
    """사용자 가격표로 원장 뒤를 이은 경우의 고지 — 원장 정지 사실과 이은 범위를 같이 적는다."""
    sp = reg["summary"].get("supplement")
    if not sp:
        return ""
    s = reg["summary"]
    ed = sp.get("editions") or {}
    return ('<div class="notice"><div class="sym">⚠</div><div><p><b>원장 정지 %s주</b>(마지막 원장 관측 %s · 편집 누락 %d) — '
            '사용자 가격표 <code>%s</code>(%s 주까지)로 <b>제품 가격 %d종</b>과 산식이 재현된 <b>스프레드 %d개</b>를 이었습니다. '
            '원장 값이 있는 날짜는 그대로 두고 그 뒤만 잇습니다. 겹치는 102주 대조에서 매핑한 열의 값이 원장과 같은 열만 씁니다'
            '(에탄 등 기준이 다른 열 %d개는 잇지 않음).</p>'
            '<p>나머지 스프레드 %d개는 원료가 가격표에 없거나(Dubai 유가·메탄올 등) 산식이 재현되지 않아 원장 날짜에 멈춰 있습니다. '
            '이은 행은 <span class="flag ok">가격표 연장</span> 배지, 사이클 위치는 kchem 5년 백분위로 다시 계산합니다(허브 pos 와 정의가 다를 수 있다).</p>'
            '<p class="mut">원장 정상 복구는 여전히 %s.</p></div></div>'
            % (s.get("ledger_stale_weeks", "—"), E(s.get("ledger_last") or "—"), ed.get("missing", 0), E(sp["file"]), E(sp["through"]),
               sp["prices_extended"], sp["spreads_extended"], sp.get("mismatch", 0),
               sp["spreads_total"] - sp["spreads_extended"], E(ed.get("recover", "최신 Weekly xlsm 1개 드롭"))))


def notice_html(reg):
    s = reg["summary"]
    if s.get("supplement"):
        return supp_notice(reg)
    wk = s.get("ledger_stale_weeks")
    if wk is None:
        return ""
    ed = s.get("editions") or {}
    if wk > 2:
        return ('<div class="notice"><div class="sym">⛔</div><div><p><b>원장 정지 %d주 · 편집 누락 %d개</b> — 마지막 원장 편집은 <code>%s</code>'
                '(관측 %s), 다음 기대 편집은 %s 였습니다. ARGUS 평가일 %s. 아래 주간 스프레드는 전부 %s 에 멈춰 있고(값은 그대로, 신선도 배지로 표시), '
                '사이클 위치는 <b>그 날짜 기준</b>입니다.</p>'
                '<p><b>복구 = 파일 1개</b>: %s. 코드 변경 없이 다음 ARGUS 빌드에 전부 반영됩니다.</p>'
                '<p class="mut">정지 중에도 갱신되는 입력: 프록시 %d종(검증 게이트 통과·정지 후 방향 표시 %d) — 원장 값·산식과 섞지 않습니다.</p></div></div>'
                % (wk, ed.get("missing", 0), E(ed.get("last_file", "—")), E(s["ledger_last"]), E(ed.get("next_expected", "—")),
                   E(reg["argus_asof"]), E(s["ledger_last"]), E(ed.get("recover", "")), s.get("proxies", 0), s.get("proxies_gated", 0)))
    return ('<div class="notice info"><div class="sym">ℹ</div><div><p>원장 마지막 관측 %s · 평가일 %s.</p></div></div>'
            % (E(s["ledger_last"]), E(reg["argus_asof"])))


def kpi_html(reg):
    s = reg["summary"]
    sf = s["spread_freshness"]
    g = s.get("grades") or {}
    return ('<div class="kpi">'
            '<div><b>%d</b><span>화학 시리즈(청크 %d 카테고리) · 스프레드 %d · 지역 간 복제 제외 고유 %d</span></div>'
            '<div><b>%d<small>/%d</small></b><span>산식 역산 재현 — 정확 %d(안쪽 잔차 ≤ %s) · 근사 %d</span></div>'
            '<div><b>%d</b><span>살아 있는 원장 스프레드 — 오래됨 %d · 장기 미갱신 %d</span></div>'
            '<div><b>%s주</b><span>원장 정지(마지막 %s) · 편집 누락 %d</span></div>'
            '<div><b>%d<small>/%d</small></b><span>살아 있는 프록시 — 정지 후 방향 표시(게이트 통과·시차 반영)</span></div>'
            '<div><b>%d</b><span>결함 의심·산식 변경·원료 불일치·이월 플래그</span></div>%s'
            '</div>' % (s["rows"], len(CHEM_CATS), s["spreads"], s.get("unique_spreads", s["spreads"]),
                        s["reproduced"], s["spreads"], g.get("exact", 0), fmt_k(reg["rules"]["exact_tol"]), g.get("approx", 0),
                        sf.get("fresh", 0), sf.get("stale", 0), sf.get("dead", 0),
                        s.get("ledger_stale_weeks", "—"), E(s.get("ledger_last") or "—"), (s.get("editions") or {}).get("missing", 0),
                        s.get("proxies_gated", 0), s.get("proxies", 0),
                        sum(s["flags"].get(f, 0) for f in ("missing_product_as_zero", "formula_changed", "feed_mismatch", "carry_forward")),
                        ('<div><b>%d<small>+%d</small></b><span><a href="prices.html">가격표 연장</a> — 제품 가격 · 스프레드(%s 주까지)</span></div>'
                         % (s["supplement"]["prices_extended"], s["supplement"]["spreads_extended"], E(s["supplement"]["through"])))
                        if s.get("supplement") else ""))


def cat_chips(reg, cur=None):
    by = reg["summary"]["by_cat"]
    out = []
    for cat in CHEM_CATS:
        n = by.get(cat, 0)
        out.append('<a href="spreads.html#cat=%s"%s><b>%s</b>%d</a>' % (E(cat), ' aria-current="true"' if cat == cur else "", E(cat), n))
    out.append('<a href="spreads.html#cat=파생"><b>파생</b>%d</a>' % reg["summary"]["derived_ok"])
    return '<div class="catchips">%s</div>' % "".join(out)


def _pct_html(v):
    if v is None:
        return '<span class="mut">—</span>'
    cls = "up" if v > 0 else ("dn" if v < 0 else "")
    return '<span class="%s">%s%s%%</span>' % (cls, "▲" if v > 0 else ("▼" if v < 0 else ""), fmt(abs(v)))


def chain_cards(reg):
    """체인 카드 — 원장 as-of 위치를 앞에, 허브 pos 는 그 기준(프록시 구성)과 함께 뒤에 둔다.

    허브 체인 pos 는 원장 스프레드가 아니라 中선물·PPI·NBS 등 프록시의 중앙값이다(2026-10 리뷰 #4).
    같은 '천장권' 색으로 회사 사이클처럼 읽히지 않도록, 허브 기준에 원장이 0 이면 pos 숫자를 크게 쓰지 않는다."""
    cards = []
    for cid, v in reg["chain_view"].items():
        basis = " · ".join("%s %d" % (k, n) for k, n in v["hub_basis"].items()) or "구성 없음"
        hub = ("허브 pos %s — 기준: %s%s" % (("%d" % round(v["hub_pos"])) if v["hub_pos"] is not None else "—", basis,
               "" if v["hub_has_ledger"] else " (원장 0 — 프록시 중앙값, 회사 사이클 아님)"))
        if v["post_halt_n"]:
            post = '%s <small class="mut">게이트 통과 %d종 중앙(%s)</small>' % (
                _pct_html(v["post_halt_median_pct"]), v["post_halt_n"], E(", ".join("%s %s%%" % (i["product"], fmt(i["pct"])) for i in v["post_halt_items"])))
        else:
            post = '<span class="mut">게이트 통과 프록시 없음 — 비표시</span>'
        h = v.get("hunts") or {}
        cards.append(
            '<div class="cardlink" style="cursor:default"><div class="t"><b>%s</b><span class="code">%s</span></div>'
            '<div class="stat"><div><b>%s</b><span>원장 as-of 위치(%s · 중위, %d개)</span></div><div><b>%s</b><span>정지 후 방향(프록시)</span></div></div>'
            '<p class="mut" style="margin:8px 0 0">%s</p>'
            '<p class="mut" style="margin:4px 0 0" title="%s">사냥 신호 bt %s · pw %s · ac %s — 검증 결과 부가가치 없음(참고만)</p>'
            '<div style="margin-top:8px">%s</div></div>'
            % (E(v["label"]), E(cid), ("%d" % round(v["ledger_pos_median"])) if v["ledger_pos_median"] is not None else "—",
               E(v["ledger_asof"] or "—"), v["ledger_n"], post, E(hub), E(HUNT_NOTE),
               h.get("bt", "—"), h.get("pw", "—"), h.get("ac", "—"),
               stocks_html([dict(s2, est=False) for s2 in v.get("stocks", [])])))
    return '<div class="cards">%s</div>' % "".join(cards)


def proxies_html(reg):
    """살아 있는 프록시 표 — 원장과 기준이 다른 값이라 원장 산식·pos·m4·채색에 넣지 않고 따로 보인다."""
    trs = []
    for p in reg["proxies"]:
        c = p.get("check") or {}
        if not p.get("ledger_sid"):
            verdict = '<span class="mut">대조할 원장 가격 없음 — 방향 비표시</span>'
        elif not c:
            verdict = '<span class="mut">겹침 부족 — 검증 불가</span>'
        elif c["gate"] and p.get("post_halt"):
            ph = p["post_halt"]
            verdict = '%s <small class="mut">%s → %s</small>' % (_pct_html(ph["pct"]), E(ph["from"]), E(ph["to"]))
        elif c["gate"]:
            verdict = '<span class="mut">게이트 통과 · 시차 %d개월 — 정지 이후 분 공표 전</span>' % p.get("lag", 0)
        else:
            verdict = '<span class="mut">게이트 미달 — 비표시</span>'
        trs.append('<tr id="p-%s"><td class="l"><b>%s</b><div class="fm">%s · %s</div></td><td class="l">%s</td><td class="l">%s</td>'
                   '<td>%s</td><td class="l">%s</td><td>%s</td><td>%s</td><td class="l">%s</td><td class="l">%s</td></tr>'
                   % (E(p["sid"]), E(p["name"]), E(p["unit"] or ""), E({"W": "주간", "M": "월간", "D": "일간"}.get(p["freq"], p["freq"] or "")),
                      E(p["product"]), E(p.get("ledger_name") or "—"), fmt(p.get("last"), 0), fr_chip(p.get("freshness")) + " " + E(p.get("last_date") or ""),
                      ("—" if c.get("hit_hold") is None else "%d%%" % round(c["hit_hold"] * 100)),
                      ("—" if c.get("r_hold") is None else fmt(c["r_hold"], 2)),
                      ("—" if not c else "%d쌍 · 시차 %d" % (c["n_hold"], c.get("lag", 0))), verdict))
    gate = reg["rules"]["live_gate"]
    return ('<div class="wrap"><table data-sortable><thead><tr><th class="l">프록시</th><th class="l">제품</th><th class="l">대조 원장</th><th>최신</th>'
            '<th class="l">신선도</th><th>홀드아웃 방향 적중</th><th>홀드아웃 r</th><th class="l">검증</th><th class="l">정지 후 방향</th></tr></thead>'
            '<tbody>%s</tbody></table></div>'
            '<p class="note">프록시 기간 Δ%%와 원장 제품 가격 Δ%%를 맞대어 최근 %d%%(최소 %d쌍)를 홀드아웃으로 두고, 방향 적중 ≥ %d%% · r ≥ %s 일 때만 '
            '<b>정지 후 방향</b>을 보입니다. 월간 무역단가는 원장보다 늦게 움직여(시차) 정지 이후 달이 공표된 뒤에만 표시합니다. '
            '이 값들은 원장 산식·사이클 위치·4W%%·채색에 들어가지 않습니다.</p>'
            % ("".join(trs), round(gate["hold_frac"] * 100), gate["min_hold"], round(gate["hit"] * 100), fmt_k(gate["r"])))


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
    body += ('<h2 class="sec">체인<span>원장 as-of 위치(중위) · 정지 후 방향(게이트 통과 프록시만) · 허브 pos 는 기준 구성과 함께 · 종목은 체인 단위 참고 라벨</span></h2>'
             + chain_cards(reg))
    body += ('<h2 class="sec">살아 있는 프록시<span>원장 정지 중에도 갱신 · 검증 게이트 통과분만 방향 표시 · 원장 값과 섞지 않음</span></h2>'
             + proxies_html(reg))
    body += ('<section class="card"><h2>이 탭이 하는 일과 하지 않는 일</h2><ul class="note">'
             '<li>원장 스프레드의 산식은 데이터에 없다. 이름(<code>제품-원료 스프레드(지역)</code>)과 주간 관측으로 <b>계수를 역산</b>해 병기한다 — 전부 추정이며 원장 수식을 본 것이 아니다.</li>'
             '<li>원장 값은 수정하지 않는다. 결함으로 보이는 것(BR−BD 결측 0 계산, 산식 변경, 이름과 다른 원료)은 배지로만 표시한다.</li>'
             '<li>中 선물·PPI·무역단가 프록시는 기준(통화·세금·스팟/선물·월간)이 달라 같은 산식·사이클 위치·채색에 넣지 않는다 — 검증 게이트를 통과한 것만 방향 참고.</li>'
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
        cf_txt = ('<span title="%s · %s">%s<small class="mut"> %s</small></span>' % (E(cf["name"]), E(cf["last_date"] or ""), fmt(cf["last"], 0), E(cf["unit"] or "CNY/t"))) if cf else '<span class="mut">—</span>'
        rep = r.get("reproduced")
        grade = {"exact": "정확", "approx": "근사"}.get(r.get("grade") or "", "")
        rep_txt = (('<span class="flag ok">재현%s</span>' % (("·" + grade) if grade else "")) if rep
                   else ('<span class="flag bad">미재현</span>' if rep is False else '<span class="flag est">추정</span>'))
        if r.get("dup_of"):
            rep_txt += '<span class="flag est" title="원장이 같은 시리즈를 여러 지역 이름으로 복사">=%s 복제</span>' % E(r.get("dup_of_region") or "?")
        halted = r.get("freshness") in ("stale", "dead")
        m4_cell = ('<td data-v="">—<small class="mut">(정지)</small></td>' if halted
                   else '<td data-v="%s">%s</td>' % (r.get("m4") if r.get("m4") is not None else "", fmt(r.get("m4"))))
        pos_cell = ('<td data-v="" class="deadpos">%s</td>' % pos_html(r.get("pos")) if r.get("freshness") == "dead"
                    else '<td data-v="%s">%s</td>' % (r.get("pos") if r.get("pos") is not None else "", pos_html(r.get("pos"))))
        date_txt = E(r.get("last_date") or "—")
        if r.get("carry_weeks") and r.get("effective_last") and r.get("effective_last") != r.get("last_date"):
            date_txt += '<div class="fm">이월 %d주 · 실제 %s</div>' % (len(r["carry_weeks"]), E(r["effective_last"]))
        unit_hint = (' <small class="mut">%s</small>' % E(r["unit_hint"])) if r.get("unit_hint") else ""
        trs.append(
            '<tr id="r-%s" data-cat="%s" data-layer="%s" data-region="%s" data-chain="%s">'
            '<td class="l">%s</td><td class="l"><b>%s</b>%s<div class="fm">%s</div></td><td class="l">%s</td>'
            '<td class="l">%s</td><td class="l fm">%s</td><td class="l">%s</td>'
            '<td data-v="%s">%s</td><td class="l">%s</td>%s%s'
            '<td class="l">%s</td><td><svg class="spk" data-sid="%s" aria-label="%s 추이"></svg></td>'
            '<td data-v="%s">%s</td><td class="l">%s</td><td class="l">%s</td></tr>'
            % (E(r["sid"]), E(r["cat"]), E(r.get("layer") or ""), E(r.get("region") or ""), E(r.get("chain") or r.get("chain_est") or ""),
               E(r["cat"]), E(r["name"]), unit_hint, E(r.get("formula") or ""), E(LAYER_KO.get(r.get("layer"), r.get("layer") or "")),
               E(r.get("product") or "—"), E(feed_txt), E(r.get("region") or "—"),
               r.get("last") if r.get("last") is not None else "", fmt(r.get("last")), date_txt,
               m4_cell, pos_cell,
               fr_chip(r.get("freshness")) + (' <small class="mut">%s주</small>' % r["weeks_since"] if r.get("weeks_since") not in (None, 0) else "")
               + (' <span class="flag ok" title="원장 %s 뒤를 사용자 가격표로 이음(같은 산식). 사이클 위치는 kchem 5년 백분위">가격표 연장</span>'
                  % E((reg["summary"].get("supplement") or {}).get("ledger_last") or "")
                  if r["sid"] in set((reg["summary"].get("supplement") or {}).get("spread_sids") or []) else ""),
               E(r["sid"]), E(r["name"]),
               cf["last"] if cf and cf.get("last") is not None else "", cf_txt,
               rep_txt + flags_html([f for f in r.get("flags", []) if f != "unreproduced"]) + stocks_html(r.get("stocks") or []),
               link_html(r["sid"]) if not r["sid"].startswith("derived:") else '<span class="mut">파생</span>'))
    body = notice_html(reg) + cat_chips(reg)
    body += ('<div class="ctl"><input id="q" type="search" placeholder="제품·원료·지역·카테고리·종목 검색 — 띄어 쓴 단어를 모두 포함 (예: 에틸렌 한국)">'
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
    body += ('<p class="note">사이클 위치 = ARGUS 허브의 전 이력 백분위(pos) — 원장 정지 시리즈는 정지 시점 기준. 4W% = 허브 m4이며, '
             '오래됨·장기 미갱신 행은 클립된 값(±200)이 정렬을 왜곡하므로 <b>—(정지)</b> 로 비우고, 장기 미갱신 행의 pos 는 흐리게·정렬 제외. '
             '행 주소는 <code>spreads.html#r-&lt;sid&gt;</code>. '
             '추이는 청크 255주(파생은 104주, 中선물은 자기 관측). 계수 k 는 최소제곱 역산 — <code>k_2pt</code>·잔차·이상치 주는 tools/assets/registry.json.</p>')
    body += '<script src="data/kchem_data.js"></script><script>%s</script><script>%s</script>' % (TABLE_JS, KCHEM_JS)
    body += r"""<script>
(function(){
  var tb=document.getElementById('sp'), sel={layer:document.getElementById('layer'),region:document.getElementById('region'),cat:document.getElementById('cat')}, q=document.getElementById('q');
  function apply(){var f={layer:sel.layer.value,region:sel.region.value,cat:sel.cat.value}; var toks=q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    Array.prototype.forEach.call(tb.tBodies[0].rows,function(r){var ok=true; for(var k in f){ if(f[k]&&r.dataset[k]!==f[k]) ok=false; }
      if(ok&&toks.length){var t=r.textContent.toLowerCase(); for(var i=0;i<toks.length;i++){ if(t.indexOf(toks[i])<0){ok=false;break;} }} r.hidden=!ok;});}
  function jump(){var m=location.hash.match(/^#r-(.+)$/); if(!m)return; var el=document.getElementById('r-'+decodeURIComponent(m[1])); if(!el)return;
    el.hidden=false; el.classList.add('hl'); el.scrollIntoView({block:'center'});}
  for(var k in sel){ sel[k].addEventListener('change',apply); }
  q.addEventListener('input',apply);
  var m=location.hash.match(/cat=([^&]+)/); if(m){ sel.cat.value=decodeURIComponent(m[1]); apply(); }
  window.addEventListener('hashchange',function(){var m=location.hash.match(/cat=([^&]+)/); sel.cat.value=m?decodeURIComponent(m[1]):''; apply(); jump();});
  jump();
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
            dead = r.get("freshness") == "dead"
            pcls = "" if (pos is None or dead) else ("p0" if pos <= 10 else "p1" if pos <= 25 else "p4" if pos >= 90 else "p3" if pos >= 75 else "")
            dup = r.get("dup_of_region")
            tds.append('<td><button type="button" class="cell %s %s %s" data-sid="%s" data-row="%s" title="%s · %s · pos %s%s">%s<small>%s</small></button></td>'
                       % (pcls, "dead" if dead else "", "dup" if dup else "", E(r["sid"]), E(g["label"]), E(r["name"]), E(r.get("last_date") or ""),
                          "—" if pos is None else round(pos), (" · %s 시리즈와 바이트 동일(복제)" % dup) if dup else "",
                          fmt(r.get("last")), ("=" + E(dup)) if dup else E((r.get("last_date") or "")[2:7])))
        trs.append('<tr><td class="rh">%s<small>%s%s</small></td>%s</tr>'
                   % (E(g["label"]), E(LAYER_KO.get(g["layer"], g["layer"] or "")), " · 파생" if g["derived"] else "", "".join(tds)))
    body = notice_html(reg)
    body += ('<div class="wrap tall"><table class="mx"><thead><tr><th style="text-align:left">제품 − 원료 <small class="mut">(레이어)</small></th>%s</tr></thead><tbody>%s</tbody></table></div>'
             % ("".join("<th>%s</th>" % E(x) for x in regions), "".join(trs)))
    body += ('<p class="note">셀 = 최신 스프레드(USD/MT)와 관측 연월. 바탕색은 사이클 위치(≤10%% 진한 초록 · ≤25%% 초록 · ≥75%% 붉음 · ≥90%% 진한 붉음). '
             '흐린 셀은 장기 미갱신(색 없음). <b>=지역</b> 셀은 원장이 다른 지역 시리즈를 바이트 그대로 복사한 것이라 지역 비교가 아닙니다 '
             '(복제 %d그룹 · 고유 스프레드 %d/%d). 셀을 누르면 그 제품의 지역별 스프레드를 겹쳐 그립니다. 지역은 시리즈 이름 접미사에서 파생했고, '
             '원료 참조 지역(−납사는 Naphtha 일본, 중국 제품은 한국 원료)은 역산으로 <b>추정</b>한 것입니다(원장 수식 미확인).</p>'
             % (reg["summary"].get("dup_groups", 0), reg["summary"].get("unique_spreads", 0), reg["summary"]["spreads"]))
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
    svg = ['<svg class="chaindiag" viewBox="0 0 %d %d" style="min-width:%dpx" role="img" aria-label="석유화학 밸류체인(레지스트리 원료→제품 관계)"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#5d6675"/></marker></defs>' % (W, H, W)]
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


def _spark(obs, w=120, h=28):
    pts = [(d, v) for d, v in obs if v is not None]
    if len(pts) < 2:
        return ""
    vs = [v for _d, v in pts]
    lo, hi = min(vs), max(vs)
    n = len(pts) - 1
    sx = lambda i: 1 + (w - 2) * i / n                     # noqa: E731
    sy = lambda v: h - 2 - (h - 4) * ((v - lo) / (hi - lo) if hi > lo else 0.5)   # noqa: E731
    path = " ".join("%.1f,%.1f" % (sx(i), sy(v)) for i, (_d, v) in enumerate(pts))
    return ('<svg class="spk" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="5년 추이 %s~%s">'
            '<polyline fill="none" stroke="currentColor" stroke-width="1.2" points="%s"/>'
            '<circle cx="%.1f" cy="%.1f" r="2" fill="currentColor"/></svg>'
            % (w, h, w, h, E(pts[0][0]), E(pts[-1][0]), path, sx(n), sy(pts[-1][1])))


def _chg(obs, weeks):
    pts = [(d, v) for d, v in obs if v is not None]
    if len(pts) <= weeks:
        return None
    a, b = pts[-1 - weeks][1], pts[-1][1]
    return round((b - a) / abs(a) * 100, 2) if a else None


def prices_html(reg):
    """사용자 가격표(제품 가격) — 최신·변화·5년/장기 위치·원장 대응. 원장 정지 뒤 7주를 잇는 근거 표."""
    sp = reg["summary"].get("supplement")
    series = reg.get("supplement_series") or []
    if not sp or not series:
        body = '<div class="notice info"><div class="sym">ℹ</div><div><p>사용자 가격표가 없습니다.</p></div></div>'
        return page("한국화학 — 제품 가격", body, depth=0, h1="💲 제품 가격", nav=NAV, crumbs=(("한국화학", "index.html"), ("가격", "")))
    st_ko = {"ok": ("원장 일치", "ok"), "mismatch": ("기준 다름", "bad"), "unmapped": ("원장에 없음", "est"), "no_ledger": ("원장에 없음", "est")}
    trs = []
    for x in series:
        obs = x["obs"]
        c1, c4, c52 = _chg(obs, 1), _chg(obs, 4), _chg(obs, 52)
        win = [v for _d, v in obs]
        pos5 = round(sum(1 for v in win if v <= x["last"]) / len(win) * 100, 1) if win else None
        ck = x["check"]
        lab, cls = st_ko.get(ck["status"], (ck["status"], ""))
        tip = ""
        if ck["status"] in ("ok", "mismatch"):
            tip = "겹침 %d주 · 정확 일치 %d · ±1%% 일치 %d · 원장 마지막 %s" % (ck["overlap"], ck.get("exact", 0), ck.get("near1pct", 0), ck.get("ledger_last") or "")
        ext = ""
        if ck["status"] == "ok" and ck.get("ledger_last") and x["last_date"] > ck["ledger_last"]:
            ext = sum(1 for d, _v in obs if d > ck["ledger_last"])
        trs.append('<tr><td class="l">%s</td><td class="l"><b>%s</b><div class="fm">%s · %s</div></td><td class="l">%s</td>'
                   '<td data-v="%s">%s</td><td class="l">%s</td><td data-v="%s">%s</td><td data-v="%s">%s</td><td data-v="%s">%s</td>'
                   '<td data-v="%s">%s</td><td data-v="%s">%s<small class="mut"> %s~</small></td><td class="spkc">%s</td>'
                   '<td class="l"><span class="flag %s" title="%s">%s</span>%s</td><td data-v="%s">%s</td></tr>'
                   % (E(x["cat"]), E(x["label"]), E(x["name"]), E(x["region"] or "—"), E(x["unit"]),
                      x["last"], fmt(x["last"], 1 if abs(x["last"]) < 100 else 0), E(x["last_date"]),
                      c1 if c1 is not None else "", _pct_html(c1), c4 if c4 is not None else "", _pct_html(c4),
                      c52 if c52 is not None else "", _pct_html(c52),
                      pos5 if pos5 is not None else "", pos_html(pos5),
                      x["long"]["rank"] if x["long"]["rank"] is not None else "", pos_html(x["long"]["rank"]), E(x["long"]["from"][:4]),
                      _spark(obs), cls, E(tip), E(lab),
                      ('<div class="fm">%s</div>' % E(x["sid"])) if x.get("sid") else "",
                      ext if ext != "" else "", ("%d주" % ext) if ext != "" else '<span class="mut">—</span>'))
    body = ('<div class="notice info"><div class="sym">💲</div><div><p>사용자 가격표 <code>%s</code> — 주간 제품 가격 %d종, %s 주까지. '
            '원장(유료 스팟 주간)이 %s 에 멈춘 뒤 <b>%d종을 원장 시리즈에 이어 붙였고</b>, 이 가격으로 산식이 재현된 스프레드 %d개를 다시 계산했습니다.</p>'
            '<p class="mut">원장 일치 = 겹치는 주의 값이 원장과 같다(±1%% 90%%·정확 50%% 이상, 그래야 잇는다). 기준 다름 = 단위·환산이 달라 잇지 않음. '
            '원장에 없음 = 가격표에만 있는 시리즈(이 표에서만). 5년 위치 = 최근 5년 관측 중 백분위, 장기 위치 = 가격표 첫 관측(2000년~) 이후 백분위. '
            '가격표 원본 값은 재배포하지 않는다 — 5년 창과 요약 통계만 레포에 둔다.</p></div></div>'
            % (E(sp["file"]), len(series), E(sp["through"]), E(sp.get("ledger_last") or "—"), sp["prices_extended"], sp["spreads_extended"]))
    body += ('<div class="wrap tall"><table data-sortable><thead><tr><th class="l">분류</th><th class="l">제품</th><th class="l">단위</th>'
             '<th>최신</th><th class="l">관측일</th><th>1W%%</th><th>4W%%</th><th>52W%%</th><th>5년 위치</th><th>장기 위치</th>'
             '<th class="l">5년 추이</th><th class="l">원장 대응</th><th>연장</th></tr></thead><tbody>%s</tbody></table></div>' % "".join(trs))
    body += '<style>.spkc{color:var(--a,#8ab4ff)}.spk{display:block}</style>'
    return page("한국화학 — 제품 가격", body, depth=0, h1="💲 제품 가격", nav=NAV, crumbs=(("한국화학", "index.html"), ("가격", "")),
                lead="사용자 가격표의 주간 제품 가격 %d종 — 최신값·변화·5년/장기 사이클 위치와 원장 대응. 원장이 멈춘 뒤 구간을 잇는 근거입니다." % len(series))


def supp_coverage(reg):
    sp = reg["summary"].get("supplement")
    if not sp:
        return ""
    trs = []
    for x in reg.get("supplement_series") or []:
        ck = x["check"]
        trs.append('<tr><td class="l">%s %s</td><td class="l">%s</td><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td class="l">%s</td></tr>'
                   % (E(x["name"]), E(x["region"]), E(x.get("sid") or "—"), E(ck["status"]), ck.get("overlap", 0), ck.get("exact", "—"),
                      ck.get("near1pct", "—"), E("; ".join("%s 가격표 %s / 원장 %s" % (d, a, b) for d, a, b in ck.get("diffs") or [])[:160])))
    return ('<h2 class="sec">사용자 가격표<span>%s · sha256 %s… · %s 주까지 · 매핑 assets/supplement_map.json</span></h2>'
            '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">가격표 열</th><th class="l">원장 시리즈</th><th class="l">판정</th>'
            '<th>겹침</th><th>정확</th><th>±1%%</th><th class="l">차이 예(최대 5)</th></tr></thead><tbody>%s</tbody></table></div>'
            % (E(sp["file"]), E(sp["sha256"][:12]), E(sp["through"]), "".join(trs)))


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

    body = notice_html(reg) + supp_coverage(reg)
    body += ('<div class="kpi"><div><b>%d</b><span>모집단 = 스프레드 패널의 화학 13 카테고리 전수</span></div><div><b>%d</b><span>스프레드(sp=true)</span></div>'
             '<div><b>%d</b><span>미재현(산식 역산 실패·겹침 부족·시리즈 없음)</span></div><div><b>%d</b><span>체인 미배정 → 추정 배정 %d</span></div>'
             '<div><b>%d</b><span>장기 미갱신(dead)</span></div></div>'
             % (s["rows"], s["spreads"], s["unreproduced"], s["chain_missing"], s["chain_est_assigned"], s["freshness"].get("dead", 0)))
    body += '<h2 class="sec">판정 규칙<span>registry.json rules</span></h2><dl class="kv">%s</dl>' % "".join(
        "<dt>%s</dt><dd>%s</dd>" % (E(k), E(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)) for k, v in reg["rules"].items())
    carry = [r for r in rows if r.get("carry_weeks")]
    ctr = "".join('<tr><td class="l">%s</td><td class="l">%s</td><td class="l">%s</td><td>%d</td><td class="l">%s</td></tr>'
                  % (E(r["name"]), E(r.get("last_date") or ""), E(r.get("effective_last") or ""), len(r["carry_weeks"]), E(", ".join(r["carry_weeks"][-6:])))
                  for r in carry)
    body += ('<h2 class="sec">원장 이월 주 %d행 · %d주<span>스프레드·제품이 전주와 같고 원료만 바뀐 주 = 갱신 없이 이어 쓴 값 → 산식 적합에서 제외, 실제 마지막 갱신 주를 따로 적는다</span></h2>'
             '<div class="wrap"><table data-sortable><thead><tr><th class="l">시리즈</th><th class="l">원장 last</th><th class="l">실제 마지막 갱신</th><th>이월 주</th><th class="l">최근 이월 주</th></tr></thead><tbody>%s</tbody></table></div>'
             % (len(carry), s.get("carry_weeks", 0), ctr))
    groups = {}
    for r in rows:
        if r.get("dup_group"):
            groups.setdefault(tuple(r["dup_group"]), []).append(r)
    gtr = "".join('<tr><td class="l">%s</td><td>%d</td></tr>' % (E(" = ".join(x["name"] for x in rs)), len(rs)) for _, rs in sorted(groups.items()))
    body += ('<h2 class="sec">지역 간 복제 %d그룹<span>관측 전부가 바이트 동일 — 고유 스프레드 %d/%d · 매트릭스는 =지역 으로 표시</span></h2>'
             '<div class="wrap"><table data-sortable><thead><tr><th class="l">같은 시리즈</th><th>행</th></tr></thead><tbody>%s</tbody></table></div>'
             % (len(groups), s.get("unique_spreads", 0), s["spreads"], gtr))
    eps = [r for r in rows if "formula_episode" in (r.get("flags") or [])]
    body += '<h2 class="sec">일시 이탈 후 복귀 %d<span>영구 산식 변경도, 상수 잔차도 아님 — 기준 k 가 한 구간 바뀌었다 돌아옴</span></h2>%s' % (len(eps), table(eps))
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


def stock_rows(reg, chains_of):
    return [r for r in reg["rows"] + [d for d in reg["derived"] if d["values"] is not None]
            if r.get("kind") in ("spread", "derived") and (r.get("chain") or r.get("chain_est")) in chains_of]


def stock_html(reg, t, name, chains_of):
    rows = stock_rows(reg, chains_of)
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
    supp = inputs.get("supplement")
    if supp:
        # 원장 정지 사실은 그대로 보인다 — 정지 주·편집 누락은 1차(원장만) 값, 이은 범위는 supplement 요약
        sm = supp["summary"]
        s_ = reg["summary"]
        s_["ledger_last"] = sm["ledger_last"]
        s_["ledger_stale_weeks"] = (datetime.date.fromisoformat(reg["argus_asof"]) - datetime.date.fromisoformat(sm["ledger_last"])).days // 7
        s_["editions"] = sm.get("editions")
        s_["supplement"] = sm
        reg["supplement_series"] = supp["series"]
    outputs = {
        os.path.join(DATA_DIR, "kchem_data.js"): build_data_js(reg, inputs),
        os.path.join(KCHEM, "index.html"): index_html(reg),
        os.path.join(KCHEM, "spreads.html"): spreads_html(reg),
        os.path.join(KCHEM, "prices.html"): prices_html(reg),
        os.path.join(KCHEM, "matrix.html"): matrix_html(reg),
        os.path.join(KCHEM, "chains.html"): chains_html(reg),
        os.path.join(KCHEM, "coverage.html"): coverage_html(reg),
    }
    # 종목 페이지는 화학 7체인 종목만, 화학 스프레드가 1행 이상일 때만(2026-10 리뷰 #3 — 반도체·철강·해운 등 0행 고아 10장 제거)
    stocks = {}
    for cid in load_asset("aliases.json")["chem_chains"]:
        for st in reg["chains"].get(cid, {}).get("stocks", []):
            stocks.setdefault(st["t"], {"name": st["n"], "chains": []})["chains"].append(cid)
    for t, info in sorted(stocks.items()):
        if stock_rows(reg, info["chains"]):
            outputs[os.path.join(KCHEM, t, "index.html")] = stock_html(reg, t, info["name"], info["chains"])
    for path, text in outputs.items():
        if len(text.encode("utf-8")) > 5 * 1024 * 1024:
            raise kchem_inputs.InputError("산출물 5MB 초과: %s" % path)
    assets = {"registry.json": dump_json(reg), "fingerprint.json": dump_json(fingerprint_doc(fp))}
    if write:
        # 쓰기 순서: 페이지 → registry → fingerprint(마지막). 중간에 죽으면 fingerprint 가 옛 값이라 다음 실행이 다시 빌드한다.
        for path, text in outputs.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, text)
        for t in stale_stock_dirs(outputs):
            os.remove(os.path.join(KCHEM, t, "index.html"))
            if not os.listdir(os.path.join(KCHEM, t)):
                os.rmdir(os.path.join(KCHEM, t))
        atomic_write(os.path.join(ASSETS, "registry.json"), assets["registry.json"])
        atomic_write(os.path.join(ASSETS, "fingerprint.json"), assets["fingerprint.json"])
    return reg, outputs, assets


STOCK_MARK = "— 화학 스프레드 역참조</title>"


def stale_stock_dirs(outputs):
    """이 생성기가 만든 종목 페이지(title 표식)인데 이번 빌드 목록에 없는 디렉터리 — 남의 파일은 건드리지 않는다."""
    out = []
    for t in sorted(os.listdir(KCHEM)):
        path = os.path.join(KCHEM, t, "index.html")
        if os.path.isfile(path) and path not in outputs and os.path.dirname(path) != KCHEM:
            with open(path, encoding="utf-8") as f:
                if STOCK_MARK in f.read(4096):
                    out.append(t)
    return out


def fingerprint_doc(fp):
    return {"fingerprint": fp["fingerprint"], "content": fp["content"], "inputs": fp["inputs"], "argus_asof": fp["argus_asof"]}


def check(outputs, assets):
    """멱등·결정성 검사 — 메모리에서 다시 만든 산출물이 디스크와 바이트 동일한가. 다르면 경로 목록."""
    bad = []
    files = dict(outputs)
    files.update({os.path.join(ASSETS, k): v for k, v in assets.items()})
    for path, text in sorted(files.items()):
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    bad.append(path)
        except OSError:
            bad.append(path)
    bad += [os.path.join(KCHEM, t) for t in stale_stock_dirs(outputs)]
    return bad


def commit_gate(new_fp, old_fp):
    """커밋 여부 — 화학 내용 지문이 바뀌었거나, 평가 주차(ISO 주)가 바뀌었을 때만.

    허브가 asof/built 만 다시 쓴 날은 커밋하지 않는다(2026-10 리뷰 #11). 주차가 바뀌면 '원장 정지 N주' 같은
    평가일 기반 문구를 갱신하려고 주 1회 커밋한다."""
    import datetime
    if not old_fp or "content" not in old_fp:
        return True, "이전 내용 지문 없음"
    if new_fp["content"] != old_fp["content"]:
        return True, "화학 내용 변경"
    wk = lambda d: datetime.date.fromisoformat(d).isocalendar()[:2]
    if wk(new_fp["argus_asof"]) != wk(old_fp["argus_asof"]):
        return True, "평가 주차 변경"
    return False, "화학 내용 동일·같은 주차(허브 asof/built 만 변경)"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--gate" in argv:
        # 사용: 빌드 후 `python3 kchem_page.py --gate <이전 fingerprint.json>` → 'commit …' 또는 'skip …'
        new = json.load(open(os.path.join(ASSETS, "fingerprint.json"), encoding="utf-8"))
        i = argv.index("--gate")
        old = None
        if i + 1 < len(argv) and os.path.isfile(argv[i + 1]) and os.path.getsize(argv[i + 1]):
            old = json.load(open(argv[i + 1], encoding="utf-8"))
        ok, why = commit_gate(new, old)
        print(("commit " if ok else "skip ") + why)
        return 0
    write = "--dry-run" not in argv and "--check" not in argv
    reg, outputs, assets = build(write=write)
    s = reg["summary"]
    print("kchem: rows %d · reproduced %d/%d (정확 %d) · unique %d · proxies %d(방향 %d) · pages %d · content %s%s"
          % (s["rows"], s["reproduced"], s["spreads"], (s.get("grades") or {}).get("exact", 0), s.get("unique_spreads", 0),
             s.get("proxies", 0), s.get("proxies_gated", 0), len(outputs), json.loads(assets["fingerprint.json"])["content"][:12],
             " (dry-run)" if not write else ""))
    if "--check" in argv:
        bad = check(outputs, assets)
        if bad:
            print("CHECK FAIL — 디스크와 다른 산출물 %d개: %s" % (len(bad), ", ".join(os.path.relpath(b, KCHEM) for b in bad[:8])))
            return 1
        print("CHECK OK — 다시 만든 산출물이 디스크와 바이트 동일(%d개)" % (len(outputs) + len(assets)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
