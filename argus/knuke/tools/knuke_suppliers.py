#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""knuke_suppliers — 발전기자재사를 **공급 계층 부품**과 **주기기·설계·정비 대형사**에 잇는다
(수집 없음, 이미 받은 원문만 쓴다).

  ① 부품 분류  회사가 무슨 기자재를 만드는가 — `assets/parts_taxonomy.json` 의 낱말을
     계약공시 계약명 · ③ 본문 탐색 인용문 · KIND 주요제품 문구에 맞춘다.
  ② 납품 관계  기자재사 → 대형사(두산에너빌리티 주기기 · 한전기술 설계 · 한전KPS 정비).
     근거 등급을 원천별로:
       grade 2 `계약공시`  단일판매ㆍ공급계약체결의 **계약상대**가 대형사 — 금액·기간이 따라온다
       grade 3 `본문언급`  ③ 탐색 인용문·사유에 대형사 이름이 나온다
       grade 4 `KIND`     주요제품 문구만(부품 분류에만 씀)

근거가 낮은 연결을 지우지 않고 등급을 화면에 띄운다(COMMON §0-1).

    python3 knuke_suppliers.py --build
"""
import argparse
import collections
import os
import re
import sys

from knuke_lib import ASSETS, load_asset, write_asset
from knuke_universe import load as load_universe
import knuke_contracts

# 발전 문맥 낱말 — ctx=True 소분류·짧은 약어는 이 낱말이 가까이 있어야 채택.
_CTX = re.compile(r"원전|원자력|원자로|발전|화력|복합발전|보일러|터빈|발전소|발전설비|한수원|"
                  r"한국수력원자력|한국전력|한전|증기발생기|송변전|변전|플랜트|열병합")
_NORM = re.compile(r"[\s　·ㆍ,()\[\]/\-–—]+")


def _norm(s):
    return _NORM.sub("", (s or "").lower())


_SHORT_LATIN = re.compile(r"^[A-Za-z0-9/\-]{2,5}$")
_SEP = r"[\s　·ㆍ,()\[\]/\-–—]*"
_WINDOW = 60


def _kw_spans(raw, kw):
    pat = _SEP.join(re.escape(ch) for ch in kw if not _NORM.match(ch))
    if not pat:
        return []
    flags = 0 if _SHORT_LATIN.match(kw) else re.I
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
            for kw in cat["kw"]:
                kwn = _norm(kw.replace("\\b", ""))
                spans = _kw_spans(raw, kw.replace("\\b", "")) if kwn and kwn in t else []
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


_SRC_RANK = ["contract", "body", "kind"]
BASIS = {"contract": (2, "계약공시 상대"), "body": (3, "본문 언급"), "kind": (4, "KIND 문구")}


def build(write=True):
    uni = load_universe()
    tax = load_asset("parts_taxonomy.json")
    probe = load_asset("universe_probe.json") if os.path.exists(
        os.path.join(ASSETS, "universe_probe.json")) else {"promoted": {}, "rejected": []}
    cons = knuke_contracts.load()
    primes = {r["stock"]: r["name"] for r in uni if r["role"] in ("main", "eng", "om")
              and r["stock"] in knuke_contracts.PRIME_NAMES}
    # PRIME_NAMES 에 든 대형사만 연결 대상으로 삼는다.
    primes = {ps: {r["stock"]: r["name"] for r in uni}.get(ps, ps)
              for ps in knuke_contracts.PRIME_NAMES}
    con_by = collections.defaultdict(list)
    for c in cons:
        con_by[c["stock"]].append(c)
    probe_p = probe.get("promoted") or {}
    probe_r = {x["stock"]: x for x in (probe.get("rejected") or [])}

    cos = []
    for r in uni:
        st = r["stock"]
        pr = probe_p.get(st) or probe_r.get(st) or {}
        quote = pr.get("reason") or ""
        cnames = " ".join((c["name"] or "") for c in con_by.get(st, []))
        texts = [("contract", cnames), ("body", re.sub(r'^[^"]*"', "", quote)),
                 ("kind", (r.get("product") or "") + " " + (r.get("industry") or ""))]
        cats = match_cats(tax, texts)

        links = {}

        def add(pstock, basis, detail, extra=None):
            if pstock not in primes or pstock == st:
                return
            g, ko = BASIS[basis]
            cur = links.get(pstock)
            rec = {"stock": pstock, "nm": primes[pstock], "basis": basis, "basis_ko": ko,
                   "grade": g, "detail": detail}
            rec.update(extra or {})
            if cur is None or g < cur["grade"]:
                links[pstock] = rec
            elif g == cur["grade"]:
                cur["detail"] = (cur["detail"] + " · " + detail)[:120]

        # ② 계약공시 상대
        byp = collections.Counter()
        amt = collections.Counter()
        for c in con_by.get(st, []):
            if c.get("party_prime"):
                byp[c["party_prime"]] += 1
                amt[c["party_prime"]] += (c["amt_krw_m"] or 0)
        for ps, n in byp.items():
            add(ps, "contract", "계약 %d건" % n, {"n_contracts": n, "amt_krw_m": amt[ps] or None})
        # ③ 본문 언급(탐색 인용문·사유에서 대형사 이름)
        blob = quote + " " + (r.get("reason") or "")
        for ps, pat in knuke_contracts.PRIME_NAMES.items():
            if ps == st:
                continue
            n = len(re.findall(pat, blob, re.I))
            if n:
                add(ps, "body", "II절 인용문에 %d회" % n, {"mentions": n})

        cos.append({
            "stock": st, "nm": r["name"], "role": r["role"], "market": r.get("market", ""),
            "industry": r.get("industry", ""), "prod_raw": (r.get("product") or "")[:160],
            "source": r.get("source"), "reason": r.get("reason") or "",
            "seen": bool(pr) or bool(con_by.get(st)),
            "cats": [{k: h[k] for k in ("cat", "kw", "src")} for h in cats],
            "primes": sorted(links.values(), key=lambda x: (x["grade"], x["stock"])),
            "n_contracts": len(con_by.get(st, [])),
        })
    out = {"n": len(cos), "grades": {k: {"grade": v[0], "ko": v[1]} for k, v in BASIS.items()},
           "cos": cos}
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
    nlink = sum(1 for c in out["cos"] if c["primes"])
    print("회사 %d · 부품 분류됨 %d · 대형사 연결 %d" % (out["n"], ncat, nlink))
    g = collections.Counter(p["basis"] for c in out["cos"] for p in c["primes"])
    print("  근거 %s" % dict(g))
    for c in out["cos"]:
        if c["primes"] or c["cats"]:
            print("  %s %-16s %-28s %s" % (
                c["stock"], c["nm"][:16],
                ",".join(h["cat"] for h in c["cats"][:3])[:28],
                " ".join("%s(%s)" % (p["nm"][:8], p["basis_ko"]) for p in c["primes"][:3])))


if __name__ == "__main__":
    sys.exit(main())
