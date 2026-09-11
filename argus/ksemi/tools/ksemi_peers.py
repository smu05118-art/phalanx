#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_peers — 상장사가 **다른 상장사 이름을 본문에서 어떻게 부르는가**를 읽는다.

## 왜 필요한가

회사 화면의 「같은 공정의 부품·부분품사」는 공정 단계–부품 **사전**으로 이은 것이다
(HANDOFF §3-5). 납품 관계가 아니고, 그렇게 적혀 있다. 그런데 정기보고서 II절 본문에는
회사들이 **서로의 이름을 직접 적어 둔다**. 그 문장을 읽으면 사전이 못 주는 것이 나온다.

  · 코스텍시스템 — *"주요 고객사로는 삼성전자, SK하이닉스, **원익IPS**, Tokyo Electron(TEL) …"*
  · 뉴파워프라즈마 — *"Dry Etch 공정 장비 제작사로 국내업체는 **주성엔지니어링, 원익IPS,
    세메스, 피에스케이** …"* (자기 RF 제너레이터가 들어가는 장비를 만드는 회사들)
  · 씨엠티엑스 — *"구분 경쟁사 After Market(공정용 부품 제조사) **월덱스**, 케이씨파츠텍 …"*
  · 하나마이크론 — *"주요 종속회사인 **하나머티리얼즈(주)**"*

같은 '언급'이어도 셋은 전혀 다른 관계다. 그래서 **관계를 문장에서 분류**하고, 분류의
근거가 된 낱말(`cue`)과 **원문 인용을 같이 남긴다**. 분류가 안 되면 `미분류`다 —
지어내지 않는다.

## 관계 등급

| kind | 뜻 | 단서 낱말 |
|---|---|---|
| `계열` | 종속·관계기업·계열회사 | 종속회사·연결대상·관계기업·계열회사·지분 |
| `경쟁` | 경쟁사 | 경쟁사·경쟁업체·경쟁관계·과점·시장점유율 |
| `업체나열` | 같은 문장의 업체 목록 — 경쟁사일 수도, 전방 장비사일 수도 있다 | 제작사·생산업체·공급하고 있는 업체 |
| `고객` | 그 회사에 판다(고객·거래처·수주) | 고객사·주요 거래처·매출처·납품·수주 |
| `미분류` | 이름은 나오는데 관계를 말하지 않는다 | — |

**'공급'은 양쪽에 다 나온다.** *"국내에 Test Handler를 **공급하고 있는 업체**는 미래산업(주),
(주)제이티, (주)테크윙"*(미래산업)은 고객이 아니라 경쟁사 목록이고, *"장비 제작사는 국내의
원익 IPS, 주성엔지니어링, 테스, 유진테크"*(뉴파워프라즈마)는 **자기 RF 제너레이터가 들어가는
장비를 만드는 회사들**이다. 둘을 가르는 표시는 **목록에 자기 이름이 있는가** 하나뿐이다 —
`classify` 참조. 가르지 못하면 `업체나열`로 남기고 원문을 화면에 싣는다.

## 이름 경계의 덫 (원문에서 실측)

  · `3S`(060310) — RF머트리얼즈 본문의 **`3S-Photonics`** 가 걸렸다. 그래서 경계 문자에
    **하이픈을 넣는다**(`3S-`·`-3S` 는 다른 이름이다).
  · `테스`(095610) — `테스트`·`유니테스트`·`두산테스나` 안에 들어 있다. 한글 경계로 막힌다.
  · `피에스케이`(319660) ↔ `피에스케이홀딩스`(031980) — 경계가 없으면 홀딩스 언급이 전부
    피에스케이로 샌다. 긴 이름을 먼저 맞춰 본다.
  · `미코`(059090) — `미코세라믹스`·`미코하이테크`(자회사)에 묻힌다. 경계로 막고, 계열
    문맥이면 `계열`로 분류된다.

## 수집하지 않는다

**DART를 두드리지 않는다.** `ksemi_scan.py` 가 이미 받아 둔 II절 캐시(`assets/cache/
sec_*.html`)만 읽는다 — 스캔이 돈 회사면 이 모듈은 언제든 공짜로 다시 돌릴 수 있다.

    python3 ksemi_peers.py            # 표로 본다(쓰지 않는다)
    python3 ksemi_peers.py --write    # assets/peers.json
    python3 ksemi_peers.py --only 264660 --show
