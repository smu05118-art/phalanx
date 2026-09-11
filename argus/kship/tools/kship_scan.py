#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_scan — 모집단 확장 탐색. KIND 제품 문구가 짧아('SCR촉매', '자유형단조품') 조선 공급망이
보이지 않는 상장사를 **정기보고서 II 절 본문**으로 찾는다.

  1) 후보 풀: KIND 전 상장사 중 제품 문구가 기자재 어휘(단조·밸브·촉매·케이블·도료…)에 걸리고
     조선과 무관한 업종(자동차·의약·금융…)이 아닌 회사 + 지정 후보(EXTRA). 이미 모집단이면 제외.
  2) 증거: kship_suppliers.collect_one 으로 II 절(제품·매출·개요)을 읽어 조선 낱말 횟수(marine_hits)와
     조선사 언급(mentions)을 센다. DART 는 프로세스 하나로 순차.
  3) 승격(fail-closed): 조선사 언급 합 ≥ 2 **또는** 조선 낱말 ≥ 8. 근거를 문장으로 남긴다.
     나머지는 '검토·제외'로 남겨 커버리지 페이지에 보인다(근거 없이 이름으로 넣지 않는다).

    python3 kship_scan.py --scan [--quarter 2026Q2]     # → assets/universe_probe.json
그 뒤 kship_universe.py --write 가 universe_probe.json 의 승격분을 '탐색' 출처로 모집단에 넣는다.
"""
import argparse
import json
import re
import sys
import time

from kship_lib import load_asset, write_asset
from kship_universe import _get, KIND_URL, parse_kind, _NOT_SUPPLY
import kship_suppliers as sup

POOL = re.compile(r"단조|주강|주물|밸브|피팅|이음쇠|펌프|압축기|감속기|기어|엔진|실린더|크랭크|촉매|SCR|스크러버|탈질|보냉|단열|"
                  r"도료|페인트|용접|케이블|전선|배전반|수배전|조명|크레인|윈치|압력용기|열교환기|탱크|강관|후판|형강|선재|항해|"
                  r"통신장비|레이더|센서|소화|소방|환경장비|평형수|배기가스|발전기|전동기|모터|베어링|가스켓|호스|유압|공압|제어반|"
                  r"계측|계장|안테나|위성|추진|블록|철구조물|구조용|의장|판넬|패널|해치|앵커|체인|로프|와이어|파스너|절연|축전지|"
                  r"배터리|연료전지|수소|암모니아|LNG|가스|냉동|공조|담수|폐수|오수|소각|필터|여과|방산|함정|무기|레저|보트|요트", re.I)
EXCL = re.compile(r"자동차|의약|반도체|소프트웨어|금융|은행|보험|증권|음식|식료|음료|섬유|의복|가죽|신발|부동산|도매|소매|운송|건설업|"
                  r"출판|방송|통신업|숙박|교육|오락|게임|광고|화장품|담배|농업|어업|광업|전기 공급|가스 공급|수도")
# 제품 문구로는 못 잡지만 조선 공급망일 수 있어 반드시 검토할 후보(근거는 프로브가 확인)
EXTRA = {"272210": "한화시스템 — 함정 전투체계", "443060": "HD현대마린솔루션 — 선박 AM·개조", "298040": "효성중공업 — 선박용 변압기·전동기?",
         "187790": "나노 — 선박용 SCR 탈질촉매"}
PROMOTE_MENTIONS = 2
PROMOTE_HITS = 8


def pool(recs, universe):
    uni = {r["stock"] for r in universe}
    out = []
    for r in recs:
        if r["stock"] in uni:
            continue
        if r["stock"] in EXTRA or (POOL.search(r["product"] or "") and not EXCL.search(r["industry"] or "")
                                   and r["industry"] not in _NOT_SUPPLY):
            out.append(r)
    return out


def role_for(r, d):
    p = (r["product"] or "") + " " + " ".join(d.get("marine_terms", {}).keys())
    if "1차 철강" in (r["industry"] or ""):
        return "steel"
    if re.search(r"엔진", r["product"] or "") and re.search(r"선박|박용", p):
        return "engine"
    return "equip"


def scan(quarter, log=sys.stderr):
    recs = parse_kind(_get(KIND_URL))
    universe = load_asset("universe.json")["rows"]
    cands = pool(recs, universe)
    log.write("후보 %d사 (모집단 %d 제외)\n" % (len(cands), len(universe)))
    promoted, rejected, failed = {}, [], []
    for i, r in enumerate(cands, 1):
        try:
            d = sup.collect_one(r, quarter)
        except Exception as e:                                   # 일시 실패 — 캐시하지 않고 다음으로
            failed.append({"stock": r["stock"], "name": r["name"], "err": str(e)[:80]})
            log.write("[warn] %s %s %s\n" % (r["stock"], r["name"], e))
            time.sleep(2)
            continue
        hits = d.get("marine_hits", 0)
        ment = d.get("mentions") or {}
        ok = d.get("ok") and (sum(ment.values()) >= PROMOTE_MENTIONS or hits >= PROMOTE_HITS)
        row = {"stock": r["stock"], "name": r["name"], "industry": r["industry"], "product": r["product"],
               "hits": hits, "terms": d.get("marine_terms", {}), "mentions": ment, "rcp": d.get("rcp"), "note": d.get("note", "")}
        if ok:
            reason = "탐색 — %s 본문: 조선 낱말 %d회(%s)%s%s" % (
                d.get("title", "정기보고서"), hits, ", ".join("%s %d" % kv for kv in list(row["terms"].items())[:3]),
                (" · 조선사 언급 %s" % json.dumps(ment, ensure_ascii=False)) if ment else "",
                (" · " + EXTRA[r["stock"]]) if r["stock"] in EXTRA else "")
            promoted[r["stock"]] = dict(row, role=role_for(r, d), reason=reason)
        else:
            rejected.append(row)
        log.write("%3d/%d %s %-14s hits=%-3d ment=%s %s\n" % (i, len(cands), r["stock"], r["name"][:14], hits, ment or "-", "승격" if ok else ""))
        log.flush()
    out = {"quarter": quarter, "scanned": time.strftime("%Y-%m-%d"), "pool": len(cands),
           "rule": "조선사 언급 ≥ %d 또는 조선 낱말 ≥ %d" % (PROMOTE_MENTIONS, PROMOTE_HITS),
           "promoted": promoted, "rejected": sorted(rejected, key=lambda x: -x["hits"]), "failed": failed}
    write_asset("universe_probe.json", out)
    log.write("승격 %d · 제외 %d · 실패 %d → assets/universe_probe.json\n" % (len(promoted), len(rejected), len(failed)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--quarter", default="2026Q2")
    a = ap.parse_args()
    if a.scan:
        scan(a.quarter)


if __name__ == "__main__":
    sys.exit(main())
