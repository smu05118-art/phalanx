#!/usr/bin/env python3
"""Panoptes 🤖 LLM 탭 데이터 수집기 — OpenRouter 랭킹 (CC BY 4.0).

openrouter.ai/rankings 페이지가 쓰는 공개 프론트엔드 API를 그대로 읽어
panoptes/data/llm_rankings.json 하나로 정규화한다. 인증 불필요.

출처 고지: Rankings data by OpenRouter (openrouter.ai/rankings), CC BY 4.0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request

BASE = "https://openrouter.ai/api/frontend/v1"  # https + openrouter.ai 고정 (허용 출처 단일)
UA = "Mozilla/5.0 (compatible; PanoptesLLM/1.0; +https://smu05118-art.github.io/phalanx/panoptes/)"
MAX_RESP_BYTES = 30 * 1024 * 1024  # 응답 크기 상한
MAX_WARNINGS = 6                   # 섹션 실패 초과 시 fail-closed (기존 파일 보존)

VIEWS = ["day", "week", "month", "trending"]
LANGS = ["English", "Korean", "Japanese", "Chinese (Simplified)", "Chinese (Traditional)",
         "Spanish", "French", "German", "Russian", "Portuguese", "Vietnamese", "Indonesian"]
PROGS = ["Python", "TypeScript", "JavaScript", "Java", "Go", "Rust", "C", "SQL", "Ruby", "Swift"]
CTX_BUCKETS = ["1K", "10K", "100K", "1M", "10M"]
LEADERBOARD_TOP = 60
BENCH_TOP = 45
PERF_TOP = 120
SESSION_MODELS_TOP = 14


def fetch(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{BASE}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                final = getattr(r, "url", url)
                if not str(final).startswith("https://openrouter.ai/"):
                    raise RuntimeError(f"redirected off allowlist: {final}")
                raw = r.read(MAX_RESP_BYTES + 1)
                if len(raw) > MAX_RESP_BYTES:
                    raise RuntimeError("response too large")
                return json.loads(raw.decode("utf-8"))
        except Exception as e:  # noqa: BLE001 — 재시도 후 최종 실패만 전파
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def series_pack(rows: list[dict]) -> dict:
    """[{x, ys:{k:v}}] → {dates:[], series:{k:[v...]}} (결측=0)."""
    rows = sorted(rows, key=lambda r: r.get("x", ""))
    dates = [r["x"] for r in rows]
    keys: list[str] = []
    for r in rows:
        for k in (r.get("ys") or {}):
            if k not in keys:
                keys.append(k)
    series = {k: [round(float((r.get("ys") or {}).get(k) or 0)) for r in rows] for k in keys}
    return {"dates": dates, "series": series}


def agg_leaderboard(rows: list[dict]) -> list[dict]:
    """일별 행을 (permaslug, variant)로 합산해 토큰순 정렬."""
    acc: dict[tuple, dict] = {}
    for r in rows:
        key = (r.get("model_permaslug"), r.get("variant") or "standard")
        a = acc.setdefault(key, {
            "m": key[0], "v": key[1], "pt": 0, "ct": 0, "rq": 0, "ch": None,
        })
        # tool_calls·reasoning·cached·media 필드는 이 엔드포인트에서 항상 0 — 수집 제외
        a["pt"] += int(r.get("total_prompt_tokens") or 0)
        a["ct"] += int(r.get("total_completion_tokens") or 0)
        a["rq"] += int(r.get("count") or 0)
        if r.get("change") is not None:
            a["ch"] = r["change"]
    out = []
    for a in acc.values():
        a["tok"] = a["pt"] + a["ct"]
        out.append(a)
    out.sort(key=lambda x: -x["tok"])
    return out[:LEADERBOARD_TOP]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="panoptes/data/llm_rankings.json")
    args = ap.parse_args()

    warnings: list[str] = []

    def safe(path, params=None):
        try:
            return fetch(path, params)
        except Exception as e:  # noqa: BLE001 — 섹션 하나 실패로 전체를 죽이지 않는다
            warnings.append(f"{path} {params or ''}: {e}")
            return None

    # ── 리더보드 (일/주/월/트렌딩) ──────────────────────────────
    leaderboard = {}
    as_of = None
    for v in VIEWS:
        d = safe("rankings/models", {"view": v})
        rows = (d or {}).get("data") or []
        if rows:
            as_of = max(as_of or "", max(r.get("date", "")[:10] for r in rows))
        leaderboard[v] = agg_leaderboard(rows)

    empty_views = [v for v in VIEWS if not leaderboard.get(v)]
    if empty_views:
        print(f"FATAL: leaderboard views empty ({','.join(empty_views)}) — aborting without touching output",
              file=sys.stderr)
        for w in warnings:
            print("warn:", w, file=sys.stderr)
        return 1

    # ── 시계열류 ────────────────────────────────────────────────
    top_chart = safe("rankings/model-rankings-chart")
    top_chart = series_pack(((top_chart or {}).get("data") or {}).get("data") or [])
    market = series_pack((safe("rankings/market-share") or {}).get("data") or [])
    tools_s = series_pack((safe("rankings/tools") or {}).get("data") or [])
    images_s = series_pack((safe("rankings/images") or {}).get("data") or [])

    # 실패한 tag도 빈 팩으로 키를 유지 (프론트 칩 구성이 흔들리지 않게)
    languages = {}
    for t in LANGS:
        d = safe("rankings/natural-language", {"tag": t})
        languages[t] = series_pack((d or {}).get("data") or [])
    programming = {}
    for t in PROGS:
        d = safe("rankings/programming-language", {"tag": t})
        programming[t] = series_pack((d or {}).get("data") or [])
    context = {}
    for b in CTX_BUCKETS:
        d = safe("rankings/context-length", {"bucket": b})
        context[b] = series_pack((d or {}).get("data") or [])

    # ── 벤치마크 ────────────────────────────────────────────────
    bench_raw = (safe("rankings/benchmarks") or {}).get("data") or {}
    aa = bench_raw.get("aaData") or {}

    def bench_rows(key):
        rows = aa.get(key) or []
        out = []
        for r in rows:
            slug = r.get("heuristic_openrouter_slug") or r.get("openrouter_slug") or r.get("permaslug")
            if slug and r.get("score") is not None:
                out.append({"m": slug, "p": r.get("permaslug"), "name": r.get("aa_name"),
                            "score": round(float(r["score"]), 1)})
        out.sort(key=lambda x: -x["score"])
        return out[:BENCH_TOP]

    benchmarks = {
        "intelligence": bench_rows("intelligence"),
        "coding": bench_rows("coding"),
        "agentic": bench_rows("agentic"),
        "pct": aa.get("percentilesBySlug") or {},
        "price_in": {k: round(v, 4) for k, v in (bench_raw.get("weightedInputPrices") or {}).items()},
        "cost_req": {k: round(v, 5) for k, v in (bench_raw.get("costPerRequest") or {}).items()},
    }

    # ── 태스크별 지출 ───────────────────────────────────────────
    task_raw = (safe("rankings/task-spend") or {}).get("data") or {}

    def pack_tasks(side):
        s = task_raw.get(side) or {}
        return {
            "window": s.get("windowDays"),
            "macro": [{"key": m.get("key"), "label": m.get("label"),
                       "share": m.get("spendShare")} for m in (s.get("macroCategories") or [])],
            "tasks": [{"tag": t.get("tag"), "cat": t.get("macroCategory"),
                       "share": t.get("spendShareOfTotal"),
                       "models": [{"m": mm.get("model"), "share": mm.get("share"),
                                   "d": mm.get("deltaPp")} for mm in (t.get("models") or [])[:5]]}
                      for t in (s.get("tasks") or [])],
        }

    tasks = {"spend": pack_tasks("spend"), "tokens": pack_tasks("tokens")}

    # ── 세션 비용 ───────────────────────────────────────────────
    # 최저가 순이 아니라 "사용량 상위" 모델 위주로 담아야 의미가 있음
    usage_rank = {}
    for i, r in enumerate(leaderboard["month"] or leaderboard["week"]):
        usage_rank.setdefault(r["m"], i)
    sc_raw = (safe("rankings/session-cost") or {}).get("data") or {}
    harnesses = []
    for h in sc_raw.get("harnesses") or []:
        models = []
        for m in h.get("models") or []:
            pts = {p["bucket"]: round(float(p["medianUsd"]), 4)
                   for p in m.get("points") or []
                   if p.get("bucket") and p.get("medianUsd") is not None}
            if pts.get("core") is not None:  # 본격 세션 값 없는 모델은 비교 불가
                models.append({"m": m.get("model"), "pts": pts})
        models.sort(key=lambda x: usage_rank.get(x["m"], usage_rank.get(x["m"].split(":")[0], 9999)))
        harnesses.append({"label": h.get("label"), "models": models[:SESSION_MODELS_TOP]})
    session_cost = {"window": sc_raw.get("windowDays"), "end": sc_raw.get("windowEnd"), "harnesses": harnesses}

    # ── Top Apps ────────────────────────────────────────────────
    apps_raw = (safe("rankings/apps") or {}).get("data") or {}
    apps = {}
    for k in ("day", "week", "month"):
        apps[k] = [{
            "rank": a.get("rank"), "title": (a.get("app") or {}).get("title") or f"app {a.get('app_id')}",
            "tok": int(a.get("total_tokens") or 0), "rq": int(a.get("total_requests") or 0),
            "url": (a.get("app") or {}).get("origin_url") or (a.get("app") or {}).get("main_url"),
            "desc": ((a.get("app") or {}).get("description") or "")[:140],
        } for a in (apps_raw.get(k) or [])[:20]]

    # ── 성능 (지연·처리량) ──────────────────────────────────────
    perf_raw = (safe("rankings/performance") or {}).get("data") or []
    perf_raw = sorted(perf_raw, key=lambda r: -(r.get("request_count") or 0))[:PERF_TOP]
    performance = [{
        "m": r.get("slug") or r.get("id"), "name": r.get("name"), "a": r.get("author"),
        "rq": r.get("request_count"), "lat": r.get("p50_latency"), "tps": r.get("p50_throughput"),
        "lp": r.get("best_latency_provider"), "tp": r.get("best_throughput_provider"),
        "price": r.get("best_throughput_price"),
    } for r in perf_raw]

    # ── 모델 카탈로그 (참조된 것만) ─────────────────────────────
    catalog_raw = (safe("catalog/models") or {}).get("data") or []
    # 동일 slug에 (batch) 같은 변형 항목이 함께 있어 — 무변형 항목이 우선하도록 정렬
    catalog_raw = sorted(catalog_raw, key=lambda c: ("(" in (c.get("short_name") or c.get("name") or "")))
    cat_by_perma, cat_by_slug = {}, {}
    for c in catalog_raw:
        e = {"n": c.get("short_name") or c.get("name"), "a": c.get("author"),
             "ad": c.get("author_display_name") or c.get("author"),
             "ctx": c.get("context_length"), "r": bool(c.get("supports_reasoning"))}
        if c.get("permaslug"):
            cat_by_perma.setdefault(c["permaslug"], e)
        if c.get("slug"):
            cat_by_slug.setdefault(c["slug"], e)

    referenced: set[str] = set()
    for v in VIEWS:
        referenced.update(r["m"] for r in leaderboard[v] if r.get("m"))
    for pack in [top_chart, tools_s, images_s, *languages.values(), *programming.values(), *context.values()]:
        referenced.update(pack.get("series", {}).keys())
    for side in tasks.values():
        for t in side.get("tasks") or []:
            referenced.update(mm["m"] for mm in t.get("models") or [] if mm.get("m"))
    for h in harnesses:
        referenced.update(m["m"] for m in h["models"])
    for b in ("intelligence", "coding", "agentic"):
        referenced.update(r["m"] for r in benchmarks[b])
    referenced.update(r["m"] for r in performance if r.get("m"))

    models = {}
    for slug in sorted(referenced):
        base = slug.split(":")[0]  # ":free" 변형은 본체 카탈로그로
        e = cat_by_perma.get(base) or cat_by_slug.get(base)
        if not e:
            # permaslug 뒤 날짜 접미사 제거 후 slug 재시도 (-20260723 형과 -2025-08-07 형 모두)
            stripped = re.sub(r"-(?:\d{8}|\d{4}-\d{2}-\d{2})$", "", base)
            if stripped != base:
                e = cat_by_slug.get(stripped) or cat_by_perma.get(stripped)
        if e:
            models[slug] = e

    # fail-closed: 핵심 섹션 결손·과다 경고 시 기존 파일을 건드리지 않고 종료
    if len(warnings) > MAX_WARNINGS:
        print(f"FATAL: too many section failures ({len(warnings)}) — keeping existing output", file=sys.stderr)
        for w in warnings:
            print("warn:", w, file=sys.stderr)
        return 1
    if not top_chart.get("dates") or not market.get("dates"):
        print("FATAL: core chart data empty — keeping existing output", file=sys.stderr)
        return 1

    out = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "source": "OpenRouter (openrouter.ai/rankings) · CC BY 4.0",
        "models": models,
        "leaderboard": leaderboard,
        "top_chart": top_chart,
        "market_share": market,
        "benchmarks": benchmarks,
        "tasks": tasks,
        "session_cost": session_cost,
        "languages": languages,
        "programming": programming,
        "context": context,
        "tools_series": tools_s,
        "images_series": images_s,
        "apps": apps,
        "performance": performance,
        "warnings": warnings,
    }
    # 원자적 쓰기: tmp에 쓰고 os.replace (구성 순서 고정 → 같은 데이터 = 같은 바이트)
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(args.output)) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, args.output)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    print(f"ok: {args.output} ({len(payload)/1024:.0f}KB, as_of={as_of}, models={len(models)}, warnings={len(warnings)})")
    for w in warnings:
        print("warn:", w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
