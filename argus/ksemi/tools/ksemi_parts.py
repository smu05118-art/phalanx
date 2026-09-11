#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ksemi_parts — 팹 공정 흐름 인포그래픽(`argus/ksemi/parts.html`).

웨이퍼 투입 → 포토 → 식각 → 증착 → 이온주입 → 열처리 → CMP → 세정 → 계측 → 이송/진공
(여기까지 전공정, 실제로는 수십 회 반복) → 테스트 → 패키징 순으로 단계를 그린다. 단계를
누르면 ① 그 단계 장비를 만드는 **편입 상장사**, 한 번 더 누르면 ② 그 장비의 **부품**
(챔버·ESC·샤워헤드·쿼츠·세라믹·펌프·RF)과 **부품사**로 들어간다. 전공정/후공정 토글.

구조는 `argus/kship/tools/kship_parts.py`(선박 단면 → 부품 영역 → 기자재사)를 본떴다.
그림과 분류축은 반도체 것으로 새로 만들었다 — 조선의 '영역 = 배의 위치'가 여기서는
'단계 = 팹 흐름의 시간'이고, 2층(대분류/소분류)이 아니라 **단계 → 부품** 2단 진입이다.

## 무엇을 싣고 무엇을 안 싣는가 (COMMON.md §0)

* **모집단 = `scan.json` 의 `편입`** 만 탭 구성원으로 싣는다(배제·보류·오류는 이름을 싣지
  않고 수만 적는다). `stage_tags.json` 에는 편입이 아닌 회사에도 태그가 붙어 있다.
* 회사 한 줄마다 **근거를 같이** 싣는다 — KIND 주요제품 문구(`product`) · 스펙 지정 사유
  (`seed`) · 정기보고서 II절 본문(`scan` 의 낱말·횟수·원문 인용).
* **근거가 없으면 분류하지 않는다.** 편입인데 단계 태그가 없는 회사는 지어서 붙이지 않고
  「단계 미분류」로 따로 보이고, 본문 힌트가 있으면 '분류 아님'이라 적고 힌트만 보인다.
* 색은 `palette.json` 슬롯 → 단계에 **고정**(필터로 줄어도 재배색하지 않는다).
* `reports.json` 은 **있으면** 단계별 수주잔고 합을 더한다. 없으면 회사 수만 — 0으로
  채우지 않는다(수집이 아직 안 끝난 것과 잔고가 0인 것은 다르다).

## 입력 (모두 이미 만들어진 것 — 여기서 다시 만들지 않는다)

    assets/stages.json      13단계(label·flow_order·front_back·words·parts)
    assets/stage_tags.json  154종목 단계 태그(근거 낱말·출처)
    assets/scan.json        편입/배제/보류 판정 + 정기보고서 II절 본문 근거
    assets/palette.json     단계 고정색(8슬롯 → 13단계)
    assets/reports.json     (있으면) 종목별 kpi.backlog — 백만원

    python3 ksemi_parts.py            # 통계만 찍는 예행
    python3 ksemi_parts.py --write    # argus/ksemi/parts.html 생성
