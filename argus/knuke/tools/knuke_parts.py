#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_parts — 발전소 인포그래픽(parts.html).

가압경수로와 LNG 복합발전의 원리를 설비 일러스트와 분리된 열·증기·전기 경로로 그린다.
발전원을 고르면 그 실루엣이 열리고, 부품 영역(원자로·증기발생기·터빈·보일러·계측제어·변전…)을
누르면 그 영역의 부품 소분류와 **그 기자재를 만드는 상장사**가 오른쪽 패널에 열린다.

부품 분류는 규칙(계약명·정기보고서 본문·KIND 문구의 낱말)이라 근거를 칩에 달아 둔다(COMMON §0-1).
회사 페이지의 부품 칩은 `parts.html#NSSS.SG` 로 들어온다 — 해시로 그 소분류를 연다.

    python3 knuke_parts.py
"""
import argparse
import collections
import os
import sys

from knuke_lib import (E, KNUKE, TABLE_JS, atomic_write, json_for_html, load_asset, page)
from knuke_universe import load as load_universe
import knuke_suppliers

SRC_KO = {"contract": "계약명", "body": "정기보고서 본문", "kind": "KIND 주요제품"}


def cat_index(sup):
    idx = collections.defaultdict(list)
    for co in sup.get("cos", []):
        for h in co["cats"]:
            idx[h["cat"]].append({
                "stock": co["stock"], "nm": co["nm"], "role": co["role"],
                "src": h["src"], "kw": h["kw"], "prod": (co["prod_raw"] or "")[:50],
                "primes": [{"nm": p["nm"], "stock": p["stock"], "basis": p["basis_ko"]}
                           for p in co["primes"][:3]]})
    for v in idx.values():
        v.sort(key=lambda c: ({"contract": 0, "body": 1, "kind": 2}[c["src"]], c["nm"]))
    return idx


def build(data):
    ui_tools = os.path.abspath(os.path.join(KNUKE, '..', 'ui', 'tools'))
    if ui_tools not in sys.path:
        sys.path.insert(0, ui_tools)
    from power_diagrams import markup, plant_payload
    idx = cat_index(data['sup'])
    pages = sorted({c['stock'] for rows in idx.values() for c in rows
                    if os.path.isfile(os.path.join(KNUKE, c['stock'], 'index.html'))})
    payload = plant_payload(data['tax'], idx, pages)
    n_co = len({c['stock'] for rows in idx.values() for c in rows})
    body = markup(payload, '열이 전기가 되는 과정',
                  '설비를 누르면 그 역할과 하위 부품, 연결 기업이 펼쳐집니다. 원전과 LNG 복합발전의 흐름을 비교해 보세요.',
                  [('발전 방식', 2), ('부품 소분류', len(data['tax']['cats'])), ('연결 상장사', n_co)])
    return page('발전소 인포그래픽 — 원전·LNG 복합', body, depth=0,
                h1='발전소 인포그래픽',
                nav=(('허브', 'index.html'), ('전력망 밸류체인', '../kgrid/grid.html'), ('← ARGUS', '../index.html')),
                crumbs=(('ARGUS', '../index.html'), ('한국원전·발전기자재', 'index.html'), ('발전소 인포그래픽', None)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", default=True)
    ap.parse_args()
    data = {"tax": load_asset("parts_taxonomy.json"), "svg": load_asset("svg_regions.json"),
            "sup": knuke_suppliers.load(), "uni": load_universe()}
    atomic_write(os.path.join(KNUKE, "parts.html"), build(data))
    idx = cat_index(data["sup"])
    print("parts.html · 소분류 %d(회사 붙은 것 %d) · 연결 기업 %d"
          % (len(data["tax"]["cats"]), sum(1 for c in data["tax"]["cats"] if idx.get(c["id"])),
             len({c["stock"] for rows in idx.values() for c in rows})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
