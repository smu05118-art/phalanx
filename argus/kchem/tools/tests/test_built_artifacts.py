# -*- coding: utf-8 -*-
"""빌드 후에만 검사할 산출물 계약. 입력/파서 검사는 test_kchem.py에서 빌드 전에도 수행한다."""
import json
import os
import unittest

from test_kchem import TOOLS, kchem_inputs, kchem_registry


class TestBuiltArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs, cls.fp = kchem_inputs.load_all()
        cls.reg = kchem_registry.Registry(cls.inputs, cls.fp).build()

    def test_registry_file_matches_inputs(self):
        path = os.path.join(TOOLS, "assets", "registry.json")
        # 이 테스트는 빌드 이후 계약이다. 산출물이 없거나 오래되면 실패한다.
        with open(path, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["fingerprint"], self.fp["fingerprint"],
                         "registry.json 이 현재 입력과 다른 fingerprint — 다시 빌드할 것")
        self.assertEqual(on_disk["summary"]["rows"], self.reg["summary"]["rows"])


if __name__ == "__main__":
    unittest.main()
