import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fetch_comext as fc  # noqa: E402

SPEC = {"output": "out.json", "reporter": "IT", "product": "90309000", "flow": 2, "since": "2020-01",
        "total_partner": "WORLD", "partners": ["WORLD", "TW"]}


def jsonstat(months, world, tw):
    """partner × time 2차원 JSON-stat 픽스처 (나머지 차원 크기 1)."""
    vals = {}
    for i, v in enumerate(tw):
        if v is not None:
            vals[str(i)] = v
    for i, v in enumerate(world):
        if v is not None:
            vals[str(len(months) + i)] = v
    return json.dumps({
        "version": "2.0", "updated": "2026-09-15T11:00:00+0200", "value": vals,
        "id": ["freq", "reporter", "partner", "product", "flow", "indicators", "time"],
        "size": [1, 1, 2, 1, 1, 1, len(months)],
        "dimension": {
            "freq": {"category": {"index": {"M": 0}}}, "reporter": {"category": {"index": {"IT": 0}}},
            "partner": {"category": {"index": {"TW": 0, "WORLD": 1}}},
            "product": {"category": {"index": {"90309000": 0}}}, "flow": {"category": {"index": {"2": 0}}},
            "indicators": {"category": {"index": {"VALUE_IN_EUROS": 0}}},
            "time": {"category": {"index": {m: i for i, m in enumerate(months)}}}},
    }).encode()


def months_from(y, m, n):
    out = []
    for _ in range(n):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class TestParse(unittest.TestCase):
    def test_parse_maps_partner_and_time(self):
        ms = months_from(2026, 1, 3)
        out, upd = fc.parse_jsonstat(jsonstat(ms, [10, 20, None], [1, 2, 3]), SPEC)
        self.assertEqual(out["WORLD"], {"2026-01": 10, "2026-02": 20})
        self.assertEqual(out["TW"], {"2026-01": 1, "2026-02": 2, "2026-03": 3})
        self.assertTrue(upd.startswith("2026-09-15"))

    def test_missing_partner_fails(self):
        spec = dict(SPEC, partners=["WORLD", "TW", "KR"])
        with self.assertRaises(fc.FetchError):
            fc.parse_jsonstat(jsonstat(months_from(2026, 1, 2), [1, 1], [1, 1]), spec)

    def test_negative_value_fails(self):
        with self.assertRaises(fc.FetchError):
            fc.parse_jsonstat(jsonstat(months_from(2026, 1, 2), [1, -5], [1, 1]), SPEC)

    def test_url_is_https_allowlisted(self):
        url = fc.build_url(SPEC)
        self.assertTrue(url.startswith("https://ec.europa.eu/"))
        self.assertIn("partner=TW", url)


class TestRun(unittest.TestCase):
    def test_window_merge_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "cfg.json")
            json.dump({"series": [SPEC]}, open(cfg, "w"))
            ms = months_from(2020, 1, 70)
            fc.run(cfg, d, fetch=lambda url: jsonstat(ms, list(range(1, 71)), [5] * 70))
            # 두 번째 응답은 최근 월만 + 리비전 → 과거는 보존, 겹치는 월은 갱신
            recent = ms[-2:] + ["2025-11"]
            fc.run(cfg, d, fetch=lambda url: jsonstat(recent, [999, 999, 7], [6, 6, 6]))
            out = json.load(open(os.path.join(d, "out.json")))
            w = out["partners"]["WORLD"]
            self.assertEqual(w["2020-01"], 1)
            self.assertEqual(w[ms[-1]], 999)
            self.assertEqual(w["2025-11"], 7)
            self.assertEqual(list(w), sorted(w))

    def test_validation_failure_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "cfg.json")
            json.dump({"series": [SPEC]}, open(cfg, "w"))
            path = os.path.join(d, "out.json")
            open(path, "w").write('{"partners": {}}')
            with self.assertRaises(fc.FetchError):
                fc.run(cfg, d, fetch=lambda url: jsonstat(months_from(2026, 1, 3), [1, 2, 3], [1, 1, 1]))
            self.assertEqual(open(path).read(), '{"partners": {}}')


if __name__ == "__main__":
    unittest.main()