"""
import argparse
import collections
import json
import os
import re
import sys

from ksemi_lib import (ASSETS, E, KSEMI, TABLE_JS, atomic_write, fmt_eok, has_asset,
                       json_for_html, load_asset, page, slot_color)
import ksemi_scan as SCAN                       # 절 HTML → 평문(같은 규칙을 두 벌로 두지 않는다)

# 근거 출처 라벨 — stage_tags.evidence_source / 부품 매칭 출처.
SRC_KO = {"product": "KIND 주요제품 문구", "seed": "스펙 지정 사유",
          "scan": "정기보고서 II절 본문", "주요제품": "정기보고서 II-2 주요제품",
          "": "원문 근거 없음"}

# scan.json 의 단계 힌트 라벨 → stages.json 의 단계 키.
# scan 쪽 라벨(ksemi_scan.PATTERNS 의 두 번째 열)은 화면 표기이고 사전 키가 아니다.
# 힌트는 **분류가 아니라 힌트**로만 쓴다(태그가 없는 편입사를 어디서 찾아볼지 가리키는 용도).
HINT_MAP = {"포토": "photo", "식각": "etch", "증착": "depo", "이온주입": "implant",
            "열처리": "thermal", "CMP": "cmp", "세정": "clean", "계측검사": "metro",
            "이송진공": "handling", "테스트": "test", "패키징후공정": "pkg",
            "부품소재": "parts"}

FB_ALL, FB_FRONT, FB_BACK = "all", "front", "back"
FB_KO = {FB_FRONT: "전공정", FB_BACK: "후공정"}

# ── SVG 배치 ────────────────────────────────────────────────
NODE_W, NODE_H, COL_GAP = 150, 60, 16
X0 = 8
ROW_Y = {1: 70, 2: 176, 3: 282, 4: 400}
VIEW_W, VIEW_H = 1000, 496


def col_x(i):
    return X0 + i * (NODE_W + COL_GAP)


def _fb_key(fb):
    """단계/회사의 front_back 문자열 → 필터에서 걸리는 집합."""
    if fb == "전공정":
        return {FB_FRONT}
    if fb == "후공정":
        return {FB_BACK}
    if fb in ("공통", "전후공정 겸업"):
        return {FB_FRONT, FB_BACK}
    return set()


# ── 낱말 매칭 (부품 ↔ 회사) ─────────────────────────────────
# build_dicts 의 규칙을 그대로 따른다: 부분문자열로 보되 ① 단계 전체를 버리는 부정 낱말
# ② 그 자리만 버리는 부정 낱말(`링` ⊂ `모니터링`) ③ 약한 낱말은 반도체 문맥이 있을 때만.
# 사전(낱말·부정 낱말·약한 낱말)은 stages.json 에서 읽는다 — 여기서 새로 만들지 않는다.

def _find(tl, w):
    out, i = [], tl.find(w)
    while i >= 0:
        out.append((i, i + len(w)))
        i = tl.find(w, i + 1)
    return out


def match_words(text, words, rule, ctx_words, need_ctx=True):
    """`text` 에서 `words` 중 걸리는 낱말. `rule` 은 stages.json 의 한 단계(부정 낱말 출처).

    `need_ctx=False` 는 이미 반도체 본문에서 뽑힌 낱말(scan 의 evidence term)에 쓴다 —
    그 낱말 자체가 반도체 문맥에서 나온 것이라 문맥 낱말을 다시 요구하면 전부 떨어진다.
    """
    tl = (text or "").lower()
    if not tl:
        return []
    kind = rule["words"].get("not_words_kind") or {}
    for nw in kind.get("stage", []):
        if nw in tl:
            return []
    veto = []
    for nw in kind.get("span", []):
        veto += _find(tl, nw)
    weak = set(rule["words"].get("weak") or [])
    ctx = any(c in tl for c in ctx_words)
    out = []
    for w in words:
        if need_ctx and w in weak and not ctx:
            continue
        for s in _find(tl, w):
            if not any(v[0] <= s[0] and s[1] <= v[1] for v in veto):
                out.append(w)
                break
    return out


# ── 자료 모으기 ─────────────────────────────────────────────

PROD_MAX = 2500                 # 주요제품 절에서 읽을 글자 수. 표 머리 + 품목 줄이면 충분하다


def products_text(stock, quarter):
    """그 회사의 **II-2 「주요 제품 및 서비스」 절 원문**(평문). 캐시가 없으면 "".

    부품 이름은 KIND 40자 문구에도, 낱말 근거 인용에도 안 나오는 일이 흔하다 — 엔투텍의
    `CHAMBER, GATE VALVE`, 제이엔비의 `쿨링 트랩·매니폴드·게이트 밸브`, 포인트엔지니어링의
    `DIFFUSER·SUSCEPTOR·Face Plate` 는 **매출 구성표 안에만** 있다(2026 반기 실측).
    이 절은 '그 회사가 파는 물건'을 적는 곳이라 「만든다」의 근거로 쓸 수 있다 —
    장비사 본문에 나오는 '자기가 쓰는 부품' 이름과 다르다. 그래서 **부품사 풀에만** 쓴다.

    DART를 두드리지 않는다(ksemi_scan 이 받아 둔 절 캐시만 읽는다).
    """
    mp = os.path.join(ASSETS, "cache", "meta_%s_%s.json" % (stock, quarter))
    if not os.path.exists(mp):
        return ""
    try:
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        fp = os.path.join(ASSETS, "cache", "sec_%s_products.html" % meta["rcpNo"])
        if not os.path.exists(fp):
            return ""
        with open(fp, encoding="utf-8") as f:
            return re.sub(r"\s+", " ", SCAN.text_of(f.read()))[:PROD_MAX]
    except Exception:                                        # noqa: BLE001
        return ""                                            # 깨진 캐시는 없는 것으로 본다


def load_all():
    """인포그래픽이 쓰는 자료 한 벌. reports.json 은 있으면 쓰고 없으면 None."""
    st = load_asset("stages.json")
    tags = load_asset("stage_tags.json")
    scan = load_asset("scan.json")
    rep = load_asset("reports.json") if has_asset("reports.json") else None
    quarter = scan.get("quarter") or ""
    prod = {r["stock"]: products_text(r["stock"], quarter)
            for r in scan.get("rows", []) if r.get("verdict") == "편입"}
    return {"stages": st, "tags": tags, "scan": scan, "reports": rep, "prod": prod}


def backlog_by_stock(rep):
    """reports.json → {종목: 수주잔고(백만원)}. kpi.backlog 가 None 이면 담지 않는다."""
    out = {}
    for r in (rep or {}).get("rows", []):
        v = (r.get("kpi") or {}).get("backlog")
        if v is not None:
            out[r["stock"]] = {"backlog": v, "quarter": (r.get("kpi") or {}).get("backlog_quarter")}
    return out


def build(data):
    stages = data["stages"]["stages"]
    ctx_words = data["stages"].get("ctx_words") or []
    by_key = {s["key"]: s for s in stages}
    tags = {t["stock"]: t for t in data["tags"]["rows"]}
    scan = {r["stock"]: r for r in data["scan"]["rows"]}
    members = [r for r in data["scan"]["rows"] if r.get("verdict") == "편입"]
    member_ids = {r["stock"] for r in members}
    bl = backlog_by_stock(data["reports"])
    has_rep = data["reports"] is not None

    def scan_ev(stock, key):
        """그 회사의 정기보고서 II절 근거 중 이 단계로 매핑되는 것(가장 많이 나온 낱말)."""
        best = None
        for e in (scan.get(stock) or {}).get("evidence") or []:
            if HINT_MAP.get(e.get("stage") or "") != key:
                continue
            if best is None or (e.get("n") or 0) > (best.get("n") or 0):
                best = e
        if not best:
            return None
        return {"term": best.get("term") or "", "n": best.get("n"),
                "quote": (best.get("quote") or "")[:220]}

    # ① 단계 → 편입 상장사
    cos = collections.OrderedDict((s["key"], []) for s in stages)
    for r in members:
        t = tags.get(r["stock"])
        if not t:
            continue
        for s in t.get("stages") or []:
            if s["key"] not in cos:
                continue
            cos[s["key"]].append({
                "stock": t["stock"], "nm": t["name"], "fb": t.get("front_back") or "",
                "words": s.get("words") or [], "src": s.get("source") or t.get("evidence_source") or "",
                "ev": (t.get("evidence") or "")[:160], "primary": t.get("primary") == s["key"],
                "scan": scan_ev(t["stock"], s["key"]),
                "bl": bl.get(t["stock"], {}).get("backlog"),
                "blq": bl.get(t["stock"], {}).get("quarter"),
            })
    for k in cos:
        cos[k].sort(key=lambda c: (not c["primary"], -(c["bl"] or 0), c["nm"]))

    # ② 부품 ↔ 부품사. 후보는 ⓐ `parts`·`service` 로 태그된 편입사(부품사 풀)와
    #    ⓑ 그 단계로 태그된 회사다. ⓑ 를 넣는 이유는 원문이 그렇게 적혀 있어서다 —
    #    리노공업 「리노핀, 반도체 소켓」·티에스이 「Probe Card」·성우테크론 「리드프레임」·
    #    한미반도체 「반도체 후공정장비,반도체금형」처럼 그 단계 장비사가 그 단계의
    #    부품 자체를 제품으로 적는다. 어느 쪽 근거인지는 `role` 로 화면에 표시한다.
    prule = by_key["parts"]
    pool = []
    for r in members:
        t = tags.get(r["stock"])
        if t and any(s["key"] in ("parts", "service") for s in (t.get("stages") or [])):
            pool.append(t)
    pool_ids = {t["stock"] for t in pool}
    partcos, matched_any = {}, set()
    for s in stages:
        cand, seen_c = list(pool), set(pool_ids)
        for c in cos[s["key"]]:
            if c["stock"] not in seen_c:
                seen_c.add(c["stock"])
                cand.append(tags[c["stock"]])
        per = {}
        for p in s.get("parts") or []:
            rows = []
            for t in cand:
                prod = match_words(t.get("evidence"), p["words"], prule, ctx_words, need_ctx=True)
                hits = []
                # 본문 낱말은 **부품사 풀의 회사**에서, 그리고 scan 이 그 낱말을 '부품소재'로
                # 본 경우에만 받는다. 장비사의 본문에는 자기가 **쓰는** 부품 이름이 흔히
                # 나온다(브이엠의 ESC 14회는 식각기 안의 정전척이지 브이엠의 제품이 아니다) —
                # 그걸 받으면 「만든다」고 지어내는 셈이 된다.
                if t["stock"] in pool_ids:
                    # II-2 주요제품 절 — 부품 이름이 여기에만 있는 회사가 있다
                    pt = data["prod"].get(t["stock"]) or ""
                    for w in match_words(pt, p["words"], prule, ctx_words, need_ctx=False):
                        at = pt.lower().find(w.lower())
                        hits.append({"term": w, "n": None, "src": "주요제품",
                                     "quote": pt[max(0, at - 60):at + 160].strip()})
                    for e in (scan.get(t["stock"]) or {}).get("evidence") or []:
                        term = e.get("term") or ""
                        if HINT_MAP.get(e.get("stage") or "") != "parts":
                            continue
                        if match_words(term, p["words"], prule, ctx_words, need_ctx=False):
                            hits.append({"term": term, "n": e.get("n"), "quote": (e.get("quote") or "")[:220]})
                if not prod and not hits:
                    continue
                hits.sort(key=lambda h: -(h["n"] or 0))
                rows.append({"stock": t["stock"], "nm": t["name"], "words": prod,
                             "ev": (t.get("evidence") or "")[:160], "scan": hits[:2],
                             "src": t.get("evidence_source") or "",
                             "role": ("부품·공정서비스사" if t["stock"] in pool_ids
                                      else "이 단계 장비사")})
                if t["stock"] in pool_ids:
                    matched_any.add((s["key"], t["stock"]))
            rows.sort(key=lambda r_: (-max([h["n"] or 0 for h in r_["scan"]] or [0]), r_["nm"]))
            per[p["key"]] = rows
        partcos[s["key"]] = per

    # 부품 종류를 원문에서 특정하지 못한 부품사 — 지우지 않고 따로 보인다.
    unspec = [{"stock": t["stock"], "nm": t["name"], "ev": (t.get("evidence") or "")[:160],
               "src": t.get("evidence_source") or "",
               "scan": [{"term": e.get("term") or "", "n": e.get("n"),
                         "quote": (e.get("quote") or "")[:220]}
                        for e in ((scan.get(t["stock"]) or {}).get("evidence") or [])[:2]]}
              for t in pool if not any((k, t["stock"]) in matched_any for k in partcos)]
    unspec.sort(key=lambda r_: r_["nm"])

    # ③ 편입인데 단계 태그가 없는 회사 — 분류하지 않고 본문 힌트만.
    untagged = []
    for r in members:
        t = tags.get(r["stock"])
        if t and (t.get("stages") or []):
            continue
        hints = [h for h in (r.get("stage_hint") or []) if h in HINT_MAP]
        untagged.append({
            "stock": r["stock"], "nm": r["name"], "prod": (r.get("product") or "")[:120],
            "hints": [HINT_MAP[h] for h in hints],
            "ev": [{"term": e.get("term") or "", "n": e.get("n"),
                    "stage": HINT_MAP.get(e.get("stage") or ""),
                    "quote": (e.get("quote") or "")[:220]}
                   for e in (r.get("evidence") or [])[:3]],
        })
    untagged.sort(key=lambda r_: r_["nm"])
    hint_idx = collections.defaultdict(list)
    for u in untagged:
        for k in u["hints"]:
            hint_idx[k].append({"stock": u["stock"], "nm": u["nm"], "prod": u["prod"],
                                "ev": [e for e in u["ev"] if e["stage"] == k][:1]})

    # ④ 단계별 집계(전체·전공정·후공정) — 필터를 바꿔도 색은 그대로, 숫자만 바뀐다.
    agg = {}
    for s in stages:
        a = {}
        for f in (FB_ALL, FB_FRONT, FB_BACK):
            sel = [c for c in cos[s["key"]] if f == FB_ALL or f in _fb_key(c["fb"])]
            known = [c for c in sel if c["bl"] is not None]
            a[f] = {"n": len(sel),
                    "bl": (sum(c["bl"] for c in known) if (has_rep and known) else None),
                    "nbl": len(known), "nmiss": len(sel) - len(known)}
        agg[s["key"]] = a
    return {"stages": stages, "by_key": by_key, "cos": cos, "partcos": partcos,
            "unspec": unspec, "untagged": untagged, "hints": dict(hint_idx), "agg": agg,
            "members": members, "member_ids": member_ids, "has_rep": has_rep,
            "bl": bl, "pool": pool, "tags": tags, "scan": scan}


# ── SVG ─────────────────────────────────────────────────────

def layout(stages):
    """단계 → SVG 좌표. flow_order 가 배치를 정한다(사전이 바뀌면 그림도 따라 바뀐다)."""
    flow = sorted([s for s in stages if s.get("flow_order")], key=lambda s: s["flow_order"])
    front = [s for s in flow if s["front_back"] != "후공정"]
    back = [s for s in flow if s["front_back"] == "후공정"]
    off = [s for s in stages if not s.get("flow_order")]
    pos = {}
    for i, s in enumerate(front[:5]):                       # 1행: 좌→우, col1..col5
        pos[s["key"]] = (col_x(i + 1), ROW_Y[1])
    rest = front[5:]
    for i, s in enumerate(rest):                            # 2행: 우→좌(뱀 배치)
        pos[s["key"]] = (col_x(5 - i), ROW_Y[2])
    for i, s in enumerate(back):                            # 3행: 후공정
        pos[s["key"]] = (col_x(i), ROW_Y[3])
    for i, s in enumerate(off):                             # 4행: 흐름 밖(부품·서비스)
        pos[s["key"]] = (col_x(1 + 2 * i), ROW_Y[4])
    return pos, front, back, off


def _arrow(x1, y1, x2, y2, dashed=False, label=None):
    cls = "flow dash" if dashed else "flow"
    out = '<path class="%s" d="M %g,%g L %g,%g" marker-end="url(#ah)"/>' % (cls, x1, y1, x2, y2)
    if label:
        out += '<text class="sm" x="%g" y="%g" text-anchor="middle">%s</text>' % (
            (x1 + x2) / 2.0, min(y1, y2) - 6, E(label))
    return out


def svg(d):
    stages = d["stages"]
    pos, front, back, off = layout(stages)
    parts = []
    parts.append('<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
                 'markerHeight="6" orient="auto-start-reverse"><path d="M 0,1 L 9,5 L 0,9 z"/></marker></defs>')
    # 흐름 밖 띠
    parts.append('<rect class="band" x="%d" y="%d" width="%d" height="96" rx="10"/>' % (X0, ROW_Y[4] - 26, VIEW_W - 2 * X0))
    parts.append('<text class="sm" x="%d" y="%d">흐름 밖 — 장비의 부분품과 공정 서비스(모든 단계에 걸린다)</text>'
                 % (X0 + 12, ROW_Y[4] - 8))
    # 투입·출하(단계가 아니라 흐름의 끝 — 회사를 달지 않는다)
    for x, y, ko in ((col_x(0), ROW_Y[1], "웨이퍼 투입"), (col_x(len(back)), ROW_Y[3], "출하")):
        parts.append('<g class="term"><rect x="%d" y="%d" width="%d" height="%d" rx="9"/>'
                     '<text x="%d" y="%d" text-anchor="middle">%s</text></g>'
                     % (x, y, NODE_W, NODE_H, x + NODE_W // 2, y + NODE_H // 2 + 5, E(ko)))
    # 화살표 — 1행
    seq1 = [col_x(0)] + [pos[s["key"]][0] for s in front[:5]]
    for i in range(len(seq1) - 1):
        parts.append(_arrow(seq1[i] + NODE_W, ROW_Y[1] + NODE_H / 2.0, seq1[i + 1] - 3, ROW_Y[1] + NODE_H / 2.0))
    rest = front[5:]
    if rest:
        # 1행 끝(col5) → 2행 첫(col5): 수직
        parts.append(_arrow(col_x(5) + NODE_W / 2.0, ROW_Y[1] + NODE_H, col_x(5) + NODE_W / 2.0, ROW_Y[2] - 3))
        for i in range(len(rest) - 1):
            x1 = pos[rest[i]["key"]][0]
            x2 = pos[rest[i + 1]["key"]][0]
            parts.append(_arrow(x1, ROW_Y[2] + NODE_H / 2.0, x2 + NODE_W + 3, ROW_Y[2] + NODE_H / 2.0))
        last = rest[-1]
        lx = pos[last["key"]][0]
        # 전공정 반복(포토로 되돌아가는 점선)
        parts.append('<path class="flow dash" d="M %g,%g L %g,%g L %g,%g"/>'
                     % (lx + NODE_W / 2.0, ROW_Y[2], lx + NODE_W / 2.0, ROW_Y[2] - 22,
                        col_x(1) + NODE_W / 2.0, ROW_Y[2] - 22))
        parts.append('<path class="flow dash" d="M %g,%g L %g,%g" marker-end="url(#ah)"/>'
                     % (col_x(1) + NODE_W / 2.0, ROW_Y[2] - 22, col_x(1) + NODE_W / 2.0, ROW_Y[1] + NODE_H + 3))
        parts.append('<text class="sm" x="%g" y="%g" text-anchor="middle">전공정은 층마다 반복된다</text>'
                     % ((lx + col_x(1)) / 2.0 + NODE_W / 2.0, ROW_Y[2] - 27))
        if back:
            # 2행 끝 → 3행 첫(후공정)
            parts.append('<path class="flow" d="M %g,%g L %g,%g L %g,%g" marker-end="url(#ah)"/>'
                         % (lx, ROW_Y[2] + NODE_H / 2.0, col_x(0) + NODE_W / 2.0, ROW_Y[2] + NODE_H / 2.0,
                            col_x(0) + NODE_W / 2.0, ROW_Y[3] - 3))
    seq3 = [pos[s["key"]][0] for s in back] + [col_x(len(back))]
    for i in range(len(seq3) - 1):
        parts.append(_arrow(seq3[i] + NODE_W, ROW_Y[3] + NODE_H / 2.0, seq3[i + 1] - 3, ROW_Y[3] + NODE_H / 2.0))

    # 단계 노드 — 색은 palette 슬롯(단계에 고정)
    for s in stages:
        x, y = pos[s["key"]]
        color = d["color"][s["key"]]
        n = d["agg"][s["key"]][FB_ALL]["n"]
        short = s["label"].split("(")[0].strip()
        sub = s["label"][len(short):].strip(" ()") if "(" in s["label"] else ""
        order = "%d" % s["flow_order"] if s.get("flow_order") else "—"
        aria = "%s · 흐름 %s · %s · 상장사 %d곳" % (short, order, s["front_back"], n)
        # 한글은 글자당 폭이 거의 1em 이라 노드(150px) 안에 들어가게 길이로 크기를 낮춘다.
        fs = 12.5 if len(short) <= 9 else (11.0 if len(short) <= 12 else 9.5)
        parts.append(
            '<g class="node" data-stage="%s" tabindex="0" role="button" aria-label="%s">'
            '<rect x="%d" y="%d" width="%d" height="%d" rx="9" style="fill:%s;stroke:%s"/>'
            '<rect class="bar" x="%d" y="%d" width="4" height="%d" style="fill:%s"/>'
            '<text class="ord" x="%d" y="%d">%s</text>'
            '<text class="nm" x="%d" y="%d" text-anchor="middle" style="font-size:%gpx">%s</text>'
            '<text class="sm2" x="%d" y="%d" text-anchor="middle">%s</text>'
            '<text class="cnt" data-cnt="%s" x="%d" y="%d" text-anchor="middle">%d사</text></g>'
            % (E(s["key"]), E(aria), x, y, NODE_W, NODE_H, color + "26", color + "99",
               x, y, NODE_H, color,
               x + 12, y + 16, E(order),
               x + NODE_W // 2, y + 27, fs, E(short[:16]),
               x + NODE_W // 2, y + 40, E(sub[:18]),
               E(s["key"]), x + NODE_W // 2, y + 54, n))
    return ('<svg id="fab" viewBox="0 0 %d %d" role="img" preserveAspectRatio="xMidYMid meet" '
            'aria-label="팹 공정 흐름 — 단계를 눌러 그 단계 장비를 만드는 상장사를, 한 번 더 눌러 부품과 부품사를 봅니다">'
            '%s</svg>' % (VIEW_W, VIEW_H, "".join(parts)))


# ── 페이지 ──────────────────────────────────────────────────

PARTS_JS = r"""
(function(){
  var S={sel:null, level:1, fb:'all'};
  var panel=document.getElementById('panel');
  function el(tag,cls,text){var e=document.createElement(tag); if(cls)e.className=cls; if(text!=null)e.textContent=text; return e;}
  function stageOf(k){ for(var i=0;i<P.stages.length;i++){ if(P.stages[i].key===k) return P.stages[i]; } return null; }
  function fbOk(fb){ if(S.fb==='all') return true;
    if(fb==='공통'||fb==='전후공정 겸업') return true;
    return fb===(S.fb==='front'?'전공정':'후공정'); }
  function srcKo(s){ return P.src[s||'']||P.src['']; }
  function evLine(co){
    var p=el('p','ev');
    if(co.ev){ p.appendChild(el('span','q','「'+co.ev+'」')); p.appendChild(el('span','src',' '+srcKo(co.src))); }
    else { p.appendChild(el('span','src','원문 근거 없음 — 분류하지 않음')); }
    if(co.words&&co.words.length){ p.appendChild(el('span','src',' · 걸린 낱말 '+co.words.join('·'))); }
    return p;
  }
  function scanLine(sc){
    if(!sc) return null;
    var p=el('p','ev');
    var where=(sc.src==='주요제품')?'정기보고서 II-2 주요제품':'정기보고서 II절 본문';
    p.appendChild(el('span','src',where+' '+(sc.term||'')+(sc.n?' '+sc.n+'회':'')+' — '));
    p.appendChild(el('span','q','「'+(sc.quote||'')+'…」'));
    return p;
  }
  function coRow(co){
    var li=el('li');
    var top=el('div','r1');
    var a=el('a',null,co.nm); a.href=co.stock+'/index.html'; top.appendChild(a);
    top.appendChild(el('span','code',co.stock));
    if(co.primary) top.appendChild(el('span','pill','주단계'));
    if(co.fb) top.appendChild(el('span','tagm',co.fb));
    if(co.bl!=null&&P.hasRep) top.appendChild(el('span','y','수주잔고 '+co.blf+'억'+(co.blq?' ('+co.blq+')':'')));
    else if(P.hasRep) top.appendChild(el('span','y','잔고 미공시'));
    li.appendChild(top);
    li.appendChild(evLine(co));
    var s=scanLine(co.scan); if(s) li.appendChild(s);
    return li;
  }
  function head(st,level){
    var h=el('h3',null,st.label);
    h.appendChild(el('em',null,(st.flow?('팹 흐름 '+st.flow+'단계'):'흐름 밖')+' · '+st.fb));
    panel.appendChild(h);
    var seg=el('div','seg');
    [['1','장비사'],['2','부품·부품사']].forEach(function(o){
      var b=el('button',null,o[1]); b.setAttribute('aria-pressed',String(String(level)===o[0]));
      b.addEventListener('click',function(){ select(st.key,parseInt(o[0],10)); });
      seg.appendChild(b);
    });
    panel.appendChild(seg);
    var a=P.agg[st.key][S.fb];
    var m=el('p','meta');
    m.appendChild(el('b',null,a.n+'사'));
    if(P.hasRep){ m.appendChild(el('span',null,a.bl!=null?(' · 수주잔고 합 '+a.blf+'억 (공시 '+a.nbl+'사 · 미공시 '+a.nmiss+'사)'):' · 수주잔고 공시 회사 없음')); }
    else { m.appendChild(el('span','src',' · 수주잔고는 reports.json 이 아직 없어 싣지 않습니다')); }
    panel.appendChild(m);
  }
  function level1(st){
    if(!fbOk(st.fb)) panel.appendChild(el('p','src','이 단계는 '+st.fb+'입니다 — 지금 고른 필터('+(S.fb==='front'?'전공정':'후공정')+') 밖입니다.'));
    var cos=(P.cos[st.key]||[]).filter(function(c){return fbOk(c.fb);});
    var hidden=(P.cos[st.key]||[]).length-cos.length;
    if(!cos.length){
      panel.appendChild(el('p','mut', (P.cos[st.key]||[]).length ? '이 필터에 해당하는 회사가 없습니다.' : '이 단계의 장비를 만드는 상장사를 원문에서 확인하지 못했습니다 — 지어내지 않습니다.'));
    } else {
      var ul=el('ul'); cos.forEach(function(c){ ul.appendChild(coRow(c)); }); panel.appendChild(ul);
    }
    if(hidden) panel.appendChild(el('p','src',hidden+'사는 현재 필터(전/후공정)에서 숨겼습니다.'));
    var hints=P.hints[st.key]||[];
    if(hints.length){
      panel.appendChild(el('h4',null,'본문 힌트 '+hints.length+'사 — 분류 아님'));
      panel.appendChild(el('p','src','단계 태그가 없는 편입사입니다. 정기보고서 II절 본문에 이 단계 낱말이 있어 가리키기만 합니다.'));
      var ul2=el('ul');
      hints.forEach(function(h){
        var li=el('li'); var t=el('div','r1');
        var a=el('a',null,h.nm); a.href=h.stock+'/index.html'; t.appendChild(a);
        t.appendChild(el('span','code',h.stock)); t.appendChild(el('span','pill est','미분류'));
        li.appendChild(t);
        if(h.prod){ var p=el('p','ev'); p.appendChild(el('span','q','「'+h.prod+'」')); p.appendChild(el('span','src',' KIND 주요제품 문구')); li.appendChild(p); }
        (h.ev||[]).forEach(function(e){ var s=scanLine(e); if(s) li.appendChild(s); });
        ul2.appendChild(li);
      });
      panel.appendChild(ul2);
    }
    if(st.note){ var n=el('p','note2',st.note); panel.appendChild(n); }
  }
  function level2(st){
    var per=P.partcos[st.key]||{};
    if(!(st.parts||[]).length){ panel.appendChild(el('p','mut','이 단계의 부품 목록이 사전에 없습니다.')); return; }
    st.parts.forEach(function(p){
      var box=el('div','partbox');
      var h=el('div','r1'); h.appendChild(el('b',null,p.label)); h.appendChild(el('span','code',p.key));
      box.appendChild(h);
      var rows=per[p.key]||[];
      if(!rows.length){ box.appendChild(el('p','mut','이 부품을 만든다고 원문에 적은 상장 부품사를 확인하지 못했습니다.')); }
      else {
        var ul=el('ul');
        rows.forEach(function(r){
          var li=el('li'); var t=el('div','r1');
          var a=el('a',null,r.nm); a.href=r.stock+'/index.html'; t.appendChild(a);
          t.appendChild(el('span','code',r.stock));
          if(r.role) t.appendChild(el('span','tagm',r.role));
          li.appendChild(t);
          if(r.words&&r.words.length){ var p1=el('p','ev'); p1.appendChild(el('span','q','「'+r.ev+'」')); p1.appendChild(el('span','src',' '+srcKo(r.src)+' · 낱말 '+r.words.join('·'))); li.appendChild(p1); }
          (r.scan||[]).forEach(function(s){ var l=scanLine(s); if(l) li.appendChild(l); });
          ul.appendChild(li);
        });
        box.appendChild(ul);
      }
      panel.appendChild(box);
    });
    if(st.key==='parts'&&P.unspec.length){
      panel.appendChild(el('h4',null,'부품 종류를 원문에서 특정하지 못한 부품사 '+P.unspec.length+'사'));
      var ul3=el('ul');
      P.unspec.forEach(function(r){
        var li=el('li'); var t=el('div','r1');
        var a=el('a',null,r.nm); a.href=r.stock+'/index.html'; t.appendChild(a);
        t.appendChild(el('span','code',r.stock)); t.appendChild(el('span','pill est','부품 미특정'));
        li.appendChild(t);
        var p=el('p','ev'); p.appendChild(el('span','q','「'+r.ev+'」')); p.appendChild(el('span','src',' '+srcKo(r.src))); li.appendChild(p);
        (r.scan||[]).forEach(function(s){ var l=scanLine(s); if(l) li.appendChild(l); });
        ul3.appendChild(li);
      });
      panel.appendChild(ul3);
    } else {
      panel.appendChild(el('p','src','부품 종류를 원문에서 특정하지 못한 부품사 '+P.unspec.length+'곳(제품 문구가 「반도체 장비 부품」처럼 두루뭉술한 회사)은 「부품소재」 단계에서 봅니다.'));
    }
  }
  function render(){
    panel.textContent='';
    if(!S.sel){
      panel.appendChild(el('h3',null,'단계를 누르세요'));
      panel.appendChild(el('p','mut','단계 → 그 장비를 만드는 편입 상장사 → 한 번 더 누르면 그 단계 장비의 부품과 부품사. 회사 이름을 누르면 회사 페이지로 갑니다.'));
      return;
    }
    var st=stageOf(S.sel); if(!st) return;
    head(st,S.level);
    if(S.level===1) level1(st); else level2(st);
  }
  function paint(){
    document.querySelectorAll('#fab .node').forEach(function(g){
      var k=g.dataset.stage, st=stageOf(k);
      g.classList.toggle('sel',S.sel===k);
      g.classList.toggle('off',!fbOk(st.fb));
      var c=g.querySelector('[data-cnt]'); if(c) c.textContent=P.agg[k][S.fb].n+'사';
      g.setAttribute('aria-label',st.label+' · '+(st.flow?('팹 흐름 '+st.flow+'단계'):'흐름 밖')+' · '+st.fb+' · 상장사 '+P.agg[k][S.fb].n+'곳');
      g.setAttribute('aria-expanded',String(S.sel===k));
    });
  }
  function select(k,level){
    if(S.sel===k&&level===undefined){ S.level=(S.level===1?2:1); }
    else { S.level=level||1; }
    S.sel=k; paint(); render();
    if(history.replaceState) history.replaceState(null,'','#'+k);
  }
  document.querySelectorAll('#fab .node').forEach(function(g){
    g.addEventListener('click',function(){ select(g.dataset.stage); });
    g.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); select(g.dataset.stage); } });
  });
  document.querySelectorAll('#fbseg button').forEach(function(b){
    b.addEventListener('click',function(){
      S.fb=b.dataset.fb;
      document.querySelectorAll('#fbseg button').forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.fb===S.fb));});
      paint(); render();
    });
  });
  document.getElementById('reset').addEventListener('click',function(){
    S.sel=null; S.level=1; S.fb='all';
    document.querySelectorAll('#fbseg button').forEach(function(x){x.setAttribute('aria-pressed',String(x.dataset.fb==='all'));});
    paint(); render();
  });
  var h=location.hash.slice(1); if(h&&stageOf(h)) select(h,1); else { paint(); render(); }
})();
"""


def parts_html(d):
    stages = d["stages"]
    n_mem = len(d["member_ids"])
    n_tagged = sum(1 for r in d["members"] if (d["tags"].get(r["stock"]) or {}).get("stages"))
    n_pool = len(d["pool"])
    n_empty = sum(1 for s in stages if not d["cos"][s["key"]])
    bl_total = None
    if d["has_rep"]:
        seen = set()
        tot = 0
        for k in d["cos"]:
            for c in d["cos"][k]:
                if c["bl"] is not None and c["stock"] not in seen:
                    seen.add(c["stock"])
                    tot += c["bl"]
        bl_total = tot

    embed = {
        "stages": [{"key": s["key"], "label": s["label"], "flow": s.get("flow_order"),
                    "fb": s["front_back"], "color": d["color"][s["key"]],
                    "note": (s.get("note") or "")[:900],
                    "parts": [{"key": p["key"], "label": p["label"]} for p in (s.get("parts") or [])]}
                   for s in stages],
        "cos": {k: [dict(c, blf=fmt_eok(c["bl"]) if c["bl"] is not None else None) for c in v]
                for k, v in d["cos"].items()},
        "partcos": d["partcos"], "unspec": d["unspec"], "hints": d["hints"],
        "agg": {k: {f: dict(a, blf=(fmt_eok(a["bl"]) if a["bl"] is not None else None))
                    for f, a in v.items()} for k, v in d["agg"].items()},
        "src": SRC_KO, "hasRep": d["has_rep"],
    }

    kpi = [
        '<div><b>%d</b><span>편입 상장사(모집단 154종목 중) · 단계 태그 있는 회사 %d</span></div>' % (n_mem, n_tagged),
        '<div><b>%d</b><span>공정 단계 · 장비사를 못 찾은 단계 %d</span></div>' % (len(stages), n_empty),
        '<div><b>%d</b><span>부품·공정서비스 태그 회사(부품사 풀)</span></div>' % n_pool,
        ('<div><b>%s</b><span>수주잔고 합(억원) · reports.json 수록분</span></div>' % fmt_eok(bl_total))
        if d["has_rep"] else
        '<div><b>—</b><span>수주잔고 — reports.json 이 아직 없습니다(수집 중) · 회사 수만 싣습니다</span></div>',
    ]
    legend = "".join(
        '<span><i style="background:%s"></i>%s</span>' % (E(d["color"][s["key"]]), E(s["label"].split("(")[0]))
        for s in stages)

    untag_rows = "".join(
        '<tr><td class="l"><a href="%s/index.html">%s</a> <span class="code">%s</span></td>'
        '<td class="l mut">%s</td><td class="l">%s</td></tr>'
        % (E(u["stock"]), E(u["nm"]), E(u["stock"]), E(u["prod"] or "—"),
           (" · ".join(E(d["by_key"][k]["label"].split("(")[0]) for k in u["hints"]) or
            '<span class="mut">본문 힌트도 없음 — 어느 단계인지 원문에서 확인 못 함</span>'))
        for u in d["untagged"])

    body = """
