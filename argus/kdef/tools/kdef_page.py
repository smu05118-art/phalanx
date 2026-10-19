#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_page — 한국방산 탭의 페이지를 만든다.

  index.html            허브 — 체계업체 카드(잔고·커버리지·방산비중·수출비중) · 계통 구성 · 최근 대형 계약
  coverage.html         모집단 전수(네 겹)와 편입 근거 · ④ 본문 탐색 승격/제외
  <종목코드>/index.html  회사 — 잔고 추이/롤포워드 · 부문매출(방산·민수, 내수·수출) · 커버리지 ·
                        계약 목록(사업명·계통·유형·금액·기간·상대) · 계약유형 구성 ·
                        납품 관계(체계업체 ↔ 부품사, 근거 등급) · 원가·수익인식 각주

축이 조선과 다른 이유는 원문에 있다(FINDINGS):
  · 계약상대가 **공개**다 — 방위사업청·체계업체·해외 정부. 익명은 1건뿐이었다(조선은 81%).
  · 잔고표는 **보안 때문에 얇다** — 잔액 한 줄만 적는 회사가 있다. 그래서 1차 축은
    잔고 그 자체가 아니라 **커버리지(잔고 ÷ 연매출, 년)** 이고, 인도 스케줄은 계약 공시로 만든다.
  · 계약명에 **유형**(체계개발·최초양산·후속양산·성능개량·PBL)이 그대로 적힌다 — 이익 성격의 축.

    python3 kdef_page.py --all
