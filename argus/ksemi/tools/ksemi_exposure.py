#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_exposure — **메모리 / 비메모리·파운드리 노출**을 회사 본문에서 읽는다.

스펙 「산업 특성 5」는 전공정/후공정과 함께 **메모리·파운드리 노출**을 회사마다 표시하라고
한다. 전/후공정은 공정 단계 사전(`build_dicts`)이 준다. 메모리/파운드리는 그렇지 않다 —
어느 회사도 "메모리 매출 몇 %"를 공시하지 않는다. 그래서 **원문 낱말**로만 표시하고,
비중이라고 적지 않는다(COMMON §0-1).

## 어느 절을 세는가 — 여기가 전부다

II절 본문에서 `메모리`는 **거의 다 산업 전망 문단**에 있다(2026-09-11 실측: 사업개요·기타
절 1,105회 ↔ 주요제품·매출실적 절 189회). 이런 문장이다:

  · 유니셈 — *"최근 **메모리 반도체**의 세계적 공급 과잉과 기업간 가격 경쟁이 치열해짐에
    따라 국내 장비업계의 경쟁력 제고필요성이 증대되고 있습니다"* → 시장 이야기지
    이 회사가 메모리에 노출됐다는 말이 아니다.

반면 **II-2 주요제품**과 **II-4 매출실적**은 그 회사의 제품·매출 칸이다:

  · 유니테스트 — *"당사의 주요 제품은 크게 **메모리**컴포넌트테스터, **메모리**모듈테스터,
    고속번인테스터…"*
  · 리노공업 — *"IC TEST SOCKET 류 반도체(**메모리 및 비메모리**) 테스트 PACKAGE용 장비의
    소모성 부품"*
  · 피에스케이홀딩스 — *"IDM, OSAT, **Foundry** 고객의 양산 및 연구개발용으로 판매"*

그래서 **`products`·`sales` 절만 센다.** 같은 규칙을 이 탭은 이미 쓰고 있다 — 부품 연결도
"II-2 근거는 매출 구성표의 품목 줄일 때만 받는다"(LOGIC §7). 산업 전망 문단은 세지 않고,
세지 않았다는 사실을 화면에 적는다.

## 낱말의 덫

**`비메모리` 안에 `메모리`가 들어 있다.** 그냥 세면 비메모리 전용 회사가 메모리 노출로
찍힌다(리노공업 *"메모리 및 비메모리"* 는 메모리 1 + 비메모리 1이어야 하는데 메모리 2가
된다). 그래서 메모리 쪽은 `(?<!비)메모리` 로 막는다.

## 수집하지 않는다

`ksemi_scan.py` 가 받아 둔 II절 캐시(`assets/cache/sec_*.html`)만 읽는다 — DART를 두드리지
않으므로 언제든 공짜로 다시 돌린다.

    python3 ksemi_exposure.py             # 표로 본다(쓰지 않는다)
    python3 ksemi_exposure.py --show      # 원문 인용까지
    python3 ksemi_exposure.py --write     # assets/exposure.json
