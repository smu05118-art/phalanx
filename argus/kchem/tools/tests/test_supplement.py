# -*- coding: utf-8 -*-
"""사용자 가격표(kchem_supplement) — 합성 xlsx 해석·검증 판정·원장 우선 잇기·산식 연장·fingerprint."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import kchem_inputs        # noqa: E402
import kchem_registry      # noqa: E402
import kchem_supplement as K   # noqa: E402

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def make_xlsx(path, header, rows):
    """header = [(분류, 제품, 지역)], rows = [(date, [v…])] — 공유 문자열 + 일련번호 날짜."""
    strs = ["날짜"] + [h for trip in header for h in trip]
    idx = {s: i for i, s in enumerate(dict.fromkeys(strs))}
    cols = [chr(ord("B") + i) for i in range(len(header))]

    def cell(ref, v, s=False):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, ' t="s"' if s else "", idx[v] if s else v)
    xml = ['<row r="1">' + cell("A1", "날짜", True) + "".join(cell("%s1" % c, h[0], True) for c, h in zip(cols, header)) + "</row>",
           '<row r="2">' + "".join(cell("%s2" % c, h[1], True) for c, h in zip(cols, header)) + "</row>",
           '<row r="3">' + "".join(cell("%s3" % c, h[2], True) for c, h in zip(cols, header) if h[2]) + "</row>"]
    for i, (d, vals) in enumerate(rows):
        r = 4 + i
        serial = (datetime.date.fromisoformat(d) - datetime.date(1899, 12, 30)).days
        xml.append('<row r="%d">' % r + cell("A%d" % r, serial) + "".join(cell("%s%d" % (c, r), v) for c, v in zip(cols, vals) if v is not None) + "</row>")
    ss = "".join("<si><t>%s</t></si>" % s for s in idx)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="%s" xmlns:r="%s"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>' % (M, R))
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", '<sst xmlns="%s">%s</sst>' % (M, ss))
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (M, "".join(xml)))


class TestReadImport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kchem_supp_")
        self.p = os.path.join(self.d, "p.xlsx")
        dates = [(datetime.date(2026, 1, 5) + datetime.timedelta(weeks=i)).isoformat() for i in range(40)]
        rows = [(d, [100 + i, (100 + i) * 1.3, 50]) for i, d in enumerate(dates)]
        make_xlsx(self.p, [("기초유분", "에틸렌", "KOREA FOB"), ("", "에틸렌", "SE ASIA FOB"), ("원료", "Henry Hub(MMBtu)", "")], rows)
        self.dates = dates

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_read(self):
        cols, n, sheet = K.read_xlsx(self.p)
        self.assertEqual((n, sheet), (40, "Sheet1"))
        self.assertEqual([(c["cat"], c["name"], c["region"]) for c in cols],
                         [("기초유분", "에틸렌", "KOREA FOB"), ("기초유분", "에틸렌", "SE ASIA FOB"), ("원료", "Henry Hub(MMBtu)", "")])
        self.assertEqual(cols[0]["obs"][0], ["2026-01-05", 100.0])

    def test_import_checks(self):
        led = [{"sid": "p_ethylene_한국", "last_date": self.dates[29], "observations": [[d, 100 + i] for i, d in enumerate(self.dates[:30])]},
               {"sid": "p_ethylene_동남아", "last_date": self.dates[29], "observations": [[d, 100 + i] for i, d in enumerate(self.dates[:30])]}]
        doc = K.import_xlsx(self.p, led, name="화학제품 가격.xlsx")
        st = {s["key"]: s["check"]["status"] for s in doc["series"]}
        self.assertEqual(st["p_ethylene_한국"], "ok")              # 30주 겹침 전부 같다
        self.assertEqual(st["p_ethylene_동남아"], "mismatch")      # 1.3배 — 같은 원천이 아니다
        self.assertEqual([s["check"]["status"] for s in doc["series"] if s["sid"] is None], ["unmapped"])
        self.assertEqual(doc["source"]["file"], "화학제품 가격.xlsx")
        self.assertEqual(doc["source"]["last_date"], self.dates[-1])

    def test_not_a_price_sheet(self):
        """A1 이 '날짜' 가 아니면(다른 서식의 엑셀) 멈춘다 — 열을 추측해 잇지 않는다."""
        bad = os.path.join(self.d, "bad.xlsx")
        make_xlsx(bad, [("a", "b", "c")], [("2026-01-05", [1])])
        with zipfile.ZipFile(bad) as z:
            files = {n: z.read(n) for n in z.namelist()}
        files["xl/sharedStrings.xml"] = files["xl/sharedStrings.xml"].decode().replace("<t>날짜</t>", "<t>일자</t>").encode()
        with zipfile.ZipFile(bad, "w") as z:
            for n, b in files.items():
                z.writestr(n, b)
        with self.assertRaises(K.SupplementError):
            K.read_xlsx(bad)


@unittest.skipUnless(K.load(), "assets/supplement/prices.json 없음")
class TestAugmentReal(unittest.TestCase):
    """커밋된 가격표로 실제 입력을 이은 결과 — 원장 우선·산식 연장·fingerprint."""

    @classmethod
    def setUpClass(cls):
        cls.raw, cls.fp0 = kchem_inputs.load_all(supplement=False)
        cls.inp, cls.fp = kchem_inputs.load_all()
        cls.summ = cls.inp["supplement"]["summary"]

    def test_ledger_first(self):
        raw = {r["sid"]: r for r in self.raw["connections"]["rows"]}["p_ethylene_한국"]
        aug = {r["sid"]: r for r in self.inp["connections"]["rows"]}["p_ethylene_한국"]
        self.assertEqual(aug["observations"][:len(raw["observations"])], raw["observations"])     # 원장 날짜는 그대로
        self.assertTrue(all(d > raw["last_date"] for d, _v in aug["observations"][len(raw["observations"]):]))
        self.assertGreater(aug["last_date"], raw["last_date"])

    def test_spread_formula_extension(self):
        conn = {r["sid"]: r for r in self.inp["connections"]["rows"]}
        reg = kchem_registry.Registry(self.inp, self.fp).build()
        rows = {r["sid"]: r for r in reg["rows"]}
        sid = self.summ["spread_sids"][0]
        r = rows[sid]
        P = dict(conn[r["product_sid"]]["observations"])
        d = r["last_date"]
        div = (1000.0 / 108.0) if r.get("unit_hint") == "USD/bbl" else 1.0
        want = round(P[d] / div - sum(f["k"] * dict(conn[f["sid"]]["observations"])[d] for f in r["feeds"]), 2)
        self.assertAlmostEqual(r["last"], want, 2)

    def test_mismatch_not_extended_and_fingerprint(self):
        conn = {r["sid"]: r for r in self.inp["connections"]["rows"]}
        raw = {r["sid"]: r for r in self.raw["connections"]["rows"]}
        self.assertEqual(conn["p_ethane_미국"]["last_date"], raw["p_ethane_미국"]["last_date"])   # 기준 다름 — 잇지 않음
        self.assertNotEqual(self.fp["fingerprint"], self.fp0["fingerprint"])
        self.assertIn("supplement/prices.json", self.fp["inputs"])
        self.assertEqual(self.summ["ledger_last"], max(r["last_date"] for r in self.raw["connections"]["rows"]
                                                       if r["sid"].startswith("sp_") and r["last_date"] and r["sid"] in conn
                                                       and any(r["sid"] == s["sid"] for c in self.raw["chunks"].values() for s in c["series"])))


if __name__ == "__main__":
    unittest.main()
