#!/usr/bin/env python3
"""tools/split_country_sets.py 단위 + 프론트 계약 테스트.

  python3 -m unittest discover -s tools/tests -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)

import split_country_sets as S  # noqa: E402


def cube(country, country_i=None):
    d = {"country": country}
    if country_i is not None:
        d["country_i"] = country_i
    return d


def write_src(path, reg, data):
    with open(path, "w", encoding="utf-8") as f:
        f.write('var PSHC=window.PSHC||(window.PSHC={});PSHC["%s"]=%s;'
                % (reg, json.dumps(data, ensure_ascii=False, separators=(",", ":"))))


FIXTURE = cube(
    {"probe_core": {"order": ["Korea", "기타"],
                    "loc": {"100": {"Korea": [1, 2, 0], "기타": [0, 0, 3]}},
                    "locw": {"100": {"Korea": [4, 5, 0], "기타": [0, 0, 6]}}},
     "mem_broad": {"order": ["China"], "loc": {"200": {"China": [7, 8, 9]}}}},
    {"probe_core": {"order": ["Taiwan"], "loc": {"100": {"Taiwan": [1, 0, 1]}}},
     "imp_only": {"order": ["USA"], "loc": {"300": {"USA": [2, 2, 2]}}}},
)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.src = os.path.join(self.dir, "data_jp_country.js")
        self.out = os.path.join(self.dir, "out")
        write_src(self.src, "JP", FIXTURE)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_split(self, *extra):
        S.main(["split_country_sets.py", self.src, "JP", self.out] + list(extra))


class TestSplit(Base):
    def test_one_file_per_set_union(self):
        """세트 파일은 country ∪ country_i 기준으로 만들어진다."""
        self.run_split()
        got = sorted(f for f in os.listdir(self.out) if f.endswith(".js"))
        self.assertEqual(got, ["imp_only.js", "mem_broad.js", "probe_core.js"])

    def test_roundtrip_identical(self):
        """샤드를 전부 합치면 원본 큐브와 정확히 같다."""
        self.run_split("--verify")          # --verify 실패 시 SystemExit
        keys = sorted(set(FIXTURE["country"]) | set(FIXTURE["country_i"]))
        self.assertTrue(S.roundtrip(self.out, "JP", FIXTURE, keys))

    def test_both_cubes_in_one_file(self):
        """country와 country_i에 같은 키가 있으면 한 파일에 둘 다 담는다."""
        self.run_split()
        js = open(os.path.join(self.out, "probe_core.js"), encoding="utf-8").read()
        self.assertIn('(R.country||(R.country={}))["probe_core"]=', js)
        self.assertIn('(R.country_i||(R.country_i={}))["probe_core"]=', js)
        js2 = open(os.path.join(self.out, "mem_broad.js"), encoding="utf-8").read()
        self.assertNotIn("country_i", js2)

    def test_index_contract(self):
        """_index.json이 manifest region.csets에 그대로 들어갈 형태인가."""
        self.run_split()
        idx = json.load(open(os.path.join(self.out, "_index.json"), encoding="utf-8"))
        self.assertEqual(idx["region"], "JP")
        self.assertEqual(idx["sets"], ["imp_only", "mem_broad", "probe_core"])
        self.assertEqual(idx["in_country"], ["mem_broad", "probe_core"])
        self.assertEqual(idx["in_country_i"], ["imp_only", "probe_core"])

    def test_deterministic_bytes(self):
        """같은 입력 → 같은 바이트 (AGENTS.md 규약 5: diff 노이즈 방지)."""
        self.run_split()
        first = {f: open(os.path.join(self.out, f), "rb").read()
                 for f in sorted(os.listdir(self.out))}
        shutil.rmtree(self.out)
        self.run_split()
        second = {f: open(os.path.join(self.out, f), "rb").read()
                  for f in sorted(os.listdir(self.out))}
        self.assertEqual(first, second)

    def test_no_tmp_left_behind(self):
        """원자적 쓰기의 tmp 파일이 남지 않는다."""
        self.run_split()
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".tmp")], [])


class TestFailClosed(Base):
    def test_path_traversal_key_rejected(self):
        """세트 키가 파일명으로 위험하면 아무것도 쓰지 않고 죽는다."""
        write_src(self.src, "JP", cube({"../../evil": {"order": [], "loc": {}}}))
        with self.assertRaises(SystemExit):
            self.run_split()
        self.assertFalse(os.path.exists(self.out))

    def test_unknown_top_key_rejected(self):
        """스키마가 바뀌면(모르는 최상위 키) 조용히 버리지 않는다."""
        d = dict(FIXTURE); d["country_w"] = {"x": 1}
        write_src(self.src, "JP", d)
        with self.assertRaises(SystemExit):
            self.run_split()

    def test_missing_marker_rejected(self):
        with open(self.src, "w", encoding="utf-8") as f:
            f.write("var PSHC={};PSHC[\"KR\"]={};")
        with self.assertRaises(SystemExit):
            self.run_split()


    def test_bad_region_rejected(self):
        with self.assertRaises(SystemExit):
            S.main(["x", self.src, "jp/../", self.out])

    def test_empty_cube_is_not_an_error(self):
        """빈 국가 큐브는 정상이다 — 실제로 ALT·TW·TB 등 12개 리전이 그렇다."""
        write_src(self.src, "JP", cube({}, {}))
        self.run_split()
        idx = json.load(open(os.path.join(self.out, "_index.json"), encoding="utf-8"))
        self.assertEqual(idx["sets"], [])
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".js")], [])


NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "node 없음 — 계약 테스트 생략")
class TestFrontContract(Base):
    """샤드가 ui/patch.js 모듈 8이 기대하는 전역 모양을 실제로 만드는가."""

    def node_eval(self, script):
        p = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def test_shards_build_expected_globals(self):
        self.run_split()
        a = os.path.join(self.out, "probe_core.js").replace("\\", "/")
        b = os.path.join(self.out, "imp_only.js").replace("\\", "/")
        # 로드 순서에 무관하게 멱등이어야 한다 — b를 먼저 넣어본다
        out = self.node_eval(
            "global.window=global;"
            "const fs=require('fs');"
            "eval(fs.readFileSync('%s','utf8'));"
            "eval(fs.readFileSync('%s','utf8'));"
            "eval(fs.readFileSync('%s','utf8'));"   # 중복 로드도 안전한가
            "const R=window.PSHC.JP;"
            "console.log(JSON.stringify({"
            " c:Object.keys(R.country).sort(), i:Object.keys(R.country_i).sort(),"
            " loc:R.country.probe_core.loc['100'].Korea}));" % (b, a, a))
        got = json.loads(out)
        self.assertEqual(got["c"], ["probe_core"])
        self.assertEqual(got["i"], ["imp_only", "probe_core"])
        self.assertEqual(got["loc"], [1, 2, 0])

    def test_patch_js_handles_cdir(self):
        """patch.js 모듈 8이 cdir/csets 계약을 실제로 들고 있는가."""
        js = open(os.path.join(ROOT, "ui", "patch.js"), encoding="utf-8").read()
        for needle in ("cdir", "csets", "mergeSet", "trimSets", "__PHX_COUNTRY_LAZY__"):
            self.assertIn(needle, js, "patch.js에 %s 계약이 없다" % needle)
        # cfile 폴백 경로가 살아 있어야 한다 (빌더 미적용 리전)
        self.assertIn("r.cfile", js)

    def test_patch_js_parses(self):
        p = subprocess.run([NODE, "--check", os.path.join(ROOT, "ui", "patch.js")],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_module8_runtime(self):
        """모듈 8을 실제로 돌려 세트 단위 로딩·LRU·폴백을 확인한다.

        하네스가 검사하는 것: cdir 모드에서 현재 세트만 요청 / 재요청 시 네트워크 없음 /
        세트 전환 시 그 세트만 / csets 밖은 요청 안 함 / 404는 한 번만 /
        LRU 상한 / cfile 폴백(상태 c) / 빌더 미적용(상태 a).
        """
        self.run_split()
        p = subprocess.run(
            [NODE, os.path.join(HERE, "patch_module8_harness.js"), self.out],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("OK", p.stdout)


if __name__ == "__main__":
    unittest.main()
