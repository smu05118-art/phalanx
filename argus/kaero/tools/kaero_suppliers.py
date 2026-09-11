#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kaero_suppliers — 회사를 **부품 분류**와 **고객**에 잇는다(수집 없음, 이미 받은 원문만 쓴다).

두 가지를 만든다.

  ① 부품 분류  회사가 무슨 부품을 만드는가 — `assets/parts_taxonomy.json` 의 낱말을
     KIND 주요제품 문구 · 수주표·매출표의 품목 이름 · 계약공시 계약명 · ④ 탐색 인용문에 맞춘다.
  ② 고객 연결  이 산업은 고객이 세계에 몇 안 되는 기체·엔진 제작사라 **실명으로** 나온다.
     근거 등급을 원천별로 매긴다(스펙 §데이터 원천 '근거 등급 표시'):

       grade 1 `매출처표`  정기보고서 「주요 매출처」 표에 이름(금액·비중까지) — 가장 강하다
       grade 2 `수주표`    II-4 수주표의 품목 열이 곧 발주처다(아스트 SPIRIT·EMBRAER…)
       grade 3 `계약공시`  단일판매ㆍ공급계약체결의 계약상대
       grade 4 `본문언급`  II절 본문에 이름이 나온다(판매전략 칸의 "GE, P&W, 롤스로이스")

낮은 등급의 연결을 지우지 않고 **등급을 화면에 띄운다**(COMMON §0-1).
약칭만 나와 사전으로 편 이름(`KAL`→대한항공)은 그 안에서도 `추정`으로 표시한다.

    python3 kaero_suppliers.py --build
