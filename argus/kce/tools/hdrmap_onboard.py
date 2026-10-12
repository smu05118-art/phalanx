#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hdrmap_onboard — 신규 편입사 머리행 온보딩과 갱신 요약(설계 B 2·3단계, kce).

왜 있나
  모집단(kce_universe --write)이 새 종목을 받아들이면 엔진(hdrmap.onboard)이 대기열에 kind new_company 를
  연다. 그 회사의 머리행이 지도에 처음 적히기 전까지 사람은 '새 회사가 들어왔다'는 것만 알고 '파서가 그 회사
  표를 읽는가'는 모른다. 이 도구는 같은 job 안에서(새 워크플로 없이) 그 빈칸을 메운다:
    1. 대기열의 open new_company 를 읽는다(유일한 입력 — git 이력을 따로 보지 않는다).
    2. 최근 2분기(latest_quarter 와 그 직전)의 lite 수집 캐시(series_cache — 같은 job 의 kce_series 가 방금
       받았다)를 **재생**해 지도에 적는다(DART 0). 캐시가 없고 --fetch 면 그 칸만 kce_series.collect_one 으로
       받는다(분기당 검색·목차·절 2 ≈ 4요청 → 신규사당 ≤ 8, kce_fetch 의 전역 간격 게이트를 그대로 탄다).
    3. 프로브 등급이 'none'(수주 절 없음)이면 지도 대상이 아니라 new_company 를 닫고, 'agg'(절은 있으나
       인식 0)면 '표 없음'으로 적고 zero_rows 를 연다 — 사람이 고칠 거리는 그쪽이다.
    4. 커밋(hdrmap.write) — 회사가 처음 커밋되면 엔진이 new_company 를 resolved 로 돌린다.
    5. --render: lite 지도 페이지(argus/kce/headers_lite.html)를 지도에서 다시 그린다(멱등). 정밀 17사
       페이지(headers.html)는 kce_build 만 그린다 — 여기서 그리면 lite 종목이 정밀 지도로 샌다.
  --snapshot / --summary 는 워크플로가 실행 전후 지도·대기열을 비교해 Step Summary·커밋 메시지 접미
  '신규 편입 n(<종목>) · 머리행 +n표 · 미지 열 open n(회귀 m)' 을 만든다. 보고 파일은 커밋하지 않는다
  (RUNNER_TEMP 에만 쓴다).

사용(argus/kce/tools 에서):
    python3 hdrmap_onboard.py --tab kce --snapshot "$RUNNER_TEMP/hdr_before"
    python3 hdrmap_onboard.py --tab kce --fetch --render
    python3 hdrmap_onboard.py --tab kce --summary --before "$RUNNER_TEMP/hdr_before" --github-output "$GITHUB_OUTPUT"
