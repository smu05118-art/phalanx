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
    II-4/III-8 갱신을 막지 않는다. DATA(D)는 읽지도 쓰지도 않는다(최소 구현)."""
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
    return parsed
