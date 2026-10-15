#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kdef_headers — 한국방산 머리행 지도(argus/kdef/headers.html)와 미지 열 큐. **DART 요청 0.**

공용 엔진(argus/kce/tools/hdrmap.py)으로 reports_cache 의 원문 표(raw_tables)를 **메모리에서** 다시 읽어
(kdef_reports.reparse_dict — 캐시 파일은 쓰지 않는다) 회사 × 표 역할(orders·revenue·segsales·customers) ×
분기를 기록한다. 산출:
  tools/assets/hdrmap.json   지도(채택·비채택·미지 표의 머리행, ent←scope·tag←shape·synth)
  tools/assets/hdr_queue.json 큐(append-only·시각 없음) — 미지 수주형 표(unknown)·실패 분기(no_tables)·
                              합성 머리행 채택(synth)·채택 머리행 바뀜(changed)·신규 편입(new_company, kdef_universe)
  argus/kdef/headers.html    지도 페이지(엔진 템플릿 — tools 밖, Pages 배포)

증분이 기본이다 — 지도에 없는 (회사, 분기)만 재생한다. 매일 전부 다시 적으면 큐가 흔들린다: 엔진은 채택이 생긴
분기에 미지 항목을 닫고, 닫힌 항목이 그보다 뒤 분기로 다시 들어오면 회귀로 연다(reopened +1). 분기 오름차순으로
분기마다 커밋해야 '닫힌 분기 ≥ 열린 분기'가 지켜져 두 번 돌려도 같은 바이트가 나온다(tests/test_headers.py).
파서를 고친 뒤에는 --all 로 전부 다시 읽는다(사람이 돌린다 — kgrid --reparse 와 같은 자리).

    python3 kdef_headers.py --write            # 증분 재생 + 페이지
    python3 kdef_headers.py --write --all      # 파서를 고친 뒤 — 캐시 전부 재생
    python3 kdef_headers.py --check            # 회귀만 exit 1(체계업체 수주표 소실 포함)
    python3 kdef_headers.py --summary --base-queue q0.json --base-map m0.json [--line-out f]
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

import kdef_reports as KR
from kdef_lib import load_asset, norm_col
import hdrmap

TAB = KR.HDR_TAB
TITLE = "한국방산 파서 머리행 지도"
# 절 라벨 — 엔진 ROLE_LABELS 의 이 탭 판. 방산 수주표는 보안 때문에 모양이 다섯 갈래라(item·gross·balance·
# openclose·roll) tag 에 모양을, 미지 표는 `미지:사유` 를 싣는다.
LABELS = {"title": TITLE,
          "orders": ["수주", "수주상황 표 — tag=모양(item·gross·balance·openclose·roll)·미지:사유, 구분=지배/종속"],
          "revenue": ["매출", "내수·수출 매출실적 — tag=근거(segment·customer)"],
          "segsales": ["부문", "부문별 매출(방산비중의 근거)"],
          "customers": ["거래처", "주요 매출처(부품사→체계업체 연결 근거)"]}


def primes():
    try:
        return [r["stock"] for r in load_asset("universe.json")["rows"] if r.get("role") == "prime"]
    except Exception:
        return []


def order():
    """버튼 순서 = 모집단 순서(체계 → 부품 → 소재 → 서비스, 종목코드) — 지도에만 있는 회사는 엔진이 뒤에 붙인다."""
    try:
        return [r["stock"] for r in load_asset("universe.json")["rows"]]
    except Exception:
        return None


def cache_files(cache=None):
    """{분기: [(종목, 경로)…]} — 분기·종목 오름차순."""
    out = {}
    for p in sorted(glob.glob(os.path.join(cache or KR.CACHE, "*", "*.json"))):
        st = os.path.basename(os.path.dirname(p))
        q = os.path.basename(p)[:-5]
        out.setdefault(q, []).append((st, p))
    return dict(sorted(out.items()))


