#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kce_xi1 — 정기보고서 XI-1 「공시내용 진행 및 변경사항」의 **나. 단일판매ㆍ공급계약 진행 현황** 표.

2024Q4 부터 반기·사업보고서에 실린다(분기보고서는 대개 없음 — '표 없음'이 정상). 이 모듈은 **최소 구현**이다
(설계 C·U3): 절 원문 → 표 파싱 → 머리행 지도(rep['headers']['xinb'], tag '나')·원문 캐시
(assets/xi1_cache/<co>/<q>.json)·미지 머리행 대기열. DATA.xip 갱신(_apply_xi1: 사업장 매칭·mt 판정)은
하지 않는다 — 원본 7사 실측상 이름 자동 정확일치가 25% 뿐이고 63% 가 사람 판정이라, 매칭 규칙과 사람 입력
파일 형식을 정하기 전에 데이터에 섞지 않는다.

왜 전역 사전(kce_lib.COL_ALIAS)을 쓰지 않는가: `_HDR_VOCAB = set(COL_ALIAS)` 라 XI 어휘를 전역에 넣으면
6개 탭의 머리행 감지가 함께 바뀌고, '계약명'·'계약상대방'·'구분'은 II-4/III-8 에서 다른 필드다.
그래서 XI 사전·어휘·머리행 상한(4줄)은 전부 이 모듈 안에서만 쓴다.

원문 방언(2026Q2 14사 실측):
  · 머리행 2~4단(`계약내역 | 계약명`, `판매ㆍ공급금액 | 당기 | 누적`), 대부분 td 머리행.
  · 단위: lead 백만원 9사 / 억원 금호·코오롱 / 원 삼성E&A. 삼성물산·대우는 `계약금액총액(원)` 열만 원이고
    나머지 열은 백만원 → **열 단위가 표 단위보다 앞선다**.
  · 계약내역 한 칸에 `계약명 : … 계약상대방 : … 계약기간 : …` 을 담는 회사 9사(줄바꿈이 지워져 라벨이
    앞 값에 붙기도 한다 — DL이앤씨·계룡·HS화성).
  · 외화 계약금액 `2,663,571,150 (USD)` → 금액 None + cur.
  · 삼성E&A 는 한 계약금액 칸(rowspan)에 계약명 2줄 — 금액이 위에서 흘러내린 줄은 앞 계약에 이름만 덧붙인다.
