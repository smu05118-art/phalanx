#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kchem_supplement — 사용자 제공 화학제품 가격표(xlsx)로 멈춘 ARGUS 원장 뒤를 잇는다.

배경: 원장(유료 스팟 주간, 수동 Weekly xlsm 드롭)이 2026-08-24 주 이후 멈췄다. 사용자가 같은 원천의 제품 가격표
(`화학제품 가격.xlsx` — 시트 1장, 머리 3줄 분류·제품(단위)·지역, 주간 2000-01~)를 줬다. 겹치는 2년(102주) 대조에서
매핑한 39개 시리즈의 값이 94% 정확히 같았다(4,182 관측 중 3,946 — 나머지는 원장 쪽 소급 수정 주).

규칙(LOGIC.md §4c):
  · **원장이 먼저다.** 원장에 값이 있는 날짜는 건드리지 않고, 시리즈마다 원장 마지막 관측 **뒤** 날짜만 가격표로 잇는다.
  · **검증된 열만 잇는다.** 매핑(assets/supplement_map.json — 머리행 글자 기준, 열 위치가 아니다)한 열의 겹침 관측이
    24주 이상이고 ±1% 일치 90% 이상·정확 일치 50% 이상일 때만. 못 넘으면 'mismatch' 로 두고 잇지 않는다(에탄 — 단위 기준이 다르다,
    카프로락탐 — 가격표는 한국, 원장은 중국).
  · **스프레드는 재현된 산식으로만 잇는다.** 레지스트리 1차 적합(원장만)에서 재현(정확·근사)된 행 중 제품·원료가 전부
    이어진 시리즈인 행만 S = P − Σk×F(크랙은 P/9.2593)로 계산한다. 원료가 원장 전용(Dubai 유가 등)이면 잇지 않는다.
  · 이은 행의 4W% 는 허브와 같은 식(4주 전 대비 %), 사이클 위치는 허브 정의(장기 원장)를 알 수 없어 **kchem 5년 백분위**로
    다시 계산하고 `pos_src='kchem_5y'` 로 표시한다.
  · 결정적: 가격표 sha256 을 fingerprint 에 넣는다. 가져오기(--import)만 파일을 읽고, 빌드는 커밋된 해석 결과만 읽는다.
  · 재배포 최소화: 커밋하는 관측은 5년 창(청크 축 시작 이후)뿐이고, 장기(2000~) 통계는 최소·최대·백분위 숫자만 남긴다.

명령:
  python3 kchem_supplement.py --import "<xlsx 경로>"     # 해석·검증 → assets/supplement/prices.json (네트워크 없음)
  python3 kchem_page.py                                  # 이후 빌드는 자동으로 잇는다
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

from kchem_lib import ASSETS, atomic_write, dump_json, load_asset

SUPP_DIR = os.path.join(ASSETS, "supplement")
SUPP = os.path.join(SUPP_DIR, "prices.json")
MAP = "supplement_map.json"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
MIN_OVERLAP = 24
MIN_MATCH = 0.90
MIN_EXACT = 0.50                    # 같은 원천이면 대부분 값이 똑같다 — 에탄은 ±1% 92% 지만 정확 0(가격표가 $/gal 을 거칠게 환산)
WINDOW_FROM = "2021-10-25"          # 청크 축 첫 주(5년 창) — 이보다 앞 관측은 커밋하지 않는다(장기 통계만)
STALE_W = 14                        # kchem_registry.STALE_AFTER["W"]


class SupplementError(Exception):
    pass


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\t", " ")).strip()


def _col(ref):
    return re.match(r"[A-Z]+", ref).group(0)


def _xdate(serial):
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=float(serial))).isoformat()


# ── xlsx 해석(표준 라이브러리 — zip + XML) ─────────────────────

