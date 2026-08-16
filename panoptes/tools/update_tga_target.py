#!/usr/bin/env python3
"""Refresh Panoptes' TGA assumptions from the latest official Treasury release.

The updater deliberately has no third-party dependencies.  It discovers the
current "Financing Estimates" release from Treasury's stable Quarterly
Refunding page, validates the official URL and structured article fields, and
only replaces the dashboard JSON after the whole document passes validation.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Callable, Iterable, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DISCOVERY_URL = (
    "https://home.treasury.gov/policy-issues/financing-the-government/"
    "quarterly-refunding/most-recent-quarterly-refunding-documents"
)
SOURCE_ID = "us_treasury_quarterly_borrowing_estimates"
PUBLISHER = "U.S. Department of the Treasury"
EXPECTED_TITLE = "Treasury Announces Marketable Borrowing Estimates"
USER_AGENT = "Panoptes-TGA-Updater/1.0 (+https://github.com/smu05118-art/phalanx)"
MAX_HTML_BYTES = 2_000_000
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

DISCOVERY_PATH = re.compile(
    r"^/policy-issues/financing-the-government/quarterly-refunding/"
    r"most-recent-quarterly-refunding-documents/?$"
)
RELEASE_PATH = re.compile(r"^/news/press-releases/[a-z]{2}\d+/?$")
PDF_PATH = re.compile(r"^/system/files/\d+/[^/]+\.pdf$", re.IGNORECASE)
FINANCING_LINK = re.compile(
    r"^Financing Estimates: (\d{4}) - (1st|2nd|3rd|4th) Quarter$"
)

MONTHS = {
    "January": 1,
    "March": 3,
    "April": 4,
    "June": 6,
    "July": 7,
    "September": 9,
    "October": 10,
    "December": 12,
}
QUARTER_RANGES = {(1, 3): 1, (4, 6): 2, (7, 9): 3, (10, 12): 4}
ASSUMPTION = re.compile(
    r"^During the "
    r"(January|April|July|October)\s*[-\N{EN DASH}]\s*"
    r"(March|June|September|December)\s+(\d{4})\s+quarter,\s+"
    r"Treasury expects to borrow\b.*?\bassuming an end-of-"
    r"(March|June|September|December) cash balance of \$([\d,]+) billion\."
    r"(?:\s|$)",
    re.IGNORECASE,
)


class UpdateError(RuntimeError):
    """Raised when official input is missing, ambiguous, or invalid."""


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def attrs_dict(attrs: Sequence[tuple[str, str | None]]) -> dict[str, str]:
    return {key: value or "" for key, value in attrs}


def class_tokens(attrs: Sequence[tuple[str, str | None]]) -> set[str]:
    return set(attrs_dict(attrs).get("class", "").split())


class AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "a" and self._href is None:
            self._href = attrs_dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, collapse_whitespace(" ".join(self._text))))
            self._href = None
            self._text = []


class TreasuryReleaseParser(HTMLParser):
    """Extract only Treasury's structured title, date, and news-body fields."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.title_depth: int | None = None
        self.date_depth: int | None = None
        self.body_depth: int | None = None
        self.li_depth: int | None = None
        self.anchor_depth: int | None = None
        self.title_parts: list[str] = []
        self.publication_datetimes: list[str] = []
        self.body_parts: list[str] = []
        self.list_items: list[str] = []
        self._li_parts: list[str] = []
        self.body_links: list[tuple[str, str]] = []
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag not in VOID_ELEMENTS:
            self.depth += 1
        classes = class_tokens(attrs)
        values = attrs_dict(attrs)

        if tag == "h2" and "uswds-page-title" in classes:
            if self.title_depth is not None:
                raise UpdateError("ambiguous structured release title")
            self.title_depth = self.depth
        if tag == "div" and "field--name-field-news-publication-date" in classes:
            if self.date_depth is not None:
                raise UpdateError("ambiguous structured publication-date field")
            self.date_depth = self.depth
        if self.date_depth is not None and tag == "time":
            value = values.get("datetime", "")
            if value:
                self.publication_datetimes.append(value)
        if tag == "div" and "field--name-field-news-body" in classes:
            if self.body_depth is not None:
                raise UpdateError("ambiguous structured news-body field")
            self.body_depth = self.depth

        if self.body_depth is not None:
            if tag == "li" and self.li_depth is None:
                self.li_depth = self.depth
                self._li_parts = []
            if tag == "a" and self.anchor_depth is None:
                self.anchor_depth = self.depth
                self._anchor_href = values.get("href", "")
                self._anchor_parts = []

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # HTMLParser reports ``<br/>`` here rather than as a start/end pair.
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.title_depth is not None:
            self.title_parts.append(data)
        if self.body_depth is not None:
            self.body_parts.append(data)
            if self.li_depth is not None:
                self._li_parts.append(data)
            if self.anchor_depth is not None:
                self._anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.anchor_depth is not None and tag == "a" and self.depth == self.anchor_depth:
            self.body_links.append(
                (
                    self._anchor_href or "",
                    collapse_whitespace(" ".join(self._anchor_parts)),
                )
            )
            self.anchor_depth = None
            self._anchor_href = None
            self._anchor_parts = []
        if self.li_depth is not None and tag == "li" and self.depth == self.li_depth:
            self.list_items.append(collapse_whitespace(" ".join(self._li_parts)))
            self.li_depth = None
            self._li_parts = []
        if self.title_depth is not None and tag == "h2" and self.depth == self.title_depth:
            self.title_depth = None
        if self.date_depth is not None and tag == "div" and self.depth == self.date_depth:
            self.date_depth = None
        if self.body_depth is not None and tag == "div" and self.depth == self.body_depth:
            self.body_depth = None
        self.depth = max(0, self.depth - 1)