"""
import argparse
import collections
import json
import os
import re
import sys

from kdef_lib import (ASSETS, E, KDEF, CHART_DEFAULTS_JS, PART_HEX, TABLE_JS, UNKNOWN_HEX,
                      atomic_write, fmt_eok, fmt_n, fmt_x, is_total, json_for_html, load_asset,
                      num_of, page, pct, slot_color)
from kdef_universe import load as load_universe
import kdef_contracts
import kdef_reports
import kdef_suppliers

DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=%s"
ROLE_KO = {"prime": "체계업체", "part": "부품", "material": "소재", "service": "용역", "holding": "지주"}
PARTY_KO = {"GOV": "방위사업청·정부기관", "PRIME": "체계업체", "G2G": "해외 정부(G2G·FMS)",
            "FOREIGN": "해외 기업", "DOMESTIC": "국내 기업", "ANON": "익명", "UNKNOWN": "미상"}
PARTY_ORDER = ["GOV", "PRIME", "G2G", "FOREIGN", "DOMESTIC", "ANON", "UNKNOWN"]
EXPORT_KO = {"direct": "수출", "indirect": "간접수출"}
EXPORT_BASIS_KO = {"party": "계약상대가 해외", "region": "공급지역이 해외", "name": "계약명에 '수출'(체계업체 경유)"}


# ── 계약 한 건의 판정 보조 ──────────────────────────────────
# 원장(contracts.json)의 필드만 읽는다 — 여기서 새로 추정하지 않는다. 사전·규칙은 kdef_contracts 에 있다.

def is_termination(c):
    """「단일판매ㆍ공급계약해지」 공시인가 — 계약이 아니라 계약의 소멸이므로 금액 집계에서 뺀다.

    kdef_orders_views 는 해지 공시로 원본 계약까지 집계에서 빼지만(status terminated), 여기 KPI·허브는
    원본은 그대로 두고 해지 공시 행만 뺀다 — 원본 매칭이 (계약명, 시작일) 휴리스틱이라 두 화면이
    다른 숫자를 보일 수 있고, 그 사실은 각주에 적는다."""
    return "해지" in (c.get("title") or "")


def dom_key(c):
    """계통 집계 키 — 계통 id, 없으면 'PART'(부품 이름만 적힌 계약) 또는 'UNKNOWN'.

    계통 미상 198건 중 부품명만 적힌 건(`관성측정장치(IMU) 공급`)은 무기체계를 지어내지 않는 편이
    맞다(HANDOFF ③). 다만 '미상'과 한 통에 넣으면 '왜 미상인지'가 사라져 따로 센다."""
    if c.get("domain"):
        return c["domain"]
    return "PART" if c.get("domain_hint") == "PART" else "UNKNOWN"


def export_split(rows):
    """방산 계약의 판로 — 수출(직·간접)과 내수를 건수·금액(백만원)으로 가른다. 근거별 건수도 함께.

    export 플래그는 kdef_contracts.export_of(상대 ∨ 공급지역 ∨ 체계업체 경유 간접수출)."""
    out = {"n": 0, "amt": 0.0, "direct": 0, "indirect": 0, "domestic_n": 0, "domestic_amt": 0.0,
           "basis": collections.Counter()}
    for c in rows:
        if c.get("export"):
            out["n"] += 1
            out["amt"] += (c["amt_krw_m"] or 0)
            out[c.get("export_kind") or "direct"] += 1
            out["basis"][c.get("export_basis") or "party"] += 1
        else:
            out["domestic_n"] += 1
            out["domestic_amt"] += (c["amt_krw_m"] or 0)
    return out


# ── 유형 × 상대 매트릭스 ────────────────────────────────────

def matrix(rows, data):
    """계약유형(행) × 계약상대(열) 매트릭스. rows = 방산 계약(해지 공시 제외).

    셀 = {n, amt(백만원), n_noamt}. 금액 미기재(공시유보) 건은 n 에만 들어가고 amt 는 0 — 합계가
    원장 금액 합과 정확히 같아야 한다(tests.test_matrix_sum). 유형·상대 축의 순서는 사전 순서."""
    cells = {}
    for c in rows:
        ct = c["ctype"] if c["ctype"] in data["ctypes"] else "UNKNOWN"
        pk = c["party_kind"] if c["party_kind"] in PARTY_KO else "UNKNOWN"
        cell = cells.setdefault((ct, pk), {"n": 0, "amt": 0.0, "n_noamt": 0})
        cell["n"] += 1
        if c["amt_krw_m"] is not None:
            cell["amt"] += c["amt_krw_m"]
        else:
            cell["n_noamt"] += 1
    ctypes = [t for t in data["ctype_order"] if any(k[0] == t for k in cells)]
    parties = [p for p in PARTY_ORDER if any(k[1] == p for k in cells)]

    def tot(keys):
        sel = [cells[k] for k in keys]
        return {"n": sum(x["n"] for x in sel), "amt": sum(x["amt"] for x in sel),
                "n_noamt": sum(x["n_noamt"] for x in sel)}
    row_tot = {t: tot([k for k in cells if k[0] == t]) for t in ctypes}
    col_tot = {p: tot([k for k in cells if k[1] == p]) for p in parties}
    return {"ctypes": ctypes, "parties": parties, "cells": cells, "row_tot": row_tot, "col_tot": col_tot,
            "total": tot(list(cells))}


def matrix_html(m, data, tid="mx"):
    """매트릭스 표 — 셀은 금액(억)과 건수, 농도는 전체 금액 대비 비중. 숫자를 색으로 대신하지 않는다."""
    if not m["cells"]:
        return '<p class="mut">집계할 방산 계약이 없습니다.</p>'
    peak = max((x["amt"] for x in m["cells"].values()), default=0) or 1
    head = ("<tr><th class=\"l\">유형 ＼ 상대</th>%s<th>합계</th></tr>"
            % "".join("<th>%s</th>" % E(PARTY_KO.get(p, p)) for p in m["parties"]))
    body = []
    for t in m["ctypes"]:
        cm = ctype_meta(data, t)
        tds = []
        for p in m["parties"]:
            x = m["cells"].get((t, p))
            if not x:
                tds.append('<td class="mut">—</td>')
                continue
            alpha = 0.06 + 0.5 * (x["amt"] / peak)
            tds.append('<td style="background:rgba(57,135,229,%.2f)" title="%s × %s · %s억 · %d건%s">%s'
                       '<span class="n">%d건%s</span></td>'
                       % (alpha, E(cm["ko"]), E(PARTY_KO.get(p, p)), fmt_eok(x["amt"]), x["n"],
                          (" · 금액 미기재 %d" % x["n_noamt"]) if x["n_noamt"] else "",
                          fmt_eok(x["amt"]), x["n"],
                          ("(유보 %d)" % x["n_noamt"]) if x["n_noamt"] else ""))
        rt = m["row_tot"][t]
        body.append('<tr><td class="l">%s%s</td>%s<td><b>%s</b><span class="n">%d건</span></td></tr>'
                    % (_sw(cm["color"]), E(cm["ko"]), "".join(tds), fmt_eok(rt["amt"]), rt["n"]))
    foot = ('<tr><th class="l">합계</th>%s<td><b>%s</b><span class="n">%d건</span></td></tr>'
            % ("".join('<td>%s<span class="n">%d건</span></td>'
                       % (fmt_eok(m["col_tot"][p]["amt"]), m["col_tot"][p]["n"]) for p in m["parties"]),
               fmt_eok(m["total"]["amt"]), m["total"]["n"]))
    return ('<div class="wrap"><table id="%s" class="mx"><thead>%s</thead><tbody>%s</tbody><tfoot>%s</tfoot></table></div>'
            % (tid, head, "".join(body), foot))


# ── II-4 납기 일정 ──────────────────────────────────────────
# 정기보고서 수주표의 품목 행(reports.json segments)에 `납기` 열이 있는 회사(실측 19사)만 만든다.
# 납기 표기는 회사마다 다르다 — `2027.12`·`2025-09-30`·`2023.01 ~ 2026.12`·`2025년~2027년`·`~2028년`·
# `'25.1~6월`·`~28년`·`26.01.01~26.12.31`·`25-12-31`(아이쓰리시스템 YY-MM-DD, 2024Q3~2025Q1 63행).
# 기간이면 **끝** 연도로 묶고, `400대`·`*`·`상세내역 참조`처럼 연도가 없으면 '미상'에 둔다(지어내지 않는다).
# 2자리 연도는 `.`·`년`·`-`·`/` 가 뒤따를 때만 — MM·DD 토큰은 2015~2060 창에서 걸러진다.

_YEAR4 = re.compile(r"(20\d{2})")
_YEAR2 = re.compile(r"(?<![\d.])'?(\d{2})(?=[.년\-/])")


def due_year(s):
    """납기 문자열 → 끝 연도(int) 또는 None."""
    t = (s or "").strip()
    if not t:
        return None
    ys = [int(y) for y in _YEAR4.findall(t)]
    if not ys:
        ys = [2000 + int(y) for y in _YEAR2.findall(t)]
    ys = [y for y in ys if 2015 <= y <= 2060]
    return max(ys) if ys else None


def due_schedule(comp, q):
    """회사 × 분기 → 납기 연도별 {n, closing(백만원), items}. 납기가 적힌 품목 행이 없으면 None.

    금액은 그 품목 행의 **수주잔고**(남은 일감)다 — 계약 공시 총액을 종료연도에 두는 orders_views 의
    인도 일정과 다르다(그쪽은 기인식분 차감 없음). 단위를 못 읽은 분기(unit_note)는 건수만."""
    v = (comp.get("quarters") or {}).get(q) or {}
    segs = [s for s in v.get("segments") or [] if (s.get("due") or "").strip() not in ("", "-")]
    if not segs:
        return None
    money = bool(v.get("unit_seen")) and not v.get("unit_note")
    buckets = {}
    for s in segs:
        y = due_year(s["due"])
        b = buckets.setdefault(y, {"n": 0, "closing": 0.0, "n_noamt": 0, "items": []})
        b["n"] += 1
        if money and s.get("closing") is not None:
            b["closing"] += s["closing"]
        else:
            b["n_noamt"] += 1
        b["items"].append(s)
    years = sorted(y for y in buckets if y is not None)
    return {"q": q, "n": len(segs), "money": money, "years": years, "buckets": buckets,
            "unknown": buckets.get(None), "rcp": v.get("rcp")}


def due_html(d):
    rows = []
    for y in d["years"] + ([None] if d["unknown"] else []):
        b = d["buckets"][y]
        names = [x["label"] for x in b["items"] if x.get("label")]
        rows.append('<tr><td class="l">%s</td><td>%d</td><td data-v="%.0f">%s</td><td class="l mut">%s</td>'
                    '<td class="l mut">%s</td></tr>'
                    % (E(str(y)) if y else '<span class="mut">연도 미상</span>', b["n"], b["closing"],
                       (fmt_eok(b["closing"]) if d["money"] and b["closing"] else "—")
                       + ((' <span class="mut">(미기재 %d)</span>' % b["n_noamt"]) if d["money"] and b["n_noamt"] else ""),
                       E(", ".join(dict.fromkeys(n[:28] for n in names))[:120]),
                       E(" · ".join(dict.fromkeys(x["due"] for x in b["items"]))[:80])))
    return ('<div class="wrap"><table data-sortable><thead><tr><th class="l">납기 연도</th><th>품목 행</th>'
            '<th>수주잔고(억)</th><th class="l">품목(원문)</th><th class="l">납기 표기(원문)</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % "".join(rows))


# ── 수량 축 ────────────────────────────────────────────────
# 표준양식 `품목|수주일자|납기|수주총액 수량·금액|기납품액 수량·금액|수주잔고 수량·금액`(실측 233파일)과
# 풍산 `중량|금액`(M/T) 표는 **수량 열**을 함께 공시한다. kdef_reports.parse_orders_table 은 금액 열을
# 우선해(`수주총액 수량|금액`) 수량을 버리므로, 여기서는 캐시(reports_cache)의 raw_tables 를 다시 읽어
# 수량 열만 뽑는다 — 추가 수집 없음. 수량 단위는 캡션 `(단위 : M/T, 백만원)`·`(단위 : 천개, 백만원)`
# 에서 금액 단위를 뺀 토큰이며, 없으면 '미표기'(지어내지 않는다). 금액과 섞어 더하지 않는다.
# 머리행이 병합돼 `수주잔고 수량금액` 한 열이 된 표(대양전기공업 108380 2025Q1 — 값은 금액 293,773백만원)는
# 수량 열이 아니다 — 열 이름에 `금액`이 함께 있으면 거른다(실측: 금액이 '미표기' 수량으로 실렸다).

_QTY_COL = re.compile(r"수량|중량|판매량")
_NUM_COL = re.compile(r"수량|중량|판매량|금액|진행률|계약자산|매출채권|계약부채|비율|비중")
_MONEY_TOK = re.compile(r"원|KRW|USD|EUR|JPY|CNY|\$|달러|유로|엔|위안", re.I)
_UNIT_CAP = re.compile(r"\(\s*단위\s*[:：]?\s*([^)]*)\)")
_UNIT_LABEL = re.compile(r"^(?:수량|중량|금액)\s*[-:：]\s*")


def _unit_tokens(cap):
    """캡션 토큰 — `,`·`·`로 나누고, `/`는 한쪽이 금액 단위일 때만 나눈다(포메탈 `EA / 백만원`·`EA/백만원`·
    `수량-EA/금액-백만원`은 가르고, 풍산 `M/T`는 한 단위로 둔다). `수량-`·`금액-` 꼬리표는 벗긴다."""
    out = []
    for x in re.split(r"[,·]", cap or ""):
        x = x.strip()
        if not x:
            continue
        parts = [p.strip() for p in x.split("/") if p.strip()]
        if len(parts) > 1 and any(_MONEY_TOK.search(_UNIT_LABEL.sub("", p)) for p in parts):
            out.extend(parts)
        else:
            out.append(x)
    return [_UNIT_LABEL.sub("", t).strip() for t in out if _UNIT_LABEL.sub("", t).strip()]


def qty_unit_of(lead, cols):
    """캡션에서 수량 단위 토큰만 — `M/T, 백만원`→`M/T`, `천개, 백만원`→`천개`, `EA / 백만원`→`EA`, `백만원`→''."""
    caps = _UNIT_CAP.findall((lead or "") + " " + " ".join(cols or []))
    for cap in reversed(caps):
        qty = [x for x in _unit_tokens(cap) if not _MONEY_TOK.search(x)]
        if qty:
            return qty[0]
    return ""


def parse_qty_table(t):
    """raw_tables 의 표 한 장 → {unit, rows:[{label, gross, delivered, closing, due, total}]} 또는 None.

    수량 열(수량·중량·판매량)이 수주총액/수주잔고 어느 쪽에도 없으면 None. 수량이 전부 `-`인 표
    (한화 `상세내역 참조`)도 None — 수량 축은 숫자가 있는 회사에만 생긴다.
    열 이름에 수량과 `금액`이 **함께** 있으면(병합 머리행 `수주잔고 수량금액`) 수량 열이 아니다."""
    cols = [re.sub(r"[\s　]+", "", c or "") for c in t.get("cols") or []]

    def col(key):
        for i, c in enumerate(cols):
            if key in c and _QTY_COL.search(c) and "금액" not in c:
                return i
        return None
    i_gross = col("수주총액")
    i_done = col("기납품")
    i_close = None
    for k in ("수주잔고", "수주잔량", "잔고", "잔액"):
        i_close = col(k)
        if i_close is not None:
            break
    if i_close is None and i_gross is None:
        return None
    i_due = next((i for i, c in enumerate(cols) if "납기" in c or "인도예정" in c), None)
    i_date = next((i for i, c in enumerate(cols) if re.search(r"수주일|계약일", c)), None)
    name_idx = [i for i, c in enumerate(cols) if not _NUM_COL.search(c) and i not in (i_due, i_date)
                and "비고" not in c]
    rows = []
    for r in t.get("rows") or []:
        labels = [r[i].strip() for i in name_idx if i < len(r) and r[i].strip()]
        label = " · ".join(dict.fromkeys(labels))

        def g(i):
            return num_of(r[i]) if (i is not None and i < len(r)) else None
        rec = {"label": label, "gross": g(i_gross), "delivered": g(i_done), "closing": g(i_close),
               "due": (r[i_due].strip() if i_due is not None and i_due < len(r) else ""),
               "total": is_total(label)}
        if rec["gross"] is None and rec["closing"] is None:
            continue
        rows.append(rec)
    if not rows:
        return None
    return {"unit": qty_unit_of(t.get("lead"), t.get("cols")), "rows": rows, "cols": t.get("cols") or [],
            "lead": (t.get("lead") or "")[-120:]}


def _qty_total(p, field):
    tot = [r for r in p["rows"] if r["total"] and r.get(field) is not None]
    if tot:
        return tot[0][field]
    vals = [r[field] for r in p["rows"] if not r["total"] and r.get(field) is not None]
    return sum(vals) if vals else None


def qty_series(stock, cache_dir=None):
    """회사의 reports_cache 분기 파일을 읽어 분기별 수량 표를 고른다 → [{q, unit, gross, delivered, closing, n, rcp, rows}].

    한 분기에 수량 표가 여럿이면(종속회사 표) 숫자 행이 가장 많은 표를 고른다. 캐시가 없으면 []."""
    d = os.path.join(cache_dir or kdef_reports.CACHE, stock)
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            rec = json.load(fh)
        cands = [p for p in (parse_qty_table(t) for t in rec.get("raw_tables") or []) if p]
        if not cands:
            continue
        best = max(cands, key=lambda p: sum(1 for r in p["rows"] if r.get("closing") is not None))
        out.append({"q": f[:-5], "unit": best["unit"], "gross": _qty_total(best, "gross"),
                    "delivered": _qty_total(best, "delivered"), "closing": _qty_total(best, "closing"),
                    "n": sum(1 for r in best["rows"] if not r["total"]), "rcp": rec.get("rcp"),
                    "rows": best["rows"]})
    return out


def qty_html(series):
    trend = "".join('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td class="l mut">%s</td>'
                    '<td>%d</td><td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                    % (E(s["q"]), fmt_n(s["gross"]), fmt_n(s["delivered"]), fmt_n(s["closing"]),
                       E(s["unit"] or "미표기"), s["n"], E(DART % (s["rcp"] or "")))
                    for s in series)
    last = series[-1]
    items = "".join('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td><b>%s</b></td><td class="l mut">%s</td></tr>'
                    % (E(r["label"][:60] or "(품목 미표기)"), fmt_n(r["gross"]), fmt_n(r["delivered"]),
                       fmt_n(r["closing"]), E(r["due"]))
                    for r in last["rows"] if not r["total"])
    return ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>수주총액</th><th>기납품</th>'
            '<th>수주잔고</th><th class="l">수량 단위(캡션)</th><th>품목 행</th><th class="l">출처</th></tr></thead>'
            '<tbody>%s</tbody></table></div>'
            '<details style="margin-top:10px"><summary style="cursor:pointer;font-size:12px">%s 품목별 수량 %d행</summary>'
            '<div class="wrap tall"><table data-sortable><thead><tr><th class="l">품목(원문)</th><th>수주총액</th>'
            '<th>기납품</th><th>수주잔고</th><th class="l">납기(원문)</th></tr></thead><tbody>%s</tbody></table></div></details>'
            % (trend, E(last["q"]), sum(1 for r in last["rows"] if not r["total"]), items))


def load_all():
    uni = load_universe()
    doms = load_asset("domains.json")["domains"]
    ctypes = load_asset("contract_types.json")["types"]
    reports = kdef_reports.load()
    return {
        "uni": uni,
        "by_stock": {r["stock"]: r for r in uni},
        "doms": {d["id"]: d for d in doms},
        "dom_order": [d["id"] for d in doms],
        "ctypes": {c["id"]: c for c in ctypes},
        "ctype_order": [c["id"] for c in ctypes] + ["UNKNOWN"],
        "contracts": kdef_contracts.load(),
        "reports": reports.get("companies", {}),
        "quarters": reports.get("quarters", []),
        "sup": {c["stock"]: c for c in kdef_suppliers.load().get("cos", [])},
        "tax": load_asset("parts_taxonomy.json"),
        "probe": load_asset("universe_probe.json") if os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets",
                         "universe_probe.json")) else {},
        # 계약 진행(XI-1) — 없으면 None(열·섹션 없음). 읽는 쪽은 늘 data.get("xi1").
        "xi1": load_xi1([r["stock"] for r in uni]),
    }


def dom_meta(data, did):
    """계통 id → 표시 메타. 'PART'·'UNKNOWN' 은 사전에 없는 집계용 가짜 id(dom_key 참조)."""
    d = data["doms"].get(did)
    if not d:
        if did == "PART":
            return {"id": "PART", "ko": "부품(계통 미상)", "color": PART_HEX}
        return {"id": "UNKNOWN", "ko": "미상", "color": UNKNOWN_HEX}
    return {"id": d["id"], "ko": d["ko"], "color": slot_color(d["slot"])}


def ctype_meta(data, cid):
    c = data["ctypes"].get(cid)
    if not c:
        return {"id": "UNKNOWN", "ko": "미상", "color": "#5d6675"}
    return {"id": c["id"], "ko": c["ko"], "color": slot_color(c["slot"])}


# ── 회사 집계 ───────────────────────────────────────────────

def summary(stock, data):
    rec = data["by_stock"][stock]
    comp = data["reports"].get(stock) or {}
    qs = [q for q in sorted((comp.get("quarters") or {})) if comp["quarters"][q].get("ok")]
    latest = comp["quarters"][qs[-1]] if qs else None
    cons = [c for c in data["contracts"] if c["stock"] == stock]
    # 해지 공시는 계약이 아니다 — 표에는 pill 로 보이되 건수·금액 집계에서 뺀다.
    terms = [c for c in cons if is_termination(c)]
    live = [c for c in cons if not is_termination(c)]
    defc = [c for c in live if not c["civil"]]
    backlog = latest.get("backlog") if latest else None
    fy = latest.get("revenue_fy") if latest else None
    cov = (backlog / fy) if (backlog and fy) else None
    dom_amt = collections.Counter()
    dom_n = collections.Counter()
    for c in live:
        did = dom_key(c)
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
    ct_amt = collections.Counter()
    ct_n = collections.Counter()
    for c in defc:
        ct_amt[c["ctype"]] += (c["amt_krw_m"] or 0)
        ct_n[c["ctype"]] += 1
    exp = latest.get("revenue_export") if latest else None
    dom_rev = latest.get("revenue_domestic") if latest else None
    # 연결 모회사의 수주표에는 자회사 체계업체가 **행으로** 들어 있다(한화에어로의 수주표에
    # 한화시스템·한화오션 행이 있다). 잔고를 그냥 더하면 33조가 두 번 세어진다.
    kids = set()
    for seg in (latest or {}).get("segments") or []:
        for ps, pat in kdef_contracts.PRIME_NAMES.items():
            if ps != stock and re.search(pat, seg.get("label") or ""):
                kids.add(ps)
    return {
        "stock": stock, "rec": rec, "comp": comp, "qs": qs, "latest_q": qs[-1] if qs else None,
        "latest": latest, "contracts": cons, "live": live, "def_contracts": defc,
        "civil_n": len(live) - len(defc), "terminations": terms,
        "export": export_split(defc),
        "backlog": backlog, "backlog_def": latest.get("backlog_def") if latest else None,
        "fy": fy, "coverage": cov,
        "def_share": pct(latest.get("sales_def"), latest.get("sales_all")) if latest else None,
        "exp_share": pct(exp, (exp or 0) + (dom_rev or 0)) if latest else None,
        "dom_amt": dom_amt, "dom_n": dom_n, "ct_amt": ct_amt, "ct_n": ct_n,
        "amt_total": sum(c["amt_krw_m"] or 0 for c in defc),
        "sup": data["sup"].get(stock) or {},
        "consolidates": sorted(kids),
        "security": bool(latest.get("security_note")) if latest else False,
    }


def has_page(s):
    """페이지를 만들 만한 회사인가 — 정기보고서 분기 기록이나 계약 공시가 있어야 한다."""
    return bool(s["qs"] or s["contracts"] or s["sup"].get("cats") or s["sup"].get("primes"))


# ── 조각 ───────────────────────────────────────────────────

def _chip(label, color=None, n=None, href=None, on=False, title=""):
    sw = '<i class="sw" style="background:%s"></i>' % E(color) if color else ""
    nn = ' <span class="n">%s</span>' % E(str(n)) if n is not None else ""
    inner = "%s%s%s" % (sw, E(label), nn)
    tt = ' title="%s"' % E(title) if title else ""
    if href:
        return '<a class="chip%s" href="%s"%s>%s</a>' % (" on" if on else "", E(href), tt, inner)
    return '<span class="chip%s"%s>%s</span>' % (" on" if on else "", tt, inner)


def _sw(color):
    return ('<i class="sw" style="display:inline-block;width:9px;height:9px;border-radius:3px;'
            'background:%s;margin-right:6px;vertical-align:-1px"></i>' % E(color))


def _grade_pill(p):
    cls = {1: "up", 2: "", 3: "mut", 4: "mut"}.get(p["grade"], "mut")
    return '<span class="pill %s" title="%s">%s</span>' % (cls, E(p.get("detail", "")), E(p["basis_ko"]))


# ── 계약 진행(XI-1) ─────────────────────────────────────────
# 반기·사업보고서 XI-1 「나. 단일판매ㆍ공급계약 진행 현황」 — 6개 수주 섹터 탭 공용 층(kce/tools):
#   xi1_sector(수집·해석·분기 잇기·원장 연결·지표 → assets/xi1/progress.json) · xi1_view(서버 렌더 조각, JS 없음).
# fail-soft: import·읽기 실패나 progress.json 없음 → data["xi1"] = None → 열·섹션을 만들지 않는다(지금 화면 그대로).
# 공용 정의(진행·수령 진척·매출채권/선수금·표준 곡선·연결 등급·외화)는 argus/kce/UPDATE.md §6-C.
XI1_FOOT = "·반기·사업보고서 「XI-1 공시내용 진행 및 변경사항」"
_XV = {"mod": None, "tried": False}


def _xi1_view():
    if not _XV["tried"]:
        _XV["tried"] = True
        try:
            import xi1_view
            _XV["mod"] = xi1_view
        except Exception as e:
            sys.stderr.write("[warn] 계약 진행(XI-1) 화면 비활성: %s\n" % e)
    return _XV["mod"]


def load_xi1(stocks=None):
    """progress.json → dict 또는 None. 화면 모집단(universe)에 없는 종목이 섞여 있으면 subset 으로 맞춘다
    (kdef 는 모집단 전부를 보이므로 평소엔 그대로 — 모집단이 바뀌고 XI-1 build 가 아직 안 돈 날의 방어)."""
    try:
        import xi1_sector
        prog = xi1_sector.load_progress("kdef")
        if prog and stocks is not None and set(prog.get("companies") or {}) - set(stocks):
            prog = xi1_sector.subset(prog, stocks)
    except Exception as e:
        sys.stderr.write("[warn] 계약 진행(XI-1) 비활성: %s\n" % e)
        return None
    if not prog or not _xi1_view():
        return None
    return prog


def _xi1(data):
    """(prog, xi1_view) — 하나라도 없으면 (None, None)."""
    prog = (data or {}).get("xi1")
    if not prog:
        return None, None
    v = _xi1_view()
    return (prog, v) if v else (None, None)


def _rcps(c):
    """원장 행의 접수번호 사슬 — [rcp] + supersedes(문자열이든 리스트든)."""
    out = [c.get("rcp")]
    sup = c.get("supersedes")
    out += [sup] if isinstance(sup, str) else list(sup or [])
    return [r for r in out if r]


def _xi1_head(data):
    """XI-1 조각을 쓰는 페이지의 <style> — 없으면 ''."""
    prog, v = _xi1(data)
    return "<style>%s</style>" % v.CSS if prog else ""


def _xi1_civil_note(data, items, scope):
    """XI-1 절은 회사의 XI-1 계약 전부다 — 방산 집계처럼 민수(CIVIL)를 빼지 않는다는 한 줄.
    민수 판정은 원장(계통 CIVIL)에만 있으므로 원장에 연결된 계약만 세고, XI 전용은 '미판정'으로 둔다."""
    civ = {r for c in data.get("contracts") or [] if c.get("civil") for r in _rcps(c)}
    n_civ = sum(1 for c in items if c.get("link") and set(c["link"].get("rcps") or [c["link"].get("rcp")]) & civ)
    n_xi = sum(1 for c in items if not c.get("link"))
    return ('<p class="note">%s XI-1 표의 계약 %d건 전부입니다(완료·이탈 포함) — 방산 집계(%s)와 달리 '
            '<b>민수(계통 CIVIL)를 빼지 않습니다</b>: 원장 연결로 민수 확인 %d건 · 원장 짝이 없는 XI 전용 %d건은 방산/민수 미판정.</p>'
            % (scope, len(items), "위 KPI·계약 공시 방산 건수" if scope == "이 회사" else "위 KPI·최근 대형 계약",
               n_civ, n_xi))


def _xi1_inject(sec, note):
    """조각의 첫 </h2> 뒤에 탭 각주를 넣는다(조각 자체는 공용 — 고치지 않는다)."""
    i = sec.find("</h2>")
    return sec if i < 0 else sec[:i + 5] + note + sec[i + 5:]


def xi1_company(data, stock):
    prog, v = _xi1(data)
    if not prog:
        return ""
    try:
        sec = v.company_section(prog, stock)
        if not sec:
            return ""
        items = [c for c in prog.get("contracts") or [] if c.get("stock") == stock]
        return _xi1_inject(sec, _xi1_civil_note(data, items, "이 회사"))
    except Exception as e:
        sys.stderr.write("[warn] %s 계약 진행(XI-1) 렌더 실패: %s\n" % (stock, e))
        return ""


def xi1_hub(data, paged):
    """허브 섹션 — 회사 페이지가 있는 종목만 링크."""
    prog, v = _xi1(data)
    if not prog:
        return ""
    try:
        sec = v.hub_section(prog, co_href=lambda st: ("%s/index.html" % st) if st in paged else None)
        if not sec:
            return ""
        return _xi1_inject(sec, _xi1_civil_note(data, prog.get("contracts") or [], "탭 전체"))
    except Exception as e:
        sys.stderr.write("[warn] 허브 계약 진행(XI-1) 렌더 실패: %s\n" % e)
        return ""


def xi1_coverage(data):
    prog, v = _xi1(data)
    if not prog:
        return ""
    try:
        return v.coverage_rows(prog) or ""
    except Exception as e:
        sys.stderr.write("[warn] 커버리지 계약 진행(XI-1) 렌더 실패: %s\n" % e)
        return ""


def _xi1_cells(rows, data):
    """원장 표의 진행(XI-1) 칸 — [td…] (rows 순서) 또는 None(열 없음). 한 칸이라도 실패하면 열 전체를 뺀다."""
    prog, v = _xi1(data)
    if not prog:
        return None
    try:
        return [v.progress_cell(prog, _rcps(c)) for c in rows]
    except Exception as e:
        sys.stderr.write("[warn] 진행(XI-1) 열 비활성: %s\n" % e)
        return None


def contracts_table(rows, data, tid="ct", show_company=False, by_stock=None, rel="../"):
    tr = []
    rows = sorted(rows, key=lambda c: (c["signed"] or c["start"] or ""), reverse=True)
    xi = _xi1_cells(rows, data)            # 진행(XI-1) 열 — 금액 바로 뒤. 없으면 열 자체가 없다(지금 표 그대로).
    for i, c in enumerate(rows):
        dm = dom_meta(data, dom_key(c))
        cm = ctype_meta(data, c["ctype"])
        amt = c["amt_krw_m"]
        who = ""
        # 해지 공시 — 계약이 아니라 소멸. 금액은 원문 주석에만 있어 집계에서 빠진다(summary 참조).
        term = ' <span class="pill term" title="단일판매ㆍ공급계약해지 공시 — 건수·금액 집계에서 뺌">해지 공시</span>' \
            if is_termination(c) else ""
        # 판로 — 상대·공급지역·계약명(체계업체 경유)의 세 근거 중 어느 것으로 수출이 됐는지 툴팁에 적는다.
        exp = ""
        if c.get("export"):
            exp = ' <span class="pill exp" title="%s">%s</span>' % (
                E(EXPORT_BASIS_KO.get(c.get("export_basis"), "")),
                E(EXPORT_KO.get(c.get("export_kind"), "수출")))
        if show_company:
            nm = (by_stock or {}).get(c["stock"], {}).get("name", c["stock"])
            who = '<td class="l"><a href="%s%s/index.html">%s</a></td>' % (rel, E(c["stock"]), E(nm))
        nm = (c["name"] or "").strip()
        if nm in ("", "-"):
            # 계약명이 비어 있는 건은 대개 **공시유보**다 — 빈칸이 아니라 유보라고 적는다.
            w = (c.get("withheld") or "").strip("- ")
            nm = ('<span class="pill">공시유보</span> %s%s'
                  % (E(w or "사유 미기재"),
                     (" · 기한 %s" % E(c["withheld_until"])) if (c.get("withheld_until") or "").strip("- ") else "")) \
                if (w or (c.get("withheld_until") or "").strip("- ")) else "—"
        else:
            nm = E(nm[:70])
        party = E(c["party"] or "—")
        if c["party_prime"]:
            party = '<a href="%s%s/index.html">%s</a>' % (rel, E(c["party_prime"]), party)
        tr.append(
            '<tr><td class="l">%s</td>%s<td class="l">%s%s</td><td class="l">%s</td>'
            '<td class="l">%s</td><td data-v="%.0f">%s</td>%s<td data-v="%s">%s</td>'
            '<td class="l">%s<br><span class="mut">%s</span></td><td class="l mut">%s</td>'
            '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a>%s</td></tr>'
            % (E(c["signed"] or c["start"] or "—"), who, _sw(dm["color"]), E(dm["ko"]),
               E(cm["ko"]), nm + term,
               (amt or 0), fmt_eok(amt), xi[i] if xi else "",
               (c["years"] if c["years"] is not None else -1),
               fmt_x(c["years"]) if c["years"] is not None else "—",
               party + exp, E(PARTY_KO.get(c["party_kind"], c["party_kind"]))
               + ((" · " + E(c["region"])) if (c.get("region") or "").strip("- ") else ""),
               E((c["start"] or "—") + " ~ " + (c["end"] or "—")),
               E(DART % c["rcp"]),
               ' <span class="pill">정정</span>' if c.get("corrected") else ""))
    head = ('<tr><th class="l">수주일</th>%s<th class="l">계통</th><th class="l">유형</th>'
            '<th class="l">사업명(체결계약명)</th><th>금액(억)</th>%s<th>기간(년)</th>'
            '<th class="l">계약상대 · 공급지역</th><th class="l">계약기간</th><th class="l">출처</th></tr>'
            % ('<th class="l">회사</th>' if show_company else "",
               _xi1(data)[1].progress_th() if xi is not None else ""))
    return ('<div class="ctl"><input data-filter="#%s" type="search" placeholder="사업명·계통·유형·상대 검색"></div>'
            '<div class="wrap tall"><table id="%s" data-sortable><thead>%s</thead><tbody>%s</tbody></table></div>'
            % (tid, tid, head, "".join(tr)))


# ── 회사 페이지 ─────────────────────────────────────────────


# Y+2 추정 섹션(스튜디오 Codex 산출 `kdef_forecast_section.py` + `assets/forecast_panel.json.gz`).
# 산출이 없거나 회사가 빠져 있으면 **섹션을 만들지 않는다** — 빈 칸으로 흉내 내면 화면이 거짓말을 한다.
_FC = {"panel": None, "src": None, "mod": None, "tried": False}



# 수주 상세(간트·분기 전환·발주처) — 스튜디오 Claude(fable/ultracode) 산출 `kdef_orders_views.py`.
# 렌더러가 던지면 섹션을 만들지 않는다. 계약 원장이 없으면 자기 사유를 스스로 적는다.
_OV = {"mod": None, "con": None, "tried": False}


def ledger_asof(rows):
    """'진행중'을 가르는 기준일 — 실행 날짜가 아니라 **원장의 최신 공시 접수일**(rcpNo 앞 8자리).
    date.today() 를 쓰면 데이터가 같아도 날마다 페이지가 바뀌어 봇 diff 가 커졌다(검토 R2-4). 원장이
    비면 None(렌더러 기본값=오늘)으로 둔다."""
    import datetime
    best = None
    for r in rows or []:
        rc = str(r.get("rcp") or "")
        if len(rc) >= 8 and rc[:8].isdigit():
            try:
                d = datetime.date(int(rc[:4]), int(rc[4:6]), int(rc[6:8]))
            except ValueError:
                continue
            if best is None or d > best:
                best = d
    return best


def _orders_section(stock):
    if not _OV["tried"]:
        _OV["tried"] = True
        try:
            import kdef_orders_views as _ov
            _OV["mod"] = _ov
            import json as _json
            with open(os.path.join(ASSETS, "contracts.json"), encoding="utf-8") as f:
                d = _json.load(f)
            rows = d.get("rows") if isinstance(d, dict) else d
            _OV["con"] = list(rows.values()) if isinstance(rows, dict) else (rows or [])
        except Exception as e:
            sys.stderr.write("[warn] 수주 상세 비활성: %s\n" % e)
    if not _OV["mod"] or _OV["con"] is None:
        return ""
    ent = (_FC.get("src") or {}).get(stock) if "_FC" in globals() else None
    if ent is None:
        ent = {"stock": stock, "co": None, "name": None}
    try:
        f = (_FC.get("panel") or {}).get(stock) if "_FC" in globals() else None
        # 렌더러에 따라 다른 종목 행이 섞이면 거부한다(knuke) — 항상 회사 행만 넘긴다.
        rows = [r for r in _OV["con"] if r.get("stock") in (None, stock)]
        return _OV["mod"].render_orders_section(ent, rows, f, today=ledger_asof(_OV["con"])) or ""
    except Exception as e:
        sys.stderr.write("[warn] %s 수주 상세 렌더 실패: %s\n" % (stock, e))
        return ""

def _forecast_section(stock):
    import gzip
    if not _FC["tried"]:
        _FC["tried"] = True
        try:
            import kdef_forecast_section as _fs
            _FC["mod"] = _fs
            with gzip.open(os.path.join(ASSETS, "forecast_panel.json.gz"), "rt", encoding="utf-8") as f:
                p = json.load(f)
            _FC["panel"] = {c.get("company_id") or c.get("stock"): c for c in p["companies"]}
            with open(os.path.join(ASSETS, "reports.json"), encoding="utf-8") as f:
                _FC["src"] = json.load(f).get("companies", {})
        except Exception as e:
            sys.stderr.write("[warn] 추정 섹션 비활성: %s\n" % e)
    if not _FC["panel"] or stock not in _FC["panel"]:
        return ""
    try:
        return _FC["mod"].render_forecast_section((_FC["src"] or {}).get(stock), _FC["panel"][stock]) or ""
    except Exception as e:
        sys.stderr.write("[warn] %s 추정 섹션 렌더 실패: %s\n" % (stock, e))
        return ""

def company_html(s, data):
    rec, latest = s["rec"], s["latest"]
    is_prime = rec["role"] == "prime"
    kpi = []
    if s["backlog"] is not None:
        kpi.append('<div class="hero"><b>%s<small>억</small></b><span>수주잔고 · 정기보고서 %s</span>%s</div>'
                   % (fmt_eok(s["backlog"]), E(s["latest_q"] or "—"),
                      '<i class="mut">방산분 %s억</i>' % fmt_eok(s["backlog_def"])
                      if s["backlog_def"] else ""))
    elif latest and latest.get("unit_note"):
        kpi.append('<div class="hero"><b class="mut">—</b><span>수주잔고</span><i class="dn">%s</i></div>'
                   % E(latest["unit_note"]))
    else:
        kpi.append('<div class="hero"><b class="mut">—</b><span>수주잔고</span>'
                   '<i class="mut">정기보고서 II-4 수주표를 찾지 못함</i></div>')
    if s["coverage"] is not None:
        kpi.append('<div><b>%s<small>년</small></b><span>잔고 커버리지 = 잔고 ÷ 연매출</span>'
                   '<i class="mut">분모 %s억(%s)</i></div>'
                   % (fmt_x(s["coverage"]), fmt_eok(s["fy"]),
                      E((latest or {}).get("revenue_fy_col") or "직전 사업연도")))
    else:
        kpi.append('<div><b class="mut">—</b><span>잔고 커버리지</span>'
                   '<i class="mut">잔고 또는 연매출 열을 못 읽음</i></div>')
    if s["def_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>방산 비중(부문매출)</span>'
                   '<i class="mut">%s 기준</i></div>'
                   % (s["def_share"], E({"revenue": "매출실적 부문×내수/수출",
                                         "segment_sales": "사업부문별 매출"}.get(
                       (latest or {}).get("sales_mix_src"), "부문표"))))
    if s["exp_share"] is not None:
        kpi.append('<div><b>%.0f<small>%%</small></b><span>수출 비중(내수/수출 표)</span></div>'
                   % s["exp_share"])
    kpi.append('<div><b>%d<small>건</small></b><span>방산 계약 공시 · %s억</span>'
               '<i class="mut">민수 %d건은 따로 셈%s</i></div>'
               % (len(s["def_contracts"]), fmt_eok(s["amt_total"]), s["civil_n"],
                  (" · 해지 공시 %d건 제외" % len(s["terminations"])) if s["terminations"] else ""))
    ex = s["export"]
    if ex["n"]:
        # 판로 재판정 — 상대(G2G·해외기업)만 보던 종전 기준에 공급지역·체계업체 경유(간접수출)를 더한 값.
        kpi.append('<div><b>%d<small>건</small></b><span>수출 계약(판로) · %s억</span>'
                   '<i class="mut">직수출 %d · 간접수출 %d(체계업체 경유)</i></div>'
                   % (ex["n"], fmt_eok(ex["amt"]), ex["direct"], ex["indirect"]))

    # 잔고 롤포워드 표
    roll = []
    for q in s["qs"]:
        v = s["comp"]["quarters"][q]
        note = v.get("unit_note") or ""
        shape_ko = {"roll": "기초+신규−기납품", "openclose": "기초·기말만(보안)",
                    "gross": "총액−기납품", "item": "품목별", "balance": "잔액 한 줄(보안)"}.get(
            v.get("shape"), v.get("shape") or "—")
        roll.append('<tr><td class="l">%s</td><td>%s</td><td>%s</td><td>%s</td><td><b>%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td>'
                    '<td class="l"><a href="%s" target="_blank" rel="noopener noreferrer">원문</a></td></tr>'
                    % (E(q), fmt_eok(v.get("opening")), fmt_eok(v.get("gross")),
                       fmt_eok(v.get("delivered")), fmt_eok(v.get("backlog")),
                       E(shape_ko), E(note), E(DART % (v.get("rcp") or ""))))
    roll_html = ('<div class="wrap"><table><thead><tr><th class="l">분기</th><th>기초</th>'
                 '<th>수주총액</th><th>기납품액</th><th>수주잔고</th><th class="l">표 모양</th>'
                 '<th class="l">비고</th><th class="l">출처</th></tr></thead><tbody>%s</tbody></table></div>'
                 % "".join(roll)) if roll else \
        '<p class="mut">이 회사의 정기보고서에서 수주표를 찾지 못했습니다.</p>'

    # 혼합 통화는 원문 단위별로만 표시한다. 환율 적용·서로 다른 통화 합계는 만들지 않는다.
    currency_rows = []
    for q in s["qs"]:
        v = s["comp"]["quarters"][q]
        for group in v.get("currency_breakdown") or []:
            values = ["—" if group.get(field) is None else format(group[field], ",.3f").rstrip("0").rstrip(".")
                      for field in ("gross", "delivered", "closing")]
            currency_rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                                 % (E(q), E(group["cur"]), E(group["unit"]), *values))
    if currency_rows:
        roll_html += ('<h3>통화별 수주 현황</h3><p class="mut">공시 원문 단위 그대로 · 통화 간 합계·환산 없음</p>'
                      '<div class="wrap"><table><thead><tr><th>분기</th><th>통화</th><th>단위</th>'
                      '<th>수주총액</th><th>기납품액</th><th>수주잔고</th></tr></thead><tbody>%s</tbody></table></div>'
                      % "".join(currency_rows))

    # 부문 매출
    seg_html = ""
    if latest and (latest.get("revenue_segments") or latest.get("sales_segments")):
        rows = []
        for r in latest.get("revenue_segments") or []:
            k = {"def": "방산", "civil": "민수", "mixed": "혼재"}.get(r["segkind"], "미판정")
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]), E(k), E(r["kind"]),
                           r["val"] or 0, fmt_eok(r["val"])))
        for r in latest.get("sales_segments") or []:
            k = {"def": "방산", "civil": "민수", "mixed": "혼재"}.get(r["segkind"], "미판정")
            rows.append('<tr><td class="l">%s</td><td class="l mut">%s</td><td class="l">%s</td>'
                        '<td class="l">%s</td><td data-v="%.0f">%s</td></tr>'
                        % (E(r["seg"] or "(부문 표기 없음)"), E((r["item"] or "")[:40]), E(k),
                           ("비중 %.1f%%" % r["pct"]) if r.get("pct") else "—",
                           r["val"] or 0, fmt_eok(r["val"])))
        seg_html = ('<section class="card"><h2>부문 매출 <em>%s · 억원 · 부문 이름은 원문 그대로, '
                    '방산/민수 판정은 이름에서 — 한쪽으로 못 가르면 <b>혼재</b></em></h2>'
                    '<div class="wrap"><table data-sortable><thead><tr><th class="l">부문(원문)</th>'
                    '<th class="l">품목</th><th class="l">판정</th><th class="l">구분</th>'
                    '<th>금액(억)</th></tr></thead><tbody>%s</tbody></table></div></section>'
                    % (E(s["latest_q"] or ""), "".join(rows)))

    # 계통·유형 구성 — 계통 미상은 '부품(계통 미상)'과 '미상'으로 갈라 보인다.
    dom_rows = [(d, s["dom_amt"][d], s["dom_n"][d]) for d in data["dom_order"] + ["PART", "UNKNOWN"]
                if s["dom_n"].get(d)]
    ct_rows = [(c, s["ct_amt"][c], s["ct_n"][c]) for c in data["ctype_order"] if s["ct_n"].get(c)]

    # II-4 납기 일정(정기보고서 품목 행의 납기 열) · 수량 축(raw_tables 의 수량·중량 열) — 있는 회사만.
    due = due_schedule(s["comp"], s["latest_q"]) if s["latest_q"] else None
    due_sec = ""
    # 연도를 하나도 못 읽는 회사(한화에어로 — 납기 열이 전부 `상세내역 참조`)는 섹션을 만들지 않는다 —
    # '연도 미상' 한 줄짜리 표는 정보가 아니다.
    if due and due["years"]:
        due_sec = ('<section class="card"><h2>II-4 납기 일정 <em>%s 수주표 품목 %d행의 납기 열 · 끝 연도로 묶음 · '
                   '금액은 그 행의 수주잔고(억)%s</em></h2>%s'
                   '<p class="mut" style="font-size:11.5px;margin-top:8px">납기 표기는 원문 그대로이며 기간(`2024.01 ~ 2027.12`)은 '
                   '끝 연도에 둡니다. 연도를 읽을 수 없는 행(`상세내역 참조`·`400대`)은 "연도 미상"입니다. '
                   '계약 공시 종료일로 만든 아래 「종료연도별 인도 일정」과는 원천이 다릅니다(이쪽은 잔고, 그쪽은 계약 총액).</p></section>'
                   % (E(due["q"]), due["n"],
                      "" if due["money"] else " — 단위를 못 읽어 건수만", due_html(due)))
    qty = qty_series(s["stock"])
    qty_sec = ""
    if qty:
        qty_sec = ('<section class="card"><h2>수량 축 <em>수주표의 수량·중량 열 · 금액과 섞지 않음 · 단위는 캡션 원문(%s)</em></h2>%s'
                   '<p class="mut" style="font-size:11.5px;margin-top:8px">표준양식 수주표는 `수주총액 수량|금액`처럼 수량을 함께 '
                   '공시합니다. 잔고 금액(위 KPI)은 금액 열에서, 이 표는 수량 열에서 읽었습니다. 단위가 캡션에 없으면 '
                   '"미표기"로 두고 환산하지 않습니다.</p></section>'
                   % (E(qty[-1]["unit"] or "미표기"), qty_html(qty)))

    # 납품 관계
    sup = s["sup"]
    rel_html = ""
    if is_prime:
        rows = []
        for st, co in sorted(data["sup"].items(), key=lambda kv: kv[1]["nm"]):
            hit = [p for p in co["primes"] if p["stock"] == s["stock"]]
            if not hit:
                continue
            p = hit[0]
            cats = [h for h in co["cats"]]
            rows.append('<tr><td class="l"><a href="../%s/index.html">%s</a></td>'
                        '<td class="l">%s</td><td class="l">%s</td><td class="l mut">%s</td>'
                        '<td class="l mut">%s</td></tr>'
                        % (E(st), E(co["nm"]),
                           " ".join(_chip(cat_ko(data, h["cat"]), None) for h in cats[:5]) or "—",
                           _grade_pill(p), E(p.get("detail", "")), E(co["prod_raw"][:60])))
        if rows:
            rel_html = ('<section class="card"><h2>이 체계업체에 납품하는 상장사 <em>근거 등급: '
                        '주요고객 주석 &gt; 계약공시 상대 &gt; 본문 언급</em></h2><div class="wrap">'
                        '<table data-sortable><thead><tr><th class="l">회사</th><th class="l">부품</th>'
                        '<th class="l">근거</th><th class="l">근거 내용</th><th class="l">주요제품(KIND)</th>'
                        '</tr></thead><tbody>%s</tbody></table></div></section>' % "".join(rows))
    elif sup.get("primes"):
        rows = "".join('<tr><td class="l"><a href="../%s/index.html">%s</a></td><td class="l">%s</td>'
                       '<td class="l mut">%s</td></tr>'
                       % (E(p["stock"]), E(p["nm"]), _grade_pill(p), E(p.get("detail", "")))
                       for p in sup["primes"])
        rel_html = ('<section class="card"><h2>납품처(체계업체) <em>근거 등급과 근거 문장을 함께 싣습니다</em></h2>'
                    '<div class="wrap"><table><thead><tr><th class="l">체계업체</th><th class="l">근거</th>'
                    '<th class="l">내용</th></tr></thead><tbody>%s</tbody></table></div></section>' % rows)

    parts_html = ""
    if sup.get("cats"):
        chips = " ".join(_chip(cat_ko(data, h["cat"]), None, href="../parts.html#" + h["cat"],
                               title="근거: %s 「%s」" % ({"contract": "계약명", "report": "정기보고서 제품 절",
                                                        "body": "II절 본문",
                                                        "kind": "KIND 주요제품"}.get(h["src"], h["src"]),
                                                       h["kw"]))
                         for h in sup["cats"])
        parts_html = ('<section class="card"><h2>부품 분류 <em>계약명·정기보고서 본문·KIND 주요제품 문구에서 '
                      '읽은 낱말 — 칩에 근거가 붙어 있습니다</em></h2><div class="chips">%s</div></section>'
                      % chips)

    # 각주
    notes = []
    if s["security"]:
        notes.append("이 회사는 정기보고서에 <b>보안 관계상 수주 상세를 생략한다</b>고 적었습니다 — "
                     "잔고는 요약치(잔액·기말)만 공시됩니다.")
    if any(c["def_payrule"] for c in s["def_contracts"]):
        notes.append("계약 공시의 대금지급 조건에 <b>방위사업청 원가·대가 규정</b>이 언급된 계약이 있습니다 — "
                     "내수 방산은 원가기반 계약이라 이익률이 규정으로 제한됩니다(수치는 공시되지 않습니다).")
    notes.append("방산 계약은 <b>진행기준</b> 수익인식이 많아 수주·인도·매출 시점이 다릅니다. "
                 "잔고 커버리지는 '몇 년치 일감'을 보는 값이지 연도별 매출 예측이 아닙니다.")
    if s["export"]["n"]:
        notes.append("수출 판정은 세 근거를 합친 것입니다 — 계약상대가 해외 정부·기업, 「판매ㆍ공급지역」이 해외, "
                     "국내 체계업체 상대인데 계약명에 '수출'이 적힌 <b>간접수출</b>. 지역 열은 납품처 이름으로 오염돼 있어 "
                     "국내 표기가 하나도 없을 때만 해외로 봅니다(모르면 내수).")
    if s["terminations"]:
        notes.append("「계약해지」 공시 %d건은 계약이 아니므로 위 건수·금액에서 뺐습니다(표에는 <b>해지 공시</b> 꼬리표). "
                     "아래 수주 상세는 해지된 원본 계약까지 (계약명, 시작일)로 찾아 함께 빼므로 합계가 다를 수 있습니다."
                     % len(s["terminations"]))

    # 계약 진행(XI-1) — 계약 공시 표 바로 아래. 진행 표가 없는 회사는 섹션을 만들지 않는다.
    xi_sec = xi1_company(data, s["stock"])

    chart = {
        "roll": [{"q": q, "backlog": s["comp"]["quarters"][q].get("backlog"),
                  "def": s["comp"]["quarters"][q].get("backlog_def")} for q in s["qs"]],
        "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                  "amt": a, "n": n} for d, a, n in dom_rows],
        "ctypes": [{"ko": ctype_meta(data, c)["ko"], "color": ctype_meta(data, c)["color"],
                    "amt": a, "n": n} for c, a, n in ct_rows],
    }
    body = """
