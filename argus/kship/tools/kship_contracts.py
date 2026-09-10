#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_contracts — 조선사의 척당 수주를 수시공시 「단일판매ㆍ공급계약체결」에서 모은다.

정기보고서 II-4 수주표는 세 조선사 모두 **사업부문 롤포워드**(기초+신규−기납품=기말, 원화)라
선종·척수·인도시점이 없다(2026 반기 실측). 그 셋은 척당 계약 공시에만 있다:
  체결계약명 "LPGC 4척" · 계약금액(원) · 계약상대(익명 '오세아니아 소재 선사') · 판매지역 ·
  계약기간 시작일/종료일(종료일 = 마지막 호선 인도 예정 → 선표) · 계약금ㆍ선급금 유무 ·
  대금지급 조건('공사진척에 따른 수금' 등) · 계약(수주)일자.

정정공시([기재정정])는 같은 계약의 새 판이다 — 원본을 덮되 이력은 남긴다.
반복건조(시리즈)는 공시에 직접 없다. 같은 조선사·같은 선종·같은 상대 표기·근접한 수주일의
계약을 묶고, 본문에 '옵션'·'동형' 언급이 있으면 표시한다(추정임을 `est`로 남긴다).

캐시: assets/contracts/<종목>/<rcpNo>.json (원문 label→value 전부 보존, 파싱 결과 병기).
    python3 kship_contracts.py --collect --from 20240101      # 조선사 전부
    python3 kship_contracts.py --build                        # 캐시 → assets/contracts.json
