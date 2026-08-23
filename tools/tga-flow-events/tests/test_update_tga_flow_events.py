from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODULE_PATH = TOOLS / "update_tga_flow_events.py"
SPEC = importlib.util.spec_from_file_location("update_tga_flow_events", MODULE_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)

COLLECTED_AT = "2026-08-23T07:15:00Z"
FIXTURE_BY_ID = {
    "irs_publication_509_2026_html": "publication-509.html",
    "irs_tax_calendar_q2_2026": "q2-calendar.html",
    "irs_tax_calendar_q3_2026": "q3-calendar.html",
    "irs_tax_calendar_q4_2026": "q4-calendar.html",
    "us_treasury_quarterly_refunding_statement_sb0590": "treasury-sb0590.html",
    "federal_reserve_tga_mechanics": "federal-reserve-mechanics.html",
}


def fixture_payloads() -> dict[str, bytes]:
    return {
        source_id: (FIXTURES / filename).read_bytes()
        for source_id, filename in FIXTURE_BY_ID.items()
    }


def fixture_fetcher(
    payloads: dict[str, bytes] | None = None,
    *,
    redirect_overrides: dict[str, str] | None = None,
    media_overrides: dict[str, str] | None = None,
):
    pages = payloads or fixture_payloads()
    redirects = redirect_overrides or {}
    media = media_overrides or {}

    def fetch(source_id: str, url: str):
        spec = updater.SPEC_BY_ID[source_id]
        if url != spec.url:
            raise AssertionError((source_id, url))
        return updater.FetchedSource(
            source_id=source_id,
            request_url=spec.url,
            final_url=redirects.get(source_id, spec.url),
            media_type=media.get(source_id, "text/html"),
            payload=pages[source_id],
        )

    return fetch