<div class="kpi">%s</div>
<div class="grid2" style="margin-top:20px">
 <section class="card" style="margin-top:0"><h2>수주잔고 추이 <em>정기보고서 II-4 · 억원</em></h2>
  <div class="chart"><canvas id="cRoll"></canvas></div></section>
 <section class="card" style="margin-top:0"><h2>계통 구성 <em>계약 공시 금액 기준 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div></section>
</div>
<section class="card"><h2>수주 롤포워드 <em>회사마다 표 모양이 다릅니다 — 원문 모양을 같이 적습니다</em></h2>%s</section>
%s
<div class="grid2">
 <section class="card"><h2>계약 유형 구성 <em>계약명에서 읽은 유형 · 이익 성격이 다릅니다</em></h2>
  <div class="chart"><canvas id="cType"></canvas></div>
  <p class="mut" style="font-size:12px;margin-top:10px">탐색·체계개발은 원가보상 성격, 최초양산은 초기 원가,
   후속양산은 원가절감분이 이익, 성능개량·후속군수지원(PBL)은 장기 매출입니다. 계약명에서 못 읽으면 '미상'입니다.</p></section>
 <section class="card"><h2>계약 상대 <em>방산은 상대가 공개입니다</em></h2>%s</section>
</div>
<section class="card"><h2>계약 공시 <em>단일판매ㆍ공급계약체결 · 방산 %d건 · 민수 %d건(계통 CIVIL 로 갈라 집계에서 뺐습니다)</em></h2>%s</section>
%s
%s
%s
%s
%s
<div class="note info">%s</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
  if(DATA.roll.length){
    new Chart(document.getElementById('cRoll'),{type:'line',data:{labels:DATA.roll.map(function(r){return r.q}),
      datasets:[{label:'수주잔고(억)',data:DATA.roll.map(function(r){return r.backlog==null?null:Math.round(r.backlog/100)}),
        borderColor:'#3987e5',backgroundColor:'rgba(57,135,229,.18)',fill:true,tension:.25,spanGaps:true},
       {label:'방산분(억)',data:DATA.roll.map(function(r){return r.def==null?null:Math.round(r.def/100)}),
        borderColor:'#c98500',backgroundColor:'rgba(201,133,0,.14)',fill:true,tension:.25,spanGaps:true}]},
      options:{scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
  }
  if(DATA.doms.length){
    new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
      datasets:[{label:'계약금액(억)',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:DATA.doms.map(function(d){return d.color})}]},
      options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
        var d=DATA.doms[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+d.n+'건'}}}},
        scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
  }
  if(DATA.ctypes.length){
    new Chart(document.getElementById('cType'),{type:'doughnut',data:{labels:DATA.ctypes.map(function(d){return d.ko}),
      datasets:[{data:DATA.ctypes.map(function(d){return Math.round(d.amt/100)}),
        backgroundColor:DATA.ctypes.map(function(d){return d.color})}]},
      options:{plugins:{tooltip:{callbacks:{label:function(c){var d=DATA.ctypes[c.dataIndex];
        return d.ko+': '+(c.parsed||0).toLocaleString()+'억 · '+d.n+'건'}}}}}});
  }
})();
</script>
<script>%s</script>
""" % ("".join(kpi), roll_html, seg_html, party_html(s), len(s["def_contracts"]), s["civil_n"],
       contracts_table(s["contracts"], data, tid="ct%s" % s["stock"]),
       xi_sec, due_sec, qty_sec, parts_html, rel_html,
       " ".join("<p>%s</p>" % n for n in notes),
       json_for_html(chart), CHART_DEFAULTS_JS, TABLE_JS) + _forecast_section(s["stock"]) + _orders_section(s["stock"])
    tags = (rec["stock"], rec["market"], ROLE_KO.get(rec["role"], rec["role"]), rec["industry"])
    dart = DART % (latest.get("rcp") if latest and latest.get("rcp") else "")
    return page("%s — 방산 수주" % rec["name"], body, depth=1, h1=rec["name"], tags=tags,
                head_extra=_xi1_head(data), foot=XI1_FOOT if _xi1(data)[0] else "",
                nav=(("허브", "../index.html"),) + ((("계약 진행", "#xi1"),) if xi_sec else ()) +
                    (("인포그래픽", "../parts.html"), ("커버리지", "../coverage.html"),
                     ("DART 원문 ↗", dart if latest else "https://dart.fss.or.kr")),
                crumbs=(("ARGUS", "../../index.html"), ("한국방산", "../index.html"),
                        (rec["name"], None)),
                scripts=("../vendor/chart.umd.min.js",),
                lead="수주잔고·부문매출은 정기보고서 II-4에서, 사업 단위 계약(사업명·계통·유형·금액·기간·상대)은 "
                     "수시공시 「단일판매ㆍ공급계약체결」에서 읽었습니다. 방산 수주표는 보안 때문에 요약만 "
                     "공시하는 회사가 있어, 잔고가 없으면 그 사실을 그대로 적습니다.")


def party_html(s):
    """계약 상대 갈래 표 + 판로(수출/내수) 한 줄. 해지 공시는 뺀다(live)."""
    cnt = collections.Counter(c["party_kind"] for c in s["live"])
    amt = collections.Counter()
    for c in s["live"]:
        amt[c["party_kind"]] += (c["amt_krw_m"] or 0)
    if not cnt:
        return '<p class="mut">계약 공시가 없습니다.</p>'
    rows = "".join('<tr><td class="l">%s</td><td>%d</td><td data-v="%.0f">%s</td></tr>'
                   % (E(PARTY_KO.get(k, k)), n, amt[k], fmt_eok(amt[k]))
                   for k, n in cnt.most_common())
    ex = s["export"]
    basis = " · ".join("%s %d" % (EXPORT_BASIS_KO.get(k, k), n) for k, n in ex["basis"].most_common())
    route = ('<p style="font-size:12px;margin-top:10px"><b>판로(방산)</b> — 수출 %d건 %s억'
             '<span class="mut">(직수출 %d · 간접수출 %d%s)</span> · 내수 %d건 %s억</p>'
             % (ex["n"], fmt_eok(ex["amt"]), ex["direct"], ex["indirect"],
                (" · 근거: " + basis) if basis else "", ex["domestic_n"], fmt_eok(ex["domestic_amt"])))
    return ('<div class="wrap"><table data-sortable><thead><tr><th class="l">상대</th><th>건수</th>'
            '<th>금액(억)</th></tr></thead><tbody>%s</tbody></table></div>%s' % (rows, route))


def cat_ko(data, cid):
    for c in data["tax"]["cats"]:
        if c["id"] == cid:
            return c["ko"]
    return cid


# ── 허브 ───────────────────────────────────────────────────

def hub_html(data, sums):
    prime = [s for s in sums if s["rec"]["role"] == "prime"]
    # 연결로 다른 체계업체를 품은 회사(한화에어로 ⊃ 한화시스템·한화오션)의 자회사는 합계에서 뺀다.
    inside = {k for s in prime for k in s["consolidates"]}
    top_primes = [s for s in prime if s["stock"] not in inside]
    dupe_note = ("한화에어로스페이스의 수주표에 한화시스템·한화오션이 행으로 들어 있어 "
                 "합계에서는 자회사를 뺐습니다" if inside else "회사마다 공시 기준 분기가 다릅니다")
    cards = []
    for s in sorted(prime, key=lambda s: -(s["backlog"] or 0)):
        rec = s["rec"]
        top = sorted(s["dom_amt"].items(), key=lambda kv: -kv[1])[:3]
        chips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], s["dom_n"][d])
                        for d, a in top if s["dom_n"][d])
        cards.append('<a class="cardlink" href="%s/index.html"><div class="t"><b>%s</b>'
                     '<span class="code">%s</span></div><p>%s</p>'
                     '<div class="chips" style="margin-top:8px">%s</div>'
                     '<div class="stat"><div><b>%s</b><span>수주잔고(억, %s)</span></div>'
                     '<div><b>%s</b><span>커버리지(년)</span></div>'
                     '<div><b>%s</b><span>방산비중</span></div>'
                     '<div><b>%s</b><span>수출비중</span></div></div>'
                     '<div class="go">회사 데이터 →</div></a>'
                     % (E(rec["stock"]), E(rec["name"]), E(rec["stock"]),
                        E((rec["product"] or "")[:70]), chips,
                        fmt_eok(s["backlog"]), E(s["latest_q"] or "—"),
                        fmt_x(s["coverage"]) if s["coverage"] else "—",
                        ("%.0f%%" % s["def_share"]) if s["def_share"] is not None else "—",
                        ("%.0f%%" % s["exp_share"]) if s["exp_share"] is not None else "—"))
    cons = data["contracts"]
    live = [c for c in cons if not is_termination(c)]
    terms = len(cons) - len(live)
    defc = [c for c in live if not c["civil"]]
    dom_amt = collections.Counter()
    dom_n = collections.Counter()
    for c in defc:
        did = dom_key(c)
        dom_amt[did] += (c["amt_krw_m"] or 0)
        dom_n[did] += 1
    # 계통 칩 — 사전 계통은 건수 순, 그 뒤에 '부품(계통 미상)'·'미상'을 붙여 미상의 크기를 숨기지 않는다.
    dchips = "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], n)
                     for d, n in dom_n.most_common() if d not in ("UNKNOWN", "PART"))
    dchips += "".join(_chip(dom_meta(data, d)["ko"], dom_meta(data, d)["color"], dom_n[d],
                            title="%s억" % fmt_eok(dom_amt[d]))
                      for d in ("PART", "UNKNOWN") if dom_n.get(d))
    ex = export_split(defc)
    mx = matrix(defc, data)
    big = sorted([c for c in defc if c["amt_krw_m"]], key=lambda c: -c["amt_krw_m"])[:25]
    names = {r["stock"]: r for r in data["uni"]}
    ncat = sum(1 for c in data["sup"].values() if c["cats"])
    nlink = sum(1 for c in data["sup"].values() if c["primes"])
    # 계약 진행(XI-1) — 회사 페이지가 있는 종목만 링크(main 이 has_page 로 거른 것과 같은 기준).
    xi_sec = xi1_hub(data, {s["stock"] for s in sums if has_page(s)})
    body = """