def validate_official_url(url: str, path_pattern: re.Pattern[str], label: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except (TypeError, ValueError) as exc:
        raise UpdateError(f"invalid {label} URL") from exc
    if (
        parts.scheme != "https"
        or parts.hostname != "home.treasury.gov"
        or parts.username is not None
        or parts.password is not None
        or port not in (None, 443)
        or parts.query
        or parts.fragment
        or not path_pattern.fullmatch(parts.path)
    ):
        raise UpdateError(f"non-official or unexpected {label} URL: {url}")
    canonical_netloc = "home.treasury.gov" if port is None else "home.treasury.gov:443"
    return urlunsplit(("https", canonical_netloc, parts.path.rstrip("/"), "", ""))


def _decode_html(payload: bytes, charset: str | None) -> str:
    encoding = charset or "utf-8"
    try:
        return payload.decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise UpdateError(f"official page is not valid {encoding} text") from exc


def fetch_html(url: str, kind: str, timeout: float = 30.0) -> tuple[str, str]:
    pattern = DISCOVERY_PATH if kind == "discovery" else RELEASE_PATH
    requested = validate_official_url(url, pattern, kind)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = Request(
                requested,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            )
            with urlopen(request, timeout=timeout) as response:
                final_url = validate_official_url(response.geturl(), pattern, kind)
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise UpdateError(f"unexpected {kind} content type: {content_type}")
                payload = response.read(MAX_HTML_BYTES + 1)
                if len(payload) > MAX_HTML_BYTES:
                    raise UpdateError(f"{kind} page exceeds size limit")
                return final_url, _decode_html(payload, response.headers.get_content_charset())
        except UpdateError:
            raise
        except Exception as exc:  # network errors are retried, never normalized
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    raise UpdateError(f"failed to fetch official {kind} page") from last_error


def parse_discovery(html_text: str, base_url: str = DISCOVERY_URL) -> tuple[str, int, int]:
    parser = AnchorCollector()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:
        raise UpdateError("invalid Treasury discovery HTML") from exc
    matches: list[tuple[str, int, int]] = []
    for href, text in parser.links:
        match = FINANCING_LINK.fullmatch(text)
        if match:
            matches.append(
                (
                    validate_official_url(urljoin(base_url, href), RELEASE_PATH, "release"),
                    int(match.group(1)),
                    int(match.group(2)[0]),
                )
            )
    unique = sorted(set(matches))
    if len(matches) != 1 or len(unique) != 1:
        raise UpdateError(
            f"expected exactly one current Financing Estimates link; found {len(matches)}"
        )
    return unique[0]


def parse_iso_datetime(value: str, as_of: dt.date) -> tuple[str, str]:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise UpdateError("invalid structured publication datetime") from exc
    if parsed.tzinfo is None:
        raise UpdateError("publication datetime must include a timezone")
    utc = parsed.astimezone(dt.timezone.utc)
    if utc.date() > as_of:
        raise UpdateError("Treasury publication date is in the future")
    return utc.date().isoformat(), utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def assumption_from_list_item(text: str, release_date: dt.date) -> dict[str, object] | None:
    match = ASSUMPTION.search(text)
    if not match:
        return None
    start_name, end_name, year_text, stated_end_name, value_text = match.groups()
    names = {name.lower(): month for name, month in MONTHS.items()}
    start_month = names[start_name.lower()]
    end_month = names[end_name.lower()]
    stated_end_month = names[stated_end_name.lower()]
    quarter = QUARTER_RANGES.get((start_month, end_month))
    if quarter is None or stated_end_month != end_month:
        raise UpdateError("forecast period is not an exact calendar quarter")
    year = int(year_text)
    target = dt.date(year, end_month, calendar.monthrange(year, end_month)[1])
    if target <= release_date:
        raise UpdateError("cash-balance assumption is not forward-looking")
    value = int(value_text.replace(",", ""))
    if value <= 0 or value > 10_000:
        raise UpdateError("cash-balance assumption is outside the supported range")
    return {
        "value": value,
        "unit": "billion_usd",
        "target_period": f"Q{quarter} {year}",
        "target_period_label": f"Q{quarter}-{str(year)[2:]}",
        "target_date": target.isoformat(),
        "target_date_label": target.strftime("%y%m%d"),
    }


def quarter_index(target_date: str) -> int:
    target = dt.date.fromisoformat(target_date)
    return target.year * 4 + ((target.month - 1) // 3)


def normalized_article_text(parts: Iterable[str]) -> str:
    # This is the documented content-hash contract: entities have already been
    # decoded by HTMLParser, every Unicode/ASCII whitespace run is collapsed,
    # and the normalized UTF-8 text ends in exactly one LF.
    return collapse_whitespace(" ".join(parts)) + "\n"


def parse_release(
    html_text: str,
    source_url: str,
    discovery_url: str,
    as_of: dt.date,
    discovery_year: int,
    discovery_quarter: int,
) -> dict[str, object]:
    parser = TreasuryReleaseParser()
    try:
        parser.feed(html_text)
        parser.close()
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError("invalid Treasury release HTML") from exc

    title = collapse_whitespace(" ".join(parser.title_parts))
    if title != EXPECTED_TITLE:
        raise UpdateError(f"unexpected Treasury release title: {title!r}")
    if len(parser.publication_datetimes) != 1:
        raise UpdateError("expected exactly one structured publication datetime")
    published_date, published_at = parse_iso_datetime(parser.publication_datetimes[0], as_of)
    release_date = dt.date.fromisoformat(published_date)

    assumptions = [
        item
        for item in (
            assumption_from_list_item(text, release_date) for text in parser.list_items
        )
        if item is not None
    ]
    assumptions.sort(key=lambda item: str(item["target_date"]))
    if len(assumptions) != 2:
        raise UpdateError(f"expected exactly two forward assumptions; found {len(assumptions)}")
    if assumptions[0]["target_date"] == assumptions[1]["target_date"]:
        raise UpdateError("duplicate cash-balance target dates")
    if quarter_index(str(assumptions[1]["target_date"])) != quarter_index(
        str(assumptions[0]["target_date"])
    ) + 1:
        raise UpdateError("cash-balance assumptions are not consecutive quarters")
    if assumptions[0]["target_period"] != f"Q{discovery_quarter} {discovery_year}":
        raise UpdateError("discovery quarter and release assumptions disagree")

    source_links = []
    for href, text in parser.body_links:
        if text == "Sources and Uses Table":
            source_links.append(
                validate_official_url(urljoin(source_url, href), PDF_PATH, "Sources and Uses")
            )
    if len(source_links) != 1:
        raise UpdateError(f"expected exactly one official Sources and Uses link; found {len(source_links)}")

    source_url = validate_official_url(source_url, RELEASE_PATH, "release")
    discovery_url = validate_official_url(discovery_url, DISCOVERY_PATH, "discovery")
    release_id = source_url.rsplit("/", 1)[-1]
    article_text = normalized_article_text(parser.body_parts)
    if article_text == "\n":
        raise UpdateError("structured Treasury article body is empty")
    return {
        "schema_version": 2,
        "release": {
            "source_id": SOURCE_ID,
            "publisher": PUBLISHER,
            "discovery_url": discovery_url,
            "source_url": source_url,
            "release_id": release_id,
            "source_published_date": published_date,
            "source_published_at": published_at,
            "source_published_label": release_date.strftime("%y%m%d"),
            "sources_uses_url": source_links[0],
            "article_content_sha256": hashlib.sha256(article_text.encode("utf-8")).hexdigest(),
        },
        "assumptions": assumptions,
    }


Fetch = Callable[[str, str, float], tuple[str, str]]


def build_config(
    *,
    as_of: dt.date | None = None,
    timeout: float = 30.0,
    fetch: Fetch = fetch_html,
) -> dict[str, object]:
    today = as_of or dt.datetime.now(dt.timezone.utc).date()
    discovery_url, discovery_html = fetch(DISCOVERY_URL, "discovery", timeout)
    release_url, discovery_year, discovery_quarter = parse_discovery(
        discovery_html, discovery_url
    )
    final_release_url, release_html = fetch(release_url, "release", timeout)
    if final_release_url != release_url:
        raise UpdateError("official release redirected to an unexpected canonical URL")
    return parse_release(
        release_html,
        final_release_url,
        discovery_url,
        today,
        discovery_year,
        discovery_quarter,
    )


def serialize_config(config: dict[str, object]) -> bytes:
    # Canonical bytes let automation distinguish a source change from key
    # insertion order or pretty-printing differences.
    return (
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def atomic_update(output: Path, payload: bytes) -> bool:
    current = output.read_bytes() if output.exists() else None
    if current == payload:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = output.stat().st_mode & 0o777 if output.exists() else 0o644
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, existing_mode)
        os.replace(temporary, output)
        temporary = None
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update(
    output: Path,
    *,
    as_of: dt.date | None = None,
    timeout: float = 30.0,
    fetch: Fetch = fetch_html,
) -> tuple[bool, dict[str, object]]:
    # Build and serialize fully before opening a temporary file.  Any fetch,
    # parse, or validation failure therefore leaves the last-known-good output.
    config = build_config(as_of=as_of, timeout=timeout, fetch=fetch)
    changed = atomic_update(output, serialize_config(config))
    return changed, config


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    default_output = Path(__file__).resolve().parents[1] / "data" / "tga_target.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--as-of", type=dt.date.fromisoformat, help="UTC validation date (YYYY-MM-DD)")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        changed, config = update(
            args.output.resolve(), as_of=args.as_of, timeout=args.timeout
        )
    except UpdateError as exc:
        print(f"TGA target update refused: {exc}", file=sys.stderr)
        return 1
    release = config["release"]
    action = "updated" if changed else "unchanged"
    print(
        f"TGA target {action}: {release['release_id']} "
        f"({release['source_published_label']}) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
