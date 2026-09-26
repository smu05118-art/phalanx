#!/usr/bin/env python3
"""tools/shrink_korea_trade.py 단위 테스트.

브라우저 검증은 tools/tests/drive_korea_trade.js 참조(playwright 필요, 수동).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)

import shrink_korea_trade as K  # noqa: E402

TD = {
    "meta": {"months": ["202506", "202507"], "latest": "202507",
             "prevY": "202407", "prevM": "202506"},
    "cnames": {"JP": "일본", "RU": "러시아"},
    "rnames": {},
    "hs2": {"01": "산동물"}, "hs4": {"0101": "말"},
    "curated": {"order": [], "items": {}},
    "total": {"exp": {}}, "companies": {"meta": {}, "list": []},
    "rows": [
        {"hs": "010121", "nm": "번식용", "e": {"202507": 9}, "w": {"202507": 1},
         "c": {"JP": {"nm": "일본", "e": {"202507": 5}},
               "RU": {"nm": "러시아 연방", "e": {"202507": 4}}}},
        {"hs": "854232", "nm": "메모리", "e": {"202507": 7}, "w": {"202507": 2},
         "c": {"US": {"nm": "미국", "e": {"202507": 7}}}},
    ],
}

RENDER = """
"use strict"; const M=TD.meta, CN=TD.cnames||{}, RN=TD.rnames||{};
function toggleExpand(tr,r){
  const nx=tr.nextElementSibling;
  if(nx&&nx.classList.contains('exprow')){nx.remove();tr.classList.remove('exp');return;}
  const citems=dimItems(r.c,state.lat);
}
function brOpen(hs){BR.openHs=BR.openHs===hs?null:hs;renderBrowse();}
/* ============================================================ TAXONOMY ======
   통일 분류 norm */
const TAXO=[];
"""


def html(td=None, render=RENDER):
    return ("<html><body><script>var TD=%s;</script>\n<script>%s</script></body></html>"
            % (json.dumps(td if td is not None else TD, ensure_ascii=False,
                          separators=(",", ":")), render))


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, "korea_trade.html")
        self.write(html())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, text):
        with open(self.src, "w", encoding="utf-8") as f:
            f.write(text)

    def run_tool(self, *extra):
        K.main(["shrink_korea_trade.py", self.src] + list(extra))

    def out_td(self):
        with open(self.src, encoding="utf-8") as f:
            s = f.read()
        i, td, _ = K.split_td(s)
        return s, td

    def shard(self, h2):
        with open(os.path.join(self.dir, K.SHARD_DIR, h2 + ".json"), encoding="utf-8") as f:
            return json.load(f)


class TestShrink(Base):
    def test_rows_c_removed_and_sharded(self):
        """rows[].c는 본문에서 사라지고 HS2별 샤드로 간다."""
        self.run_tool()
        _, td = self.out_td()
        self.assertTrue(all("c" not in r for r in td["rows"]))
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, K.SHARD_DIR))),
                         ["01.json", "85.json"])
        self.assertEqual(self.shard("01")["010121"]["JP"]["e"], {"202507": 5})
        self.assertEqual(self.shard("85")["854232"]["US"]["e"], {"202507": 7})

    def test_inline_names_moved_to_cnames(self):
        """c[].nm은 지우고 cnames로 올린다 — 인라인 이름이 기존 cnames보다 우선."""
        self.run_tool()
        _, td = self.out_td()
        self.assertEqual(td["cnames"]["US"], "미국")        # 신규
        self.assertEqual(td["cnames"]["RU"], "러시아 연방")  # 인라인이 이긴다
        for hs2 in ("01", "85"):
            for cv in self.shard(hs2).values():
                for entry in cv.values():
                    self.assertNotIn("nm", entry)

    def test_all_months_survive(self):
        """월 선택 드롭다운이 15개월을 다 쓰므로 월을 잘라내면 안 된다."""
        self.run_tool()
        self.assertEqual(self.shard("01")["010121"]["JP"]["e"], {"202507": 5})
        _, td = self.out_td()
        self.assertEqual(td["meta"]["months"], ["202506", "202507"])
        self.assertEqual(td["rows"][0]["e"], {"202507": 9})   # 본문 시계열은 그대로

    def test_render_patched(self):
        self.run_tool()
        s, _ = self.out_td()
        self.assertIn("function needC(hs,cb)", s)
        self.assertIn("if(!r.c) return needC(r.hs,()=>toggleExpand(tr,r));", s)
        self.assertIn("if(BR.openHs) return needC(BR.openHs,renderBrowse);", s)
        self.assertIn(K.SHARD_DIR + "/", s)

    def test_idempotent(self):
        self.run_tool()
        with open(self.src, encoding="utf-8") as f:
            once = f.read()
        self.run_tool()                       # 두 번째는 no-op이어야 한다
        with open(self.src, encoding="utf-8") as f:
            self.assertEqual(f.read(), once)

    def test_check_writes_nothing(self):
        before = open(self.src, encoding="utf-8").read()
        self.run_tool("--check")
        self.assertEqual(open(self.src, encoding="utf-8").read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.dir, K.SHARD_DIR)))

    def test_shard_deterministic(self):
        self.run_tool()
        first = open(os.path.join(self.dir, K.SHARD_DIR, "01.json"), "rb").read()
        shutil.rmtree(self.dir); os.makedirs(self.dir)
        self.write(html()); self.run_tool()
        self.assertEqual(open(os.path.join(self.dir, K.SHARD_DIR, "01.json"), "rb").read(),
                         first)


class TestFailClosed(Base):
    def test_missing_td(self):
        self.write("<html><script>var NOPE={};</script></html>")
        with self.assertRaises(SystemExit):
            self.run_tool()

    def test_missing_patch_anchor(self):
        """렌더 스크립트가 바뀌어 패치 지점이 없어지면 조용히 넘어가지 않는다."""
        self.write(html(render=RENDER.replace(
            "function brOpen(hs){BR.openHs=BR.openHs===hs?null:hs;renderBrowse();}", "")))
        with self.assertRaises(SystemExit):
            self.run_tool()

    def test_already_split_rejected(self):
        td = json.loads(json.dumps(TD))
        for r in td["rows"]:
            r.pop("c")
        self.write(html(td))
        with self.assertRaises(SystemExit):
            self.run_tool()

    def test_bad_json(self):
        self.write("<html><script>var TD={nope;</script></html>")
        with self.assertRaises(SystemExit):
            self.run_tool()


if __name__ == "__main__":
    unittest.main()
