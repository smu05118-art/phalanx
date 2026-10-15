"""계약공시 정상 0건과 검색/본문 실패를 실행 결과에서 구분한다."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ksemi_contracts as K


class TestContractCollectionStatus(unittest.TestCase):
    def run_main(self, result, *, offline=False, missing=True, rows=None):
        stock = {"stock": "123456", "name": "검증회사"}
        def parallel(items, one, on_done):
            for i, row in enumerate(items):
                try:
                    value = one(row)
                except Exception as error:
                    value = error
                on_done(i, row, value)
        args = ["ksemi_contracts.py", "--write", "--since", "20210101", "--until", "20261015"]
        if offline:
            args.append("--no-collect")
        with mock.patch.object(sys, "argv", args), \
                mock.patch.object(K, "_stocks", return_value=[stock]), \
                mock.patch.object(K, "collect_stock", side_effect=result if isinstance(result, Exception) else None,
                                  return_value=result) as collect, \
                mock.patch.object(K, "parallel", side_effect=parallel), \
                mock.patch.object(K, "build", return_value=(rows or [], [stock["stock"]] if missing else [])), \
                mock.patch.object(K, "recent", return_value=[]), \
                mock.patch.object(K, "write_asset") as write, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = K.main()
        return code, write.call_args.args[1], collect.call_count

    def test_confirmed_zero_is_success_without_cache(self):
        code, payload, called = self.run_main((0, 0, 0))
        self.assertEqual((code, called, payload["errors"], payload["rows"]), (0, 1, [], []))
        self.assertEqual(payload["collection"]["123456"],
                         {"status": "success", "contracts": 0, "cached": 0, "failed": 0})

    def test_search_exception_is_not_confirmed_zero(self):
        code, payload, _ = self.run_main(OSError("source unavailable"))
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertIn("OSError", payload["errors"][0]["error"])
        self.assertIsNone(payload["collection"]["123456"]["contracts"])

    def test_partial_body_failure_is_reported_even_with_existing_cache(self):
        row = {"stock": "123456", "rcp": "20261015000001", "filed": "20261015", "name": "검증회사",
               "amt_mkrw": 17, "unit_seen": True, "parse_flags": []}
        code, payload, _ = self.run_main((2, 1, 1), missing=False, rows=[row])
        self.assertEqual(code, 1)
        self.assertEqual(payload["rows"], [row])
        self.assertEqual(payload["collection"]["123456"]["status"], "partial")
        self.assertIn("2건 중 1건", payload["errors"][0]["error"])

    def test_all_bodies_failed_is_not_zero_or_duplicate_error(self):
        code, payload, _ = self.run_main((2, 0, 2))
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertEqual(payload["collection"]["123456"]["contracts"], 2)

    def test_offline_missing_cache_is_unknown_not_zero(self):
        code, payload, called = self.run_main((0, 0, 0), offline=True)
        self.assertEqual((code, called, payload["collection"]), (1, 0, {}))
        self.assertIn("정상 0건 확인 없음", payload["errors"][0]["error"])

    def test_successful_collection_with_missing_cache_remains_failure(self):
        code, payload, _ = self.run_main((1, 1, 0))
        self.assertEqual(code, 1)
        self.assertEqual(len(payload["errors"]), 1)

    def test_parse_uncertainty_stays_in_record(self):
        row = {"stock": "123456", "rcp": "20261015000001", "filed": "20261015", "name": "검증회사",
               "amt_mkrw": None, "unit_seen": False, "parse_flags": ["계약금액 라벨 매칭 실패"]}
        code, payload, _ = self.run_main((1, 1, 0), missing=False, rows=[row])
        self.assertEqual(code, 0)
        self.assertEqual(payload["rows"], [row])
        self.assertEqual(payload["errors"], [])

    def test_offline_existing_cache_remains_success(self):
        code, payload, called = self.run_main((0, 0, 0), offline=True, missing=False)
        self.assertEqual((code, payload["errors"], called), (0, [], 0))


if __name__ == "__main__":
    unittest.main()
