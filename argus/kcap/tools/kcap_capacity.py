#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kcap_capacity — 정기보고서 「II. 사업의 내용 — 원재료 및 생산설비」 절에서 생산능력·생산실적·가동률을 읽는다.

회사마다 표 모양이 다르다(실측 2026Q2):
  · 롯데케미칼  [사업구분|대상 회사|품목| 2026년 반기(당기) 생산능력/생산실적/가동률(%) | 2025년(전기) …]  머리 2줄, 톤
  · 대한유화    생산능력 표 [사업장|품 목|품 목|제58기 반기|제57기|제56기] (M/T) + 생산실적·가동율 표(행 라벨이 측정값)
  · 금호석유    [사업부문|품목|사업소|단위|제50기 반기|제49기|제48기] 단위 열(천톤) + 종속회사 표 여러 개
  · 휴켐스      [품 목|제25기 반기 생산능력|제25기 반기 생산실적|제25기 반기 가동률|제24기 …] 머리 1줄(기간+측정)
  · 롯데정밀    생산실적 [부문|품목|사업소|2026년 반기|2025년|2024년] + 가동률 [부 문|부 문| 2026년 반기 생산능력(계획)/생산실적/평균가동률 …]
  · S-Oil      [구분|구분|단위|제52기(2026년 상반기)|…] 단위 열(천배럴·천톤) + 산출근거(표준생산능력 톤/년)
  · LG화학      금액 기준(백만원) — 톤 아님 → 모델에 못 쓴다(표시만)
그래서 표 하나하나를 **열 머리의 기간·측정값**과 **본문 맥락(lead)의 측정값**으로 분류하고, 같은 (부문·품목·사업소) 키로 합친다.
못 읽는 표·행은 버리지 않고 `unparsed` 에 이유와 함께 남긴다(fail-closed, COMMON.md §0).