<div class="kpi">
 <div class="hero"><b>%s<small>억</small></b><span>체계업체 %d사 수주잔고 합(최근 분기)</span>
  <i class="mut">%s</i></div>
 <div><b>%d</b><span>방산 계약 공시(2020~) · %s억</span><i class="mut">민수 %d건은 갈라 뒀습니다%s</i></div>
 <div><b>%d</b><span>수출 계약(판로 재판정) · %s억</span><i class="mut">직수출 %d · 간접수출 %d — 상대·공급지역·계약명 세 근거</i></div>
 <div><b>%d</b><span>모집단 종목(네 겹 전수)</span><i class="mut">부품 분류 %d · 체계업체 연결 %d</i></div>
 <div><b>%d</b><span>계통(무기체계 계열)</span><i class="mut">계약명에서 판정 · 미상 %d건(부품명만 %d)</i></div>
</div>
<h2 class="sec">체계업체<span>수주잔고 순 · 칩은 계약 공시 상위 계통(건수)</span></h2>
<div class="cards">%s</div>
<div class="grid2">
 <section class="card"><h2>계통별 계약 금액 <em>수주잔고는 계통별로 공시되지 않습니다 — 계통 구성은 계약 공시 금액으로 봅니다 · 억원</em></h2>
  <div class="chart"><canvas id="cDom"></canvas></div>
  <div class="chips" style="margin-top:10px">%s</div></section>
 <section class="card"><h2>계약 유형별 금액 <em>이익 성격이 유형마다 다릅니다</em></h2>
  <div class="chart"><canvas id="cType"></canvas></div></section>