<div class="kpi">%s</div>
<section class="card"><h2>팹 공정 흐름 <em>단계를 누르면 그 단계 장비를 만드는 편입 상장사 · 한 번 더 누르면 그 단계 장비의 부품과 부품사</em>
 <span class="right"><button class="chip" id="reset">선택 해제</button></span></h2>
 <div class="ctl">
  <span class="mut" style="font-size:10.5px">전/후공정</span>
  <div class="seg" id="fbseg">
   <button data-fb="all" aria-pressed="true">전체</button>
   <button data-fb="front" aria-pressed="false">전공정</button>
   <button data-fb="back" aria-pressed="false">후공정</button>
  </div>
  <span class="mut" style="font-size:10.5px">공통(계측·이송·부품·서비스)은 양쪽에 모두 남습니다 · 색은 단계에 고정이라 필터로 바뀌지 않습니다</span>
 </div>
 <div class="ig">
  <div class="fab">%s<div class="legend">%s</div></div>
  <div class="panel" id="panel" aria-live="polite"></div>
 </div>
</section>
<section class="card"><h2>단계 미분류 편입사 <em>%d사 — 제품 문구·지정 사유로는 단계를 정할 수 없었습니다. 지어 붙이지 않고 그대로 남깁니다</em></h2>
 <div class="wrap"><table data-sortable><thead><tr><th class="l">회사</th><th class="l">KIND 주요제품 문구</th><th class="l">정기보고서 II절 본문 힌트(분류 아님)</th></tr></thead><tbody>%s</tbody></table></div>
