# -*- coding: utf-8 -*-
"""한국화학(kchem) 계약 테스트.

두 겹이다.
① 합성 fixture(이 파일이 임시 디렉터리에 만든다): 알려진 산식으로 만든 스프레드를 레지스트리가 그대로 역산하는가,
   스키마가 깨지면 빌드가 멈추는가(fail-closed), 같은 입력으로 두 번 빌드하면 바이트가 같은가.
② 실제 레포 입력(argus/data/* 가 있을 때만): 패널의 화학 시리즈 수 = 레지스트리 행 수, 재현 비율 하한, 5MB 상한.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import kchem_inputs       # noqa: E402
import kchem_registry     # noqa: E402
import kchem_page         # noqa: E402
from kchem_lib import ARGUS, load_asset   # noqa: E402

CHEM_CATS = load_asset("aliases.json")["chem_categories"]


# ── 합성 세계 ───────────────────────────────────────────────

def _dates(n, start=(2025, 9, 1)):
    import datetime
    d0 = datetime.date(*start)
    return [(d0 + datetime.timedelta(days=7 * i)).isoformat() for i in range(n)]


def _walk(seed, base, step, n):
    """결정적 의사난수 보행(LCG) — 0.5 단위 반올림(원장과 같은 모양)."""
    x, out = seed, []
    v = float(base)
    for _ in range(n):
        x = (x * 1103515245 + 12345) % (2 ** 31)
        v += ((x / float(2 ** 31)) - 0.5) * step
        out.append(round(v * 2) / 2.0)
    return out


def make_world(n=50):
    """가격 시리즈와 그 산식으로 만든 스프레드. 돌려줌: (prices{name: [v]}, spreads[{name,cat,chain,v}], dates)."""
    dates = _dates(n)
    P = {
        "Ethylene 한국": _walk(1, 1000, 40, n), "Naphtha 일본": _walk(2, 700, 30, n),
        "HDPE(사출) 한국": _walk(3, 1100, 40, n), "ABS 한국": _walk(4, 1500, 40, n),
        "Butadiene 한국": _walk(5, 1100, 50, n), "SM 한국": _walk(6, 1050, 40, n), "AN 한국": _walk(7, 1300, 40, n),
        "BR 한국": _walk(8, 1800, 40, n), "PX 대만": _walk(9, 900, 30, n), "Xylene(솔벤트) 대만": _walk(10, 750, 30, n),
        "Acetone 한국": _walk(11, 650, 30, n), "Propylene 한국": _walk(12, 850, 40, n), "메탄올 한국": _walk(13, 300, 10, n),
    }
    cut = 30                      # BR 가격은 30주에서 끊긴다
    P["BR 한국"] = P["BR 한국"][:cut] + [None] * (n - cut)
    sw = 20                       # PX-자일렌(대만)은 20주에서 산식이 바뀐다
    spreads = [
        {"name": "에틸렌-납사 스프레드(한국)", "cat": "올레핀", "chain": "ncc",
         "v": [round(e - 1.0 * f, 1) for e, f in zip(P["Ethylene 한국"], P["Naphtha 일본"])]},
        {"name": "HDPE(Injection)-에틸렌 스프레드(한국)", "cat": "폴리머", "chain": "ncc",
         "v": [round(h - 1.0 * e, 1) for h, e in zip(P["HDPE(사출) 한국"], P["Ethylene 한국"])]},
        {"name": "ABS-BD&SM 스프레드(한국)", "cat": "폴리머", "chain": "butadiene",
         "v": [round(a - 0.19 * b - 0.54 * s - 0.27 * an, 1) for a, b, s, an in
               zip(P["ABS 한국"], P["Butadiene 한국"], P["SM 한국"], P["AN 한국"])]},
        {"name": "BR-BD 스프레드(한국)", "cat": "고무", "chain": "butadiene",
         "v": [round((br if br is not None else 0.0) - 1.0 * b, 1) for br, b in zip(P["BR 한국"], P["Butadiene 한국"])]},
        {"name": "PX-자일렌 스프레드(대만)", "cat": "아로마틱", "chain": "aromatics",
         "v": [round(px - (1.25 * xy if i < sw else 1.0 * na), 1) for i, (px, xy, na) in
               enumerate(zip(P["PX 대만"], P["Xylene(솔벤트) 대만"], P["Naphtha 일본"]))]},
        {"name": "아세톤 스프레드(한국)", "cat": "솔벤트", "chain": "solvents",
         "v": [round(a - 0.85 * p, 1) for a, p in zip(P["Acetone 한국"], P["Propylene 한국"])]},
        {"name": "AN-프로필렌 스프레드(한국)", "cat": "화섬", "chain": None,
         "v": [round(an - 1.05 * p, 1) for an, p in zip(P["AN 한국"], P["Propylene 한국"])]},
    ]
    return P, spreads, dates


def write_world(root, P, spreads, dates, asof="2026-08-31"):
    """합성 세계를 ARGUS 빌더 산출물 모양으로 디스크에 쓴다. 돌려줌: argus_dir."""
    argus = os.path.join(root, "argus")
    os.makedirs(os.path.join(argus, "data"))
    cats = sorted({s["cat"] for s in spreads})
    sid_of = {}
    panel = []
    for s in spreads:
        sid = "sp_" + s["name"].replace(" 스프레드", "").replace("-", "_").replace("(", "_").replace(")", "").replace(" ", "_").lower()
        sid_of[s["name"]] = sid
        last = [v for v in s["v"] if v is not None][-1]
        panel.append({"sid": sid, "name": s["name"], "cat": s["cat"], "chain": s["chain"], "unit": "USD/MT", "sp": True,
                      "pos": 50.0, "m4": 1.0, "hunt": [], "last_date": dates[-1], "freshness": "fresh", "last": last})
    price_row = {"sid": "sp_메탄올_가격_한국", "name": "메탄올 가격(한국)", "cat": "기초유분", "chain": None, "unit": "USD/MT", "sp": False,
                 "pos": 50.0, "m4": 0.0, "hunt": [], "last_date": dates[-1], "freshness": "fresh", "last": P["메탄올 한국"][-1]}
    panel.append(price_row)
    cf_row = {"sid": "cf_benzene", "name": "벤젠 선물 주력 (纯苯)", "cat": "아로마틱", "chain": "aromatics", "unit": "CNY/t", "sp": False,
              "pos": 40.0, "m4": 2.0, "hunt": [], "last_date": dates[-1], "freshness": "fresh", "last": 8000.0}
    panel.append(cf_row)
    cats = sorted({r["cat"] for r in panel})
    chunks = {c: "data/chunk_%s.js" % c for c in cats}
    for c in cats:
        series = [dict(r, v=(next(s["v"] for s in spreads if s["name"] == r["name"]) if r["sp"] else
                             (P["메탄올 한국"] if r["sid"].startswith("sp_") else [8000.0] * len(dates))))
                  for r in panel if r["cat"] == c]
        body = {"kind": "spread", "key": c, "axis": dates, "series": series}
        with open(os.path.join(argus, chunks[c]), "w", encoding="utf-8") as f:
            f.write('window.ARGUS_CHUNKS=window.ARGUS_CHUNKS||{};window.ARGUS_CHUNKS["spread:%s"]=%s;\n' % (c, json.dumps(body, ensure_ascii=False)))
    # 다른 카테고리(화학 13 중 fixture 에 없는 것)는 빈 청크
    for c in CHEM_CATS:
        if c not in chunks:
            chunks[c] = "data/chunk_%s.js" % c
            with open(os.path.join(argus, chunks[c]), "w", encoding="utf-8") as f:
                f.write('window.ARGUS_CHUNKS=window.ARGUS_CHUNKS||{};window.ARGUS_CHUNKS["spread:%s"]=%s;\n'
                        % (c, json.dumps({"kind": "spread", "key": c, "axis": dates, "series": []}, ensure_ascii=False)))
    chains = [
        {"id": "ncc", "label": "NCC·올레핀", "pos": 60.0, "mom": {"w1": 1.0, "w4": 2.0, "w13": 3.0, "w26": 4.0}, "n": 2, "hunts": {"bt": 0, "pw": 0, "ac": 0},
         "members": [], "stocks": [{"t": "011170", "n": "롯데케미칼", "note": "에틸렌"}, {"t": "006650", "n": "대한유화", "note": "NCC"}]},
        {"id": "butadiene", "label": "부타디엔·합성고무", "pos": 30.0, "mom": {"w1": 0.0, "w4": 0.0, "w13": 0.0, "w26": 0.0}, "n": 1, "hunts": {"bt": 0, "pw": 0, "ac": 0},
         "members": [], "stocks": [{"t": "011780", "n": "금호석유", "note": "BD"}]},
        {"id": "aromatics", "label": "아로마틱", "pos": 50.0, "mom": {"w1": 0.0, "w4": 0.0, "w13": 0.0, "w26": 0.0}, "n": 1, "hunts": {"bt": 0, "pw": 0, "ac": 0}, "members": [], "stocks": []},
        {"id": "solvents", "label": "솔벤트", "pos": 50.0, "mom": {"w1": 0.0, "w4": 0.0, "w13": 0.0, "w26": 0.0}, "n": 1, "hunts": {"bt": 0, "pw": 0, "ac": 0}, "members": [], "stocks": []},
    ]
    argus_data = {"version": 2, "built": asof, "updated": asof, "asof": asof, "mock": False,
                  "kpi": {"n_series": len(panel), "n_bt": 0, "n_pw": 0, "n_ac": 0},
                  "health": {"freshness_evaluated_at": asof, "freshness_counts": {}, "total": len(panel), "active": len(panel), "stale": 0,
                             "low_confidence": 0, "stale_series": [], "low_confidence_series": []},
                  "axes": {"wk": [], "sol": [], "oil": []}, "chains": chains, "signals": {"bt": [], "pw": [], "btc": [], "pwc": []},
                  "spread": {"cats": cats, "series": panel}, "solar": {}, "oil": {}, "research": {},
                  "chunks": {"version": 1, "spread": chunks, "solar": {}, "oil": {}, "fallback": "data/argus_data_full.js"}}
    with open(os.path.join(argus, "data", "argus_data.js"), "w", encoding="utf-8") as f:
        f.write("window.ARGUS=%s;\n" % json.dumps(argus_data, ensure_ascii=False))
    rows, items = [], []

    def row(sid, name, cat, unit, obs, freq="W", lane=None):
        rows.append({"sid": sid, "name": name, "cat": cat, "unit": unit, "freq": freq, "lane": lane, "freshness": "fresh",
                     "last_date": obs[-1][0], "last": obs[-1][1], "source": "fixture", "url": None, "basis": "", "reason": "",
                     "related": [], "observations": obs})
        items.append({"id": "argus:" + sid, "sid": sid, "name": name, "unit": unit, "freq": freq, "group": "chain:ncc", "chain": "ncc",
                      "category": cat, "source": "ARGUS", "last": obs[-1][1], "date": obs[-1][0], "prev": obs[-2][1], "prev_date": obs[-2][0],
                      "detail": "map_data/detail_00.js"})
    for name, vals in P.items():
        row("p_" + name.replace(" ", "_").lower(), name, "가격", "USD/MT", [[d, v] for d, v in zip(dates, vals)])
    for s in spreads:
        row(sid_of[s["name"]], s["name"], s["cat"], "USD/MT", [[d, v] for d, v in zip(dates, s["v"])])
    row("sp_메탄올_가격_한국", "메탄올 가격(한국)", "기초유분", "USD/MT", [[d, v] for d, v in zip(dates, P["메탄올 한국"])])
    row("cf_benzene", "벤젠 선물 주력 (纯苯)", "아로마틱", "CNY/t", [[d, 8000.0 + i] for i, d in enumerate(dates)], freq="D", lane="cnfut")
    with open(os.path.join(argus, "data", "connections.js"), "w", encoding="utf-8") as f:
        f.write("window.ARGUS_CONNECTIONS=%s;\n" % json.dumps({"built": asof, "total": len(rows), "connected": 0, "rows": rows}, ensure_ascii=False))
    dmap = {"version": 1, "built": asof, "fingerprint": "x", "source_updated": {}, "counts": {"series": len(items), "commodity": 0, "input": len(items),
            "tiles": len(items), "alternatives": 0, "cf": 0, "empty": 0}, "change_basis": "", "chart_bundle": "", "sources": {},
            "groups": [], "chains": [{"id": "ncc", "label": "NCC"}], "items": items, "empty_series": []}
    with open(os.path.join(argus, "data_map.js"), "w", encoding="utf-8") as f:
        f.write("window.ARGUS_MAP=%s;\n" % json.dumps(dmap, ensure_ascii=False))
    return argus, sid_of


class SyntheticBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kchem_fx_")
        cls.P, cls.spreads, cls.dates = make_world()
        cls.argus, cls.sid_of = write_world(cls.tmp, cls.P, cls.spreads, cls.dates)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def registry(self):
        inputs, fp = kchem_inputs.load_all(self.argus)
        return kchem_registry.Registry(inputs, fp).build(), inputs


# ── 이름 분해 ───────────────────────────────────────────────

class TestParse(unittest.TestCase):
    def test_split_last_dash(self):
        self.assertEqual(kchem_registry.split_last_dash("S-SBR-BD"), ("S-SBR", "BD"))
        self.assertEqual(kchem_registry.split_last_dash("PS(GP)-SM"), ("PS(GP)", "SM"))
        self.assertEqual(kchem_registry.split_last_dash("자일렌(솔벤트)-납사"), ("자일렌(솔벤트)", "납사"))
        self.assertEqual(kchem_registry.split_last_dash("아세톤"), ("아세톤", None))

    def test_parse_name(self):
        p = kchem_registry.parse_name("ABS-BD&SM 스프레드(중국 Huadong)")
        self.assertEqual((p["kind"], p["product"], p["feeds"], p["region"]), ("spread", "ABS", ["BD", "SM"], "중국 Huadong"))
        p = kchem_registry.parse_name("납사-Dubai 크랙 스프레드(일본)")
        self.assertEqual((p["kind"], p["product"], p["feeds"]), ("crack", "납사", ["Dubai"]))
        p = kchem_registry.parse_name("메탄올 가격(유럽)")
        self.assertEqual((p["kind"], p["product"], p["region"]), ("price", "메탄올", "유럽"))
        self.assertIsNone(kchem_registry.parse_name("벤젠 선물 주력 (纯苯)")["kind"])

    def test_lstsq(self):
        X = [[1.0, 2.0], [2.0, 1.0], [3.0, 5.0], [4.0, 1.0]]
        k = [0.7, 0.3]
        y = [sum(a * b for a, b in zip(r, k)) for r in X]
        got = kchem_registry.lstsq(X, y)
        self.assertAlmostEqual(got[0], 0.7, 6)
        self.assertAlmostEqual(got[1], 0.3, 6)


# ── fail-closed 입력 ────────────────────────────────────────

class TestInputs(SyntheticBase):
    def test_loads_and_fingerprints(self):
        inputs, fp = kchem_inputs.load_all(self.argus)
        self.assertEqual(len(inputs["chunks"]), len(CHEM_CATS))
        self.assertEqual(len(fp["fingerprint"]), 64)
        self.assertEqual(fp["argus_asof"], "2026-08-31")

    def _mutate(self, rel, fn):
        root = tempfile.mkdtemp(prefix="kchem_mut_")
        shutil.copytree(self.argus, os.path.join(root, "argus"))
        path = os.path.join(root, "argus", rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(fn(text))
        return os.path.join(root, "argus")

    def test_missing_field_stops_build(self):
        argus = self._mutate("data/chunk_올레핀.js", lambda t: t.replace('"freshness": "fresh"', '"fresh_ness": "fresh"'))
        with self.assertRaises(kchem_inputs.InputError):
            kchem_inputs.load_all(argus)

    def test_axis_length_mismatch_stops_build(self):
        argus = self._mutate("data/chunk_올레핀.js", lambda t: t.replace('"v": [', '"v": [1.0, ', 1))
        with self.assertRaises(kchem_inputs.InputError):
            kchem_inputs.load_all(argus)

    def test_panel_chunk_set_mismatch_stops_build(self):
        argus = self._mutate("data/argus_data.js", lambda t: t.replace('"sid": "sp_아세톤_한국"', '"sid": "sp_아세톤_한국_x"'))
        with self.assertRaises(kchem_inputs.InputError):
            kchem_inputs.load_all(argus)

    def test_unsorted_observations_stop_build(self):
        def swap(t):
            d = json.loads(t[t.index("{"):t.rindex("}") + 1])
            d["rows"][0]["observations"][0], d["rows"][0]["observations"][1] = d["rows"][0]["observations"][1], d["rows"][0]["observations"][0]
            return "window.ARGUS_CONNECTIONS=%s;\n" % json.dumps(d, ensure_ascii=False)
        argus = self._mutate("data/connections.js", swap)
        with self.assertRaises(kchem_inputs.InputError):
            kchem_inputs.load_all(argus)


# ── 레지스트리 ──────────────────────────────────────────────

class TestRegistry(SyntheticBase):
    def rows(self):
        reg, _ = self.registry()
        return reg, {r["name"]: r for r in reg["rows"]}

    def test_single_feed_reproduced(self):
        reg, by = self.rows()
        r = by["에틸렌-납사 스프레드(한국)"]
        self.assertTrue(r["reproduced"])
        self.assertEqual(r["layer"], "integrated")
        self.assertEqual(r["region"], "한국")
        self.assertEqual(r["feeds"][0]["name"], "Naphtha 일본")
        self.assertAlmostEqual(r["feeds"][0]["k"], 1.0, 2)
        self.assertEqual(r["fit"]["n_in"], r["fit"]["n"])
        self.assertEqual(r["stocks"][0]["t"], "011170")
        self.assertFalse(r["stocks"][0]["est"])
        self.assertEqual(r["formula"], "Ethylene 한국 − 1×Naphtha 일본")

    def test_step_layer(self):
        _, by = self.rows()
        r = by["HDPE(Injection)-에틸렌 스프레드(한국)"]
        self.assertTrue(r["reproduced"])
        self.assertEqual(r["layer"], "step")
        self.assertEqual(r["cnfut"]["sid"], "cf_benzene" if False else r["cnfut"]["sid"]) if r["cnfut"] else None

    def test_composite_extra_feed(self):
        _, by = self.rows()
        r = by["ABS-BD&SM 스프레드(한국)"]
        self.assertTrue(r["reproduced"])
        self.assertIn("composite_extra_feed", r["flags"])
        ks = {f["token"]: round(f["k"], 2) for f in r["feeds"]}
        self.assertEqual(ks, {"BD": 0.19, "SM": 0.54, "AN": 0.27})

    def test_missing_product_as_zero(self):
        _, by = self.rows()
        r = by["BR-BD 스프레드(한국)"]
        self.assertIn("missing_product_as_zero", r["flags"])
        self.assertEqual(r["product_last_date"], self.dates[29])

    def test_formula_change_and_feed_mismatch(self):
        _, by = self.rows()
        r = by["PX-자일렌 스프레드(대만)"]
        self.assertTrue(r["reproduced"])
        self.assertIn("formula_changed", r["flags"])
        self.assertIn("feed_mismatch", r["flags"])
        self.assertEqual(r["feeds"][0]["name"], "Naphtha 일본")
        self.assertEqual(r["fit"]["regime_start"], self.dates[20])

    def test_feed_unspecified_probe(self):
        _, by = self.rows()
        r = by["아세톤 스프레드(한국)"]
        self.assertTrue(r["reproduced"])
        self.assertIn("feed_unspecified", r["flags"])
        self.assertEqual(r["feeds"][0]["name"], "Propylene 한국")
        self.assertAlmostEqual(r["feeds"][0]["k"], 0.85, 2)

    def test_chain_est_and_price_rows(self):
        reg, by = self.rows()
        r = by["AN-프로필렌 스프레드(한국)"]
        self.assertIsNone(r["chain"])
        self.assertEqual(r["chain_est"], "ncc")
        self.assertTrue(all(s["est"] for s in r["stocks"]))
        self.assertEqual(by["메탄올 가격(한국)"]["kind"], "price")
        self.assertEqual(by["벤젠 선물 주력 (纯苯)"]["kind"], "proxy_cnfut")
        self.assertEqual(reg["summary"]["rows"], 9)
        self.assertEqual(reg["summary"]["spreads"], 7)
        self.assertEqual(reg["summary"]["reproduced"], 7)

    def test_derived(self):
        reg, _ = self.rows()
        d = {x["sid"]: x for x in reg["derived"]}
        ok = d["derived:pe_hdpe_inj_naphtha_한국"]
        self.assertIsNotNone(ok["values"])
        i = len(reg["axis2y"]) - 1
        exp = round(self.P["HDPE(사출) 한국"][-1] - self.P["Naphtha 일본"][-1], 2)
        self.assertEqual(ok["values"][i], exp)
        self.assertIn("derived_estimate", ok["flags"])
        self.assertIn("constituent_missing", d["derived:pe_ldpe_naphtha_한국"]["flags"])
        self.assertIsNone(d["derived:pe_ldpe_naphtha_한국"]["values"])

    def test_ledger_stale_weeks(self):
        reg, _ = self.rows()
        self.assertEqual(reg["summary"]["ledger_last"], self.dates[-1])
        import datetime
        expect = (datetime.date(2026, 8, 31) - datetime.date.fromisoformat(self.dates[-1])).days // 7
        self.assertEqual(reg["summary"]["ledger_stale_weeks"], expect)


# ── 페이지 ──────────────────────────────────────────────────

class TestPages(SyntheticBase):
    def _build(self):
        # kchem_page 는 모듈 경로(ARGUS)를 보므로 fixture 경로로 잠시 바꾼다
        orig_all = kchem_inputs.load_all
        kchem_inputs.load_all = lambda argus_dir=None, categories=None: orig_all(self.argus, categories)
        try:
            reg, outputs = kchem_page.build(write=False)
        finally:
            kchem_inputs.load_all = orig_all
        return reg, outputs

    def test_pages_contract_and_determinism(self):
        reg, out1 = self._build()
        _, out2 = self._build()
        self.assertEqual(out1, out2)
        names = {os.path.relpath(p, kchem_page.KCHEM) for p in out1}
        self.assertTrue({"index.html", "spreads.html", "matrix.html", "chains.html", "coverage.html", "data/kchem_data.js",
                         "011170/index.html", "011780/index.html"} <= names)
        js = out1[os.path.join(kchem_page.DATA_DIR, "kchem_data.js")]
        self.assertTrue(js.startswith("window.KCHEM="))
        data = json.loads(js[len("window.KCHEM="):].rstrip().rstrip(";"))
        self.assertEqual(len(data["axes"]["wk"]), len(self.dates))
        self.assertIn(self.sid_of["에틸렌-납사 스프레드(한국)"], data["series"])
        self.assertEqual(len(data["rows"]), reg["summary"]["rows"] + len(reg["derived"]))
        sp = out1[os.path.join(kchem_page.KCHEM, "spreads.html")]
        self.assertIn("Ethylene 한국 − 1×Naphtha 일본", sp)
        self.assertIn("이름에 없는 원료 추가", sp)
        self.assertNotIn("%s", sp)
        for text in out1.values():
            self.assertLess(len(text.encode("utf-8")), 5 * 1024 * 1024)
            self.assertNotIn("<script>undefined", text)


# ── 실제 입력(있을 때만) ────────────────────────────────────

@unittest.skipUnless(os.path.isfile(os.path.join(ARGUS, "data", "argus_data.js")), "실제 ARGUS 산출물 없음")
class TestLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.fp = kchem_inputs.load_all()
        cls.reg = kchem_registry.Registry(cls.inputs, cls.fp).build()

    def test_rows_equal_panel_chem_series(self):
        panel = [s for s in self.inputs["argus"]["spread"]["series"] if s["cat"] in CHEM_CATS]
        self.assertEqual(self.reg["summary"]["rows"], len(panel))
        self.assertEqual({r["sid"] for r in self.reg["rows"]}, {s["sid"] for s in panel})

    def test_reproduction_floor(self):
        s = self.reg["summary"]
        self.assertGreaterEqual(s["reproduced"], int(0.8 * s["spreads"]))
        for r in self.reg["rows"]:
            if r["kind"] == "spread":
                self.assertIsNotNone(r["region"], r["name"])
                self.assertIsNotNone(r["product"], r["name"])

    def test_registry_file_matches_inputs(self):
        path = os.path.join(TOOLS, "assets", "registry.json")
        if not os.path.isfile(path):
            self.skipTest("registry.json 미생성")
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["fingerprint"], self.fp["fingerprint"], "registry.json 이 현재 입력과 다른 fingerprint — 다시 빌드할 것")
        self.assertEqual(on_disk["summary"]["rows"], self.reg["summary"]["rows"])


if __name__ == "__main__":
    unittest.main()
