#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kchem_inputs — ARGUS 빌더 산출물을 읽기 전용으로 파싱하고 스키마를 검증한다.

입력(전부 레포 안의 빌더 산출물, 수정 금지):
  argus/data/argus_data.js        window.ARGUS = {...}          요약(asof·spread.series·chains·health)
  argus/data/chunk_<cat>.js       window.ARGUS_CHUNKS["spread:<cat>"] = {kind,key,axis,series[{..,v}]}
  argus/data/connections.js       window.ARGUS_CONNECTIONS = {total,connected,rows[{sid,..,observations}]}
  argus/data_map.js               window.ARGUS_MAP = {counts,groups,chains,items[]}

청크·ARGUS 스키마는 문서화된 계약이 아니다(`version 1/2`). 그래서 **fail-closed** 다 —
필드가 빠지거나 길이가 안 맞으면 예외를 던져 빌드를 멈춘다(기존 산출물은 건드리지 않는다).
빌드 시각은 기록하지 않고 입력 파일의 sha256 fingerprint 만 남긴다 — 입력이 같으면
산출물 바이트가 같아야 한다(AGENTS.md 수집기 규약 5).
"""
import hashlib
import json
import os
import re

from kchem_lib import ARGUS, load_asset

ARGUS_DATA = os.path.join(ARGUS, "data", "argus_data.js")
CONNECTIONS = os.path.join(ARGUS, "data", "connections.js")
DATA_MAP = os.path.join(ARGUS, "data_map.js")

SPREAD_FIELDS = ("sid", "name", "cat", "chain", "unit", "sp", "pos", "m4", "hunt", "last_date", "freshness", "last")
CHUNK_FIELDS = ("kind", "key", "axis", "series")
CONN_FIELDS = ("sid", "name", "cat", "unit", "freq", "lane", "freshness", "last_date", "last", "source", "basis", "reason", "related", "observations")
MAP_ITEM_FIELDS = ("id", "sid", "name", "unit", "freq", "group", "chain", "category", "source", "last", "date", "prev", "prev_date", "detail")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InputError(Exception):
    """입력 스키마 불일치 — 빌드를 멈춘다."""


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_ASSIGN_RE = re.compile(r'(?:window\.)?[A-Za-z_$][\w$]*(?:\[["\'][^"\']+["\']\])?\s*=\s*\{')


def _json_after_assign(text, what):
    """`window.X = {...};` 또는 `window.X=window.X||{};window.X["k"]={...}` 에서 **마지막 대입문** 뒤의
    `{` 부터 마지막 `}` 까지를 JSON 으로. (청크 파일은 앞에 `||{}` 빈 객체가 있어 첫 `{` 로는 안 된다.)"""
    starts = [m.end() - 1 for m in _ASSIGN_RE.finditer(text)]
    j = text.rfind("}")
    if not starts or j < starts[-1]:
        raise InputError("%s: JSON 본문을 찾지 못함" % what)
    i = starts[-1]
    try:
        return json.loads(text[i:j + 1])
    except ValueError as e:
        raise InputError("%s: JSON 파싱 실패 — %s" % (what, e))


def _need(obj, fields, what):
    missing = [f for f in fields if f not in obj]
    if missing:
        raise InputError("%s: 필드 누락 %s" % (what, missing))


def _check_date(v, what):
    if v is not None and not (isinstance(v, str) and DATE_RE.match(v)):
        raise InputError("%s: 날짜 형식 아님 %r" % (what, v))


def load_argus_data(path=ARGUS_DATA):
    text = _read(path)
    d = _json_after_assign(text, "argus_data.js")
    _need(d, ("version", "asof", "spread", "chains", "health", "chunks", "kpi"), "argus_data.js")
    if d["version"] != 2:
        raise InputError("argus_data.js: version %r (기대 2) — 스키마 확인 필요" % d["version"])
    _check_date(d["asof"], "argus_data.asof")
    _need(d["spread"], ("cats", "series"), "argus_data.spread")
    for s in d["spread"]["series"]:
        _need(s, SPREAD_FIELDS, "argus_data.spread.series[%s]" % s.get("sid"))
        _check_date(s["last_date"], "spread.series[%s].last_date" % s["sid"])
    for c in d["chains"]:
        _need(c, ("id", "label", "pos", "mom", "n", "hunts", "members", "stocks"), "argus_data.chains[%s]" % c.get("id"))
        for st in c["stocks"]:
            _need(st, ("t", "n"), "chains[%s].stocks" % c["id"])
    _need(d["chunks"], ("spread",), "argus_data.chunks")
    return d, _sha(text)


def load_chunk(cat, rel_path, argus_dir=ARGUS):
    path = os.path.join(argus_dir, rel_path)
    text = _read(path)
    d = _json_after_assign(text, "chunk %s" % cat)
    _need(d, CHUNK_FIELDS, "chunk %s" % cat)
    if d["kind"] != "spread" or d["key"] != cat:
        raise InputError("chunk %s: kind/key 불일치 %r/%r" % (cat, d["kind"], d["key"]))
    axis = d["axis"]
    if not axis or not all(isinstance(a, str) and DATE_RE.match(a) for a in axis):
        raise InputError("chunk %s: axis 가 날짜 배열이 아님" % cat)
    if axis != sorted(axis):
        raise InputError("chunk %s: axis 가 오름차순이 아님" % cat)
    for s in d["series"]:
        _need(s, SPREAD_FIELDS + ("v",), "chunk %s series[%s]" % (cat, s.get("sid")))
        if len(s["v"]) != len(axis):
            raise InputError("chunk %s: %s v 길이 %d ≠ axis %d" % (cat, s["sid"], len(s["v"]), len(axis)))
        for v in s["v"]:
            if v is not None and not isinstance(v, (int, float)):
                raise InputError("chunk %s: %s v 에 숫자 아닌 값 %r" % (cat, s["sid"], v))
    return d, _sha(text)


def load_connections(path=CONNECTIONS):
    text = _read(path)
    d = _json_after_assign(text, "connections.js")
    _need(d, ("total", "connected", "rows"), "connections.js")
    if d["total"] != len(d["rows"]):
        raise InputError("connections.js: total %d ≠ rows %d" % (d["total"], len(d["rows"])))
    for r in d["rows"]:
        _need(r, CONN_FIELDS, "connections.rows[%s]" % r.get("sid"))
        obs = r["observations"]
        if not isinstance(obs, list):
            raise InputError("connections.rows[%s]: observations 가 배열이 아님" % r["sid"])
        prev = None
        for o in obs:
            if not (isinstance(o, list) and len(o) == 2 and isinstance(o[0], str) and DATE_RE.match(o[0])
                    and (o[1] is None or isinstance(o[1], (int, float)))):
                raise InputError("connections.rows[%s]: observation 형식 %r" % (r["sid"], o))
            if prev is not None and o[0] <= prev:
                raise InputError("connections.rows[%s]: observations 가 오름차순이 아님(%s 뒤 %s)" % (r["sid"], prev, o[0]))
            prev = o[0]
    return d, _sha(text)


def load_data_map(path=DATA_MAP):
    text = _read(path)
    d = _json_after_assign(text, "data_map.js")
    _need(d, ("version", "counts", "groups", "chains", "items"), "data_map.js")
    if d["version"] != 1:
        raise InputError("data_map.js: version %r (기대 1)" % d["version"])
    if d["counts"].get("tiles") != len(d["items"]):
        raise InputError("data_map.js: counts.tiles %r ≠ items %d" % (d["counts"].get("tiles"), len(d["items"])))
    for it in d["items"]:
        _need(it, MAP_ITEM_FIELDS, "data_map.items[%s]" % it.get("sid"))
    return d, _sha(text)


def load_all(argus_dir=ARGUS, categories=None):
    """모든 입력을 읽어 검증하고 (inputs, fingerprint) 를 돌려준다.

    inputs = {argus, chunks{cat: chunk}, connections, data_map, chem_cats}
    fingerprint = {"inputs": {상대경로: sha256}, "fingerprint": sha256(정렬된 경로:해시 목록)}
    """
    cats = list(categories or load_asset("aliases.json")["chem_categories"])
    shas = {}
    argus, h = load_argus_data(os.path.join(argus_dir, "data", "argus_data.js"))
    shas["data/argus_data.js"] = h
    chunks = {}
    for cat in cats:
        rel = argus["chunks"]["spread"].get(cat)
        if not rel:
            raise InputError("argus_data.chunks.spread 에 카테고리 %r 없음" % cat)
        chunks[cat], shas[rel] = load_chunk(cat, rel, argus_dir)
    conn, shas["data/connections.js"] = load_connections(os.path.join(argus_dir, "data", "connections.js"))
    dmap, shas["data_map.js"] = load_data_map(os.path.join(argus_dir, "data_map.js"))
    # 교차 검증: 패널의 화학 시리즈가 청크에 전부 있어야 한다(둘 다 같은 빌드에서 나온다).
    panel = {s["sid"] for s in argus["spread"]["series"] if s["cat"] in cats}
    chunked = {s["sid"] for c in chunks.values() for s in c["series"]}
    if panel != chunked:
        raise InputError("패널(%d)과 청크(%d)의 화학 시리즈 집합이 다름: 패널만 %s / 청크만 %s"
                         % (len(panel), len(chunked), sorted(panel - chunked)[:5], sorted(chunked - panel)[:5]))
    digest = hashlib.sha256("\n".join("%s:%s" % kv for kv in sorted(shas.items())).encode("utf-8")).hexdigest()
    fp = {"inputs": shas, "fingerprint": digest, "argus_asof": argus["asof"], "argus_built": argus.get("built")}
    return {"argus": argus, "chunks": chunks, "connections": conn, "data_map": dmap, "chem_cats": cats}, fp


if __name__ == "__main__":
    inputs, fp = load_all()
    print("fingerprint", fp["fingerprint"][:16], "asof", fp["argus_asof"])
    print("chem categories", len(inputs["chunks"]), "series",
          sum(len(c["series"]) for c in inputs["chunks"].values()),
          "connections rows", inputs["connections"]["total"], "map items", len(inputs["data_map"]["items"]))