</section>
<div class="note info">싣는 기준: <b>scan.json 판정이 「편입」인 회사만</b> 탭 구성원으로 싣습니다(배제 %d · 보류 %d · 오류 %d 는 이름을 싣지 않습니다).
 단계 분류는 KIND 주요제품 문구·스펙 지정 사유·정기보고서 II절 본문의 낱말 규칙이고, 회사마다 걸린 낱말과 원문 문구를 같이 보입니다.
 단계 태그가 있으나 편입이 아닌 회사 %d곳은 이 화면에 넣지 않았습니다.
 <b>부품 ↔ 회사</b> 연결 규칙: ① 회사의 KIND 주요제품 문구·지정 사유에 그 부품 이름이 적혀 있거나, ② <b>부품·공정서비스사</b>의 정기보고서 II절 본문에서 scan 이 <b>장비 부분품</b>으로 본 낱말이 그 부품 이름일 때만 잇습니다.
 장비사 본문에 나오는 부품 이름(식각기 안의 정전척 같은)은 잇지 않습니다 — 자기가 쓰는 부품이지 만드는 부품이 아닙니다. 어느 쪽 근거인지는 회사마다 적었고, 연결은 「원문에 그렇게 적혀 있다」는 뜻일 뿐 납품 관계를 주장하지 않습니다.%s</div>