</div>
<section class="card"><h2>계약유형 × 계약상대 <em>방산 계약 %d건 · 억원(건수) · 유형은 계약명에서, 상대는 공시 상대에서 · 농도는 금액 비중</em></h2>%s
 <p class="mut" style="font-size:11.5px;margin-top:8px">같은 유형이라도 상대가 방위사업청이면 원가기반(이익률 규정), 해외 정부(G2G)면
  수출사업 이행계약입니다. 유형 낱말이 없는 G2G 계약(`잠수함 3척`)은 상대로 되짚어 '수출사업 이행'에 둡니다.
  공시유보로 금액이 없는 건은 건수에만 들어갑니다. 해지 공시 %d건은 뺐습니다.</p></section>
<section class="card"><h2>최근 대형 계약 <em>금액 상위 25건 · 계약상대가 공개인 것이 방산의 특징입니다</em></h2>%s</section>
%s
<h2 class="sec">더 보기<span>부품 인포그래픽과 모집단 근거</span></h2>
<div class="cards">
 <a class="cardlink" href="parts.html"><div class="t"><b>🛠 무기체계 인포그래픽</b></div>
  <p>전차·전투기·함정·유도탄 실루엣에서 부품 영역을 누르면 그 부품을 만드는 상장사로 갑니다.</p>
  <div class="go">인포그래픽 →</div></a>
 <a class="cardlink" href="coverage.html"><div class="t"><b>커버리지</b></div>
  <p>모집단 %d종목이 어떤 근거로 들어왔는지, ④ 본문 탐색에서 무엇이 승격·제외됐는지.</p>
  <div class="go">커버리지 →</div></a>