"""
import argparse
import json
import os
import re
import sys
import time

from kship_lib import (ASSETS, atomic_write, fetch_section, load_asset, num_of,
                       parse_tables, search_reports, toc, write_asset)
from kship_universe import load as load_universe

CACHE = os.path.join(ASSETS, "contracts")
_SHIPS = re.compile(r"(\d+)\s*(?:척|기|대)(?![가-힣])")     # 해양플랜트는 'FPSO 1기'로 센다
_OPTION = re.compile(r"옵션|option|동형|시리즈|series", re.I)


def _types():
    d = load_asset("ship_types.json")
    pairs = []
    for t in d["types"]:
        for a in [t["ko"], t["id"]] + list(t.get("aliases") or []):
            pairs.append((a.lower().replace(" ", ""), t["id"]))
    pairs.sort(key=lambda p: -len(p[0]))           # 긴 별칭 우선('LPG운반선(VLGC)' > 'LPG')
    return pairs


_TYPE_PAIRS = None


_NONSHIP = re.compile(r"공사|마감|저탄장|플랜트|발전기|엔진|블록|기자재|설계|용역|납품|모듈|설비|구조물|건설"
                      r"|정비사업|재개발|재건축|주택|현대화사업|조절사업|포장사업|신설|어시장|도로", re.I)   # HJ중공업 건설부문


def ship_type_of(name):
    """체결계약명 → 선종 id. 선박이 아닌 계약(조선사의 건설·엔진·블록 납품)은 'OTHER'.
    못 찾으면 None(추정하지 않는다)."""
    global _TYPE_PAIRS
    if _TYPE_PAIRS is None:
        _TYPE_PAIRS = _types()
    t = (name or "").lower().replace(" ", "")
    for alias, tid in _TYPE_PAIRS:
        if alias and alias in t:
            return tid
    if "척" not in t and _NONSHIP.search(name or ""):
        return "OTHER"                    # HJ중공업 건설공사·HD현대重 엔진발전기·대한조선 블록 납품
    # 특수선: 관공선·조사선·방제선처럼 사전에 없는 이름은 '…함/…선 N척' 꼴로 잡는다
    if re.search(r"쇄빙|조사선|관공선|여객선|페리|카페리|예인선|준설선|방제|경비|순찰|훈련함|지원함", name or "") \
       or re.search(r"[가-힣]함\s*\d+\s*척", name or ""):
        return "NAVAL"
    return None


def _kv(html):
    """공시 본문의 (항목, 세부항목, 값) 3열 표 → {정규화 라벨: 값}. 원문 라벨도 함께 남긴다."""
    kv, raw = {}, []
    for t in parse_tables(html):
        for row in t["rows"]:
            cells = [c.strip() for c in row]
            if len(cells) < 2:
                continue
            val = cells[-1]
            labels = [c for c in cells[:-1] if c and c != val]
            key = " ".join(dict.fromkeys(labels))            # 중복 라벨 제거, 순서 보존
            if not key:
                continue
            raw.append((key, val))
            kv.setdefault(_norm_key(key), val)
    return kv, raw


def _find(kv, *needles):
    """needle 을 모두 품은 라벨 중 **가장 짧은** 라벨의 값. 정정공시는 앞에 '계약기간-종료일2029-03-31'
    같은 정정 표 라벨이 먼저 오는데, 본표의 '계약기간종료일'이 더 짧아 본표 값이 이긴다."""
    hits = [(len(k), i, v) for i, (k, v) in enumerate(kv.items()) if all(n in k for n in needles)]
    return min(hits)[2] if hits else None


def _fields_from_kv(kv):
    """정규화 라벨 사전 → 계약 필드. 거래소 서식이 둘이다:
      · 구형: '체결계약명' 행에 계약명
      · 2025~ 신형(HD현대重 등): '1. 판매ㆍ공급계약 구분'(공사수주) + '- 세부내용'(VLCC 2척), 수주일 라벨은 '계약(수주)일'
    정정공시는 앞에 정정 표(정정전/정정후)가 붙지만 본표 라벨은 같다."""
    name = _find(kv, "체결계약명") or _find(kv, "계약명") or ""
    if not name and _find(kv, "판매공급계약구분"):
        name = _find(kv, "세부내용") or ""
    amt_krw = num_of(_find(kv, "계약금액(원)") or _find(kv, "계약금액") or "")
    return {
        "name": name,
        "type": ship_type_of(name),
        "ships": (int(_SHIPS.search(name).group(1)) if _SHIPS.search(name) else None),
        "amt_krw_m": (round(amt_krw / 1e6, 3) if amt_krw is not None else None),   # 백만원
        "rev_ratio": num_of(_find(kv, "매출액대비") or ""),
        "party": _find(kv, "계약상대") or "",
        "region": _find(kv, "판매", "지역") or _find(kv, "공급지역") or "",
        "start": _find(kv, "계약기간", "시작") or _find(kv, "시작일") or "",
        "end": _find(kv, "계약기간", "종료") or _find(kv, "종료일") or "",
        "signed": _find(kv, "수주", "일자") or _find(kv, "계약(수주)일자") or _find(kv, "계약(수주)일") or "",
        "advance": _find(kv, "선급금") or "",
        "payterm": _find(kv, "대금지급") or "",
        "withheld": _find(kv, "공시유보") or _find(kv, "유보") or "",
        "note": _find(kv, "기타", "중요") or _find(kv, "기타") or "",
    }


def _norm_key(key):
    return re.sub(r"^\s*[\d]+\.\s*|^\s*-\s*|[\s　ㆍ·]", "", key)


def _kv_from_raw(raw):
    """캐시의 원문 (라벨, 값) 목록 → 정규화 사전(첫 값 우선). 정정 표의 '5. 계약기간 -종료일 2029-03-31'
    같은 라벨은 본표의 '계약기간 종료일'과 다른 키가 되므로 본표 값이 그대로 남는다."""
    kv = {}
    for k, v in raw:
        kv.setdefault(_norm_key(k), v)
    return kv


def parse_contract(html, rcp, title, stock):
    kv, raw = _kv(html)
    rec = {"rcp": rcp, "stock": stock, "title": title, "corrected": "정정" in (title or "")}
    rec.update(_fields_from_kv(kv))
    rec["kv"] = raw
    blob = " ".join(v for _, v in raw)
    rec["option_hint"] = bool(_OPTION.search(blob))
    rec["party_anon"] = bool(re.search(r"소재|선사|선주|비공개|유보", rec["party"]))
    return rec


def collect(stocks, start, end, force=False, log=sys.stderr):
    for st in stocks:
        lst = search_reports(st, start, end, "I001")
        cons = [(r, t) for r, t in lst if "단일판매" in t or "공급계약" in t]
        got = 0
        for rcp, title in cons:
            path = os.path.join(CACHE, st, rcp + ".json")
            if os.path.exists(path) and not force:
                got += 1
                continue
            try:
                nodes = toc(rcp)
                if not nodes:
                    continue
                html = fetch_section(nodes[0])
                rec = parse_contract(html, rcp, title, st)
            except Exception as e:                          # 일시 실패는 캐시하지 않는다
                log.write("[warn] %s %s %s\n" % (st, rcp, e))
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            atomic_write(path, json.dumps(rec, ensure_ascii=False, indent=1) + "\n")
            got += 1
        log.write("%s 계약 공시 %d건 중 캐시 %d건\n" % (st, len(cons), got))
        log.flush()


def build(stocks):
    """캐시 → contracts.json. 정정공시는 같은 (조선사, 계약명, 수주일)의 원본을 덮는다."""
    out = []
    for st in stocks:
        d = os.path.join(CACHE, st)
        if not os.path.isdir(d):
            continue
        recs = []
        for f in sorted(os.listdir(d)):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                recs.append(json.load(fh))
        by = {}
        for r in sorted(recs, key=lambda r: r["rcp"]):      # rcp 오름차순 → 뒤(정정)가 덮는다
            # 선종·척수는 캐시값을 믿지 않고 이름에서 다시 뽑는다 — 별칭 사전이 자라도
            # 재수집 없이 반영되도록(캐시는 원문 보존이 목적이지 판정 보존이 아니다).
            if r.get("kv"):
                r.update(_fields_from_kv(_kv_from_raw(r["kv"])))
            else:
                r["type"] = ship_type_of(r["name"])
                m = _SHIPS.search(r["name"] or "")
                r["ships"] = int(m.group(1)) if m else r.get("ships")
            key = (r["stock"], r["name"], r["signed"] or r["start"])
            if key in by:
                r["supersedes"] = by[key]["rcp"]
            by[key] = r
        out.extend(by.values())
    out.sort(key=lambda r: (r["stock"], r["signed"] or r["start"], r["rcp"]))
    for r in out:
        r.pop("kv", None)
    write_asset("contracts.json", {"n": len(out), "rows": out})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--from", dest="start", default="20240101")
    ap.add_argument("--to", dest="end", default=time.strftime("%Y%m%d"))
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    yards = [r["stock"] for r in load_universe() if r["role"] in ("yard", "holding")]
    if a.only:
        yards = [s for s in a.only.split(",")]
    if a.collect:
        collect(yards, a.start, a.end, a.force)
    if a.build:
        rows = build(yards)
        from collections import Counter
        print("계약 %d건 · 선종 %s · 척수합 %s" % (
            len(rows), dict(Counter(r["type"] for r in rows)),
            sum(r["ships"] or 0 for r in rows)))
        for r in rows[-5:]:
            print("  ", r["stock"], r["signed"], r["type"], r["ships"], r["name"][:30], r["amt_krw_m"], r["region"], r["end"])


if __name__ == "__main__":
    sys.exit(main())