def read_xlsx(path):
    """시트 1장, 머리 3줄(분류 · 제품(단위) · 지역), A 열 = 날짜(엑셀 일련번호). → (cols, rows_n, sheet).
    cols = [{col, cat, name, region, obs:[[YYYY-MM-DD, float]]}] (원문 순서)."""
    z = zipfile.ZipFile(path)
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    sheets = [(s.get("name"), rels[s.get("{%s}id" % NS["r"])]) for s in wb.find("m:sheets", NS)]
    if len(sheets) != 1:
        raise SupplementError("시트가 %d장 — 1장인 가격표만 읽는다" % len(sheets))
    sheet, target = sheets[0]
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    x = ET.fromstring(z.read("xl/" + target.lstrip("/").replace("xl/", "", 1)))
    grid = {}
    for row in x.find("m:sheetData", NS).findall("m:row", NS):
        r = int(row.get("r"))
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is None:
                continue
            val = v.text
            if c.get("t") == "s":
                val = ss[int(val)]
            grid[(r, _col(c.get("r")))] = val
    if _norm(grid.get((1, "A"))) != "날짜":
        raise SupplementError("A1 이 '날짜' 가 아니다 — 가격표 서식이 다르다")
    letters = sorted({k[1] for k in grid}, key=lambda s: (len(s), s))
    maxr = max(k[0] for k in grid)
    out, cat = [], ""
    for col in letters:
        if col == "A":
            continue
        cat = _norm(grid.get((1, col))) or cat
        obs = []
        for r in range(4, maxr + 1):
            v, dt = grid.get((r, col)), grid.get((r, "A"))
            if v in (None, "") or not dt:
                continue
            try:
                obs.append([_xdate(dt), round(float(v), 6)])
            except ValueError:
                continue
        out.append({"col": col, "cat": cat, "name": _norm(grid.get((2, col))), "region": _norm(grid.get((3, col))), "obs": obs})
    return out, maxr - 3, sheet


# ── 가져오기 ───────────────────────────────────────────────────

def _pct_rank(vals, x):
    if not vals:
        return None
    return round(sum(1 for v in vals if v <= x) / len(vals) * 100, 2)


def import_xlsx(path, conn_rows, name=None):
    """가격표 → 커밋할 문서. conn_rows = ARGUS connections.rows(검증용 원장 관측). name = 원래 파일 이름(기록용)."""
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    cols, nrows, sheet = read_xlsx(path)
    mp = load_asset(MAP)
    by_key = {(_norm(m["name"]), _norm(m["region"])): m for m in mp["series"]}
    conn = {r["sid"]: r for r in conn_rows}
    series, seen = [], set()
    for c in cols:
        m = by_key.get((c["name"], c["region"]))
        if not c["obs"]:
            continue
        key = m["key"] if m else "x_%s" % c["col"]
        if key in seen:
            raise SupplementError("같은 열이 두 번 매핑됨: %s" % key)
        seen.add(key)
        vals = [v for _d, v in c["obs"]]
        last_d, last_v = c["obs"][-1]
        ent = {"key": key, "cat": c["cat"], "name": c["name"], "region": c["region"], "unit": (m or {}).get("unit") or "USD/MT",
               "label": (m or {}).get("label") or ("%s %s" % (c["name"], c["region"])).strip(),
               "sid": (m or {}).get("sid"), "chain": (m or {}).get("chain"),
               "long": {"from": c["obs"][0][0], "n": len(vals), "min": min(vals), "max": max(vals),
                        "rank": _pct_rank(vals, last_v)},
               "last": last_v, "last_date": last_d,
               "obs": [o for o in c["obs"] if o[0] >= WINDOW_FROM]}
        sid = ent["sid"]
        if sid:
            led = conn.get(sid)
            if not led:
                ent["check"] = {"status": "no_ledger", "overlap": 0}
            else:
                lo = {d: v for d, v in led["observations"] if v is not None}
                xo = dict(c["obs"])
                common = sorted(set(lo) & set(xo))
                exact = sum(1 for d in common if abs(xo[d] - lo[d]) < 1e-6)
                near = sum(1 for d in common if abs(xo[d] - lo[d]) <= 0.01 * max(1.0, abs(lo[d])))
                ok = len(common) >= MIN_OVERLAP and near >= MIN_MATCH * len(common) and exact >= MIN_EXACT * len(common)
                ent["check"] = {"status": "ok" if ok else "mismatch", "overlap": len(common), "exact": exact, "near1pct": near,
                                "ledger_last": led["last_date"],
                                "diffs": [[d, xo[d], lo[d]] for d in common if abs(xo[d] - lo[d]) > 0.01 * max(1.0, abs(lo[d]))][:5]}
        else:
            ent["check"] = {"status": "unmapped", "overlap": 0}
        series.append(ent)
    last = max(s["last_date"] for s in series)
    return {"version": 1, "source": {"file": name or os.path.basename(path), "sha256": sha, "sheet": sheet, "rows": nrows,
                                     "last_date": last, "window_from": WINDOW_FROM},
            "rules": {"min_overlap": MIN_OVERLAP, "min_match": MIN_MATCH, "min_exact": MIN_EXACT,
                      "note": "원장 관측이 있는 날짜는 원장 그대로, 원장 마지막 관측 뒤 날짜만 가격표로 잇는다"},
            "series": series}


