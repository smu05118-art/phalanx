from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPEC = importlib.util.spec_from_file_location("update_tga_target", TOOLS / "update_tga_target.py")
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)

DISCOVERY = (FIXTURES / "discovery.html").read_text(encoding="utf-8")
RELEASE = (FIXTURES / "release.html").read_text(encoding="utf-8")
AS_OF = dt.date(2026, 8, 14)
RELEASE_URL = "https://home.treasury.gov/news/press-releases/sb0584"


def fixture_fetch(discovery: str = DISCOVERY, release: str = RELEASE):
    def fetch(url: str, kind: str, timeout: float):
        del timeout
        if kind == "discovery":
            return updater.DISCOVERY_URL, discovery
        if kind == "release" and url == RELEASE_URL:
            return RELEASE_URL, release
        raise AssertionError((url, kind))

    return fetch


class TreasuryUpdaterTests(unittest.TestCase):
    def test_successful_normalization_is_schema_v2_and_deterministic(self):
        first = updater.build_config(as_of=AS_OF, fetch=fixture_fetch())
        second = updater.build_config(as_of=AS_OF, fetch=fixture_fetch())
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 2)
        self.assertEqual(
            first["release"]["source_id"],
            "us_treasury_quarterly_borrowing_estimates",
        )
        self.assertEqual(first["release"]["source_url"], RELEASE_URL)
        self.assertEqual(first["release"]["source_published_date"], "2026-08-03")
        self.assertEqual(first["release"]["source_published_label"], "260803")
        self.assertEqual(
            first["release"]["sources_uses_url"],
            "https://home.treasury.gov/system/files/136/Sources-Uses-Public-Table-August-2026.pdf",
        )
        self.assertRegex(first["release"]["article_content_sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(
            [(item["value"], item["target_date"]) for item in first["assumptions"]],
            [(950, "2026-09-30"), (850, "2026-12-31")],
        )
        decoded = json.loads(updater.serialize_config(first))
        self.assertEqual(decoded, first)

    def test_content_hash_contract_collapses_whitespace_and_appends_lf(self):
        normalized = updater.normalized_article_text([" A\n\tB ", " C\u00a0D "])
        self.assertEqual(normalized, "A B C D\n")
        self.assertEqual(
            hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "7f1656704b876fe5991eeefcd8d680064e7f729598edf0fbf5e7077583a2b9f4",
        )

    def test_malformed_release_with_one_forecast_is_rejected(self):
        malformed = RELEASE.replace(
            "<li>During the October–December 2026 quarter, Treasury expects to borrow $628 billion in privately-held net marketable debt, assuming an end-of-December cash balance of $850 billion.</li>",
            "",
        )
        with self.assertRaisesRegex(updater.UpdateError, "exactly two forward assumptions"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(release=malformed))

    def test_non_quarter_end_language_is_rejected(self):
        malformed = RELEASE.replace("end-of-September", "end-of-December", 1)
        with self.assertRaisesRegex(updater.UpdateError, "exact calendar quarter"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(release=malformed))

    def test_hostile_discovery_host_is_rejected(self):
        hostile = DISCOVERY.replace(
            "/news/press-releases/sb0584",
            "https://home.treasury.gov.attacker.invalid/news/press-releases/sb9999",
        )
        with self.assertRaisesRegex(updater.UpdateError, "non-official"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(discovery=hostile))

    def test_hostile_sources_and_uses_host_is_rejected(self):
        hostile = RELEASE.replace(
            "/system/files/136/Sources-Uses-Public-Table-August-2026.pdf",
            "https://home.treasury.gov.attacker.invalid/system/files/136/fake.pdf",
        )
        with self.assertRaisesRegex(updater.UpdateError, "non-official"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(release=hostile))

    def test_duplicate_financing_links_are_ambiguous(self):
        duplicate = DISCOVERY.replace(
            "</div>",
            '<p><a href="/news/press-releases/sb0584">Financing Estimates: 2026 - 3rd Quarter</a></p></div>',
            1,
        )
        with self.assertRaisesRegex(updater.UpdateError, "exactly one"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(discovery=duplicate))

    def test_discovery_quarter_must_match_release_assumptions(self):
        mismatched = DISCOVERY.replace("2026 - 3rd Quarter", "2026 - 2nd Quarter")
        with self.assertRaisesRegex(updater.UpdateError, "discovery quarter"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(discovery=mismatched))

    def test_future_publication_is_rejected(self):
        future = RELEASE.replace("2026-08-03T19:00:00Z", "2026-08-15T19:00:00Z")
        with self.assertRaisesRegex(updater.UpdateError, "future"):
            updater.build_config(as_of=AS_OF, fetch=fixture_fetch(release=future))

    def test_failed_refresh_never_overwrites_last_known_good(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tga_target.json"
            sentinel = b'{"last_known_good":true}\n'
            output.write_bytes(sentinel)
            malformed = RELEASE.replace(updater.EXPECTED_TITLE, "Wrong title")
            with self.assertRaises(updater.UpdateError):
                updater.update(output, as_of=AS_OF, fetch=fixture_fetch(release=malformed))
            self.assertEqual(output.read_bytes(), sentinel)

    def test_atomic_update_reports_only_normalized_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "tga_target.json"
            changed, first = updater.update(output, as_of=AS_OF, fetch=fixture_fetch())
            self.assertTrue(changed)
            first_bytes = output.read_bytes()
            changed, second = updater.update(output, as_of=AS_OF, fetch=fixture_fetch())
            self.assertFalse(changed)
            self.assertEqual(first, second)
            self.assertEqual(output.read_bytes(), first_bytes)


if __name__ == "__main__":
    unittest.main()
