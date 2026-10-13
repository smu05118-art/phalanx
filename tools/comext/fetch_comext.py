#!/usr/bin/env python3
"""Eurostat Comext 월별 수출 수집기 (리서치 나우캐스트용).

설정(tools/comext/series.json)의 각 시리즈에 대해 Eurostat Comext DS-045409
(reporter × partner × CN8 × flow, 월별, EUR)를 받아 정규화 JSON으로 저장한다.

규약(AGENTS.md): stdlib만 · fail-closed(검증 실패 시 기존 파일 보존, 비정상 종료) ·
https + hostname 정확 일치 · 응답 크기 상한 · tmp 쓰기 후 os.replace · 키 정렬 정규화 ·
window-merge(API가 과거 월을 덜 주면 기존 값 보존, 겹치는 월은 최신 리비전으로 덮어씀).
"""
import argparse
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

HOST = "ec.europa.eu"
BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"
MAX_BYTES = 8 * 1024 * 1024
MIN_MONTHS = 60


class FetchError(Exception):
    pass


def build_url(spec):
    params = [("format", "JSON"), ("lang", "en"), ("reporter", spec["reporter"]),
              ("product", spec["product"]), ("flow", str(spec["flow"])),
              ("indicators", "VALUE_IN_EUROS"), ("freq", "M"), ("sinceTimePeriod", spec["since"])]
    params += [("partner", p) for p in spec["partners"]]
    url = BASE + "?" + urllib.parse.urlencode(params)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        raise FetchError("허용되지 않은 출처: %s" % url)
    return url


def http_get(url, timeout=120):
    req = urllib.request.Request(url, headers={"User-Agent": "phalanx-comext/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final = urllib.parse.urlparse(resp.geturl())
        if final.scheme != "https" or final.hostname != HOST:
            raise FetchError("리다이렉트 출처 거부: %s" % resp.geturl())
        body = resp.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise FetchError("응답 크기 상한 초과")
    return body


def parse_jsonstat(raw, spec):
    """JSON-stat 2.0 → {partner: {YYYY-MM: EUR}}. 값이 없는 셀은 키 자체를 두지 않는다."""
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise FetchError("JSON 파싱 실패: %s" % e)
    if doc.get("error"):
        raise FetchError("API 오류: %s" % doc["error"])
    ids, size, dim = doc.get("id"), doc.get("size"), doc.get("dimension")
    if not (isinstance(ids, list) and isinstance(size, list) and isinstance(dim, dict) and len(ids) == len(size)):
        raise FetchError("JSON-stat 구조 불일치")
    for fixed in ("freq", "reporter", "product", "flow", "indicators"):
        if fixed not in ids or size[ids.index(fixed)] != 1:
            raise FetchError("고정 차원 %s 크기가 1이 아님" % fixed)
    pidx = dim["partner"]["category"]["index"]
    tidx = dim["time"]["category"]["index"]
    missing = [p for p in spec["partners"] if p not in pidx]
    if missing:
        raise FetchError("요청 partner 누락: %s" % missing)
    strides, acc = {}, 1
    for name, n in reversed(list(zip(ids, size))):
        strides[name] = acc
        acc *= n
    values = doc.get("value", {})
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    out = {}
    for p, pi in pidx.items():
        series = {}
        for t, ti in tidx.items():
            v = values.get(str(pi * strides["partner"] + ti * strides["time"]))
            if v is None:
                continue
            if not isinstance(v, (int, float)) or v < 0:
                raise FetchError("비정상 값 %s %s: %r" % (p, t, v))
            series[t] = int(round(v))
        out[p] = series
    return out, doc.get("updated", "")


def merge(old, new):
    merged = {}
    for p in set(old) | set(new):
        s = dict(old.get(p, {}))
        s.update(new.get(p, {}))
        merged[p] = dict(sorted(s.items()))
    return merged


def validate(spec, series):
    world = series.get(spec["total_partner"], {})
    if len(world) < MIN_MONTHS:
        raise FetchError("%s 시계열이 %d개월뿐(최소 %d)" % (spec["total_partner"], len(world), MIN_MONTHS))
    months = sorted(world)
    y, m = int(months[0][:4]), int(months[0][5:])
    for ym in months:
        if ym != "%04d-%02d" % (y, m):
            raise FetchError("%s 월 결측: %s 기대, %s 발견" % (spec["total_partner"], "%04d-%02d" % (y, m), ym))
        m += 1
        if m > 12:
            y, m = y + 1, 1


def write_atomic(path, obj):
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def run(config_path, root, fetch=http_get):
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    for spec in cfg["series"]:
        out_path = os.path.join(root, spec["output"])
        old = {}
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f).get("partners", {})
        new, updated = parse_jsonstat(fetch(build_url(spec)), spec)
        merged = merge(old, new)
        validate(spec, merged)
        write_atomic(out_path, {
            "dataset": "DS-045409", "source": "Eurostat Comext (EU trade since 1988 by HS2-4-6 and CN8)",
            "source_updated": updated, "reporter": spec["reporter"], "product": spec["product"],
            "flow": "export" if str(spec["flow"]) == "2" else "import", "unit": "EUR",
            "label": spec.get("label", ""), "total_partner": spec["total_partner"],
            "partners": merged,
        })
        print("ok %s: %d partners, last %s" % (spec["output"], len(merged), max(merged[spec["total_partner"]])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "series.json"))
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    try:
        run(a.config, a.root)
    except (FetchError, OSError, KeyError) as e:
        print("FAIL (기존 파일 보존): %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
