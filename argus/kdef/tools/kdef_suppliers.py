#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_suppliers — 부품사를 **부품 분류**와 **체계업체**에 잇는다(수집 없음, 이미 받은 원문만 쓴다).

두 가지를 만든다.

  ① 부품 분류  회사가 무슨 부품을 만드는가 — `assets/parts_taxonomy.json` 의 낱말을
     KIND 주요제품 문구 · 그 회사의 계약공시 계약명 · ④ 본문 탐색이 남긴 인용문에 맞춘다.
  ② 납품 관계  부품사 → 체계업체. 근거 등급을 **원천별로** 매긴다(스펙 §데이터 원천):

       grade 1 `주요고객`  정기보고서 「주요 매출처」 주석에 체계업체 이름 — 가장 강하다(비중 %까지)
       grade 2 `계약공시`  단일판매ㆍ공급계약체결의 **계약상대**가 체계업체 — 금액·기간이 따라온다
       grade 3 `본문언급`  정기보고서 II절 본문에 체계업체 이름이 나온다(④ 탐색이 센 횟수)
       grade 4 `KIND`     주요제품 문구만 — 납품 관계의 근거로는 쓰지 않는다(부품 분류에만)

근거 등급이 낮은 연결을 지우지 않고 **등급을 화면에 띄운다**. 방산 공급망은 공시가 얇아
'본문 언급'이 유일한 단서인 경우가 많고, 그 한계는 숨기지 않는 편이 낫다(COMMON §0-1).

    python3 kdef_suppliers.py --build
"""
import argparse
import collections
import os
import re
import sys

from kdef_lib import ASSETS, load_asset, write_asset
from kdef_universe import load as load_universe
import kdef_contracts
import kdef_products
import kdef_reports

# 방산 문맥 낱말 — 부품 소분류 중 `ctx=True` 인 것은 이 낱말이 같이 있어야 채택한다
# (민수 변속기·민수 레이더를 방산 부품으로 잡으면 인포그래픽이 통째로 거짓이 된다).
_CTX = re.compile(r"방산|방위|국방|군용|군수|전차|자주포|장갑차|함정|잠수함|유도|미사일|"
                  r"전투기|헬기|무인기|레이더|레이다|탄약|포탄|방탄|군납|방위사업청|무기체계")
_NORM = re.compile(r"[\s　·ㆍ,()\[\]/\-–—]+")


def _norm(s):
    return _NORM.sub("", (s or "").lower())


# 짧은 로마자 약어는 민수 낱말과 충돌한다 — 엣지파운드리의 `자동차용 센서(APS, TPS…)`가
# 능동방호(APS)로 잡혔다(실측). 이런 낱말은 방산 문맥이 **가까이** 있을 때만 채택한다.
_SHORT_LATIN = re.compile(r"^[A-Za-z0-9/\-]{2,4}$")
_SEP = r"[\s　·ㆍ,()\[\]/\-–—]*"
_WINDOW = 60


def _kw_spans(raw, kw):
    """원문에서 낱말 위치(사이에 공백·가운뎃점이 끼어도 찾는다)."""
    pat = _SEP.join(re.escape(ch) for ch in kw if not _NORM.match(ch))
    if not pat:
        return []
    flags = 0 if _SHORT_LATIN.match(kw) else re.I      # 짧은 약어는 대소문자까지 맞춘다
    return [(m.start(), m.end()) for m in re.finditer(pat, raw, flags)]


def match_cats(tax, texts):
    """texts = [(src, 원문), …] → [{cat, kw, src}] (우선순위 내림차순, 중복 제거).

    `ctx=True` 인 소분류와 짧은 로마자 약어는 낱말에서 %d자 안에 방산 문맥 낱말이 있어야
    채택한다 — 문서 어딘가에 '방산'이 한 번 나온다고 민수 부품을 방산 부품으로 세면 안 된다.""" % _WINDOW
    hits = {}
    for cat in tax["cats"]:
        for src, raw in texts:
            if not raw:
                continue
            t = _norm(raw)
            if any(_norm(n) and _norm(n) in t for n in cat["neg"]):
                continue
            for kw in cat["kw"]:
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


_SRC_RANK = ["contract", "report", "body", "kind"]   # 앞일수록 강한 근거
BASIS = {"customer": (1, "주요고객 주석"), "contract": (2, "계약공시 상대"),
         "body": (3, "본문 언급"), "kind": (4, "KIND 문구")}


def build(write=True):
    uni = load_universe()
    tax = load_asset("parts_taxonomy.json")
    probe = load_asset("universe_probe.json") if os.path.exists(
        os.path.join(ASSETS, "universe_probe.json")) else {"promoted": {}, "rejected": []}
    cons = kdef_contracts.load()
    reports = kdef_reports.load()["companies"]
    prod_text = kdef_products.load()          # 정기보고서 「II-2 주요 제품」 절 본문
    primes = {r["stock"]: r["name"] for r in uni if r["role"] == "prime"}
    names = {r["stock"]: r["name"] for r in uni}
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
        # 탐색이 남긴 **인용문**만 쓴다 — terms 는 탐지기의 어휘 목록이라 그걸 제품으로
        # 읽으면 '전자전'·'전투체계'가 안료 회사의 부품이 된다(실측).
        texts = [("contract", cnames),
                 ("report", prod_text.get(st, "")),
                 ("body", re.sub(r"^[^\"]*\"", "", quote)),
                 ("kind", (r.get("product") or "") + " " + (r.get("industry") or ""))]
        cats = match_cats(tax, texts)

        # ── 체계업체 연결 ──
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

        # ① 주요고객 주석
        comp = reports.get(st) or {}
        for q in sorted((comp.get("quarters") or {})):
            v = comp["quarters"][q]
            for cu in v.get("customers") or []:
                nm = cu.get("name") or ""
                for ps, pat in kdef_contracts.PRIME_NAMES.items():
                    if re.search(pat, nm, re.I):
                        add(ps, "customer", "%s 「%s」%s" % (
                            q, nm[:24],
                            (" 비중 %.1f%%" % cu["share_pct"]) if cu.get("share_pct") else ""),
                            {"share": cu.get("share_pct")})
        # ② 계약공시 상대
        byp = collections.Counter()
        amt = collections.Counter()
        for c in con_by.get(st, []):
            if c.get("party_prime"):
                byp[c["party_prime"]] += 1
                amt[c["party_prime"]] += (c["amt_krw_m"] or 0)
        for ps, n in byp.items():
            add(ps, "contract", "계약 %d건" % n, {"n_contracts": n, "amt_krw_m": amt[ps] or None})
        # ③ 본문 언급
        for ps, n in (pr.get("mentions") or {}).items():
            add(ps, "body", "II절에서 %d회 언급" % n, {"mentions": n})

        cos.append({
            "stock": st, "nm": r["name"], "role": r["role"], "market": r.get("market", ""),
            "industry": r.get("industry", ""), "prod_raw": (r.get("product") or "")[:160],
            "source": r.get("source"), "reason": r.get("reason") or "",
            "seen": bool(pr) or bool(comp) or bool(con_by.get(st)),
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
    print("회사 %d · 부품 분류됨 %d · 체계업체 연결 %d" % (out["n"], ncat, nlink))
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