"""
import argparse
import json
import os
import re
import sys
import time

from ksemi_lib import ASSETS, load_asset, write_asset
import ksemi_scan as S

# 세는 절 — 그 회사의 제품·매출 칸. 나머지(overview·etc)는 산업 전망 문단이라 세지 않는다.
SECTIONS = ("products", "sales")

# 메모리: `비메모리` 를 먹지 않게 앞에 `비`가 오면 뺀다. 영문은 낱말 경계로 막는다
# (NAND 가 다른 낱말 안에 들어가는 일은 드물지만 경계를 두는 편이 싸다).
MEM = re.compile(r"(?<!비)메모리|디램|D램|\bDRAM\b|낸드|\bNAND\b|\bHBM\d*\b|\bSSD\b", re.I)
# 비메모리·파운드리. `시스템반도체`·`로직`은 원문 표기 그대로.
FND = re.compile(r"파운드리|\bFoundry\b|비메모리|시스템\s*반도체|시스템\s*LSI|"
                 r"로직\s*반도체|\bLogic\s*(?:IC|Device)\b", re.I)

MAX_QUOTES = 3                      # 화면에 싣는 인용 수. 근거는 사람이 읽을 수 있어야 한다.
# 인용끼리 겹치지 않게 하는 최소 간격(글자). 「메모리컴포넌트테스터, 메모리모듈테스터」는
# 낱말이 둘이지만 한 문장이라 인용을 두 번 실으면 같은 문장이 두 번 찍힌다.
QUOTE_GAP = 200


def sections_of_cache(stock, quarter):
    """스캔 캐시의 II절을 **절별로** 준다. 없으면 None(받으러 가지 않는다).

    `ksemi_peers.text_of_cache` 는 절을 한 덩어리로 붙인다 — 여기서는 어느 절에서 나온
    낱말인지가 판정의 전부라서 절을 나눠 둔 채로 읽는다.
    """
    mp = S._meta_path(stock, quarter)
    if not os.path.exists(mp):
        return None
    with open(mp, encoding="utf-8") as f:
        meta = json.load(f)
    out = {}
    for key in (meta.get("sections") or {}):
        p = S._sec_path(meta["rcpNo"], key)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            out[key] = re.sub(r"\s+", " ", S.text_of(f.read()))
    if not out:
        return None
    return out, meta["rcpNo"], meta.get("title", "")


SEC_KO = {"products": "II-2 주요제품", "sales": "II-4 매출실적",
          "overview": "II-1 사업의 개요", "etc": "II 기타", "ii": "II절"}


def hits(secs):
    """{절: 평문} → (메모리 hit, 비메모리 hit). hit = {n, quotes[{sec, quote}]}."""
    out = {}
    for label, rx in (("mem", MEM), ("fnd", FND)):
        n, quotes = 0, []
        for key in SECTIONS:
            txt = secs.get(key) or ""
            last = None
            for m in rx.finditer(txt):
                n += 1
                if len(quotes) < MAX_QUOTES and (last is None or m.start() - last >= QUOTE_GAP):
                    last = m.start()
                    quotes.append({"sec": key, "sec_ko": SEC_KO.get(key, key),
                                   "word": m.group(0),
                                   "quote": S.quote_at(txt, m.start(), m.end(), want=170)})
        out[label] = {"n": n, "quotes": quotes}
    return out


def verdict_of(mem_n, fnd_n):
    """양쪽이면 '양쪽', 한쪽이면 그쪽, 없으면 '미확인'(0이 아니라 모름이다)."""
    if mem_n and fnd_n:
        return "양쪽"
    if mem_n:
        return "메모리"
    if fnd_n:
        return "비메모리·파운드리"
    return "미확인"


def build(quarter=None, only=None):
    uni = load_asset("universe.json")["rows"]
    scan = load_asset("scan.json")
    quarter = quarter or scan.get("quarter") or "2026Q2"
    verdict = {r["stock"]: r.get("verdict") for r in scan["rows"]}
    members = [r for r in uni
               if verdict.get(r["stock"]) == "편입" or r.get("source") == "지정"]

    rows, dist, no_cache = [], {}, 0
    for rec in sorted(members, key=lambda r: r["stock"]):
        st = rec["stock"]
        if only and st not in only:
            continue
        got = sections_of_cache(st, quarter)
        if not got:
            no_cache += 1
            continue
        secs, rcp, title = got
        h = hits(secs)
        v = verdict_of(h["mem"]["n"], h["fnd"]["n"])
        dist[v] = dist.get(v, 0) + 1
        rows.append({"stock": st, "name": rec["name"], "rcpNo": rcp, "title": title,
                     "quarter": quarter, "verdict": v,
                     "mem": h["mem"], "fnd": h["fnd"],
                     "sections": sorted(k for k in SECTIONS if secs.get(k))})
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "quarter": quarter,
            "n": len(rows), "members": len(members), "no_cache": no_cache,
            "dist": dist, "rows": rows,
            "note": "정기보고서 **II-2 주요제품·II-4 매출실적 절에 적힌 낱말**이다. "
                    "매출 비중이 아니고, 산업 전망 문단(사업의 개요·기타)은 그 회사의 "
                    "노출이 아니므로 세지 않는다. 낱말이 없으면 '미확인'이다."}


def _show(d):
    for r in d["rows"]:
        if r["verdict"] == "미확인":
            continue
        print("%-7s %-16s %-12s 메모리 %-3d 비메모리 %-3d"
              % (r["stock"], r["name"][:16], r["verdict"], r["mem"]["n"], r["fnd"]["n"]))
        for side in ("mem", "fnd"):
            for q in r[side]["quotes"][:1]:
                print("     %s [%s] %s" % ("M" if side == "mem" else "F",
                                           q["sec_ko"], q["quote"][:120]))


def main():
    ap = argparse.ArgumentParser(description="II-2·II-4 절의 메모리/비메모리 낱말 → 노출 표시")
    ap.add_argument("--write", action="store_true", help="assets/exposure.json 갱신")
    ap.add_argument("--quarter")
    ap.add_argument("--only", help="종목코드 쉼표")
    ap.add_argument("--show", action="store_true", help="인용까지 사람이 읽는 형태로")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    d = build(quarter=a.quarter, only=only)
    print("%d사 판정 · %s · 캐시 없음 %d사"
          % (d["n"], json.dumps(d["dist"], ensure_ascii=False), d["no_cache"]),
          file=sys.stderr)
    if a.show:
        _show(d)
    if a.write:
        write_asset("exposure.json", d)
        print("→ %s" % os.path.join(ASSETS, "exposure.json"), file=sys.stderr)


if __name__ == "__main__":
    main()
