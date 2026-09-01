#!/usr/bin/env python3
"""리전 샤드에서 국가 큐브를 분리하고 company.topc를 사전계산한다.

index.html의 coTopC(540-560행) 세 분기를 그대로 포팅했다. 검증용 참조 구현이며,
맥스튜디오의 jem_site_build.py에 이식하면 된다.

  usage: split_shard.py data_jp.js JP [outdir]
  출력:  <outdir>/data_jp.js          — country/country_i 제거 + companies[].topc 추가
         <outdir>/data_jp_country.js  — PSHC["JP"]={"country":…,"country_i":…}
"""
import json
import os
import sys

TOPN = 6  # 프론트 최대 요구치(hubPanel)에 맞춤. 카드(4)는 slice로 잘라 씀


def last_idx(vals):
    for i in range(len(vals) - 1, -1, -1):
        if vals[i]:
            return i
    return -1


def f_country_loc(co, cdata, n):
    """fCountryLoc(co,'ALL') 포팅 — filtered 기업용 (cdata 기반)."""
    bpc = (cdata.get(co["id"]) or {}).get("bpc") or {}
    flow = co.get("rev_flow") or "exp"
    loc = {c: [0.0] * n for c in co.get("countries", [])}
    for pc in co.get("ports", []):
        pp = bpc.get(pc)
        if not pp:
            continue
        for c in co.get("countries", []):
            s = pp.get(c)
            if not s:
                continue
            v = s[flow]["v"]
            for i in range(min(n, len(v))):
                loc[c][i] += v[i]
    order = sorted(loc, key=lambda c: -sum(loc[c]))
    return order, loc


def compute_topc(co, shard, n):
    """coTopC(co, 6) → {"idx":int,"grouped":bool?,"top":[{"name","share"}]}"""
    cdata = shard.get("cdata") or {}
    groups = co.get("country_groups") or []

    # 분기 1: country_groups (수요처 추정 — 그룹 가중합)
    if groups:
        _, loc = f_country_loc(co, cdata, n)
        li = -1
        for i in range(n - 1, -1, -1):
            if sum((loc.get(c) or [0] * n)[i] for c in co.get("countries", [])):
                li = i
                break
        if li < 0:
            return None
        tot = sum((loc.get(c) or [0] * n)[li] for c in co.get("countries", [])) or 1
        out = []
        for g in groups:
            val = 0.0
            for c in g.get("countries", []):
                nm = c.get("c") if isinstance(c, dict) else c
                w = c.get("w", 1) if isinstance(c, dict) else 1
                val += (loc.get(nm) or [0] * n)[li] * w
            out.append({"name": g["name"], "share": val / tot})
        out.sort(key=lambda x: -x["share"])
        return {"idx": li, "grouped": True, "top": out[:TOPN]}

    # 분기 2: filtered (cdata 기반)
    if co.get("filtered"):
        order, loc = f_country_loc(co, cdata, n)
        li = -1
        for i in range(n - 1, -1, -1):
            if sum(loc[c][i] for c in order):
                li = i
                break
        if li < 0:
            return None
        tot = sum(loc[c][li] for c in order) or 1
        out = [{"name": c, "share": loc[c][li] / tot} for c in order]
        out.sort(key=lambda x: -x["share"])
        return {"idx": li, "top": out[:TOPN]}

    # 분기 3: 일반 (country[core_set] 기반)
    src_key = "country_i" if co.get("rev_flow") == "imp" else "country"
    src = (shard.get(src_key) or {}).get(co.get("core_set"))
    if not src or not src.get("order") or not src.get("loc"):
        return None
    order, loc = src["order"], src["loc"]
    ports = co.get("main_ports") or []
    li = -1
    for i in range(n - 1, -1, -1):
        s = 0.0
        for pc in ports:
            lp = loc.get(pc)
            if not lp:
                continue
            for c in order:
                arr = lp.get(c)
                if arr and i < len(arr):
                    s += arr[i] or 0
        if s:
            li = i
            break
    if li < 0:
        return None
    agg = {c: 0.0 for c in order}
    for pc in ports:
        lp = loc.get(pc)
        if not lp:
            continue
        for c in order:
            arr = lp.get(c)
            if arr and li < len(arr):
                agg[c] += arr[li] or 0
    tot = sum(agg.values()) or 1
    out = [{"name": c, "share": agg[c] / tot} for c in order]
    out.sort(key=lambda x: -x["share"])
    return {"idx": li, "top": out[:TOPN]}


def rnd(o):
    """share를 4자리로 반올림해 바이트 절약 (표시는 소수점 0자리)."""
    if isinstance(o, float):
        return round(o, 4)
    if isinstance(o, dict):
        return {k: rnd(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rnd(v) for v in o]
    return o


def main(path, reg, outdir):
    src = open(path, encoding="utf-8").read()
    marker = 'PSH["%s"]=' % reg
    i = src.index(marker)
    shard = json.loads(src[i + len(marker):].strip().rstrip(";"))

    n = max((len(c.get("revenue") or []) for c in shard["companies"]), default=0)
    if not n:  # revenue 없는 리전 — detail 길이로 추정
        for st in (shard.get("detail") or {}).values():
            for pt in st.values():
                n = max(n, len(pt["exp"]["v"]))
                break
            break

    hit = 0
    for co in shard["companies"]:
        tc = compute_topc(co, shard, n)
        if tc:
            co["topc"] = rnd(tc)
            hit += 1

    country = {k: shard.pop(k) for k in ("country", "country_i") if k in shard}

    os.makedirs(outdir, exist_ok=True)
    base = os.path.basename(path)
    lite = os.path.join(outdir, base)
    cfile = os.path.join(outdir, base.replace(".js", "_country.js"))

    with open(lite, "w", encoding="utf-8") as f:
        f.write("var PSH=window.PSH||(window.PSH={});%s%s;"
                % (marker, json.dumps(shard, ensure_ascii=False, separators=(",", ":"))))
    with open(cfile, "w", encoding="utf-8") as f:
        f.write('var PSHC=window.PSHC||(window.PSHC={});PSHC["%s"]=%s;'
                % (reg, json.dumps(country, ensure_ascii=False, separators=(",", ":"))))

    mb = lambda p: os.path.getsize(p) / 1048576
    print("원본 %6.1fMB → 메인 %6.1fMB + 국가 %6.1fMB   (topc %d/%d사)"
          % (len(src) / 1048576, mb(lite), mb(cfile), hit, len(shard["companies"])))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "split_out")