"""
import json
import os
import re

import hdrmap
from kce_lib import atomic_write, norm_col, num_of
import kce_parse as KP

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "assets", "xi1_cache")

XI_ALIAS = {
    "신고일자": "xi_dt", "신고일자(최초)": "xi_dt", "신고일자(최근)": "xi_dt", "신고일자(최종)": "xi_dt",
    "신고일자(정정)": "xi_dt", "공시일자": "xi_dt",
    "계약내역": "xi_nm", "계약내역계약명": "xi_nm", "계약내역(공사명)": "xi_nm", "계약명": "xi_nm",
    "계약내역계약상대방": "xi_cl", "계약상대방": "xi_cl",
    "계약내역계약시작월": "xi_sd", "계약내역계약기간시작일": "xi_sd",
    "계약내역계약종료월": "xi_ed", "계약내역계약기간종료일": "xi_ed", "계약내역계약만기": "xi_ed",
    "계약내역계약기간": "xi_period",
    "계약금액총액": "xi_amt", "계약금액총액(원)": "xi_amt", "계약금액총액(부가세포함)": "xi_amt",
    "계약금액": "xi_amt", "계약내역계약금액총액": "xi_amt",
    "판매공급금액당기": "xi_supCur", "판매공급금액누적": "xi_supCum",
    "판매공급금액(백만원)당기": "xi_supCur", "판매공급금액(백만원)누적": "xi_supCum",
    "판매공급금액(매출액)당기": "xi_supCur", "판매공급금액(매출액)누적": "xi_supCum",
    "대금수령금액당기": "xi_recvCur", "대금수령금액누적": "xi_recvCum",
    "대금수령금액(백만원)당기": "xi_recvCur", "대금수령금액(백만원)누적": "xi_recvCum",
    "대금수령당기": "xi_recvCur", "대금수령누적": "xi_recvCum",
    "비고": "xi_note", "대금미수령사유": "xi_note", "향후추진계획": "xi_note",
    "대금미수령사유및향후추진계획": "xi_note", "향후추진계획판매공급이행": "xi_note",
    "향후추진계획대금수령": "xi_note", "변동가능성": "xi_note",
    "계약내역기타사항": "xi_etc", "계약내역주요계약조건": "xi_etc", "계약내역조건부계약금액": "xi_etc",
    "계약내역계약금선급금유무": "xi_etc", "계약내역대금지급조건등": "xi_etc",
    "구분": "xi_kind",
}
# 다단 머리행의 부모 줄 낱말 — 이것만으로 된 줄도 머리행으로 본다(지역 어휘, 전역 불변).
_XI_PARENT = {"계약내역", "판매공급금액", "대금수령금액", "계약금액총액", "판매공급금액(백만원)",
              "대금수령금액(백만원)", "판매공급금액(매출액)", "계약금액총액(원)", "향후추진계획", "계약기간",
              "계약상대방", "계약명", "계약시작월", "계약종료월", "기타사항", "주요계약조건", "조건부계약금액",
              "계약금선급금유무", "대금지급조건등", "계약만기", "공시일자", "시작일", "종료일", "당기", "누적"}
XI_VOCAB = set(KP._HDR_VOCAB) | set(XI_ALIAS) | _XI_PARENT
NEED = {"xi_nm", "xi_amt", "xi_supCum", "xi_recvCum"}
MONEY = ("xi_amt", "xi_supCur", "xi_supCum", "xi_recvCur", "xi_recvCum")
# 판매공급·대금수령 문구가 머리행에 있는데 NEED 가 안 서면 '읽어야 할 표를 못 읽은 것'(미지).
# 가 표(신고일자|제목|신고내용|진행상황)·사유 부표는 이 문구가 없어 경보하지 않는다.
_XI_HINT = re.compile(r"판매.?공급|대금\s*수령")

_COL_UNIT = re.compile(r"\((원|천원|백만원|억원)\)")
_UNIT_MUL = {"원": 1e-6, "천원": 1e-3, "백만원": 1.0, "억원": 100.0}
_CUR = re.compile(r"\(([A-Z]{3})\)|\b([A-Z]{3})\s*[\d,]")
_LBL = (r"(?:체결\s*계약\s*명|계약\s*명|계약\s*상대방|계약\s*기간|계약\s*\(수주\)\s*일자|주요\s*계약\s*조건|"
        r"계약금[ㆍ·,]\s*선급금\s*유무|대금\s*지급\s*조건\s*등?|조건부\s*계약금액|기타(?:\s*투자판단과\s*관련한\s*중요사항)?)")
# 라벨은 앞 값에 붙어 올 수 있다(줄바꿈이 지워진 원문) — 경계를 요구하지 않고, 글머리 `1) `만 공백 뒤에서 본다.
_SPLIT = re.compile(r"(?:^|\s|[-●•]|(?:^|\s)\d\)\s*|(?<=[가-힣A-Za-z0-9)\]]))(" + _LBL + r")\s*[:：]\s*")
_TRAIL = re.compile(r"[\s\-●•]+$")
_DATE = re.compile(r"((?:19|20)\d{2}|['`’]\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


def field_of(ncol):
    return XI_ALIAS.get(ncol) or KP._field_of(ncol)


def col_unit(ncol):
    m = _COL_UNIT.search(ncol or "")
    return _UNIT_MUL[m.group(1)] if m else None


def split_detail(cell):
    """계약내역 셀 → {'계약명','계약상대방','계약기간',…}. 라벨이 없으면 셀 전체가 계약명."""
    cell = (cell or "").strip()
    parts = _SPLIT.split(cell)
    if len(parts) < 3:
        return {"계약명": _TRAIL.sub("", cell.lstrip("-").strip())}
    out = {}
    for i in range(1, len(parts) - 1, 2):
        lab = re.sub(r"[\sㆍ·]", "", parts[i])
        val = _TRAIL.sub("", parts[i + 1].strip())
        if "계약명" in lab:
            out.setdefault("계약명", val)
        elif lab.startswith("계약상대방"):
            out.setdefault("계약상대방", val)
        elif lab.startswith("계약기간"):
            out.setdefault("계약기간", val)
        elif lab.startswith("계약(수주)일자"):
            out.setdefault("계약일자", val)
        else:
            out["기타"] = (out.get("기타", "") + " " + lab + ":" + val).strip()
    if "계약명" not in out:
        out["계약명"] = _TRAIL.sub("", parts[0].strip().lstrip("-").strip())
    return out


def norm_dt(s):
    """신고일자 → YYYY.MM.DD. `26.06.25(변경계약)`처럼 2자리 연도는 20YY. 못 읽으면 None."""
    m = _DATE.search(s or "")
    if not m:
        return None
    y, mo, d = m.groups()
    y = int("20" + y[1:]) if not y[0].isdigit() else int(y)
    mo, d = int(mo), int(d)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d.%02d.%02d" % (y, mo, d)


def _scaled(v, mul):
    if v is None:
        return None
    x = v * mul
    return int(x) if float(x).is_integer() else round(x, 6)


def _records(t, idx):
    scale = KP.unit_scale(t.get("lead"), t.get("cols"))
    units = {f: (col_unit(t["ncols"][i]) or scale) for f, i in idx.items() if f in MONEY}
    rsp = t.get("rspan") or []
    out = []
    for ri, r in enumerate(t["rows"]):
        def g(f):
            i = idx.get(f)
            return (r[i] if i is not None and i < len(r) else "").strip()
        flags = rsp[ri] if ri < len(rsp) else []
        carried = (out and idx["xi_amt"] < len(flags) and flags[idx["xi_amt"]]
                   and idx["xi_supCum"] < len(flags) and flags[idx["xi_supCum"]])
        d = split_detail(g("xi_nm"))
        if carried:
            # 계약금액·판매공급이 위에서 흘러내린 줄 = 같은 계약의 둘째 이름(삼성E&A). 금액을 두 번 세지 않는다.
            if d.get("계약명"):
                out[-1].setdefault("nm_more", []).append(d["계약명"])
            continue
        amt_raw = g("xi_amt")
        vals = {f: _scaled(num_of(g(f)), units[f]) for f in MONEY if f in idx}
        cur = None
        if vals.get("xi_amt") is None and amt_raw not in ("", "-"):
            m = _CUR.search(amt_raw)
            if m:
                cur = m.group(1) or m.group(2)
        nm = d.get("계약명") or ""
        dt = g("xi_dt")
        # 주석 줄(신고일자가 날짜가 아니고 금액이 전부 비었다)과 합계 줄은 계약이 아니다.
        if not nm and all(v is None for v in vals.values()):
            continue
        if re.sub(r"\s", "", nm) in ("합계", "계", "총계", "소계"):
            continue
        if dt and norm_dt(dt) is None and all(v is None for v in vals.values()):
            continue
        rec = {"nm": nm, "cl": d.get("계약상대방") or g("xi_cl") or None,
               "period": d.get("계약기간") or ((g("xi_sd") + " ~ " + g("xi_ed")).strip(" ~") or g("xi_period") or None),
               "dt": norm_dt(dt), "dt_raw": dt or None, "amt_raw": amt_raw or None, "cur": cur}
        rec.update({k.replace("xi_", ""): v for k, v in vals.items()})
        out.append(rec)
    return out


def parse_xi1(html):
    """절 HTML → {'tables':[{lead,cols,ncols,fields,n_raw,n_rec,unit,rows}], 'rejected', 'unknown_headers'}."""
    tables = KP.parse_tables(html, max_header_rows=4, vocab=XI_VOCAB, keep_rowspan=True)
    picked, rejected, unknown = [], [], []
    for i, t in enumerate(tables):
        fields = [field_of(c) for c in t["ncols"]]
        idx = {}
        for j, f in enumerate(fields):
            if f and f not in idx:
                idx[f] = j
        base = {"idx": i, "lead": t.get("lead") or "", "cols": list(t["cols"]), "ncols": list(t["ncols"]),
                "fields": fields, "n": t.get("n_raw") or len(t["rows"])}
        if NEED.issubset(idx):
            recs = _records(t, idx)
            picked.append(dict(base, n_raw=base["n"], n_rec=len(recs), rows=recs,
                               unit=KP.unit_scale(t.get("lead"), t.get("cols"))))
            continue
        # '향후 추진계획 판매ㆍ공급 이행' 같은 서술 열(xi_note)은 문구가 겹쳐도 금액 열이 아니다 — 3) 향후 추진계획
        # 부표(7사)가 미지로 올라오던 오탐. 서술 열을 뺀 나머지 머리행에서만 판매공급·대금수령을 찾는다.
        head = " ".join(c for c, f in zip(t["cols"], fields) if f != "xi_note")
        if t["cols"] and _XI_HINT.search(head) and t["rows"]:
            unknown.append({"cols": list(t["cols"]), "n": len(t["rows"])})
            rejected.append(dict(base, reason="near_miss", rows=t["rows"]))
        elif t["cols"] and any(fields):
            rejected.append(dict(base, reason="no_core"))
    return {"tables": picked, "rejected": rejected, "unknown_headers": unknown}


def headers_of(parsed):
    """rep['headers']['xinb'] 항목 — 상류 지도 관례대로 tag '나'(76표 전부), 채택표만 pick True."""
    items = ([(t["idx"], t, True) for t in parsed["tables"]]
             + [(r["idx"], r, False) for r in parsed.get("rejected") or []])
    out = []
    for _i, t, ok in sorted(items, key=lambda x: x[0]):
        out.append({"cols": t["cols"], "ncols": t["ncols"], "fields": t["fields"], "n": t["n"],
                    "n_rec": t.get("n_rec") if ok else None, "lead": KP.lead_tail(t.get("lead")),
                    "tag": "나" if ok else "", "pick": ok, "reason": "picked" if ok else t["reason"]})
    return out


def cache_path(co, q, root=None):
    base = os.path.join(root, "xi1_cache") if root else CACHE
    return os.path.join(base, co, "%s.json" % q)


def write_cache(co, q, parsed, rcp=None, root=None):
    doc = {"co": co, "quarter": q, "rcpNo": rcp,
           "tables": [{"cols": t["cols"], "n": t["n"], "n_rec": t["n_rec"], "unit": t["unit"],
                       "lead": KP.lead_tail(t.get("lead")), "rows": t["rows"]} for t in parsed["tables"]]}
    p = cache_path(co, q, root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write(p, json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return p


def apply(co, q, raw_dir, D, k, rep, hdr_root=None, queue=False, cache_root=None):
    """kce_build.update_quarter 의 XI-1 단계(fail-soft). 원문이 없으면 아무것도 적지 않는다(지도에 절 키 없음 =
    그 분기 기록 안 함). 표가 없으면 빈 목록('봤는데 표 없음'). 미지는 rep['xi1_status'] + 대기열 — 예외로
    II-4/III-8 갱신을 막지 않는다. D 가 주어지면 확정 매칭만 DATA.xip 에 쓰고 나머지는 검토 목록(apply 때)."""
    path = os.path.join(raw_dir, "%s_xi1.html" % co)
    if not os.path.exists(path):
        rep["xi1_status"] = "absent"
        return None
    with open(path, encoding="utf-8") as f:
        parsed = parse_xi1(f.read())
    rep["headers"]["xinb"] = headers_of(parsed)
    rep["xi1_rows"] = sum(t["n_rec"] for t in parsed["tables"])
    if parsed["unknown_headers"]:
        rep["xi1_status"] = "unknown_headers"
        if queue:
            from kce_lib import CORP
            for r in parsed["rejected"]:
                if r["reason"] != "near_miss":
                    continue
                hdrmap.enqueue("kce", {"kind": "unknown", "key": co, "role": "xi", "quarter": q,
                                       "cols_raw": r["cols"], "ncols": r["ncols"], "fields": r["fields"],
                                       "n": r["n"], "lead": KP.lead_tail(r.get("lead")),
                                       "name": CORP[co]["name"], "stock": CORP[co]["stock"]},
                               root=hdr_root, strict=False)
    else:
        rep["xi1_status"] = "ok" if parsed["tables"] else "no_table"
    if queue and parsed["tables"]:
        write_cache(co, q, parsed, root=cache_root)
    if D is not None and parsed["tables"]:
        rows = [r for t in parsed["tables"] for r in t["rows"]]
        m = match_rows(D, k, rows, load_fill(co))
        rep["xi1_matched"] = apply_data(D, k, rows, m)
        rep["xi1_review"] = sum(1 for x in m if not x[1])
        if queue:
            write_review(co, q, rows, m, D)
    return parsed


# ── DATA.xip 반영(2026-10-13) — 사업장 매칭 ─────────────────────────────────
# 정답지: 라이브 7사 DATA 에 원본 사이트가 사람 판정까지 끝낸 2026Q2 연결 320건이 있다. 아래 규칙을 그 정답지로
# 평가해 **오매칭 0** 일 때만 데이터에 쓴다(tests/test_xi1.py TestXi1Match).
#   · 이력(warm): 직전 분기들의 XI-1 계약명(xip.nm·xipFull.계약명)과 정규화 이름이 같고 그 사업장이 유일 → 매칭.
#     같은 계약이 분기마다 다시 실리는 표라 가장 강한 신호다(실측 255/259 자동, 오매칭 0).
#   · 금액(cold): 판매공급 누적 = 그 분기 II-4 완성공사액(**±1백만원**, 실측 154/178 이 정확히 같다)인 사업장이 유일하고,
#     이름이 조금이라도 닮았거나(바이그램 Jaccard ≥ 0.2) 계약금액이 도급액 ±15%(또는 부가세 1.1배) → 매칭.
#     ±0.1% 로 느슨하게 두면 다른 계약이 우연히 걸린다(DL이앤씨 Gas Chemical ↔ 아크로 베스티뉴, 차이 0.07%).
#   · 이름(cold): 정규화 이름이 사업장 이름·이름 이력·III-8 품목과 같거나(6자 이상) 포함 관계이고, 그중 금액(누적≈완성공사액
#     ±1% 또는 계약금액≈도급액)이 맞는 후보가 하나 → 매칭.
#   · 그 밖은 **데이터에 쓰지 않고** 검토 목록(tools/assets/xi1_review.csv)에 후보와 근거를 남긴다. 신규(-11-) 사업장은
#     자동으로 만들지 않는다 — 이름이 다른 기존 사업장일 수 있다(원본도 '검토필요'·'수동보정'이 37%).
#   · 사람 판정: tools/assets/xi1_fill.csv (co,xi_name,site_id) — site_id 가 SKIP 이면 쓰지 않음. 자동 판정보다 우선.
# xifill{pend,chk} 는 원본 빌더의 xi1_fill 작업 카운터라 데이터로 재현되지 않는다(실측 34/51) — 건드리지 않는다.

import csv

_NOTE = re.compile(r"\(\*\d*\)|\*\d+\)?|\(주\d+\)")
XIP_ARR = ("amt", "supCur", "supCum", "recvCur", "recvCum")
FILL = os.path.join(HERE, "assets", "xi1_fill.csv")
REVIEW = os.path.join(HERE, "assets", "xi1_review.csv")
_REVIEW_COLS = ["co", "quarter", "xi_name", "amt", "supCum", "suggest_site", "suggest_name", "reason"]


def nkey(s):
    return re.sub(r"[\s()（）\[\]·ㆍ,.\-*'\"]", "", _NOTE.sub("", s or "")).lower()


def _bigr(s):
    s = nkey(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _sim(a, b):
    A, B = _bigr(a), _bigr(b)
    return len(A & B) / max(1, len(A | B))


def _near(a, b, tol=0.01):
    return a is not None and b is not None and b != 0 and abs(a - b) <= abs(b) * tol


def _amt_ok(a, b):
    if not a or not b:
        return False
    r = a / b
    return abs(r - 1) <= 0.15 or abs(r - 1.1) <= 0.01


def _at(arr, k):
    return arr[k] if isinstance(arr, list) and k < len(arr) else None


def _site_names(s):
    out = [s.get("nm") or ""]
    out += [n[1] for n in (s.get("names") or []) if isinstance(n, list) and len(n) > 1 and isinstance(n[1], str)]
    pf = (s.get("p8Full") or {}).get("품목")
    if isinstance(pf, list):
        out += [x for x in pf if isinstance(x, str)]
    return [x for x in out if x]


def load_fill(co, path=None):
    p = path or FILL
    out = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("co") or "").strip() == co:
                    out[nkey(r.get("xi_name"))] = (r.get("site_id") or "").strip()
    return out


def match_rows(D, k, rows, fill=None):
    """XI-1 행 → [(site_id|None, mt|None, how, suggest_site)]. mt None = 데이터에 쓰지 않음(검토)."""
    fill = fill or {}
    sites = D["sites"]
    sid = {s["id"]: s for s in sites}
    idx, prev = {}, {}
    for s in sites:
        for n in _site_names(s):
            idx.setdefault(nkey(n), set()).add(s["id"])
        x = s.get("xip") or {}
        names = [x.get("nm")] + [v for v in (((s.get("xipFull") or {}).get("계약명")) or [])[:k] if isinstance(v, str)]
        for n in names:
            if n:
                prev.setdefault(nkey(n), set()).add(s["id"])
    cmpk = {s["id"]: _at(s["s"].get("cmp"), k) for s in sites}
    out = []
    for r in rows:
        key = nkey(r["nm"])
        names = [r["nm"]] + list(r.get("nm_more") or [])
        f = fill.get(key)
        if f:
            if f == "SKIP" or f not in sid:
                out.append((None, None, "fill_skip", None))
            else:
                out.append((f, "매칭(수동보정)", "fill", f))
            continue
        if key in prev and len(prev[key]) == 1:
            s = next(iter(prev[key]))
            out.append((s, (sid[s].get("xip") or {}).get("mt") or "매칭", "prev_xi", s))
            continue
        sc = r.get("supCum")
        mon = [s for s, c in cmpk.items() if sc and sc >= 100 and c and abs(sc - c) <= 1]
        if len(mon) == 1:
            s = mon[0]
            simv = max(_sim(a, b) for a in names for b in (_site_names(sid[s]) or [""]))
            if simv >= 0.2 or _amt_ok(r.get("amt"), _at(sid[s]["s"].get("amt"), k)):
                out.append((s, "매칭", "money+" + ("name" if simv >= 0.2 else "amt"), s))
            else:
                out.append((None, None, "money_only", s))
            continue
        cands = set()
        for n in names:
            cands |= idx.get(nkey(n), set())
        if not cands and len(key) >= 6:
            cands = {s for kk, ss in idx.items() if len(kk) >= 6 and (kk in key or key in kk) for s in ss}
        ok = [c for c in cands if _near(sc, cmpk[c]) or _amt_ok(r.get("amt"), _at(sid[c]["s"].get("amt"), k))]
        if len(ok) == 1:
            out.append((ok[0], "매칭", "name+money", ok[0]))
        elif cands:
            out.append((None, None, "name_ambiguous" if len(cands) > 1 else "name_no_money",
                        sorted(cands)[0] if len(cands) == 1 else None))
        else:
            out.append((None, None, "no_candidate", None))
    # 같은 사업장에 두 계약이 붙으면(묶음 계약·이름 충돌) 둘 다 검토로 — 한쪽 값으로 덮지 않는다.
    cnt = {}
    for s, mt, _h, _g in out:
        if mt:
            cnt[s] = cnt.get(s, 0) + 1
    return [(None, None, "dup_site", s) if mt and cnt[s] > 1 else (s, mt, h, g) for s, mt, h, g in out]


def _set_at(arr, k, n, v):
    if not isinstance(arr, list):
        arr = [None] * n
    if len(arr) < n:
        arr = arr + [None] * (n - len(arr))
    arr[k] = v
    return arr


def apply_data(D, k, rows, matches):
    """매칭된 행만 DATA 에 쓴다: xip 5배열[k]·cur·nm(비었을 때)·mt, xipFull[k], has[2]=1. 반환: 쓴 건수."""
    n = len(D["fqF"])
    sid = {s["id"]: s for s in D["sites"]}
    wrote = 0
    for r, (s_id, mt, _how, _g) in zip(rows, matches):
        if not mt:
            continue
        s = sid[s_id]
        x = s.setdefault("xip", {})
        for f in XIP_ARR:
            x[f] = _set_at(x.get(f), k, n, r.get(f))
        if r.get("cur"):
            x["cur"] = r["cur"]
        else:
            x.setdefault("cur", None)
        if not x.get("nm"):
            x["nm"] = r["nm"]
        x["mt"] = mt
        xf = s.setdefault("xipFull", {})
        per = r.get("period") or ""
        ds = re.findall(r"((?:19|20)\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", per)
        fmt = lambda t: "%s-%02d-%02d" % (t[0], int(t[1]), int(t[2]))
        vals = {"계약명": r["nm"], "계약상대방": r.get("cl"),
                "계약시작일": fmt(ds[0]) if ds else None, "계약종료일": fmt(ds[1]) if len(ds) > 1 else None,
                "계약금액": r.get("amt") if r.get("amt") is not None else r.get("amt_raw")}
        for key, v in vals.items():
            xf[key] = _set_at(xf.get(key), k, n, v)
        has = s.get("has") or [0, 0, 0]
        has[2] = 1
        s["has"] = has
        wrote += 1
    return wrote


def write_review(co, q, rows, matches, D, path=None):
    """검토 목록 CSV — 이 회사·분기 줄만 교체하고 나머지는 보존(정렬·시각 없음)."""
    p = path or REVIEW
    keep = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            keep = [r for r in csv.DictReader(f) if not (r["co"] == co and r["quarter"] == q)]
    sid = {s["id"]: s for s in D["sites"]}
    for r, (_s, mt, how, g) in zip(rows, matches):
        if mt:
            continue
        keep.append({"co": co, "quarter": q, "xi_name": r["nm"], "amt": "" if r.get("amt") is None else r["amt"],
                     "supCum": "" if r.get("supCum") is None else r["supCum"], "suggest_site": g or "",
                     "suggest_name": (sid[g].get("nm") if g in sid else "") or "", "reason": how})
    keep.sort(key=lambda r: (r["co"], r["quarter"], r["xi_name"]))
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_REVIEW_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(keep)
    atomic_write(p, buf.getvalue())
    return sum(1 for r in keep if r["co"] == co and r["quarter"] == q)