</div>
<script>const DATA=%s;</script>
<script>%s</script>
<script>
(function(){
 new Chart(document.getElementById('cDom'),{type:'bar',data:{labels:DATA.doms.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.doms.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.doms.map(function(d){return d.color})}]},
  options:{indexAxis:'y',plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
   var d=DATA.doms[c.dataIndex];return (c.parsed.x||0).toLocaleString()+'억 · '+d.n+'건'}}}},
   scales:{x:{ticks:{callback:function(v){return v.toLocaleString()}}},y:{grid:{display:false}}}}});
 new Chart(document.getElementById('cType'),{type:'bar',data:{labels:DATA.ctypes.map(function(d){return d.ko}),
  datasets:[{label:'억원',data:DATA.ctypes.map(function(d){return Math.round(d.amt/100)}),
   backgroundColor:DATA.ctypes.map(function(d){return d.color})}]},
  options:{plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){
   var d=DATA.ctypes[c.dataIndex];return (c.parsed.y||0).toLocaleString()+'억 · '+d.n+'건'}}}},
   scales:{y:{ticks:{callback:function(v){return v.toLocaleString()}}},x:{grid:{display:false}}}}});
})();
</script>
<script>%s</script>
""" % (fmt_eok(sum(s["backlog"] or 0 for s in top_primes)), len(top_primes), dupe_note,
       len(defc), fmt_eok(sum(c["amt_krw_m"] or 0 for c in defc)), len(live) - len(defc),
       (" · 해지 공시 %d건 제외" % terms) if terms else "",
       ex["n"], fmt_eok(ex["amt"]), ex["direct"], ex["indirect"],
       len(data["uni"]), ncat, nlink, len([d for d in data["dom_order"] if d != "CIVIL"]),
       dom_n.get("UNKNOWN", 0) + dom_n.get("PART", 0), dom_n.get("PART", 0),
       "".join(cards), dchips,
       len(defc), matrix_html(mx, data), terms,
       contracts_table(big, data, tid="cbig", show_company=True, by_stock=names, rel=""),
       xi_sec, len(data["uni"]),
       json_for_html({
           "doms": [{"ko": dom_meta(data, d)["ko"], "color": dom_meta(data, d)["color"],
                     "amt": dom_amt[d], "n": dom_n[d]}
                    for d, _ in dom_amt.most_common() if d not in ("UNKNOWN", "PART")],
           "ctypes": [{"ko": ctype_meta(data, c)["ko"], "color": ctype_meta(data, c)["color"],
                       "amt": sum(x["amt_krw_m"] or 0 for x in defc if x["ctype"] == c),
                       "n": sum(1 for x in defc if x["ctype"] == c)}
                      for c in data["ctype_order"]]}),
       CHART_DEFAULTS_JS, TABLE_JS)
    return page("한국방산 — 수주·계약·부품", body, depth=0, h1="🛡 한국방산",
                scripts=("vendor/chart.umd.min.js",),
                head_extra=_xi1_head(data), foot=XI1_FOOT if _xi1(data)[0] else "",
                nav=(("← ARGUS", "../index.html"), ("🏗 한국건설", "../kce/index.html"),
                     ("⚓ 한국조선", "../kship/index.html")) + ((("계약 진행", "#xi1"),) if xi_sec else ()),
                lead="국내 상장 방산기업의 수주를 이 산업의 축으로 읽습니다 — 사업 단위 계약(계약상대가 공개입니다), "
                     "무기체계 계통, 계약 유형(체계개발·양산·성능개량·PBL), 방산/민수·내수/수출 부문 매출, "
                     "그리고 <b>잔고 커버리지(몇 년치 일감)</b>. 체계업체뿐 아니라 부품사까지 전수로 담습니다.")


# ── 커버리지 ───────────────────────────────────────────────

def coverage_html(data, sums):
    by = {s["stock"]: s for s in sums}
    rows = []
    for r in data["uni"]:
        s = by.get(r["stock"])
        st = r["stock"]
        bits = []
        if s and s["qs"]:
            bits.append("정기보고서 %d분기" % len(s["qs"]))
        if s and s["contracts"]:
            bits.append("계약 %d건" % len(s["contracts"]))
        if s and s["sup"].get("cats"):
            bits.append("부품 %d" % len(s["sup"]["cats"]))
        if s and s["sup"].get("primes"):
            bits.append("체계업체 연결 %d" % len(s["sup"]["primes"]))
        status = " · ".join(bits) or "원문에서 수치를 찾지 못함"
        cls = "up" if (s and (s["backlog"] is not None or s["contracts"])) else (
            "wn" if bits else "tx3")
        link = ('<a href="%s/index.html">%s</a>' % (E(st), E(r["name"]))
                if s and has_page(s) else E(r["name"]))
        rows.append('<tr><td class="l">%s</td><td class="mut">%s</td><td class="l">%s</td>'
                    '<td class="l mut">%s</td><td class="l"><b class="%s">%s</b></td>'
                    '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                    % (link, E(st), E(ROLE_KO.get(r["role"], r["role"])),
                       E((r["industry"] or "")[:22]), cls, E(status), E(r["source"]),
                       E((r.get("reason") or r.get("product") or "")[:70])))
    probe = data.get("probe") or {}
    xi_cov = xi1_coverage(data)            # 계약 진행(XI-1) 수집 상태 — 회사 × 반기 · 원장 연결 등급
    rej = probe.get("rejected") or []
    scan = ""
    if probe:
        rj = "".join('<tr><td class="l">%s</td><td>%s</td><td class="l">%s</td><td>%d</td>'
                     '<td class="l mut">%s</td><td class="l mut">%s</td></tr>'
                     % (E(x["name"]), E(x["stock"]), E((x.get("industry") or "")[:20]),
                        x.get("hits", 0),
                        E(", ".join("%s %d" % kv for kv in list((x.get("terms") or {}).items())[:4])),
                        E(json.dumps(x.get("mentions") or {}, ensure_ascii=False)
                          if x.get("mentions") else (x.get("product") or "")[:40]))
                     for x in sorted(rej, key=lambda x: -x.get("hits", 0))[:80])
        scan = ('<section class="card"><h2>④ 본문 탐색 <em>%s 정기보고서 · 후보 %d사 · 승격 %d · '
                '검토·제외 %d · 원문 못 읽음 %d</em></h2>'
                '<p style="font-size:12px;color:var(--tx2);line-height:1.8">기준: %s</p>'
                '<details><summary style="cursor:pointer;font-size:12px">검토·제외 상위 80사 '
                '(방산 낱말 많은 순)</summary><div class="wrap"><table data-sortable><thead><tr>'
                '<th class="l">회사</th><th>종목코드</th><th class="l">업종</th><th>방산 낱말</th>'
                '<th class="l">낱말</th><th class="l">체계업체 언급 · 제품</th></tr></thead>'
                '<tbody>%s</tbody></table></div></details>%s</section>'
                % (E(probe.get("quarter", "")), probe.get("n_cand", 0),
                   len(probe.get("promoted") or {}), len(rej), len(probe.get("failed") or []),
                   E(probe.get("rule", "")), rj,
                   ('<p class="mut" style="font-size:11.5px;margin-top:8px">원문을 못 읽어 판정하지 못한 회사'
                    '(승격하지 않는다): %s</p>'
                    % E(", ".join("%s(%s — %s)" % (x["name"], x["stock"], x.get("note", ""))
                                  for x in (probe.get("failed") or [])[:20])))
                   if probe.get("failed") else ""))
    body = """