"""
import argparse
import collections
import os
import re
import sys

from kaero_lib import ASSETS, load_asset, write_asset
from kaero_universe import load as load_universe
import kaero_contracts
import kaero_reports

# 항공·우주 문맥 낱말 — `ctx=True` 인 소분류는 낱말 가까이에 이 말이 있어야 채택한다.
# (자동차 단조사·통신 안테나사가 항공 부품사로 잡히는 것을 막는다)
_CTX = re.compile(r"항공|우주|위성|발사체|로켓|기체|동체|엔진부품|가스터빈|OEM|Boeing|Airbus|"
                  r"Embraer|보잉|에어버스|KAI|한국항공우주|대한항공|MRO|창정비|감항|AS9100|Nadcap",
                  re.I)
_NORM = re.compile(r"[\s　·ㆍ,()\[\]/\-–—]+")
_SHORT_LATIN = re.compile(r"^[A-Za-z0-9/\-]{2,4}$")
_SEP = r"[\s　·ㆍ,()\[\]/\-–—]*"
_WINDOW = 70

_SRC_RANK = ["item", "contract", "body", "kind"]        # 앞일수록 강한 근거
SRC_KO = {"item": "공시 품목명", "contract": "계약명", "body": "II절 본문", "kind": "KIND 주요제품"}
BASIS = {"customer": (1, "매출처 표"), "order": (2, "수주표 품목"),
         "contract": (3, "계약공시 상대"), "body": (4, "본문 언급")}


def _norm(s):
    return _NORM.sub("", (s or "").lower())


def _kw_spans(raw, kw):
    """원문에서 낱말 위치(사이에 공백·가운뎃점이 끼어도 찾는다)."""
    pat = _SEP.join(re.escape(ch) for ch in kw if not _NORM.match(ch))
    if not pat:
        return []
    flags = 0 if _SHORT_LATIN.match(kw) else re.I      # 짧은 약어는 대소문자까지 맞춘다
    return [(m.start(), m.end()) for m in re.finditer(pat, raw, flags)]


def match_cats(tax, texts):
    """texts = [(src, 원문), …] → [{cat, kw, src}] (우선순위 내림차순, 중복 제거)."""
    hits = {}
    for cat in tax["cats"]:
        for src, raw in texts:
            if not raw:
                continue
            t = _norm(raw)
            if any(_norm(n) and _norm(n) in t for n in cat["neg"]):
                continue
            for kw in cat["keywords"]:
                spans = _kw_spans(raw, kw) if _norm(kw) and _norm(kw) in t else []
                if not spans:
                    continue
                if cat["ctx"] or _SHORT_LATIN.match(kw):
                    near = any(_CTX.search(raw[max(0, a - _WINDOW):b + _WINDOW]) for a, b in spans)
                    if not near:
                        continue
                prev = hits.get(cat["id"])
                if prev is None or _SRC_RANK.index(src) < _SRC_RANK.index(prev["src"]):
                    hits[cat["id"]] = {"cat": cat["id"], "kw": kw, "src": src, "prio": cat["prio"]}
                break
    return sorted(hits.values(), key=lambda h: (-h["prio"], h["cat"]))


def _item_text(comp):
    """그 회사 공시의 **품목 이름**을 모은 문자열 — 부품 분류의 가장 좋은 재료다.

    수주표·상세표의 계약명(`Leap & LM2500 HPT Disk 공급계약`)과 매출표 품목(`Section48`)이
    여기 들어온다. KIND 한 줄보다 훨씬 구체적이다."""
    bits = []
    for q in sorted((comp.get("quarters") or {})):
        v = comp["quarters"][q]
        if not v.get("ok"):
            continue
        for c in v.get("contracts") or []:
            bits.append(c.get("label") or "")
        for r in (v.get("revenue_segments") or []) + (v.get("sales_segments") or []):
            bits.append("%s %s" % (r.get("seg") or "", r.get("item") or ""))
    return " · ".join(b for b in dict.fromkeys(bits) if b)


def build(write=True):
    uni = load_universe()
    tax = load_asset("parts_taxonomy.json")
    probe = load_asset("universe_probe.json") if os.path.exists(
        os.path.join(ASSETS, "universe_probe.json")) else {"promoted": {}, "rejected": []}
    cons = kaero_contracts.load()
    reports = kaero_reports.load()["companies"]
    probe_p = probe.get("promoted") or {}
    probe_r = {x["stock"]: x for x in (probe.get("rejected") or [])}
    con_by = collections.defaultdict(list)
    for c in cons:
        con_by[c["stock"]].append(c)

    cos = []
    for r in uni:
        st = r["stock"]
        comp = reports.get(st) or {}
        pr = probe_p.get(st) or probe_r.get(st) or {}
        quote = pr.get("reason") or ""
        cnames = " ".join((c["name"] or "") for c in con_by.get(st, []))
        texts = [("item", _item_text(comp)),
                 ("contract", cnames),
                 # 탐색이 남긴 **인용문**만 쓴다 — terms 는 탐지기의 어휘 목록이라 그것을
                 # 제품으로 읽으면 탐지 어휘가 그 회사의 부품이 된다.
                 ("body", re.sub(r"^[^\"]*\"", "", quote)),
                 ("kind", (r.get("product") or "") + " " + (r.get("industry") or ""))]
        cats = match_cats(tax, texts)

        # ── 고객 연결 ──
        links = {}

        def add(name, tier, basis, detail, grade_hint="B", stock=None, extra=None):
            g, ko = BASIS[basis]
            cur = links.get(name)
            rec = {"name": name, "tier": tier, "basis": basis, "basis_ko": ko, "grade": g,
                   "evidence": grade_hint, "stock": stock, "detail": detail}
            rec.update(extra or {})
            if cur is None or g < cur["grade"]:
                links[name] = rec
            elif g == cur["grade"]:
                cur["detail"] = (cur["detail"] + " · " + detail)[:140]

        qs = [q for q in sorted((comp.get("quarters") or {})) if comp["quarters"][q].get("ok")]
        last = comp["quarters"][qs[-1]] if qs else {}
        # ① 매출처 표
        for cu in last.get("customers") or []:
            nm = (cu.get("name") or "").strip()
            if not nm:
                continue
            matched = cu.get("matched") or []
            tier = matched[0]["tier"] if matched else ("prime" if cu.get("kind") == "내수" else None)
            add(matched[0]["name"] if matched else nm, tier, "customer",
                "%s 매출처 표 「%s」%s" % (qs[-1] if qs else "", nm[:24],
                                     (" 비중 %.1f%%" % cu["share_pct"]) if cu.get("share_pct") else ""),
                matched[0]["grade"] if matched else "A",
                matched[0].get("stock") if matched else None,
                {"amount": cu.get("amount"), "share": cu.get("share_pct"), "raw": nm[:40]})
        # ② 수주표 품목 열
        for c in last.get("order_customers") or []:
            add(c["name"], c["tier"], "order",
                "수주표 품목 열에 이름 — 잔고 %s" % ", ".join(
                    "%s %s" % (k, format(int(v), ",d")) for k, v in sorted(c["backlog"].items())),
                c.get("grade", "B"), c.get("stock"), {"backlog": c["backlog"]})
        # ③ 계약공시 상대
        for c in con_by.get(st, []):
            for h in c.get("customers") or []:
                add(h["name"], h["tier"], "contract",
                    "계약공시 상대 「%s」" % (c.get("party") or "")[:30], h.get("grade", "B"),
                    h.get("stock"))
        # ④ 본문 언급
        for h in last.get("text_customers") or []:
            add(h["name"], h["tier"], "body", "II-4 본문에 이름", h.get("grade", "B"), h.get("stock"))

        cos.append({
            "stock": st, "nm": r["name"], "role": r["role"], "market": r.get("market", ""),
            "industry": r.get("industry", ""), "prod_raw": (r.get("product") or "")[:160],
            "source": r.get("source"), "reason": r.get("reason") or "",
            "seen": bool(qs) or bool(con_by.get(st)),
            "cats": [{k: h[k] for k in ("cat", "kw", "src")} for h in cats],
            "customers": sorted(links.values(), key=lambda x: (x["grade"], x["name"])),
            "n_contracts": len(con_by.get(st, [])),
        })
    out = {"n": len(cos),
           "grades": {k: {"grade": v[0], "ko": v[1]} for k, v in BASIS.items()},
           "srcs": SRC_KO, "cos": cos}
    if write:
        write_asset("suppliers.json", out)
    return out


def load():
    try:
        return load_asset("suppliers.json")
    except FileNotFoundError:
        return {"n": 0, "cos": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()
    out = build(write=a.build)
    ncat = sum(1 for c in out["cos"] if c["cats"])
    nlink = sum(1 for c in out["cos"] if c["customers"])
    print("회사 %d · 부품 분류됨 %d · 고객 연결 %d" % (out["n"], ncat, nlink))
    print("  근거 %s" % dict(collections.Counter(
        p["basis"] for c in out["cos"] for p in c["customers"])))
    for c in out["cos"]:
        if c["cats"] or c["customers"]:
            print("  %s %-16s %-30s %s" % (
                c["stock"], c["nm"][:16],
                ",".join(h["cat"] for h in c["cats"][:3])[:30],
                " ".join("%s(%s)" % (p["name"][:12], p["basis_ko"]) for p in c["customers"][:4])))


if __name__ == "__main__":
    sys.exit(main())
