#!/usr/bin/env python3
"""Publish the public Panoptes TGA estimated-tax event context.

The collector intentionally uses only six public HTML sources.  It does not
copy the private Atlas archive, persona material, local paths, or PDF parsing
dependencies into the Pages repository.  Every source is fetched from one
exact allowlisted HTTPS URL and parsed before the previous publication is
atomically replaced.

This is a calendar/context overlay.  It never changes the dashboard's
``WALCL - TGA - RRP`` formula or promotes a Treasury cash-balance assumption
to a cap or an observed liquidity release.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "atlas-panoptes-tga-event-context-v1"
USER_AGENT = "Panoptes-TGA-Flow-Events/1.0 (+https://github.com/smu05118-art/phalanx)"
MAX_HTML_BYTES = 4_000_000
MAX_OUTPUT_BYTES = 5_000_000
SEOUL = ZoneInfo("Asia/Seoul")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class UpdateError(RuntimeError):
    """Official input is missing, ambiguous, or outside the public contract."""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    publisher: str
    source_role: str
    url: str


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        "irs_publication_509_2026_html",
        "Internal Revenue Service",
        "primary_individual_and_corporate_due_date_rules",
        "https://www.irs.gov/publications/p509",
    ),
    SourceSpec(
        "irs_tax_calendar_q2_2026",
        "Internal Revenue Service",
        "event_calendar_q2_and_source_conflict_observation",
        "https://www.irs.gov/businesses/small-businesses-self-employed/second-quarter-tax-calendar",
    ),
    SourceSpec(
        "irs_tax_calendar_q3_2026",
        "Internal Revenue Service",
        "event_calendar_q3",
        "https://www.irs.gov/businesses/small-businesses-self-employed/third-quarter-tax-calendar",
    ),
    SourceSpec(
        "irs_tax_calendar_q4_2026",
        "Internal Revenue Service",
        "event_calendar_q4",
        "https://www.irs.gov/businesses/small-businesses-self-employed/fourth-quarter-tax-calendar",
    ),
    SourceSpec(
        "us_treasury_quarterly_refunding_statement_sb0590",
        "U.S. Department of the Treasury",
        "treasury_financing_and_cash_balance_guidance",
        "https://home.treasury.gov/news/press-releases/sb0590",
    ),
    SourceSpec(
        "federal_reserve_tga_mechanics",
        "Board of Governors of the Federal Reserve System",
        "primary_tga_reserve_accounting_mechanics",
        "https://www.federalreserve.gov/monetarypolicy/bsd-background-202008.htm",
    ),
)
SPEC_BY_ID = {spec.source_id: spec for spec in SOURCE_SPECS}


@dataclass(frozen=True)
class FetchedSource:
    source_id: str
    request_url: str
    final_url: str
    media_type: str
    payload: bytes


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def iso_z(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_utc_timestamp(value: str, label: str = "collected_at") -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise UpdateError(f"{label} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateError(f"{label} is not a valid UTC RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise UpdateError(f"{label} must be a UTC RFC3339 timestamp")
    return parsed


def yymmdd(value: date) -> str:
    return value.strftime("%y%m%d")


def exact_official_url(value: str, spec: SourceSpec, label: str) -> str:
    try:
        actual = urlsplit(value)
        expected = urlsplit(spec.url)
        port = actual.port
    except (TypeError, ValueError) as exc:
        raise UpdateError(f"{label}: invalid URL") from exc
    if (
        actual.scheme != "https"
        or actual.hostname != expected.hostname
        or port not in (None, 443)
        or actual.username is not None
        or actual.password is not None
        or actual.query
        or actual.fragment
        or actual.path.rstrip("/") != expected.path.rstrip("/")
    ):
        raise UpdateError(f"{label}: expected exact allowlisted official URL")
    netloc = expected.hostname if port is None else f"{expected.hostname}:443"
    return urlunsplit(("https", netloc, expected.path, "", ""))


def validate_fetched(page: FetchedSource, spec: SourceSpec) -> FetchedSource:
    if page.source_id != spec.source_id:
        raise UpdateError(f"{spec.source_id}: source id mismatch")
    requested = exact_official_url(page.request_url, spec, spec.source_id)
    final = exact_official_url(page.final_url, spec, f"{spec.source_id} redirect")
    if requested.rstrip("/") != spec.url.rstrip("/") or final.rstrip("/") != spec.url.rstrip("/"):
        raise UpdateError(f"{spec.source_id}: canonical URL mismatch")
    if page.media_type not in {"text/html", "application/xhtml+xml"}:
        raise UpdateError(f"{spec.source_id}: unexpected content type {page.media_type!r}")
    if not page.payload or len(page.payload) > MAX_HTML_BYTES:
        raise UpdateError(f"{spec.source_id}: empty or oversized response")
    try:
        header = page.payload[:8192].decode("utf-8").casefold()
    except UnicodeDecodeError as exc:
        raise UpdateError(f"{spec.source_id}: response is not UTF-8 HTML") from exc
    if "<html" not in header and "<!doctype html" not in header:
        raise UpdateError(f"{spec.source_id}: invalid HTML document")
    return page


def fetch_source(source_id: str, url: str, timeout: float = 40.0) -> FetchedSource:
    spec = SPEC_BY_ID.get(source_id)
    if spec is None:
        raise UpdateError(f"{source_id}: source is not allowlisted")
    official_url = exact_official_url(url, spec, source_id)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(
                official_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise UpdateError(f"{source_id}: HTTP status {response.status}")
                final_url = exact_official_url(
                    response.geturl(), spec, f"{source_id} redirect"
                )
                media_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset()
                if charset and charset.casefold().replace("-", "") != "utf8":
                    raise UpdateError(f"{source_id}: unexpected charset {charset!r}")
                payload = response.read(MAX_HTML_BYTES + 1)
            return validate_fetched(
                FetchedSource(source_id, official_url, final_url, media_type, payload),
                spec,
            )
        except UpdateError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(float(attempt + 1))
    raise UpdateError(f"{source_id}: failed to fetch official page") from last_error


class VisibleTextParser(HTMLParser):
    """Extract text while excluding executable and template content."""

    BOUNDARIES = {
        "article",
        "br",
        "dd",
        "div",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }
    SUPPRESSED = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(
        self, tag: str, _attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized = tag.casefold()
        if normalized in self.SUPPRESSED:
            self.suppressed_depth += 1
        elif self.suppressed_depth == 0 and normalized in self.BOUNDARIES:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self.SUPPRESSED:
            self.suppressed_depth = max(0, self.suppressed_depth - 1)
        elif self.suppressed_depth == 0 and normalized in self.BOUNDARIES:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.suppressed_depth == 0:
            self.parts.append(data)


def visible_text(page: FetchedSource) -> str:
    try:
        decoded = page.payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UpdateError(f"{page.source_id}: response is not UTF-8 HTML") from exc
    parser = VisibleTextParser()
    try:
        parser.feed(decoded)
        parser.close()
    except Exception as exc:
        raise UpdateError(f"{page.source_id}: malformed HTML") from exc
    result = collapse_whitespace("".join(parser.parts))
    if not result:
        raise UpdateError(f"{page.source_id}: no visible text")
    return result


def require_regex(text: str, pattern: str, label: str) -> re.Match[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None:
        raise UpdateError(f"{label}: required official evidence is missing")
    return match


def require_event_claim(
    text: str, event_date: str, pattern: str, label: str, width: int = 900
) -> re.Match[str]:
    start = 0
    while True:
        index = text.find(event_date, start)
        if index < 0:
            break
        match = re.search(pattern, text[index : index + width], re.IGNORECASE)
        if match is not None:
            return match
        start = index + len(event_date)
    raise UpdateError(f"{label}: expected dated event row is missing")


def parse_publication_509(text: str) -> None:
    require_regex(text, r"Publication 509 \(2026\),? Tax Calendars", "Publication 509 title")
    require_regex(
        text,
        r"Individuals.{0,900}Estimated tax payments\..{0,180}15th day of the 4th, 6th, and 9th months.{0,180}15th day of the 1st month after your tax year ends",
        "Publication 509 individual schedule",
    )
    require_regex(
        text,
        r"Corporations and S Corporations.{0,1800}Estimated tax payments\..{0,180}15th day of the 4th, 6th, 9th, and 12th months",
        "Publication 509 corporate schedule",
    )


def parse_q2_calendar(text: str) -> int:
    require_regex(text, r"Important tax deadlines and dates", "IRS Q2 calendar title")
    first = require_event_claim(
        text,
        "4/15/2026",
        r"Individuals:.{0,300}?Pay the first installment of (?P<year>2025|2026) estimated tax",
        "IRS Q2 April individual installment",
    )
    require_event_claim(
        text,
        "4/15/2026",
        r"Corporations:.{0,240}?Deposit estimated tax",
        "IRS Q2 April corporate installment",
    )
    require_event_claim(
        text,
        "6/15/2026",
        r"Individuals:.{0,180}?second installment of 2026 estimated tax",
        "IRS Q2 June individual installment",
    )
    require_event_claim(
        text,
        "6/15/2026",
        r"Corporations:.{0,180}?second installment of your 2026 estimated tax",
        "IRS Q2 June corporate installment",
    )
    return int(first.group("year"))


def parse_q3_calendar(text: str) -> None:
    require_regex(text, r"Important tax deadlines and dates", "IRS Q3 calendar title")
    require_event_claim(
        text,
        "9/15/2026",
        r"Corporations:.{0,180}?third installment of your 2026 estimated tax",
        "IRS Q3 corporate installment",
    )
    require_event_claim(
        text,
        "9/15/2026",
        r"Individuals:.{0,180}?third installment of your 2026 estimated tax",
        "IRS Q3 individual installment",
    )


def parse_q4_calendar(text: str) -> None:
    require_regex(text, r"Important tax deadlines and dates", "IRS Q4 calendar title")
    require_event_claim(
        text,
        "12/15/2026",
        r"Corporations:.{0,180}?fourth installment of your 2026 estimated tax",
        "IRS Q4 corporate installment",
    )


def parse_treasury_statement(text: str) -> dict[str, Any]:
    require_regex(
        text,
        r"Quarterly Refunding Statement of Deputy Assistant Secretary for Federal Finance Brian Smith",
        "Treasury statement title",
    )
    require_regex(text, r"\bAugust 5, 2026\b", "Treasury publication date")
    require_regex(
        text,
        r"receipts associated with the mid-September corporate and non-withheld tax date.{0,180}reductions to shorter-dated bill auction sizes during the month of September",
        "Treasury September bill guidance",
    )
    cash = require_regex(
        text,
        r"assuming a \$(?P<balance>[0-9,]+) billion cash balance at the end of September",
        "Treasury September cash assumption",
    )
    peak = require_regex(
        text,
        r"TGA\) could peak at \$(?P<peak>[0-9.]+) trillion \(plus or minus \$(?P<band>[0-9,]+) billion\) in late October",
        "Treasury late-October TGA projection",
    )
    balance = int(cash.group("balance").replace(",", ""))
    peak_billion = round(float(peak.group("peak")) * 1_000)
    band_billion = int(peak.group("band").replace(",", ""))
    if (balance, peak_billion, band_billion) != (950, 1050, 50):
        raise UpdateError("Treasury statement: cash guidance contract changed")
    return {
        "source_published_date": "2026-08-05",
        "quarter_end_balance_billion_usd": balance,
        "late_october_peak_billion_usd": peak_billion,
        "late_october_peak_band_billion_usd": band_billion,
    }


def parse_fed_mechanics(text: str) -> None:
    require_regex(text, r"Background on Selected Assets", "Federal Reserve page title")
    require_regex(
        text,
        r"funds that flow into the TGA drain balances from the reserves of depository institutions",
        "Federal Reserve TGA inflow mechanics",
    )
    require_regex(
        text,
        r"A tax payment to the Treasury['’]s account reduces the reserves of depository institutions",
        "Federal Reserve tax-payment mechanics",
    )
    require_regex(
        text,
        r"decline in the balances held in the TGA results in an increase in the reserves of depository institutions",
        "Federal Reserve TGA outflow mechanics",
    )


def payer_scope(payer_type: str, installment: int, source_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "payer_type": payer_type,
        "installment_number": installment,
        "source_ids": list(source_ids),
    }


def event_row(
    event_date: str,
    scopes: Sequence[dict[str, Any]],
    *,
    treasury_context_id: str | None = None,
) -> dict[str, Any]:
    parsed = date.fromisoformat(event_date)
    row: dict[str, Any] = {
        "event_id": f"us-estimated-tax-{event_date}",
        "event_type": "us_estimated_tax_due_date",
        "event_date": event_date,
        "event_date_label": yymmdd(parsed),
        "event_date_role": "statutory_due_date",
        "tax_year": 2026,
        "payer_scopes": list(scopes),
        "cash_flow_context": {
            "expected_tga_direction": "increase",
            "expected_bank_reserve_direction": "decrease",
            "net_liquidity_proxy_effect": "drain",
            "classification": "scheduled_seasonal_drain",
            "magnitude_billion_usd": "UNKNOWN",
            "formula_override": False,
        },
        "interpretation": {
            "mechanical_effect": "negative_for_net_liquidity_proxy",
            "seasonal_context": "expected_calendar_flow_not_a_standalone_regime_signal",
            "macro_information_effect": "UNKNOWN",
            "positive_effect_allowed_without_observed_offset_or_drawdown": False,
            "display_ko": "예정된 세금 유입: TGA↑·준비금↓의 기계적 흡수. 계절 요인으로 맥락화하되 플러스로 뒤집지 않음.",
        },
    }
    if treasury_context_id is not None:
        row["treasury_financing_context_id"] = treasury_context_id
    return row


def source_records(
    pages: Sequence[FetchedSource],
    treasury: Mapping[str, Any],
    text_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for page in pages:
        spec = SPEC_BY_ID[page.source_id]
        published = (
            str(treasury["source_published_date"])
            if page.source_id == "us_treasury_quarterly_refunding_statement_sb0590"
            else "UNKNOWN"
        )
        result.append(
            {
                "source_id": spec.source_id,
                "publisher": spec.publisher,
                "source_role": spec.source_role,
                "source_url": spec.url,
                "media_type": "text/html",
                # Hash normalized visible source content. Official Drupal pages
                # contain request-variant markup, so raw HTML hashes would
                # create commits with no evidence change.
                "content_sha256": hashlib.sha256(
                    (text_by_id[page.source_id] + "\n").encode("utf-8")
                ).hexdigest(),
                "source_published_date": published,
                "source_published_date_label": (
                    yymmdd(date.fromisoformat(published))
                    if published != "UNKNOWN"
                    else "UNKNOWN"
                ),
                "source_updated_date": "UNKNOWN",
                "source_updated_date_label": "UNKNOWN",
            }
        )
    return result


def build_context(
    *,
    collected_at: str,
    fetcher: Callable[[str, str], FetchedSource] = fetch_source,
) -> dict[str, Any]:
    collected = parse_utc_timestamp(collected_at)
    if collected > datetime.now(timezone.utc).replace(microsecond=0):
        raise UpdateError("collected_at must not be in the future")

    pages = [
        validate_fetched(fetcher(spec.source_id, spec.url), spec)
        for spec in SOURCE_SPECS
    ]
    if len({page.source_id for page in pages}) != len(SOURCE_SPECS):
        raise UpdateError("source collection is incomplete or duplicated")
    text = {page.source_id: visible_text(page) for page in pages}

    parse_publication_509(text["irs_publication_509_2026_html"])
    q2_first_year = parse_q2_calendar(text["irs_tax_calendar_q2_2026"])
    parse_q3_calendar(text["irs_tax_calendar_q3_2026"])
    parse_q4_calendar(text["irs_tax_calendar_q4_2026"])
    treasury = parse_treasury_statement(
        text["us_treasury_quarterly_refunding_statement_sb0590"]
    )
    parse_fed_mechanics(text["federal_reserve_tga_mechanics"])
    if q2_first_year not in {2025, 2026}:
        raise UpdateError("IRS Q2 calendar: unsupported first-installment tax year")

    rule = ["irs_publication_509_2026_html"]
    events = [
        event_row(
            "2026-04-15",
            [
                payer_scope("individual", 1, rule + ["irs_tax_calendar_q2_2026"]),
                payer_scope(
                    "calendar_year_corporation",
                    1,
                    rule + ["irs_tax_calendar_q2_2026"],
                ),
            ],
        ),
        event_row(
            "2026-06-15",
            [
                payer_scope("individual", 2, rule + ["irs_tax_calendar_q2_2026"]),
                payer_scope(
                    "calendar_year_corporation",
                    2,
                    rule + ["irs_tax_calendar_q2_2026"],
                ),
            ],
        ),
        event_row(
            "2026-09-15",
            [
                payer_scope("individual", 3, rule + ["irs_tax_calendar_q3_2026"]),
                payer_scope(
                    "calendar_year_corporation",
                    3,
                    rule + ["irs_tax_calendar_q3_2026"],
                ),
            ],
            treasury_context_id="treasury-september-2026-bill-guidance",
        ),
        event_row(
            "2026-12-15",
            [
                payer_scope(
                    "calendar_year_corporation",
                    4,
                    rule + ["irs_tax_calendar_q4_2026"],
                )
            ],
        ),
        event_row(
            "2027-01-15",
            [payer_scope("individual", 4, rule)],
        ),
    ]

    result = {
        "schema_version": SCHEMA_VERSION,
        "tax_year": 2026,
        "collected_at": iso_z(collected),
        "atlas_created_yymmdd": collected.astimezone(SEOUL).strftime("%y%m%d"),
        "status": "ok",
        "signal_label": "판단 보조용 자동등급",
        "net_liquidity_contract": {
            "formula": "WALCL - TGA - RRP",
            "formula_override_allowed": False,
            "tga_increase_mechanical_effect": "net_liquidity_proxy_decrease",
            "tga_decrease_mechanical_effect": "net_liquidity_proxy_increase",
            "scheduled_event_policy": "contextualize_seasonality_without_reversing_formula_sign",
            "source_id": "federal_reserve_tga_mechanics",
        },
        "events": events,
        "treasury_context": {
            "context_id": "treasury-september-2026-bill-guidance",
            "source_id": "us_treasury_quarterly_refunding_statement_sb0590",
            "source_published_date": treasury["source_published_date"],
            "source_published_date_label": "260805",
            "september_short_bill_guidance": {
                "status": "expected_reduction_announced",
                "instrument_scope": "shorter_dated_bill_auction_sizes",
                "effective_period": "2026-09",
                "effective_start_date": "2026-09-01",
                "effective_start_date_label": "260901",
                "effective_end_date": "2026-09-30",
                "effective_end_date_label": "260930",
                "reason": "projected_mid_september_corporate_and_non_withheld_tax_receipts",
                "interpretation": "less_issuance_than_otherwise_not_an_observed_tga_release",
            },
            "cash_balance_reference": {
                "reference_date": "2026-09-30",
                "reference_date_label": "260930",
                "value": treasury["quarter_end_balance_billion_usd"],
                "unit": "billion_usd",
                "semantic": "treasury_assumption_not_cap",
            },
            "late_october_projection": {
                "source_period_text": "late October 2026",
                "projection_date": "UNKNOWN",
                "projection_date_label": "UNKNOWN",
                "peak_value": treasury["late_october_peak_billion_usd"],
                "plus_or_minus": treasury["late_october_peak_band_billion_usd"],
                "unit": "billion_usd",
                "semantic": "projection_not_cap",
            },
        },
        "release_watch_policy": {
            "default_status": "unconfirmed",
            "quarter_end_assumption_is_cap": False,
            "reference_overshoot_alone_confirms_release": False,
            "watch_condition": "observed_tga_above_reference_after_tax_event",
            "confirmation_requires_any": [
                "subsequent_observed_tga_drawdown",
                "official_treasury_outflow_or_net_financing_evidence_implying_drawdown",
                "verified_federal_reserve_offset_or_observed_reserve_replenishment",
            ],
            "positive_liquidity_effect_before_confirmation": False,
            "display_ko": "재무부 현금가정은 상한이 아닙니다. 상회만으로 방출을 확정하지 않고, 이후 실제 TGA 감소·공식 지출/조달 근거·Fed 상쇄를 확인합니다.",
        },
        "sources": source_records(pages, treasury, text),
    }
    validate_contract(result)
    return result


def validate_contract(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION or value.get("status") != "ok":
        raise UpdateError("output: schema or status mismatch")
    if value.get("tax_year") != 2026 or value.get("signal_label") != "판단 보조용 자동등급":
        raise UpdateError("output: calendar identity mismatch")
    collected = parse_utc_timestamp(str(value.get("collected_at", "")))
    expected_label = collected.astimezone(SEOUL).strftime("%y%m%d")
    if value.get("atlas_created_yymmdd") != expected_label:
        raise UpdateError("output: Atlas creation date label mismatch")

    contract = value.get("net_liquidity_contract")
    if not isinstance(contract, Mapping) or contract != {
        "formula": "WALCL - TGA - RRP",
        "formula_override_allowed": False,
        "tga_increase_mechanical_effect": "net_liquidity_proxy_decrease",
        "tga_decrease_mechanical_effect": "net_liquidity_proxy_increase",
        "scheduled_event_policy": "contextualize_seasonality_without_reversing_formula_sign",
        "source_id": "federal_reserve_tga_mechanics",
    }:
        raise UpdateError("output: net-liquidity contract mismatch")

    sources = value.get("sources")
    if not isinstance(sources, list) or len(sources) != len(SOURCE_SPECS):
        raise UpdateError("output: official source set mismatch")
    source_ids: set[str] = set()
    for source, spec in zip(sources, SOURCE_SPECS):
        if not isinstance(source, Mapping) or source.get("source_id") != spec.source_id:
            raise UpdateError("output: source order or identity mismatch")
        exact_official_url(str(source.get("source_url", "")), spec, spec.source_id)
        if source.get("media_type") != "text/html" or not SHA256_RE.fullmatch(
            str(source.get("content_sha256", ""))
        ):
            raise UpdateError(f"output: invalid source record {spec.source_id}")
        source_ids.add(spec.source_id)

    events = value.get("events")
    expected_events = [
        ("2026-04-15", (("individual", 1), ("calendar_year_corporation", 1))),
        ("2026-06-15", (("individual", 2), ("calendar_year_corporation", 2))),
        ("2026-09-15", (("individual", 3), ("calendar_year_corporation", 3))),
        ("2026-12-15", (("calendar_year_corporation", 4),)),
        ("2027-01-15", (("individual", 4),)),
    ]
    if not isinstance(events, list) or len(events) != len(expected_events):
        raise UpdateError("output: expected exactly five tax events")
    for event, (event_date, expected_scopes) in zip(events, expected_events):
        if not isinstance(event, Mapping):
            raise UpdateError("output: invalid event row")
        if (
            event.get("event_date") != event_date
            or event.get("event_date_label") != yymmdd(date.fromisoformat(event_date))
            or event.get("event_date_role") != "statutory_due_date"
            or event.get("event_type") != "us_estimated_tax_due_date"
            or event.get("tax_year") != 2026
        ):
            raise UpdateError("output: event identity mismatch")
        scopes = event.get("payer_scopes")
        if not isinstance(scopes, list):
            raise UpdateError("output: event payer scope missing")
        actual_scopes = tuple(
            (scope.get("payer_type"), scope.get("installment_number"))
            for scope in scopes
            if isinstance(scope, Mapping)
        )
        if actual_scopes != expected_scopes or len(actual_scopes) != len(scopes):
            raise UpdateError("output: event payer scope mismatch")
        for scope in scopes:
            ids = scope.get("source_ids")
            if not isinstance(ids, list) or not ids or not set(ids).issubset(source_ids):
                raise UpdateError("output: event evidence source mismatch")
        flow = event.get("cash_flow_context", {})
        interpretation = event.get("interpretation", {})
        if (
            flow.get("expected_tga_direction") != "increase"
            or flow.get("expected_bank_reserve_direction") != "decrease"
            or flow.get("net_liquidity_proxy_effect") != "drain"
            or flow.get("classification") != "scheduled_seasonal_drain"
            or flow.get("formula_override") is not False
            or interpretation.get("mechanical_effect")
            != "negative_for_net_liquidity_proxy"
            or interpretation.get(
                "positive_effect_allowed_without_observed_offset_or_drawdown"
            )
            is not False
        ):
            raise UpdateError("output: unsafe event interpretation")

    treasury = value.get("treasury_context", {})
    if (
        treasury.get("source_id")
        != "us_treasury_quarterly_refunding_statement_sb0590"
        or treasury.get("cash_balance_reference", {}).get("value") != 950
        or treasury.get("cash_balance_reference", {}).get("semantic")
        != "treasury_assumption_not_cap"
        or treasury.get("late_october_projection", {}).get("peak_value") != 1050
        or treasury.get("late_october_projection", {}).get("plus_or_minus") != 50
        or treasury.get("september_short_bill_guidance", {}).get("interpretation")
        != "less_issuance_than_otherwise_not_an_observed_tga_release"
    ):
        raise UpdateError("output: Treasury context mismatch")
    release = value.get("release_watch_policy", {})
    if (
        release.get("quarter_end_assumption_is_cap") is not False
        or release.get("reference_overshoot_alone_confirms_release") is not False
        or release.get("positive_liquidity_effect_before_confirmation") is not False
        or not release.get("confirmation_requires_any")
    ):
        raise UpdateError("output: unsafe release-watch policy")

    serialized = canonical_json_bytes(value)
    if len(serialized) > MAX_OUTPUT_BYTES:
        raise UpdateError("output: publication exceeds 5 MB")
    lowered = serialized.lower()
    for forbidden in (b"persona", b"evidence_refs", b"file://"):
        if forbidden in lowered:
            raise UpdateError("output: private or local-only material detected")


def _comparison_value(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(value))
    normalized.pop("collected_at", None)
    normalized.pop("atlas_created_yymmdd", None)
    return normalized


def atomic_write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise UpdateError("output path must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def update(
    output: Path,
    *,
    collected_at: str | None = None,
    fetcher: Callable[[str, str], FetchedSource] = fetch_source,
) -> tuple[bool, dict[str, Any]]:
    timestamp = collected_at or iso_z(datetime.now(timezone.utc))
    candidate = build_context(collected_at=timestamp, fetcher=fetcher)
    payload = canonical_json_bytes(candidate)

    existing: dict[str, Any] | None = None
    if output.exists():
        if output.is_symlink() or not output.is_file():
            raise UpdateError("output path must be a regular file")
        try:
            parsed = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            existing = parsed
    if existing is not None and _comparison_value(existing) == _comparison_value(candidate):
        return False, existing

    atomic_write(output, payload)
    return True, candidate


def default_output() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "tga-flow-events" / "current.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output())
    parser.add_argument("--collected-at", help="fixed UTC RFC3339 time for reproducible runs")
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 120:
        parser.error("--timeout must be between 0 and 120 seconds")

    def network_fetcher(source_id: str, url: str) -> FetchedSource:
        return fetch_source(source_id, url, timeout=args.timeout)

    try:
        changed, value = update(
            args.output,
            collected_at=args.collected_at,
            fetcher=network_fetcher,
        )
    except UpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    state = "updated" if changed else "unchanged"
    print(f"{state}: {args.output} ({len(value['events'])} events, {len(value['sources'])} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