<section class="card" style="margin-top:0"><h2>모집단 규칙 <em>재현 가능한 네 겹 · 이름으로 넣지 않습니다</em></h2>
<p style="font-size:12px;color:var(--tx2);line-height:1.8">
① KIND 업종 <b>항공기·우주선 및 부품 제조업</b>·<b>무기 및 총포탄 제조업</b> 전 종목 ·
② KIND 주요제품 문구에 방산 어휘(방산·군용·함정·유도·탄약·전차·자주포·레이더·야시·항전·군수…) ·
③ 사유를 적은 지정(체계업체와 널리 알려진 부품사 — <b>종목코드는 KIND에서 이름으로 조회해 확인</b>했습니다) ·
④ 그래도 빠지는 회사를 <b>정기보고서 II절 본문 탐색</b>으로 찾습니다. 고객이 정부·공공기관인 업종은 제외합니다.
편입 근거(업종·제품·지정·탐색)를 종목마다 남깁니다.</p></section>
<section class="card"><h2>종목별 상태 <em>%d종목</em></h2><div class="wrap"><table data-sortable>
<thead><tr><th class="l">회사</th><th>종목코드</th><th class="l">역할</th><th class="l">업종</th>
<th class="l">수록 상태</th><th class="l">편입 근거</th><th class="l">사유·주요제품</th></tr></thead>
<tbody>%s</tbody></table></div></section>
%s
%s
<div class="note info">방산은 <b>보안 관계상</b> 수주 상세를 생략하는 회사가 있습니다(잔액 한 줄·기초/기말만).
그런 회사는 잔고 추이 대신 공시된 값만 싣고, 못 읽은 것은 못 읽었다고 적습니다.
부품사→체계업체 연결은 근거 등급(주요고객 주석 &gt; 계약공시 상대 &gt; 본문 언급)을 화면에 함께 띄웁니다.</div>
<script>%s</script>
""" % (len(data["uni"]), "".join(rows), scan, xi_cov, TABLE_JS)
    return page("한국방산 커버리지", body, depth=0, h1="커버리지",
                head_extra=_xi1_head(data), foot=XI1_FOOT if _xi1(data)[0] else "",
                nav=(("허브", "index.html"),) + ((("계약 진행 수집", "#xi1cov"),) if xi_cov else ()) +
                    (("← ARGUS", "../index.html"),),
                crumbs=(("ARGUS", "../index.html"), ("한국방산", "index.html"), ("커버리지", None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    data = load_all()
    want = set(a.only.split(",")) if a.only else None
    sums, made = [], 0
    for r in data["uni"]:
        s = summary(r["stock"], data)
        sums.append(s)
        if want and r["stock"] not in want:
            continue
        if not has_page(s):
            continue
        d = os.path.join(KDEF, r["stock"])
        os.makedirs(d, exist_ok=True)
        atomic_write(os.path.join(d, "index.html"), company_html(s, data))
        made += 1
    print("회사 페이지 %d개" % made)
    if a.all:
        atomic_write(os.path.join(KDEF, "index.html"), hub_html(data, sums))
        atomic_write(os.path.join(KDEF, "coverage.html"), coverage_html(data, sums))
        print("index.html · coverage.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