"""
import argparse
import json
import os
import re
import sys
import time

from ksemi_lib import ASSETS, load_asset, write_asset
import ksemi_scan as S

# 관계 단서 — (kind, 정규식). 거리가 같을 때만 이 순서로 가른다.
CUES = [
    ("계열", r"종속\s*회사|종속기업|연결\s*대상|연결\s*회사|관계\s*기업|계열\s*회사|자회사|"
             r"지분\s*(?:을|율|취득)|합작|인적\s*분할|물적\s*분할|분할\s*(?:전|이후|신설|존속)|"
             r"존속\s*법인|신설\s*법인"),
    ("경쟁", r"경쟁\s*(?:사|업체|관계|자|구도)|과점|시장\s*점유|점유율"),
    ("업체나열", r"제작사(?!업)|제조사는|제조\s*업체|공급하고\s*있는\s*업체|생산업체|"
                 r"업체(?:는|로는|로서|들)|메이커"),
    ("고객", r"고객\s*(?:사|은|으로)|주요\s*거래처|거래처|매출처|판매처|납품(?:하|처|한)|"
             r"수주를?\s*받|공급하고\s*있으며|공급처|벤더|Vendor"),
]
CUE_RX = [(k, re.compile(p, re.I)) for k, p in CUES]
WINDOW = 400                       # 단서를 찾는 좌우 문맥 폭(글자). 표 한 칸·문단 하나쯤.


# 이름 뒤에 붙는 조사. 오른쪽 경계를 '한글이면 무조건 아니다'로 두면 **「테크윙의」·
# 「원익IPS는」이 통째로 사라진다**. 그래서 조사만 예외로 연다. `나`는 넣지 않았다 —
# 「테스」+「나」가 두산**테스나**를 먹는다(티에스이 본문에 실제로 나온다).
PARTICLES = ("에서|에게|으로|부터|까지|보다|와의|과의|은|는|이|가|을|를|와|과|의|에|도|로|만|등")
_BOUND_L = r"(?<![가-힣A-Za-z0-9\-])"
_BOUND_R = r"(?![A-Za-z0-9\-])(?=$|[^가-힣]|(?:%s)(?![가-힣]))" % PARTICLES
_RUN = re.compile(r"[가-힣]+|[A-Za-z0-9]+|[^가-힣A-Za-z0-9]+")

# 회사 이름이 **보통명사**이기도 한 종목. 이 이름은 법인 표시가 붙었을 때만 회사로 센다.
# 미래산업(025560) — 씨앤지하이테크 *"유비쿼터스 시대 등의 **미래산업**과 더불어"*, 주성
# 엔지니어링 *"…미래산업…"* 처럼 산업 일반을 가리키는 말로 본문에 흔하게 나온다.
NEEDS_MARK = {"025560"}
_MARK = re.compile(r"\(\s*주\s*\)|㈜|주식회사")
MARK_NEAR = 6                      # 이름 바로 앞뒤 — 「미래산업(주)」·「(주)미래산업」


def name_rx(name):
    """회사 이름 정규식.

    셋을 동시에 지켜야 한다(전부 원문에서 밟았다).
      ① 경계에 **하이픈을 넣는다** — `3S-Photonics` 는 우리 `3S`(060310)가 아니다.
      ② 한글/영문이 바뀌는 자리에 **공백을 허용한다** — 뉴파워프라즈마는 같은 문단에서
         `원익IPS` 와 `원익 IPS` 를 섞어 쓴다.
      ③ 뒤따르는 **조사는 이름의 일부가 아니다** — 「테크윙의」·「원익IPS는」.
    """
    pat = r"\s*".join(re.escape(x) for x in _RUN.findall(name))
    return re.compile(_BOUND_L + pat + _BOUND_R)


def classify(text, at, self_rx=None):
    """언급 위치 좌우 문맥 → (kind, cue). 단서가 없으면 ('미분류', '').

    **가장 가까운 단서가 이긴다.** 종류별로 순서대로 보면 멀리 있는 `합작`·`종속회사`가
    바로 옆의 `경쟁사`를 이겨 버린다(티에스이·미코 실측). 거리가 같을 때만 위 표의
    순서로 가른다.

    `업체나열`(「… 장비 제작사는 국내의 A, B, C」)은 **경쟁사 목록일 수도, 자기 부품이
    들어가는 전방 장비사 목록일 수도 있다.** 원문에서 둘을 가르는 표시는 하나뿐이다 —
    **그 목록에 자기 이름(또는 '당사')이 들어 있는가**.

      · 미래산업 *"Test Handler를 공급하고 있는 업체는 **미래산업(주)**, (주)제이티,
        (주)테크윙 …"* → 자기가 목록 안에 있다 = 경쟁사 목록.
      · 뉴파워프라즈마 *"장비 제작사는 국내의 원익 IPS, 주성엔지니어링, 테스, 유진테크"*
        → 자기 이름이 없다. 이 회사는 RF 제너레이터를 만들어 저 장비사에 넣는다 —
        경쟁사라고 적으면 틀린다. 그래서 `업체나열`로 남기고 화면이 원문을 보여 준다.
    """
    a, b = max(0, at[0] - WINDOW), min(len(text), at[1] + WINDOW)
    ctx, rel = text[a:b], (at[0] - a, at[1] - a)
    best = None
    for prio, (kind, rx) in enumerate(CUE_RX):
        for m in rx.finditer(ctx):
            d = 0 if m.start() < rel[1] and rel[0] < m.end() else \
                min(abs(m.start() - rel[1]), abs(rel[0] - m.end()))
            if best is None or (d, prio) < (best[0], best[1]):
                best = (d, prio, kind, re.sub(r"\s+", " ", m.group(0)))
    if not best:
        return "미분류", ""
    kind, cue = best[2], best[3]
    if kind == "업체나열" and _in_list(ctx, rel, self_rx):
        return "경쟁", cue                      # 목록 안에 자기가 있다 — 경쟁사 목록이다
    return kind, cue


def _sentence(ctx, rel):
    """언급이 들어 있는 **문장**. 목록 소속은 문장을 넘지 않는다.

    그린리소스 *"…원익IPS가 2위, 3위를 다투고 있습니다. **당사는** 디스플레이 식각…"* —
    `당사`가 가깝다는 것만 보면 이 회사를 원익IPS의 경쟁사로 적게 된다. 문장이 끊겼으므로
    같은 목록이 아니다. 반대로 마이크로투나노 *"…공급하는 **당사** 이 외에 티에스이…"* 는
    한 문장이라 같은 목록이다.
    """
    a = 0
    for m in S._SENT_END.finditer(ctx, 0, rel[0]):
        a = m.end()
    m = S._SENT_END.search(ctx, rel[1])
    return ctx[a:m.start() if m else len(ctx)]


def _in_list(ctx, rel, self_rx):
    """그 업체 목록 안에 자기가 들어 있나 — **같은 문장 안**의 자기 이름 또는 `당사`."""
    sent = _sentence(ctx, rel)
    return bool((self_rx and self_rx.search(sent)) or "당사" in sent)


def text_of_cache(stock, quarter):
    """스캔 캐시의 II절 → 평문 한 덩어리. 캐시가 없으면 None(받으러 가지 않는다)."""
    mp = S._meta_path(stock, quarter)
    if not os.path.exists(mp):
        return None
    with open(mp, encoding="utf-8") as f:
        meta = json.load(f)
    parts = []
    for key in (meta.get("sections") or {}):
        p = S._sec_path(meta["rcpNo"], key)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                parts.append(S.text_of(f.read()))
    if not parts:
        return None
    return re.sub(r"\s+", " ", "\n".join(parts)), meta["rcpNo"], meta.get("title", "")


def build(quarter=None, only=None):
    """캐시 전수 → 언급 행. 반환 {quarter, n, rows, edges}."""
    uni = load_asset("universe.json")["rows"]
    scan = load_asset("scan.json")
    quarter = quarter or scan.get("quarter") or "2026Q2"
    by_stock = {r["stock"]: r for r in uni}
    verdict = {r["stock"]: r.get("verdict") for r in scan["rows"]}
    members = [r for r in uni
               if verdict.get(r["stock"]) == "편입" or r.get("source") == "지정"]
    # 긴 이름을 먼저 본다 — 피에스케이홀딩스가 피에스케이로 새지 않게.
    targets = sorted(members, key=lambda r: -len(r["name"]))
    rx = {r["stock"]: name_rx(r["name"]) for r in targets}

    rows, edges = [], []
    for rec in sorted(members, key=lambda r: r["stock"]):
        st = rec["stock"]
        if only and st not in only:
            continue
        got = text_of_cache(st, quarter)
        if not got:
            continue
        blob, rcp, title = got
        seen = []                                  # 이미 맞춘 구간 — 긴 이름이 이긴다
        ms = []
        for t in targets:
            if t["stock"] == st:
                continue
            spans = [m.span() for m in rx[t["stock"]].finditer(blob)]
            spans = [s for s in spans if not any(s[0] < e and a < s[1] for a, e in seen)]
            if t["stock"] in NEEDS_MARK:           # 보통명사 이름은 법인 표시가 있어야 회사다
                spans = [s for s in spans
                         if _MARK.search(blob[max(0, s[0] - MARK_NEAR):s[1] + MARK_NEAR])]
            if not spans:
                continue
            seen.extend(spans)
            kind, cue = classify(blob, spans[0], rx[st])
            ms.append({"stock": t["stock"], "name": t["name"], "n": len(spans),
                       "kind": kind, "cue": cue,
                       "quote": S.quote_at(blob, *spans[0], want=200)})
            edges.append({"from": st, "to": t["stock"], "kind": kind, "n": len(spans)})
        if ms:
            ms.sort(key=lambda m: (-m["n"], m["name"]))
            rows.append({"stock": st, "name": rec["name"], "rcpNo": rcp, "title": title,
                         "mentions": ms})
    kinds = {}
    for e in edges:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "quarter": quarter,
            "n": len(rows), "n_edges": len(edges), "kinds": kinds,
            "members": len(members), "rows": rows,
            "note": "정기보고서 II절 본문의 **이름 언급**이다. 납품 계약이 아니다 — "
                    "관계는 문장의 단서 낱말로 분류하고 원문을 같이 싣는다.",
            "_by_target": _reverse(rows, by_stock)}


def _reverse(rows, by_stock):
    """역참조 — 어느 회사가 나를 어떻게 부르나."""
    out = {}
    for r in rows:
        for m in r["mentions"]:
            out.setdefault(m["stock"], []).append(
                {"stock": r["stock"], "name": r["name"], "kind": m["kind"],
                 "n": m["n"], "quote": m["quote"]})
    for k in out:
        out[k].sort(key=lambda m: (-m["n"], m["name"]))
    return out


def _show(d, only=None):
    for r in d["rows"]:
        if only and r["stock"] not in only:
            continue
        print("── %s %s (%s %s)" % (r["stock"], r["name"], r["rcpNo"], r["title"]))
        for m in r["mentions"]:
            print("   [%s] %s ×%d %s" % (m["kind"], m["name"], m["n"],
                                         ("· 단서 '%s'" % m["cue"]) if m["cue"] else ""))
            print("      “%s”" % m["quote"][:150])


def main():
    ap = argparse.ArgumentParser(description="II절 본문의 상장사 이름 언급 → 관계 분류")
    ap.add_argument("--write", action="store_true", help="assets/peers.json 갱신")
    ap.add_argument("--quarter")
    ap.add_argument("--only", help="종목코드 쉼표")
    ap.add_argument("--show", action="store_true", help="인용까지 사람이 읽는 형태로")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    d = build(quarter=a.quarter, only=only)
    print("언급을 남긴 회사 %d사 · 간선 %d개 · %s"
          % (d["n"], d["n_edges"], json.dumps(d["kinds"], ensure_ascii=False)), file=sys.stderr)
    if a.show:
        _show(d, only)
    if a.write:
        write_asset("peers.json", d)
        print("→ %s" % os.path.join(ASSETS, "peers.json"), file=sys.stderr)


if __name__ == "__main__":
    main()