def _tracker(M):
    """{종목: {분기: 채택 머리행(마스킹) | None}} — 지도에 기록된 수주 역할."""
    tr = {}
    for st, co in (M.get("companies") or {}).items():
        for q, entries in ((co.get("roles") or {}).get("orders") or {}).items():
            picked = [e for e in entries if e.get("pick")]
            tr.setdefault(st, {})[q] = (hdrmap.mask_cols(picked[0].get("ncols") or picked[0].get("cols"))
                                        if picked else None)
    return tr


def _prev(tr, st, q):
    """kdef_reports.prev_pick 과 같은 규칙 — 직전 기록 분기에 채택이 있으면 (분기, 마스킹 열)."""
    by = tr.get(st) or {}
    before = sorted(x for x in by if x < q)
    if not before or by[before[-1]] is None:
        return None
    return before[-1], by[before[-1]]


def replay(all_=False, root=None, cache=None, log=sys.stderr):
    """캐시 → 지도·큐. 분기 오름차순, 분기마다 커밋. 반환 {files, skipped, quarters, failed:{갈래: n}}."""
    M = hdrmap.load_map(TAB, root)
    have = {(k, q) for k, co in M["companies"].items() for q in co.get("fq") or []}
    tr = _tracker(M)
    n = skipped = 0
    fk = Counter()
    qs = []
    allf = cache_files(cache)
    latest = {}
    for q, files in allf.items():
        for st, _ in files:
            latest[st] = max(latest.get(st, ""), q)
    for q, files in allf.items():
        staged = 0
        for st, path in files:
            if not all_ and (st, q) in have:
                skipped += 1
                continue
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("stock", st)
            d.setdefault("quarter", q)
            nd, res = KR.reparse_dict(d)
            if not nd.get("ok"):
                fk[nd.get("fail_kind") or "?"] += 1
            # 큐는 회사마다 최신 분기만 — 과거 분기는 지도에만(kdef_reports.hdr_stage 참고)
            recs = KR.hdr_stage(nd, res, prev=_prev(tr, st, q), root=root, queue=(q == latest[st]))
            pk = KR._picked_entry(recs[0])
            tr.setdefault(st, {})[q] = (hdrmap.mask_cols([norm_col(c) for c in pk["cols"]]) if pk else None)
            staged += 1
        if staged:
            hdrmap.write(TAB, root=root, strict=True)
            KR.resolve_not_applicable(root)
            qs.append(q)
        n += staged
    log.write("kdef 머리행 재생: %d파일(건너뜀 %d) · %d분기 · 실패 %s\n" % (n, skipped, len(qs), dict(fk)))
    return {"files": n, "skipped": skipped, "quarters": qs, "failed": dict(sorted(fk.items()))}


def render(root=None):
    return hdrmap.render_headers(TAB, order=order(), labels=LABELS, root=root, strict=True)


def stats(root=None):
    """지도·큐 실측 — 보고·Step Summary 용."""
    M = hdrmap.load_map(TAB, root)
    by_role = Counter()
    picks = Counter()
    for co in M["companies"].values():
        for role, by_q in (co.get("roles") or {}).items():
            for entries in by_q.values():
                by_role[role] += len(entries)
                picks[role] += sum(1 for e in entries if e.get("pick"))
    Q = hdrmap.load_queue(TAB, root)
    opens = [i for i in Q if i["status"] == "open"]
    return {"companies": len(M["companies"]), "tables": sum(by_role.values()),
            "by_role": dict(sorted(by_role.items())), "picked": dict(sorted(picks.items())),
            "queue": len(Q), "open": len(opens),
            "open_by_kind": dict(sorted(Counter(i["kind"] for i in opens).items())),
            "resolved": sum(1 for i in Q if i["status"] == "resolved")}


def _ntables(M):
    return sum(len(e) for co in (M.get("companies") or {}).values()
               for by_q in (co.get("roles") or {}).values() for e in by_q.values())


