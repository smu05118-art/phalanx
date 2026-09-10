#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kship_suppliers — 기자재사의 부품·납품처를 정기보고서 II. 사업의 내용에서 읽는다.

원하는 것 세 가지:
  ① 무슨 부품을 만드는가   — II.2 「주요 제품 및 서비스」 표(품목·매출액·비중)와 KIND 주요제품 문구
  ② 어느 조선사에 파는가   — II 절 본문에서 조선사 이름의 언급(주요 매출처·매출 비중이 있으면 함께)
  ③ 얼마나 파는가          — II.4 매출실적 표(부문·품목별, 수출/내수)

납품 관계의 근거 등급(basis): ifrs8(주요 고객 주석·10% 이상 고객만) > contract(단일판매공급계약
상대방) > text(사업의 내용 본문 언급, 비중 없음) > kind(KIND 제품 문구에만 근거). 등급이 낮을수록
화면에서 '추정'으로 표시한다 — 없는 정밀도를 주장하지 않는다.

부품 분류는 parts_taxonomy.json 의 키워드 규칙으로 한다(긴 키워드·높은 우선순위 우선, 부정
키워드 배제, 문맥 필요 낱말은 선박·조선·해양이 함께 있을 때만). 매칭 실패는 UNCL 로 남겨
사람이 override 할 수 있게 한다(assets/parts_override.csv: stock,prod_text,cat).

    python3 kship_suppliers.py --collect [--quarter 2026Q2] [--only 033500]
    python3 kship_suppliers.py --build            # 캐시 → assets/suppliers.json