<script>const P=%s;</script>
<script>%s</script>
<script>%s</script>
""" % ("".join(kpi), svg(d), legend, len(d["untagged"]), untag_rows,
       d["dist"].get("배제", 0), d["dist"].get("보류", 0), d["dist"].get("오류", 0),
       d["n_tag_not_member"],
       ("" if d["has_rep"] else
        " 수주잔고는 <code>tools/assets/reports.json</code> 이 만들어진 뒤에 이 화면에 붙습니다 — 지금은 0으로 채우지 않고 비워 둡니다."),
       json_for_html(embed), TABLE_JS, PARTS_JS)

    return page("팹 공정 흐름 인포그래픽 — 단계 · 장비사 · 부품사", body, depth=0,
                h1="🔧 팹 공정 흐름 인포그래픽",
                nav=(("허브", "index.html"), ("커버리지", "coverage.html"), ("← ARGUS", "../index.html")),
                crumbs=(("ARGUS", "../index.html"), ("한국반도체장비", "index.html"), ("인포그래픽", None)),
                lead="웨이퍼 투입에서 패키징까지 팹 공정을 단계로 나누고, 각 단계의 장비를 만드는 국내 상장사와 "
                     "그 장비의 부품·부품사를 원문 근거와 함께 연결했습니다. 단계를 누르면 회사가, 한 번 더 누르면 부품이 열립니다.")


# ── 실행 ───────────────────────────────────────────────────

def prepare():
    data = load_all()
    d = build(data)
    d["color"] = {s["key"]: _stage_color(s["key"], data["stages"]["stages"]) for s in data["stages"]["stages"]}
    d["dist"] = data["scan"].get("dist") or {}
    tagged = {t["stock"] for t in data["tags"]["rows"] if t.get("stages")}
    d["n_tag_not_member"] = len(tagged - d["member_ids"])
    return d


_SLOT = None


def _stage_color(key, stages):
    """palette.json 슬롯 → 단계 고정색. 슬롯이 없으면 fail-closed(색을 지어내지 않는다)."""
    global _SLOT
    if _SLOT is None:
        _SLOT = {}
        for s in load_asset("palette.json")["categorical_order_fixed"]:
            for k in s.get("stages", []):
                _SLOT[k] = s["slot"]
    if key not in _SLOT:
        raise KeyError("palette.json 에 단계 %s 의 슬롯이 없다 — 색을 지어내지 않는다" % key)
    return slot_color(_SLOT[key])


def main():
    ap = argparse.ArgumentParser(description="팹 공정 흐름 인포그래픽(parts.html)")
    ap.add_argument("--write", action="store_true", help="argus/ksemi/parts.html 를 쓴다")
    ap.add_argument("--out", default=None, help="출력 경로(기본 argus/ksemi/parts.html)")
    a = ap.parse_args()
    d = prepare()
    html = parts_html(d)
    for s in d["stages"]:
        n = len(d["cos"][s["key"]])
        print("%-9s %-28s 흐름 %-4s %-5s 회사 %2d · 부품 %d"
              % (s["key"], s["label"][:26], s.get("flow_order") or "—", s["front_back"], n,
                 len(s.get("parts") or [])), file=sys.stderr)
    print("편입 %d · 단계 미분류 %d · 부품사 풀 %d · reports.json %s · %.1fKB"
          % (len(d["member_ids"]), len(d["untagged"]), len(d["pool"]),
             "있음" if d["has_rep"] else "없음", len(html.encode("utf-8")) / 1024.0), file=sys.stderr)
    if a.write:
        out = a.out or os.path.join(KSEMI, "parts.html")
        atomic_write(out, html)
        print("→ %s" % out)
    else:
        print("(예행 — 쓰려면 --write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