규약: stdlib 전용 · 산출물에 실행 시각을 넣지 않는다 · 엔진 오류는 엔진이 stderr + engine_error 로 남긴다.
"""
import argparse
import json
import os
import shutil
import sys

import hdrmap
from kce_lib import CORP, latest_quarter

HERE = os.path.dirname(os.path.abspath(__file__))
KCE = os.path.dirname(HERE)
LITE_PAGE = os.path.join(KCE, "headers_lite.html")
LITE_TITLE = "파서헤드 지도 — 국내 상장 건설사(lite)"
MAX_FETCH_Q = 2                 # 신규사당 받아 볼 분기 수(설계 B2: 최근 2분기)


def q_prev(q):
    y, n = int(q[:4]), int(q[5])
    return "%dQ%d" % (y - 1, 4) if n == 1 else "%dQ%d" % (y, n - 1)


def newest_probe(assets):
    """가장 최근 프로브 산출물의 {종목: 행}. kce_series·kce_page 와 같은 규칙(파일명 정렬 마지막)."""
    cands = sorted(f for f in os.listdir(assets) if f.startswith("probe_") and f.endswith(".json"))
    if not cands:
        return {}
    with open(os.path.join(assets, cands[-1]), encoding="utf-8") as f:
        return {r["stock"]: r for r in json.load(f)["rows"]}


def _corp_stocks():
    return {v["stock"] for v in CORP.values() if v.get("stock")}


def onboard_kce(fetch=False, root=None, probe=None, quarters=None, log=sys.stderr):
    """open new_company → 최근 2분기 캐시 재생(·부족분 수집) → 기록·커밋. 결과 요약 dict."""
    import kce_series
    items = hdrmap.open_items("kce", root=root, kind="new_company")
    if probe is None:
        probe = newest_probe(os.path.join(HERE, "assets"))
    qs = quarters or [latest_quarter(), q_prev(latest_quarter())]
    corp = _corp_stocks()
    out = {"open": len(items), "recorded": [], "closed_none": [], "zero_rows": [], "waiting": [], "fetched": 0}
    for it in sorted(items, key=lambda x: x["id"]):
        st, key = it.get("stock"), it.get("key")
        if not st or st in corp:
            # 정밀 17사 슬러그는 kce_build 가 첫 갱신 때 커밋하며 닫는다(lite 캐시 재생 대상 아님).
            out["waiting"].append(key)
            continue
        rec = {"stock": st, "slug": key, "name": it.get("name") or key}
        tier = (probe.get(st) or {}).get("tier")
        if tier == "none":
            # 수주 절 자체가 없다(실내건축·발전 등) — 머리행 지도 대상이 아니다. 닫되 사유는 resolved_in 분기로 남는다.
            hdrmap.resolve_clean("kce", key, "*", qs[0], root=root)
            out["closed_none"].append(st)
            continue
        got = 0
        for q in qs[:MAX_FETCH_Q]:
            path = kce_series.cache_path(st, q)
            res = None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    res = json.load(f)
            elif fetch and tier in ("site", "segment", None):
                res = kce_series.collect_one(st, q)
                out["fetched"] += 1
            if not res:
                continue
            if res.get("ok") and kce_series.stage_headers(rec, q, res, root=root):
                got += 1
            elif not res.get("ok") and "인식 0" in (res.get("note") or ""):
                # 절은 있는데 파서가 표를 하나도 못 읽었다 — '표 없음'으로 적고 사람 몫(zero_rows)을 연다.
                hdrmap.record("kce", key, q, "orders", [], meta={"name": rec["name"], "stock": st}, root=root)
                hdrmap.enqueue("kce", {"kind": "zero_rows", "key": key, "stock": st, "name": rec["name"],
                                       "role": "orders", "quarter": q, "rcpNo": res.get("rcpNo"),
                                       "reason": res.get("note")}, root=root, strict=False)
                out["zero_rows"].append(st)
                got += 1
        (out["recorded"] if got else out["waiting"]).append(st if got else key)
        if not got:
            log.write("[onboard] %s %s — 최근 %s 캐시 없음(다음 실행에 다시 본다)\n" % (st, rec["name"], "/".join(qs)))
    w = hdrmap.write("kce", root=root) or {}
    out["committed_tables"] = w.get("tables", 0)
    out["resolved"] = w.get("resolved", 0)
    return out


def render_lite(root=None, out_html=None):
    """지도의 lite 종목(키 ∉ 정밀 17사 슬러그)만으로 headers_lite.html 을 그린다. 없으면 아무것도 안 한다."""
    M = hdrmap.load_map("kce", root)
    keys = sorted(k for k in M["companies"] if k not in CORP)
    if not keys:
        return None
    if out_html is None:
        out_html = os.path.join(root, "kce", "headers_lite.html") if root else LITE_PAGE
    return hdrmap.render_headers("kce", out_html=out_html, root=root, keys=keys,
                                 labels={"title": LITE_TITLE}, strict=True, stage=False)


def snapshot(dest, root=None):
    """실행 전 지도·대기열 사본(없으면 빈 꼴) — --summary 의 비교 기준. dest 는 RUNNER_TEMP 아래(커밋 안 됨)."""
    os.makedirs(dest, exist_ok=True)
    for src, name in ((hdrmap.map_path("kce", root), "hdrmap.json"), (hdrmap.queue_path("kce", root), "hdr_queue.json")):
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(dest, name))
        elif os.path.exists(os.path.join(dest, name)):
            os.remove(os.path.join(dest, name))


def _count_tables(M):
    return sum(len(entries) for co in (M.get("companies") or {}).values()
               for by_q in (co.get("roles") or {}).values() for entries in by_q.values())


def summary(before, root=None):
    """실행 전후 비교 → {new: [종목], tables: +n, open: n, regressions: m, line}."""
    def _load(name, default):
        p = os.path.join(before, name) if before else None
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return default
    M0 = _load("hdrmap.json", {"companies": {}})
    Q0 = {i["id"] for i in _load("hdr_queue.json", [])}
    Q1 = hdrmap.load_queue("kce", root)
    new = sorted({i.get("stock") or i["key"] for i in Q1 if i["kind"] == "new_company" and i["id"] not in Q0})
    dt = _count_tables(hdrmap.load_map("kce", root)) - _count_tables(M0)
    n_open = sum(1 for i in Q1 if i["status"] == "open" and i["kind"] == "unknown")
    chk = hdrmap.check("kce", root=root)
    m = len(chk["regressions"])
    line = "신규 편입 %d%s · 머리행 %+d표 · 미지 열 open %d(회귀 %d)" % (
        len(new), "(%s)" % ",".join(new) if new else "", dt, n_open, m)
    return {"new": new, "tables": dt, "open": n_open, "regressions": m, "line": line}


def main(argv=None):
    ap = argparse.ArgumentParser(description="머리행 지도 온보딩·요약(kce)")
    ap.add_argument("--tab", default="kce", choices=["kce"], help="지금은 kce 만 — 다른 탭은 U4 가 붙인다")
    ap.add_argument("--root", default=None, help="argus/ 루트(테스트·점검용)")
    ap.add_argument("--fetch", action="store_true", help="캐시 없는 칸은 DART 에서 받는다(신규사당 ≤ 2분기)")
    ap.add_argument("--render", action="store_true", help="lite 지도 페이지 headers_lite.html 재생성(멱등)")
    ap.add_argument("--snapshot", metavar="DIR", help="실행 전 지도·대기열 사본을 DIR 에")
    ap.add_argument("--summary", action="store_true", help="--before 와 비교한 한 줄 요약")
    ap.add_argument("--before", metavar="DIR", help="--snapshot 으로 만든 디렉터리")
    ap.add_argument("--github-output", metavar="PATH", help="요약을 key=value 로 덧붙일 파일($GITHUB_OUTPUT)")
    a = ap.parse_args(argv)
    if a.snapshot:
        snapshot(a.snapshot, a.root)
        return 0
    if a.summary:
        s = summary(a.before, a.root)
        print(s["line"])
        if a.github_output:
            with open(a.github_output, "a", encoding="utf-8") as f:
                f.write("hdr_new=%d\nhdr_tables=%d\nhdr_open=%d\nhdr_regressions=%d\nhdr_line=%s\n"
                        % (len(s["new"]), s["tables"], s["open"], s["regressions"], s["line"]))
        return 0
    res = onboard_kce(fetch=a.fetch, root=a.root)
    print(json.dumps(res, ensure_ascii=False, sort_keys=True))
    if a.render:
        text = render_lite(a.root)
        print("headers_lite.html — %s" % ("지도에 lite 종목 없음" if text is None else "%d bytes" % len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