def load(path=SUPP):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 잇기 ──────────────────────────────────────────────────────

def _fresh(asof, d):
    days = (asof - datetime.date.fromisoformat(d)).days
    return "fresh" if days <= STALE_W else ("dead" if days > 365 else "stale")


def augment(inputs, fp, supp, registry_cls):
    """원장 입력 + 가격표 → (이은 입력, fingerprint, 요약). 입력은 깊은 복사본을 고친다(원본 불변)."""
    asof = datetime.date.fromisoformat(inputs["argus"]["asof"])
    reg0 = registry_cls(inputs, fp).build()                    # 1차: 원장만으로 산식 적합
    out = copy.deepcopy(inputs)
    conn = {r["sid"]: r for r in out["connections"]["rows"]}
    ext_p, notes = {}, []
    for s in supp["series"]:
        sid = s.get("sid")
        if not sid or s["check"]["status"] != "ok" or sid not in conn:
            continue
        r = conn[sid]
        last = r["last_date"] or ""
        new = [o for o in s["obs"] if o[0] > last and o[0] <= asof.isoformat()]
        if not new:
            continue
        r["observations"] = list(r["observations"]) + [list(o) for o in new]
        r["last_date"], r["last"] = new[-1]
        r["freshness"] = _fresh(asof, r["last_date"])
        r["supplement"] = {"from": new[0][0], "through": new[-1][0], "weeks": len(new)}
        ext_p[sid] = dict(r["observations"])
    # 스프레드 — 재현된 산식, 제품·원료가 전부 이어진 시리즈일 때만
    by_sid = {}
    for cat, ch in out["chunks"].items():
        for s in ch["series"]:
            by_sid[s["sid"]] = (ch, s)
    ext_s = []
    for row in reg0["rows"]:
        if row["kind"] != "spread" or not row.get("reproduced") or row.get("grade") not in ("exact", "approx"):
            continue
        psid, feeds = row.get("product_sid"), row.get("feeds") or []
        if psid not in ext_p or not feeds or any(f["sid"] not in ext_p for f in feeds):
            continue
        sid = row["sid"]
        if sid not in conn or sid not in by_sid:
            continue
        r = conn[sid]
        last = r["last_date"] or ""
        P, Fs = ext_p[psid], [ext_p[f["sid"]] for f in feeds]
        div = (1000.0 / 108.0) if row.get("unit_hint") == "USD/bbl" else 1.0
        dates = sorted(d for d in P if d > last and d <= asof.isoformat() and all(F.get(d) is not None for F in Fs)
                       and P.get(d) is not None)
        if not dates:
            continue
        vals = [[d, round(float(P[d]) / div - sum(f["k"] * float(F[d]) for f, F in zip(feeds, Fs)), 2)] for d in dates]
        r["observations"] = list(r["observations"]) + vals
        r["last_date"], r["last"] = vals[-1]
        r["freshness"] = _fresh(asof, r["last_date"])
        ch, cs = by_sid[sid]
        ax = ch["axis"]
        v = list(cs["v"])
        for d, x in vals:
            if d in ax:
                v[ax.index(d)] = x
        cs["v"] = v
        i = ax.index(vals[-1][0]) if vals[-1][0] in ax else None
        cs["last"], cs["last_date"], cs["freshness"] = vals[-1][1], vals[-1][0], r["freshness"]
        if i is not None:
            prev = v[i - 4] if i >= 4 else None
            cs["m4"] = round((vals[-1][1] - prev) / abs(prev) * 100, 2) if prev not in (None, 0) else None
            win = [x for x in v[:i + 1] if x is not None]
            cs["pos"] = _pct_rank(win, vals[-1][1])
        cs["pos_src"] = "kchem_5y"
        cs["supplement"] = {"from": vals[0][0], "through": vals[-1][0], "weeks": len(vals), "grade": row.get("grade")}
        ext_s.append(sid)
    for s in supp["series"]:
        if s["check"]["status"] == "mismatch":
            notes.append("%s %s — 겹침 %d주 중 ±1%% 일치 %d(잇지 않음)" % (s["name"], s["region"], s["check"]["overlap"],
                                                                     s["check"].get("near1pct", 0)))
    fp2 = dict(fp)
    fp2["inputs"] = dict(fp["inputs"], **{"supplement/prices.json": supp["source"]["sha256"]})
    fp2["fingerprint"] = hashlib.sha256(("%s\nsupplement:%s" % (fp["fingerprint"], supp["source"]["sha256"]))
                                        .encode("utf-8")).hexdigest()
    summary = {"file": supp["source"]["file"], "sha256": supp["source"]["sha256"], "through": supp["source"]["last_date"],
               "ledger_last": reg0["summary"]["ledger_last"], "editions": reg0["summary"].get("editions"),
               "prices_extended": len(ext_p), "spreads_extended": len(ext_s), "spreads_total": reg0["summary"]["spreads"],
               "series": len(supp["series"]),
               "ok": sum(1 for s in supp["series"] if s["check"]["status"] == "ok"),
               "mismatch": sum(1 for s in supp["series"] if s["check"]["status"] == "mismatch"),
               "unmapped": sum(1 for s in supp["series"] if s["check"]["status"] == "unmapped"),
               "notes": notes, "spread_sids": sorted(ext_s)}
    return out, fp2, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--import", dest="imp", help="가격표 xlsx 경로")
    ap.add_argument("--name", help="기록할 원래 파일 이름(기본: 경로의 파일 이름)")
    a = ap.parse_args(argv)
    if not a.imp:
        ap.print_help()
        return 2
    import kchem_inputs
    _inp, _fp = kchem_inputs.load_all(supplement=False)
    doc = import_xlsx(a.imp, _inp["connections"]["rows"], a.name)
    os.makedirs(SUPP_DIR, exist_ok=True)
    atomic_write(SUPP, dump_json(doc))
    st = {}
    for s in doc["series"]:
        st[s["check"]["status"]] = st.get(s["check"]["status"], 0) + 1
    print("가격표 %s: 시리즈 %d (%s) · 마지막 %s → %s" % (doc["source"]["file"], len(doc["series"]),
                                                   ", ".join("%s %d" % kv for kv in sorted(st.items())),
                                                   doc["source"]["last_date"], os.path.relpath(SUPP)))
    for s in doc["series"]:
        if s["check"]["status"] == "mismatch":
            print("  잇지 않음: %s %s — 겹침 %d · ±1%% 일치 %d" % (s["name"], s["region"], s["check"]["overlap"], s["check"]["near1pct"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