"""
import argparse
import csv
import json
import os
import re
import sys

from kship_lib import (ASSETS, atomic_write, fetch_section, find_sections, latest_quarter,
                       load_asset, num_of, parse_tables, pick_report, report_kind,
                       search_reports, toc, write_asset)
from kship_parse import unit_of
from kship_universe import load as load_universe
from kce_probe import report_window                      # noqa: E402

CACHE = os.path.join(ASSETS, "suppliers_cache")
SECTIONS = [
    ("products", ["주요 제품", "주요 제품 및 서비스", "주요제품"]),
    ("sales", ["매출 및 수주상황", "매출실적", "수주상황"]),
    ("overview", ["사업의 개요"]),
]

# 조선사 언급 탐지 — 정식명·약칭·구명. (id → 정규식)
YARD_NAMES = {
    "329180": r"HD현대중공업|현대중공업|HHI",
    "010140": r"삼성중공업|SHI",
    "042660": r"한화오션|대우조선해양|대우조선|DSME",
    "010620": r"HD현대미포|현대미포조선|현대미포",
    "HSHI": r"HD현대삼호|현대삼호중공업|현대삼호",
    "009540": r"HD한국조선해양|한국조선해양",
    "439260": r"대한조선",
    "097230": r"HJ중공업|한진중공업",
    "KSOE_GRP": r"HD현대(?!중공업|미포|삼호|마린|일렉|에너지|건설기계|인프라)",
}


def _norm(s):
    return re.sub(r"[\s　]+", "", (s or "")).lower()


_TAX = None


def taxonomy():
    global _TAX
    if _TAX is None:
        t = load_asset("parts_taxonomy.json")
        cats = sorted(t["cats"], key=lambda c: -c["prio"])
        _TAX = (t, cats)
    return _TAX


def classify_product(text, marine_ctx=False):
    """제품 문구 → [소분류 id]. 우선순위 높은 소분류부터, 긴 키워드부터. 없으면 ['UNCL']."""
    t, cats = taxonomy()
    n = _norm(text)
    if not n:
        return []
    ctx = marine_ctx or any(k in n for k in ("선박", "조선", "해양", "선용", "marine", "ship", "vessel", "offshore", "해상"))
    hits = []
    for c in cats:
        if any(_norm(x) in n for x in c["neg"]):
            continue
        if c["ctx"] and not ctx:
            continue
        for k in sorted(c["kw"], key=lambda x: -len(x)):
            if _norm(k) and _norm(k) in n:
                hits.append((c["prio"], len(k), c["id"]))
                break
    if not hits:
        return ["UNCL"]
    hits.sort(key=lambda h: (-h[0], -h[1]))
    out = []
    for _, _, cid in hits:
        if cid not in out:
            out.append(cid)
    return out[:4]


def parse_products(html):
    """주요 제품 표 → [{prod, share, amt}]. 회사마다 열이 달라 '품목/제품/구분' 열과 '매출액·비중' 열을 찾는다."""
    out = []
    for t in parse_tables(html):
        cols = [_norm(c) for c in t["cols"]]
        if not cols or len(t["rows"]) < 1:
            continue
        i_name = next((i for i, c in enumerate(cols) if any(k in c for k in ("품목", "제품", "구분", "주요제품", "품명", "제품명", "서비스"))), None)
        # 비중 열은 이름에 '비율/비중'이 있는 열만 믿는다. '%'는 '(단위: 백만원, %)' 같은 단위
        # 캡션이 금액 열에도 붙어 한국카본의 매출액 430,877이 '비중 430877%'로 실렸다.
        i_share = next((i for i, c in enumerate(cols) if "비율" in c or "비중" in c), None)
        if i_share is None:
            i_share = next((i for i, c in enumerate(cols) if c.endswith("%") or "(%)" in c), None)
        i_amt = next((i for i, c in enumerate(cols) if ("매출" in c or "금액" in c) and i != i_share), None)
        if i_name is None or (i_share is None and i_amt is None):
            continue
        cur, mul, _ = unit_of(t.get("lead"), t.get("cols"))
        for r in t["rows"]:
            if i_name >= len(r):
                continue
            name = r[i_name].strip()
            if not name or re.search(r"합\s*계|총\s*계|소\s*계", name):
                continue
            share = num_of(r[i_share]) if i_share is not None and i_share < len(r) else None
            amt = num_of(r[i_amt]) if i_amt is not None and i_amt < len(r) else None
            if amt is not None and mul != 1.0:
                amt = round(amt * mul, 3)
            if share is not None and share > 100:      # 비중이 100%를 넘으면 금액을 잘못 읽은 것이다
                amt, share = (amt if amt is not None else share), None
            if share is None and amt is None:
                continue
            out.append({"prod": name, "share": share, "amt": amt, "cur": cur})
    return out


def find_yard_mentions(text):
    """본문에서 조선사 언급을 센다. {yard_id: count}."""
    found = {}
    for yid, pat in YARD_NAMES.items():
        n = len(re.findall(pat, text))
        if n:
            found[yid] = n
    return found


def _text_of(html):
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t\xa0]+", " ", s)


def parse_major_customers(html):
    """'주요 매출처'·'10% 이상 고객' 표/문장에서 비중을 뽑는다(있으면)."""
    text = _text_of(html)
    out = []
    for m in re.finditer(r"([가-힣A-Za-z&()㈜ ]{2,24}(?:중공업|조선|오션|조선해양|HHI|SHI|DSME))[^0-9%]{0,40}?(\d{1,2}(?:\.\d)?)\s*%", text):
        party = m.group(1).strip()
        # 상대 표기를 조선사 id 로 정규화한다 — 문장 조각('…매출기준으로 현대중공업')이 그대로
        # 화면에 실리던 것을 막고, 페이지가 조선사 링크를 걸 수 있게.
        yid = next((k for k, pat in YARD_NAMES.items() if re.search(pat, party)), None)
        if not yid:
            continue
        out.append({"party": party[-12:], "yard": yid, "share": float(m.group(2)), "basis": "text"})
    seen, uniq = set(), []
    for c in out:
        if c["yard"] in seen:
            continue
        seen.add(c["yard"]); uniq.append(c)
    return uniq[:8]


def collect_one(rec, quarter, force=False):
    st = rec["stock"]
    path = os.path.join(CACHE, st, quarter + ".json")
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    start, end = report_window(quarter)
    reports = pick_report(search_reports(st, start, end, report_kind(quarter)), quarter)
    if not reports and int(quarter[5]) != 4:                      # 코넥스 등 연 1회
        q2 = "%dQ4" % (int(quarter[:4]) - 1)
        start, end = report_window(q2)
        reports = pick_report(search_reports(st, start, end, report_kind(q2)), q2)
        quarter = q2 if reports else quarter
    out = {"stock": st, "quarter": quarter, "ok": False, "note": ""}
    if not reports:
        out["note"] = "정기보고서 없음"
        return out
    rcp, title = reports[0]
    nodes = toc(rcp)
    found = find_sections(nodes, SECTIONS)
    out.update({"rcp": rcp, "title": title})
    texts, products, cust = [], [], []
    for key in ("products", "sales", "overview"):
        if key not in found:
            continue
        html = fetch_section(found[key])
        texts.append(_text_of(html))
        if key == "products":
            products = parse_products(html)
        if key in ("sales", "products"):
            cust += parse_major_customers(html)
    blob = " ".join(texts)
    out["products"] = products
    out["mentions"] = find_yard_mentions(blob)
    out["customers"] = cust
    out["marine_ctx"] = bool(re.search(r"선박|조선|해양|선용|marine|offshore", blob))
    out["ok"] = bool(texts)
    if not out["ok"]:
        out["note"] = "II 절을 찾지 못함"
        return out
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


def _overrides():
    p = os.path.join(ASSETS, "parts_override.csv")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[(row["stock"], _norm(row["prod_text"]))] = row["cat"]
    return out


def build(quarter):
    uni = load_universe()
    ovr = _overrides()
    cos, uncl = [], []
    for r in uni:
        if r["role"] not in ("equip", "engine", "steel"):
            continue
        p = os.path.join(CACHE, r["stock"], quarter + ".json")
        d = None
        if os.path.isdir(os.path.dirname(p)):
            fs = sorted(os.listdir(os.path.dirname(p)))
            if fs:
                with open(os.path.join(os.path.dirname(p), fs[-1]), encoding="utf-8") as f:
                    d = json.load(f)
        ctx = bool(d and d.get("marine_ctx")) or r["industry"] == "선박 및 보트 건조업" or bool(r.get("reason"))
        cats = []
        seen = set()
        srcs = (d.get("products") if d else None) or []
        if not srcs:
            srcs = [{"prod": r["product"], "share": None, "amt": None, "cur": None, "kind": True}]
        for pr in srcs:
            if pr.get("share") is not None and pr["share"] > 100:     # 옛 캐시의 오독 방어
                pr = dict(pr, amt=pr.get("amt") if pr.get("amt") is not None else pr["share"], share=None)
            key = (r["stock"], _norm(pr["prod"]))
            ids = [ovr[key]] if key in ovr else classify_product(pr["prod"], ctx)
            for cid in ids:
                if cid == "UNCL":
                    uncl.append((r["stock"], r["name"], pr["prod"]))
                cats.append({"cat": cid, "prod": pr["prod"], "share": pr.get("share"), "amt": pr.get("amt"),
                             "est": len(ids) > 1 or bool(pr.get("kind")), "basis": ("kind" if pr.get("kind") else "report")})
        # 시드 사유에 적힌 제품도 분류에 보탠다(KIND 문구가 빈약한 회사: 한국카본 '카본')
        if r.get("reason"):
            for cid in classify_product(r["reason"], True):
                if cid != "UNCL" and cid not in {c["cat"] for c in cats}:
                    cats.append({"cat": cid, "prod": r["reason"].split("—")[-1].strip(), "share": None, "amt": None, "est": True, "basis": "seed"})
        yards = []
        for yid, n in sorted(((d or {}).get("mentions") or {}).items(), key=lambda kv: -kv[1]):
            yards.append({"yard": yid, "mentions": n, "basis": "text", "share": None})
        for c in (d or {}).get("customers") or []:
            yards.append({"yard": c["party"], "mentions": None, "basis": "text", "share": c["share"]})
        cos.append({"stock": r["stock"], "nm": r["name"], "mkt": r["market"], "ind": r["industry"],
                    "role": r["role"], "prod_raw": r["product"], "reason": r.get("reason", ""),
                    "cats": cats, "yards": yards, "rcp": (d or {}).get("rcp"), "quarter": (d or {}).get("quarter"),
                    "confirmed": bool(yards), "seen": bool(d)})
    write_asset("suppliers.json", {"quarter": quarter, "n": len(cos), "cos": cos})
    with open(os.path.join(ASSETS, "unclassified.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stock", "name", "prod_text"])
        for row in uncl:
            w.writerow(row)
    return cos, uncl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--quarter", default=None)
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    q = a.quarter or latest_quarter()
    recs = [r for r in load_universe() if r["role"] in ("equip", "engine", "steel")]
    if a.only:
        sel = set(a.only.split(","))
        recs = [r for r in recs if r["stock"] in sel]
    if a.collect:
        for r in recs:
            try:
                d = collect_one(r, q, a.force)
            except Exception as e:
                print("%s %s 실패: %s" % (r["stock"], r["name"], e), file=sys.stderr)
                continue
            print("%s %-12s %s 제품 %d · 조선사 언급 %s" % (r["stock"], r["name"][:12], "✓" if d.get("ok") else "✗ " + d.get("note", ""),
                                                      len(d.get("products") or []), d.get("mentions") or {}))
    if a.build:
        cos, uncl = build(q)
        from collections import Counter
        print("기자재사 %d · 조선사 언급 확인 %d · 미분류 제품 %d" % (len(cos), sum(1 for c in cos if c["confirmed"]), len(uncl)))
        print("소분류 분포:", dict(Counter(c["cat"] for co in cos for c in co["cats"]).most_common(12)))


if __name__ == "__main__":
    sys.exit(main())