연환산: 반기·분기 보고서의 생산능력이 기간 비례(반기 = 연간의 1/2)로 적힌 회사(롯데·대한유화·휴켐스)와 연간 명판을 그대로
적는 회사(금호)가 섞여 있다. 같은 표의 직전 연간 열과 비교해 비율이 PRORATED_MAX 미만이면 기간 비례로 보고 12/개월 을 곱한다.
근거(`basis`)를 행마다 남긴다. 명판(톤/년)이 산출근거 표에 따로 있으면 `nameplate` 로 병기한다.
"""
import re
import sys

from kcap_lib import (fetch_section, load_asset, parse_tables, pick_report, quarter_months, read_cache, report_kind,
                      search_reports, search_window, to_float, toc, unit_of, write_asset, write_cache)

SECTION_PATTERNS = [("cap", ["원재료 및 생산설비", "생산설비", "생산능력", "생산 및 설비", "생산에 관한 사항"])]
MEASURE_RX = {                                      # 순서가 우선순위다 — '생산능력 대비 가동률' 은 가동률
    "util": re.compile(r"가동\s*[률율]"),
    "output": re.compile(r"생산\s*실적|실제\s*생산|생산량"),
    "capacity": re.compile(r"생산\s*능력|생산능력\(계획\)|CAPA|Capa|capa"),
}
LABEL_RX = re.compile(r"사업\s*부문|부\s*문|사업\s*구분|구\s*분|품\s*목|제\s*품|사업장|사업소|대상\s*회사|생산지|단\s*위|취급설비|회사명|공장")
PRODUCT_RX = re.compile(r"품\s*목|제\s*품|취급설비|공정명|공\s*정|주요제품|제품/서비스")
SITE_RX = re.compile(r"사업장|사업소|생산지|공장")
ENTITY_RX = re.compile(r"대상\s*회사|회사명")
UNIT_COL_RX = re.compile(r"^단\s*위$")
SKIP_COL_RX = re.compile(r"가동\s*가능\s*일수|가동\s*일수|가동\s*가능\s*시간|실제\s*가동\s*시간|산출근거|산출\s*기준|비\s*고|시설\s*현황|기\s*계\s*명"
                         r"|일일\s*생산\s*능력|1일\s*생산|일\s*생산\s*능력|시간당|증\s*감(?!\s*[률율])|증감\s*[률율]|전년\s*대비")   # 일일 생산능력(산출근거 표)·증감 열은 기간 생산능력이 아니다
PERIOD_RX = re.compile(r"제\s*\d+\s*기|\d{4}\s*년|당\s*기|전\s*기|전전기|당반기|전반기|당분기|반기|분기|상반기|누적")
TOTAL_RX = re.compile(r"^\s*(합\s*계|소\s*계|총\s*계|계)\s*$")
PRORATED_MAX = 0.8     # 기간값/직전연간 < 0.8 이면 기간 비례로 본다
NONTON_UNITS = re.compile(r"배럴|bbl|백만원|천원|억원|시간|대|개|시트|회선|MW|㎡|m2|㎥|매|장|병|vial|Vial", re.I)


# ── 머리행·기간 ───────────────────────────────────────────────

CELL_UNIT_RX = re.compile(r"^\s*([-−(]?\s*\d[\d,]*(?:\.\d+)?\s*\)?)\s*(천톤|천 톤|만톤|톤|천T|천t|TON|Ton|ton|MT|M/T|T|t|천배럴|배럴|천개|개|시간|일|%)?\s*$")
PROD_UNIT_RX = re.compile(r"\((\s*(?:TON|Ton|ton|MT|M/T|톤|천톤|천T|KYD|천개|개|㎡|㎥|MW|시간)\s*)\)\s*$")


def _num_unit(c):
    """'281 천톤' → (281.0, '천톤') · '1,022,000 TON' → (1022000.0, 'TON') · '70.6%' → (70.6, '%') · '-' → (None, None)."""
    m = CELL_UNIT_RX.match(c or "")
    if not m:
        return to_float(c), None
    return to_float(m.group(1)), (m.group(2) or None)


def _is_num_cell(c):
    v, u = _num_unit(c)
    return v is not None and (u is not None or not re.search(r"[가-힣A-Za-z]", c.replace("%", "")))


def _header_rows(mat):
    """앞에서부터 숫자가 없는 줄(최대 3)을 머리로. 데이터 첫 줄은 숫자 셀을 하나는 가진다."""
    n = 0
    while n < min(3, len(mat) - 1):
        r = mat[n]
        if any(_is_num_cell(c) for c in r[1:]) and not all(len(c) <= 2 for c in r[1:]):
            break
        n += 1
    return max(n, 0)


def _combine_headers(mat, nh):
    ncol = max(len(r) for r in mat) if mat else 0
    out = []
    for j in range(ncol):
        parts = []
        for i in range(nh):
            c = mat[i][j] if j < len(mat[i]) else ""
            c = re.sub(r"\s+", " ", c).strip()
            if c and c not in parts:
                parts.append(c)
        out.append(" ".join(parts))
    return out


def _period_of(h):
    """머리 셀 → (기간 라벨, 기수|None, 연도|None, 당기 여부, 반기/분기 힌트)."""
    t = re.sub(r"\s+", "", h)
    m_gi = re.search(r"제(\d+)기", t)
    m_y = re.search(r"(20\d{2})년", t)
    cur = bool(re.search(r"당기|당반기|당분기|당해", t))
    partial = bool(re.search(r"반기|분기|상반기|누적|개월", t))
    lab = re.search(r"(제\d+기(?:반기|\d?분기|상반기)?|20\d{2}년(?:반기|\d?분기|상반기)?(?:\([^)]*\))?|당반기|전반기|당기|전기|전전기|당분기)", t)
    return (lab.group(1) if lab else None, int(m_gi.group(1)) if m_gi else None, int(m_y.group(1)) if m_y else None, cur, partial)


def _measure_of(h, ctx):
    for k, rx in MEASURE_RX.items():
        if rx.search(h):
            return k
    if re.search(r"수량|금액", h):
        return ctx      # '제58기 반기 수량' — 측정값은 본문 맥락(생산능력/생산실적)에서
    return ctx if PERIOD_RX.search(h) else None


HEADING_RX = re.compile(r"(?:^|[\s.)\]】])(?:[가-힣]\s*[.．]|\(\d+\)|\d+\)|[①②③④⑤⑥]|\d+\s*[.．])\s*((?:생산\s*능력|생산\s*실적|가동\s*[률율])[^가-힣]{0,3}(?:및|,|·)?[^.()\n]{0,24})")


def _ctx_measure(lead):
    """본문 맥락 — 표 앞 글의 **마지막 소제목**('가. 생산능력', '(2) 가동률')의 첫 측정 낱말. 소제목이 없으면 표 바로 앞 60자 안의 낱말만
    (서술문 속 '가동률 하락' 같은 언급은 쓰지 않는다)."""
    lead = lead or ""
    heads = list(HEADING_RX.finditer(lead))
    if heads:
        txt = heads[-1].group(1)
        first = None
        for k, rx in MEASURE_RX.items():           # '생산실적 및 가동률' → 앞에 나온 낱말(생산실적)
            m = rx.search(txt)
            if m and (first is None or m.start() < first[0]):
                first = (m.start(), k)
        if first:
            return first[1]
    tail = lead[-60:]
    best, pos = None, -1
    for k, rx in MEASURE_RX.items():
        for m in rx.finditer(tail):
            if m.start() > pos:
                best, pos = k, m.start()
    return best


# ── 표 하나 ───────────────────────────────────────────────────

def parse_table(t, quarter):
    """parse_tables 의 표 하나 → {'kind','unit','ton_mul','periods','rows'[{keys, values{period:{measure: v}}}]} 또는 None."""
    lead = re.sub(r"\s+", " ", t.get("lead") or "")
    mat = ([list(t["cols"])] if t.get("cols") else []) + [list(r) for r in t["rows"]]
    mat = [r for r in mat if any(c.strip() for c in r)]
    if len(mat) < 2:
        return None
    nh = _header_rows(mat)
    if nh == 0:
        return None
    heads = _combine_headers(mat, nh)
    ctx = _ctx_measure(lead)
    unit_raw, mul = unit_of(lead)
    if not unit_raw:
        # 캡션이 첫 셀에 있는 표('(단위 : 천톤)' 한 줄짜리 표가 앞에 따로 오는 경우는 lead 로 들어온다)
        unit_raw, mul = unit_of(" ".join(mat[0]))
    cols = []
    for j, h in enumerate(heads):
        if j == 0 or (LABEL_RX.search(h) and not PERIOD_RX.search(h) and not any(rx.search(h) for rx in MEASURE_RX.values())):
            role = "unit" if UNIT_COL_RX.search(h.strip()) else ("product" if PRODUCT_RX.search(h) else "site" if SITE_RX.search(h) else "entity" if ENTITY_RX.search(h) else "label")
            cols.append({"j": j, "role": role, "h": h})
            continue
        if SKIP_COL_RX.search(h) and not MEASURE_RX["util"].search(h):
            cols.append({"j": j, "role": "skip", "h": h})       # 가동가능일수·실제가동시간·산출근거 — 측정값이 아니다
            continue
        meas = _measure_of(h, ctx)
        per = _period_of(h)
        if meas is None and per[0] is None:
            cols.append({"j": j, "role": "label", "h": h})
            continue
        if re.search(r"금액", h) and not re.search(r"수량", h):
            cols.append({"j": j, "role": "skip", "h": h})       # 금액 열은 톤이 아니다
            continue
        cols.append({"j": j, "role": "value", "h": h, "measure": meas, "period": per})
    vals = [c for c in cols if c["role"] == "value"]
    if not vals:
        return None
    if not any(c["measure"] for c in vals):
        return None
    if re.search(r"백만원|천원|억원|천달러|USD|\$", unit_raw or "") and not re.search(r"톤|ton|M/T|MT", unit_raw or "", re.I):
        return None      # 금액 표(유형자산 변동·투자) — 생산능력이 아니다
    # 가동률 표 중 '가동가능시간·실제가동시간·평균가동률' 꼴 — 기간 없이 측정만 있다
    periods = []
    for c in vals:
        key = c["period"][0] or ("당기" if c["period"][3] else "미상")
        c["pkey"] = key
        if key not in periods:
            periods.append(key)
    # 당기 결정: 당기 표기 > 반기/분기 힌트 > 가장 큰 기수 > 가장 큰 연도 > 첫 기간
    def rank(c):
        p = c["period"]
        return (p[3], p[4], p[1] or 0, p[2] or 0)
    cur_key = max(vals, key=rank)["pkey"]
    rows, unparsed = [], []
    for r in mat[nh:]:
        if not any(c.strip() for c in r):
            continue
        labels = {c["role"]: (r[c["j"]].strip() if c["j"] < len(r) else "") for c in cols if c["role"] in ("product", "site", "entity", "unit")}
        lab_cells = [r[c["j"]].strip() for c in cols if c["role"] in ("label", "product", "site", "entity") and c["j"] < len(r)]
        lab_cells = [x for x in lab_cells if x and not re.match(r"^[\d,.\-−()%\s]+(시간|일|개|톤|기|식)?$", x)]
        plain_cells = [r[c["j"]].strip() for c in cols if c["role"] == "label" and c["j"] < len(r)]
        plain_cells = [x for x in plain_cells if x and not re.match(r"^[\d,.\-−()%\s]+(시간|일|개|톤|기|식)?$", x)]
        product = labels.get("product") or (plain_cells[-1] if plain_cells else (lab_cells[-1] if lab_cells else ""))
        # 제품 열이 둘이면(대한유화 '품 목','품 목') 마지막이 품목, 앞은 분류
        prod_cols = [c for c in cols if c["role"] == "product"]
        family = ""
        if len(prod_cols) >= 2:
            fam_cells = [r[c["j"]].strip() for c in prod_cols[:-1] if c["j"] < len(r)]
            family = " / ".join(x for x in fam_cells if x and x != product)
            product = r[prod_cols[-1]["j"]].strip() if prod_cols[-1]["j"] < len(r) else product
        segment = ""
        seg_cols = [c for c in cols if c["role"] == "label"]
        if seg_cols:
            segment = " / ".join(dict.fromkeys(r[c["j"]].strip() for c in seg_cols if c["j"] < len(r) and r[c["j"]].strip()))
        row_unit = labels.get("unit", "")
        pm = PROD_UNIT_RX.search(product or "")
        if pm and not row_unit:
            row_unit = pm.group(1).strip()          # '석유화학제품(TON)' — 품목 괄호에 단위
            product = PROD_UNIT_RX.sub("", product).strip()
        row_mul = unit_of("(단위 : %s)" % row_unit)[1] if row_unit else None
        is_total = bool(TOTAL_RX.match(product or "")) or bool(TOTAL_RX.match(segment or "")) or product in ("합 계(금액 기준)",)
        # 측정값이 행 라벨에 있는 전치 표(대한유화 생산실적/가동율)
        row_measure = None
        if not any(c["measure"] and any(rx.search(c["h"]) for rx in MEASURE_RX.values()) for c in vals):
            # 열 머리에 측정값이 하나도 없을 때만 — 짧은 라벨 셀('생산실적'·'가동율(%)')이 측정값을 말한다(대한유화 전치 표)
            for cell in lab_cells:
                if len(cell) > 12:
                    continue
                cell_n = re.sub(r"\s+", "", cell)             # '가 동 율'(후성) — 글자 사이 공백을 지우고 본다
                for k, rx in MEASURE_RX.items():
                    if rx.search(cell) or rx.search(cell_n):
                        row_measure = k
        values = {}
        cell_unit = None
        for c in vals:
            if c["j"] >= len(r):
                continue
            v, cu = _num_unit(r[c["j"]])
            if v is None:
                continue
            if cu and cu != "%" and unit_of("(단위 : %s)" % cu)[1] is not None:
                cell_unit = cu                     # 셀에 단위가 붙은 표(SK케미칼 '281 천톤', 태광 '1,022,000 TON')
            meas = row_measure or c["measure"]
            if meas is None:
                continue
            values.setdefault(c["pkey"], {})[meas] = v
        if not values:
            unparsed.append({"row": r[:8], "why": "숫자 없음"})
            continue
        aggregate = False
        if row_measure:
            # 전치 표: 품목은 라벨 중 측정 낱말이 아닌 마지막 셀 — 보통 부문·사업장 단위 집계다
            prods = [x for x in lab_cells if not any(rx.search(x) or rx.search(re.sub(r"\s+", "", x)) for rx in MEASURE_RX.values())]
            product = prods[-1] if prods else product
            family = prods[-2] if len(prods) >= 2 else family
            aggregate = True
        if cell_unit and not row_unit:
            row_unit, row_mul = cell_unit, unit_of("(단위 : %s)" % cell_unit)[1]
        rows.append({"product_raw": product, "family": family, "segment": segment, "site": labels.get("site", ""),
                     "entity": labels.get("entity", ""), "unit_raw": row_unit or unit_raw, "ton_mul": row_mul if row_unit else mul,
                     "total": is_total, "aggregate": aggregate, "values": values})
    return {"lead": lead[-120:], "heads": heads, "unit": unit_raw, "ton_mul": mul, "periods": periods, "cur": cur_key,
            "ctx": ctx, "rows": rows, "unparsed": unparsed}


# ── 절 하나 → 회사 분기 레코드 ───────────────────────────────

def _key(r, with_segment=False):
    k = (re.sub(r"\s+", "", r["product_raw"]), re.sub(r"\s+", "", r["site"]), re.sub(r"\s+", "", r["entity"]))
    return k + (re.sub(r"\s+", "", r["segment"]),) if with_segment else k


def _conflicts(m, r):
    for pk, mv in r["values"].items():
        s = m["periods"].get(pk)
        if s and "capacity" in mv and s.get("capacity") is not None and abs(s["capacity"] - mv["capacity"]) > 1e-6:
            return True
    return False


def parse_section(html, quarter):
    """절 HTML → {'tables': n, 'products': [...], 'unparsed': [...], 'nameplates': [...]}"""
    tables = [x for x in (parse_table(t, quarter) for t in parse_tables(html)) if x]
    months = quarter_months(quarter)
    merged = {}
    nameplates = []
    for t in tables:
        # 산출근거 표(표준생산능력 톤/년 — S-Oil) 는 명판으로 따로
        # 산출근거 표(표준생산능력 톤/년·배럴/일 — S-Oil): 머리 또는 단위 열에 명판 단위가 있고 기간 열이 없다
        unit_vals = " ".join(r["unit_raw"] or "" for r in t["rows"])
        if re.search(r"표준생산능력|톤/년|톤/일|배럴/일|연간\s*생산능력", " ".join(t["heads"]) + " " + unit_vals) and not any(
                PERIOD_RX.search(h) and not SKIP_COL_RX.search(h) for h in t["heads"]):
            for r in t["rows"]:
                v = None
                for pk, mv in r["values"].items():
                    v = mv.get("capacity", v)
                if v is not None:
                    nameplates.append({"product_raw": r["product_raw"], "segment": r["segment"], "unit_raw": r["unit_raw"], "value": v})
            continue
        for r in t["rows"]:
            if r["total"]:
                continue
            k = _key(r)
            if k not in merged:
                # 사업소가 한쪽에만 적힌 같은 품목·회사 행은 하나로(롯데정밀: 생산실적 표에는 '본사', 가동률 표에는 없음)
                for kk, mm in merged.items():
                    if kk[0] == k[0] and kk[2] == k[2] and (not k[1] or not kk[1]) and not _conflicts(mm, r):
                        k = kk
                        break
            if k in merged and _conflicts(merged[k], r):
                k = _key(r, with_segment=True)
            m = merged.setdefault(k, {"product_raw": r["product_raw"], "family": r["family"], "segment": r["segment"], "site": r["site"],
                                      "entity": r["entity"], "unit_raw": r["unit_raw"], "ton_mul": r["ton_mul"], "aggregate": r.get("aggregate", False),
                                      "periods": {}, "tables": []})
            if not m["segment"] and r["segment"]:
                m["segment"] = r["segment"]
            if not m["site"] and r["site"]:
                m["site"] = r["site"]
            if m["ton_mul"] is None and r["ton_mul"] is not None:
                m["ton_mul"], m["unit_raw"] = r["ton_mul"], r["unit_raw"]
            m["tables"].append(t["lead"][-40:])
            for pk, mv in r["values"].items():
                slot = m["periods"].setdefault(pk, {"cur": pk == t["cur"]})
                for meas, v in mv.items():
                    slot.setdefault(meas, v)
    products = []
    for k, m in merged.items():
        cur_keys = [pk for pk, s in m["periods"].items() if s["cur"]]
        cur = m["periods"][cur_keys[0]] if cur_keys else None
        prev_annual = None
        for pk, s in m["periods"].items():
            if not s["cur"] and s.get("capacity") is not None and not re.search(r"반기|분기|상반기", pk):
                prev_annual = s["capacity"] if prev_annual is None else prev_annual
        rec = dict(m)
        rec["is_ton"] = m["ton_mul"] is not None      # 톤 환산계수는 첫 단위 토큰에서만 나온다('톤, 매' 는 톤) — 배럴·백만원·시간·T/H 는 None
        rec["cur_period"] = cur_keys[0] if cur_keys else None
        rec["capacity_period"] = (cur or {}).get("capacity")
        rec["output_period"] = (cur or {}).get("output")
        rec["util_pct"] = (cur or {}).get("util")
        rec["util_src"] = None
        if rec["util_pct"] is not None:
            rec["util_src"] = "reported"
            if rec["util_pct"] <= 1.5 and rec["output_period"] and rec["capacity_period"]:
                rec["util_pct"] = round(rec["util_pct"] * 100, 1)   # 0.70 꼴
        rec["prev_annual_capacity"] = prev_annual
        rec["months"] = months
        cap = rec["capacity_period"]
        if cap is not None and rec["ton_mul"]:
            cap_t = cap * rec["ton_mul"]
            prorated = (months < 12 and prev_annual and cap / prev_annual < PRORATED_MAX) or (months < 12 and not prev_annual and False)
            if months < 12 and prev_annual is None:
                prorated = None      # 판단 근거 없음 — 연환산하지 않고 표시
            rec["capacity_ton_period"] = cap_t
            rec["capacity_ton_annual"] = cap_t * 12.0 / months if prorated else cap_t
            rec["basis"] = ("기간비례(%d개월)→연환산" % months if prorated else
                            "연간 명판 그대로(직전 연간과 %.0f%%)" % (100.0 * cap / prev_annual) if prev_annual else
                            "연환산 근거 없음(직전 연간 열 없음) — 기간값 그대로")
            rec["prev_annual_ton"] = prev_annual * rec["ton_mul"] if prev_annual else None
        else:
            rec["capacity_ton_period"] = rec["capacity_ton_annual"] = None
            rec["basis"] = "톤 단위 아님(%s)" % (rec["unit_raw"] or "단위 미확인") if cap is not None else "생산능력 없음"
        rec["output_ton_period"] = rec["output_period"] * rec["ton_mul"] if (rec["output_period"] is not None and rec["ton_mul"]) else None
        # 가동률이 보고되지 않았으면 생산실적 ÷ (연간 생산능력 × 개월/12) — 기간이 맞는 분모를 쓴다(한화: 연간 명판 + 반기 실적)
        if rec["util_pct"] is None and rec["capacity_ton_annual"] and rec["output_ton_period"] is not None:
            denom = rec["capacity_ton_annual"] * months / 12.0
            rec["util_pct"] = round(100.0 * rec["output_ton_period"] / denom, 1) if denom else None
            rec["util_src"] = "computed(%d개월 분모)" % months
        # 기간별 원값 보존(연간 열 포함) — 증설/축소 탐지는 build 에서 연간 열끼리 비교
        rec["history"] = {pk: {kk: vv for kk, vv in s.items() if kk != "cur"} for pk, s in m["periods"].items()}
        products.append(rec)
    def _np(s):
        return re.sub(r"[\s(*)]", "", s or "").lower()
    for rec in products:
        for n in nameplates:
            if unit_of("(단위 : %s)" % n["unit_raw"])[1] and _np(n["product_raw"]) == _np(rec["product_raw"]):
                rec["nameplate_ton"] = n["value"] * unit_of("(단위 : %s)" % n["unit_raw"])[1]
                rec["nameplate_unit"] = n["unit_raw"]
    unparsed = [u for t in tables for u in t["unparsed"]]
    return {"tables": len(tables), "products": products, "unparsed": unparsed, "nameplates": nameplates,
            "table_heads": [t["heads"][:9] for t in tables]}


# ── 수집 ──────────────────────────────────────────────────────

def section_node(nodes):
    for key, pats in SECTION_PATTERNS:
        for n in nodes:
            if any(p in n.get("text", "") for p in pats):
                return n
    return None


def collect(stock, name, quarter, force=False, log=None):
    """정기보고서 → 캐시 → 파싱. 반환 {'ok', 'rcp', 'title', 'note', 'parsed'}. 네트워크는 캐시가 없을 때만."""
    cname = "%s_cap.html" % quarter
    meta_name = "%s_cap.meta.json" % quarter
    html = None if force else read_cache(stock, cname)
    meta = None
    if html is None:
        start, end = search_window(quarter)
        reps = pick_report(search_reports(stock, start, end, report_kind(quarter)), quarter)
        if not reps:
            return {"ok": False, "note": "정기보고서 없음(%s~%s)" % (start, end)}
        for rcp, title in reps[:3]:
            nodes = toc(rcp)
            node = section_node(nodes)
            if node:
                break
        else:
            return {"ok": False, "rcp": reps[0][0], "title": reps[0][1], "note": "생산설비 절 없음"}
        html = fetch_section(node)
        write_cache(stock, cname, html)
        meta = {"rcp": rcp, "title": title, "node": node.get("text")}
        write_cache(stock, meta_name, __import__("json").dumps(meta, ensure_ascii=False))
    else:
        raw = read_cache(stock, meta_name)
        meta = __import__("json").loads(raw) if raw else {}
    parsed = parse_section(html, quarter)
    return {"ok": True, "rcp": meta.get("rcp"), "title": meta.get("title"), "note": "", "parsed": parsed}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stocks", default="")
    ap.add_argument("--quarter", default="2026Q2")
    ap.add_argument("--fixture", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args(argv)
    if a.fixture:
        html = open(a.fixture, encoding="utf-8").read()
        if a.debug:
            for t in parse_tables(html):
                pt = parse_table(t, a.quarter)
                if pt:
                    print("TABLE ctx=%s cur=%s unit=%r mul=%s periods=%s\n   heads=%s\n   lead=…%s" % (pt["ctx"], pt["cur"], pt["unit"], pt["ton_mul"], pt["periods"], pt["heads"][:9], pt["lead"][-70:]))
        p = parse_section(html, a.quarter)
        print("tables %d · products %d · unparsed %d · nameplates %d" % (p["tables"], len(p["products"]), len(p["unparsed"]), len(p["nameplates"])))
        for r in p["products"]:
            print("  %-28s | %-14s | %-10s | %-6s | cap %s → annual %s | out %s | util %s | %s" % (
                r["product_raw"][:28], r["segment"][:14], r["site"][:10], (r["unit_raw"] or "")[:6], r["capacity_period"],
                r["capacity_ton_annual"], r["output_period"], r["util_pct"], r["basis"]))
        for n in p["nameplates"]:
            print("  명판:", n)
        return
    uni = load_asset("universe.json")["rows"]
    names = {r["stock"]: r["name"] for r in uni}
    stocks = [s for s in a.stocks.split(",") if s] or ([r["stock"] for r in uni if not r.get("excluded")] if a.all else [])
    results = {}
    for i, st in enumerate(stocks):
        try:
            res = collect(st, names.get(st, st), a.quarter, force=a.force)
        except Exception as e:          # 한 회사 실패가 전체를 멈추지 않게 — 사유는 남긴다
            res = {"ok": False, "note": "%s: %s" % (type(e).__name__, str(e)[:120])}
        n = len(res.get("parsed", {}).get("products", [])) if res.get("ok") else "-"
        print("[%d/%d] %s %s ok=%s %s rcp=%s products=%s" % (i + 1, len(stocks), st, names.get(st, ""), res.get("ok"), res.get("note") or "", res.get("rcp"), n), flush=True)
        results[st] = {k: v for k, v in res.items() if k != "parsed"}
    if a.all:
        write_asset("collect_%s.json" % a.quarter, results)


if __name__ == "__main__":
    main()