def summary(base_queue, base_map, root=None):
    """직전 커밋(HEAD) 대비 — 커밋 메시지 꼬리 한 줄과 Step Summary 마크다운.
    꼬리: ` · 신규 편입 n(<종목,…>) · 머리행 +n표 · 미지 열 open n(회귀 m)` (신규 편입이 없으면 그 토막은 뺀다)."""
    q0 = {i["id"]: i for i in (base_queue or [])}
    Q = hdrmap.load_queue(TAB, root)
    M = hdrmap.load_map(TAB, root)
    newco = sorted({i.get("stock") or i["key"] for i in Q if i["kind"] == "new_company" and i["id"] not in q0})
    opened = [i for i in Q if i["status"] == "open" and (i["id"] not in q0 or q0[i["id"]]["status"] != "open")]
    rep = hdrmap.check(TAB, critical=primes(), root=root)
    dt = _ntables(M) - _ntables(base_map or {})
    parts = []
    if newco:
        parts.append("신규 편입 %d(%s)" % (len(newco), ",".join(newco)))
    parts.append("머리행 %+d표" % dt)
    parts.append("미지 열 open %d(회귀 %d)" % (rep["open"], len(rep["regressions"])))
    line = " · " + " · ".join(parts)
    md = ["### kdef 머리행 지도", "",
          "| 항목 | 값 |", "|---|---|",
          "| 지도 표 수(증감) | %d (%+d) |" % (_ntables(M), dt),
          "| 큐 open | %d %s |" % (rep["open"], json.dumps(rep["open_by_kind"], ensure_ascii=False)),
          "| 회귀(직전 분기 채택 → 이번 미지·체계업체 수주표 소실) | %d |" % len(rep["regressions"]),
          "| 신규 편입 | %s |" % (", ".join(newco) or "-"), ""]
    if opened:
        md += ["새로 열린 항목(사람 확인 — 큐는 손으로 고치지 않고 사전·파서·테스트를 고친다):", "",
               "| id | 종류 | 회사 | 역할 | 분기 | 사유 | 열 |", "|---|---|---|---|---|---|---|"]
        def cell(x):
            return (x or "").replace("|", "/").replace("\n", " ")     # 표 칸 안의 '|' 는 마크다운 표를 깬다
        for i in sorted(opened, key=lambda x: (x["kind"], x["key"], x["quarter_first"]))[:40]:
            md.append("| %s | %s | %s %s | %s | %s | %s | %s |" % (
                i["id"][:7], i["kind"], i["key"], cell(i.get("name"))[:12], i["role"], i["quarter_first"],
                cell(i.get("reason"))[:40], cell(" · ".join(i.get("cols_raw") or []))[:80]))
    for r in rep["regressions"]:
        md.append("- 회귀: %s %s %s (직전 정상 %s, %s)" % (r["key"], r["role"], r["quarter"], r["prev_clean"], r["kind"]))
    return line, "\n".join(md) + "\n", rep


def _load(path, default):
    if not path or not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        txt = f.read().strip()
    return json.loads(txt) if txt else default


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="캐시 재생(증분) → 지도·큐 + headers.html")
    ap.add_argument("--all", action="store_true", help="--write 와 함께: 캐시 전부 재생(파서를 고친 뒤)")
    ap.add_argument("--check", action="store_true", help="회귀만 exit 1")
    ap.add_argument("--summary", action="store_true", help="HEAD 대비 수치(커밋 꼬리·Step Summary)")
    ap.add_argument("--base-queue", default=None)
    ap.add_argument("--base-map", default=None)
    ap.add_argument("--line-out", default=None, help="--summary: 커밋 메시지 꼬리 한 줄을 이 파일에")
    a = ap.parse_args(argv)
    rc = 0
    if a.write:
        replay(all_=a.all)
        render()
        print(json.dumps(stats(), ensure_ascii=False))
    if a.summary:
        line, md, _ = summary(_load(a.base_queue, []), _load(a.base_map, {}))
        if a.line_out:
            with open(a.line_out, "w", encoding="utf-8") as f:
                f.write(line + "\n")
        sys.stdout.write(md)
    if a.check:
        rep = hdrmap.check(TAB, critical=primes())
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        rc = rep["exit"]
    return rc


if __name__ == "__main__":
    sys.exit(main())