class PublicCollectorTests(unittest.TestCase):
    def build(self, payloads: dict[str, bytes] | None = None):
        return updater.build_context(
            collected_at=COLLECTED_AT,
            fetcher=fixture_fetcher(payloads),
        )

    def test_public_contract_is_exact_and_frontend_compatible(self) -> None:
        context = self.build()
        self.assertEqual(context["schema_version"], updater.SCHEMA_VERSION)
        self.assertEqual(context["status"], "ok")
        self.assertEqual(context["signal_label"], "판단 보조용 자동등급")
        self.assertEqual(
            context["net_liquidity_contract"]["formula"],
            "WALCL - TGA - RRP",
        )
        self.assertIs(
            context["net_liquidity_contract"]["formula_override_allowed"],
            False,
        )
        self.assertEqual(
            [event["event_date"] for event in context["events"]],
            [
                "2026-04-15",
                "2026-06-15",
                "2026-09-15",
                "2026-12-15",
                "2027-01-15",
            ],
        )
        self.assertEqual(
            [event["event_date_label"] for event in context["events"]],
            ["260415", "260615", "260915", "261215", "270115"],
        )
        self.assertEqual(len(context["sources"]), 6)
        payloads = fixture_payloads()
        self.assertEqual(
            context["sources"][0]["content_sha256"],
            hashlib.sha256(payloads["irs_publication_509_2026_html"]).hexdigest(),
        )
        updater.validate_contract(context)

    def test_september_scope_and_treasury_semantics_are_conditional(self) -> None:
        context = self.build()
        event = context["events"][2]
        self.assertEqual(
            [scope["payer_type"] for scope in event["payer_scopes"]],
            ["individual", "calendar_year_corporation"],
        )
        self.assertEqual(
            [scope["installment_number"] for scope in event["payer_scopes"]],
            [3, 3],
        )
        self.assertEqual(
            event["cash_flow_context"]["net_liquidity_proxy_effect"], "drain"
        )
        self.assertIs(event["cash_flow_context"]["formula_override"], False)
        treasury = context["treasury_context"]
        self.assertEqual(treasury["cash_balance_reference"]["value"], 950)
        self.assertEqual(
            treasury["cash_balance_reference"]["semantic"],
            "treasury_assumption_not_cap",
        )
        self.assertEqual(
            treasury["september_short_bill_guidance"]["interpretation"],
            "less_issuance_than_otherwise_not_an_observed_tga_release",
        )
        release = context["release_watch_policy"]
        self.assertIs(release["quarter_end_assumption_is_cap"], False)
        self.assertIs(release["reference_overshoot_alone_confirms_release"], False)
        self.assertIs(release["positive_liquidity_effect_before_confirmation"], False)

    def test_output_excludes_private_and_local_only_material(self) -> None:
        payload = updater.canonical_json_bytes(self.build()).lower()
        self.assertNotIn(b"persona", payload)
        self.assertNotIn(b"evidence_refs", payload)
        self.assertNotIn(b"file://", payload)

    def test_same_inputs_and_timestamp_are_byte_deterministic(self) -> None:
        first = updater.canonical_json_bytes(self.build())
        second = updater.canonical_json_bytes(self.build())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertEqual(json.loads(first), json.loads(second))

    def test_q2_upstream_typo_and_correction_normalize_to_same_event(self) -> None:
        typo = self.build()
        payloads = fixture_payloads()
        payloads["irs_tax_calendar_q2_2026"] = payloads[
            "irs_tax_calendar_q2_2026"
        ].replace(b"first installment of\n      2025", b"first installment of\n      2026")
        corrected = self.build(payloads)
        self.assertEqual(typo["events"], corrected["events"])
        self.assertNotEqual(typo["sources"], corrected["sources"])

    def test_missing_q3_event_fails_closed(self) -> None:
        payloads = fixture_payloads()
        payloads["irs_tax_calendar_q3_2026"] = payloads[
            "irs_tax_calendar_q3_2026"
        ].replace(b"third installment", b"estimated payment")
        with self.assertRaisesRegex(updater.UpdateError, "Q3 .* installment"):
            self.build(payloads)

    def test_changed_treasury_cash_guidance_fails_closed(self) -> None:
        payloads = fixture_payloads()
        payloads["us_treasury_quarterly_refunding_statement_sb0590"] = payloads[
            "us_treasury_quarterly_refunding_statement_sb0590"
        ].replace(b"$950 billion", b"$951 billion")
        with self.assertRaisesRegex(updater.UpdateError, "cash guidance contract changed"):
            self.build(payloads)

    def test_hostile_redirect_is_rejected(self) -> None:
        source_id = "irs_tax_calendar_q3_2026"
        fetch = fixture_fetcher(
            redirect_overrides={source_id: "https://www.irs.gov.attacker.invalid/q3"}
        )
        with self.assertRaisesRegex(updater.UpdateError, "exact allowlisted"):
            updater.build_context(collected_at=COLLECTED_AT, fetcher=fetch)

    def test_wrong_content_type_is_rejected(self) -> None:
        source_id = "federal_reserve_tga_mechanics"
        fetch = fixture_fetcher(media_overrides={source_id: "application/json"})
        with self.assertRaisesRegex(updater.UpdateError, "content type"):
            updater.build_context(collected_at=COLLECTED_AT, fetcher=fetch)

    def test_failed_refresh_preserves_last_known_good_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "current.json"
            sentinel = b'{"last_known_good":true}\n'
            output.write_bytes(sentinel)
            payloads = fixture_payloads()
            payloads["irs_tax_calendar_q3_2026"] = payloads[
                "irs_tax_calendar_q3_2026"
            ].replace(b"third installment", b"estimated payment")
            with self.assertRaises(updater.UpdateError):
                updater.update(
                    output,
                    collected_at=COLLECTED_AT,
                    fetcher=fixture_fetcher(payloads),
                )
            self.assertEqual(output.read_bytes(), sentinel)

    def test_identical_semantics_do_not_create_timestamp_only_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "current.json"
            changed, first = updater.update(
                output,
                collected_at=COLLECTED_AT,
                fetcher=fixture_fetcher(),
            )
            self.assertTrue(changed)
            first_bytes = output.read_bytes()
            changed, second = updater.update(
                output,
                collected_at="2026-08-23T07:45:00Z",
                fetcher=fixture_fetcher(),
            )
            self.assertFalse(changed)
            self.assertEqual(first, second)
            self.assertEqual(output.read_bytes(), first_bytes)

    def test_output_symlink_is_rejected(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlink is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.json"
            target.write_text("{}\n", encoding="utf-8")
            output = root / "current.json"
            output.symlink_to(target)
            with self.assertRaisesRegex(updater.UpdateError, "regular file"):
                updater.update(
                    output,
                    collected_at=COLLECTED_AT,
                    fetcher=fixture_fetcher(),
                )


if __name__ == "__main__":
    unittest.main()
