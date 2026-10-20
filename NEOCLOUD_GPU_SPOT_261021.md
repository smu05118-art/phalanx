# Official Nebius Spot Prices operations · 261021

This replaces the image-seeded tracker with public, unauthenticated Nebius observations. The historical `NEOCLOUD_GPU_SPOT_261020.md` is preserved unchanged.

## Source contract and rights

- Official page: https://nebius.com/spot-prices
- Documentation: https://docs.nebius.com/signup-billing/spot-prices
- Current: `GET https://api.nebius.cloud/billing/v1alpha1/spot-price?pageSize=100`
- History: `GET https://api.nebius.cloud/billing/v1alpha1/spot-price/list-series`
- API contract evidence: https://github.com/nebius/api/commit/71e545df5f43d637e9cea815d75b43e7a741f4fb

The documentation confirms public access without an account, per-GPU-hour prices, rolling history and aggregation options. A live request with the deployed GitHub Pages origin returned HTTP 200 and the matching `Access-Control-Allow-Origin`; the official page's regional chart uses hourly LAST. No explicit raw-data redistribution license was established. Repository data therefore contains normalized observations, required metadata, source URLs and response hashes; full capture envelopes and raw-download features are excluded. Small trimmed parser fixtures are documented separately.

Current cards select the lowest current Decimal price per family and show its region, SKU, effective time, response snapshot time and live/fallback/stale status. Equal prices resolve deterministically by region then SKU. Nebius defines response `snapshotTime` as the earliest observation time when individual prices were taken at different times, so an item's valid `effectiveTime` may be later than that global snapshot; only an effective time later than collection is rejected. Family mapping is discovered from `computeInstance.platform`; IDs and regions are not hard-coded. B200 and RTX aliases are supported. Unknown platforms, units or currencies fail closed for operator review. H100's official `$0.79` happens to match its legacy chart label; its source is independently the current API capture.

`GRANULARITY_HOUR_1` + `METHOD_LAST_PRICE` is the durable region series. AVG is an unweighted arithmetic mean and remains a different layer. The API has a 30-day hourly limit and a 7-day 15-minute limit. This implementation accepts hourly data only. Each point timestamp denotes interval **end**; interval start is exactly one hour earlier. Day and month attribution uses the start. No interpolation, forward-fill, unavailable dates or incomplete hourly points are stored.

## Initial import and exact boundaries

The initial data has **8,640 AVG observations plus 8,352 LAST observations, 12 SKUs, five families**, and 12 current observations. AVG and LAST were imported from separate, positively allowlisted capture hashes; no AVG value is relabeled as LAST.

Machine evidence:

```json
{
  "current_source_snapshot_time": "2026-10-20T15:18:18.881912Z",
  "avg_source_snapshot_time": "2026-10-20T15:18:29.680984Z",
  "last_source_snapshot_time": "2026-10-20T15:23:56.421018Z",
  "collected_time": "2026-10-20T16:00:00Z",
  "avg_interval_end_min": "2026-09-20T16:00:00Z",
  "last_interval_end_min": "2026-09-21T16:00:00Z",
  "interval_end_max": "2026-10-20T15:00:00Z",
  "avg_interval_start_min": "2026-09-20T15:00:00Z",
  "last_interval_start_min": "2026-09-21T15:00:00Z",
  "interval_start_max": "2026-10-20T14:00:00Z",
  "current_capture_sha256": "e5053b8dccf4a2a1843abaad5accfbbb52ef7416c65606b677907ad09deb1098",
  "avg_capture_sha256": "1594b1e56042e2762a9cc9656ebbc6ca8f24bd1cf2a7c1ff7df5e58f4e6df909",
  "last_capture_sha256": "614ef24e7449a27c016d3bedd2284c210858e4404e8ed94ad3568433dcf40c67"
}
```

Human range: 260920–261020, with only the explicitly listed hours available on the boundary days. **No 260919 observations or full 260920 day are claimed.** The supplied capture already includes the older first hours; a later live backfill cannot promise to recover them.

| File | Rows | Bytes |
| --- | ---: | ---: |
| `history/2026-09.json` | 2,700 | 1,653,788 |
| `history/2026-10.json` | 5,652 | 3,461,036 |
| `imported-average/2026-09.json` | 2,988 | 1,827,200 |
| `imported-average/2026-10.json` | 5,652 | 3,457,225 |
| `index.json` | 12 current | 7,428 |

## Schema and storage

`tools/neocloud_spot.schema.json` describes v2 structure. The stdlib collector is the authoritative semantic validator: duplicate JSON keys, Decimal canonicalization, platform/family correspondence, timestamps, interval completeness, uniqueness, shard hashes, paths, counts and immutable identities are also checked.

- `data/neocloud_spot/index.json`: source URLs, supported families, current per-SKU snapshot, snapshot/collection times, aggregation contract, shard paths/counts/ranges/hashes and separately named latest completed LAST/AVG endpoints.
- `history/YYYY-MM.json`: completed official LAST observations, attributed to interval-start UTC month.
- `imported-average/YYYY-MM.json`: isolated official AVG import.
- A full month of 12+ SKU histories can exceed 5 MiB when provenance is retained per observation. Deterministic, chronological monthly overflow parts (`YYYY-MM-02.json`, etc.) therefore begin at approximately 4 MiB. Part ranges do not overlap, so a short-range browser query can skip closed prefixes. The manifest lists every part; each file stays strictly below 5 MiB.
- Normal collection decodes and rebuilds only the method/month groups touched by the incoming overlap and carries closed manifest entries byte-for-byte. `--check` remains the deliberate full-archive hash, schema and uniqueness audit.
- Rows contain SKU/title/platform/family/region, canonical exact decimal price string, `USD`, `USD/GPU-hour`, interval boundaries, method/granularity, source snapshot time, collection time, endpoint and source response SHA-256.
- Immutable key: `(sku_id, interval_end, granularity, method)`. Conflicting price or metadata identity aborts the entire update. Equal overlap retains first-seen snapshot/collection/hash provenance, so a new response envelope does not churn old observations. Current snapshots can advance; snapshot regressions are rejected.
- `legacy-user-chart-261020.json`: original five chart values and provenance plus classification `legacy_unverified_derived_chart`. It is never read by the official UI or collector. The exact previous file bytes are preserved in `tools/tests/fixtures/neocloud_spot/legacy.json`.

## Commands

Run from the integrated repository root. No dependencies or authentication are needed.

```sh
python3 tools/collect_neocloud_spot.py --check
python3 tools/collect_neocloud_spot.py --mode refresh
python3 tools/collect_neocloud_spot.py --mode backfill
```

`refresh` automatically performs the first LAST backfill whenever the index has no LAST endpoint, even if AVG import data exists. Both backfill and refresh request hourly LAST with explicit `filters.endTime`, `filters.startTime` and pagination. Backfill uses a 29-day span ending at the current UTC hour. Later refreshes overlap two days, clamped to the available 29-day span. If the collector is offline longer than the rolling window, the unrecoverable gap remains explicit. A returned point timestamp equal to the requested end boundary is valid when it represents a completed interval; the parser also gates completion against the response snapshot.

For exact initial reproduction, coordinator-private source captures are needed:

```sh
python3 tools/collect_neocloud_spot.py --data /tmp/nebius-reproduce \
  --mode import-avg \
  --current-fixture /private/source/official-current.json \
  --series-fixture /private/source/official-series-avg.json \
  --collected-at 2026-10-20T16:00:00Z

python3 tools/collect_neocloud_spot.py --data /tmp/nebius-reproduce \
  --mode fixture-last \
  --current-fixture /private/source/official-current.json \
  --series-fixture /private/source/official-series-last.json \
  --collected-at 2026-10-20T16:00:00Z
```

The commands produce the same normalized index, AVG and LAST files byte for byte. Paths above are placeholders, not repository-owned source copies. Because API responses do not echo aggregation, both fixture modes accept only the exact reviewed current and method-specific response SHA-256 values compiled into the collector. Reserialized, trimmed, substituted or newly captured fixtures fail closed and require a code/provenance review. `--check` is entirely offline and writes no dataset files.

## Fetching, failure and recovery

The only network hostname allowed by the collector is exactly `api.nebius.cloud`, HTTPS, without credentials or unusual ports. Redirects are rejected. No cookie handler, authentication, credential store or environment proxy is used. Socket timeout is 20 seconds; responses cap at 16 MiB, pagination at 100 pages with cycle detection, and 429/5xx retries at four attempts. Each page retains its own response snapshot because Nebius defines it as the earliest observation represented by that response. Retry-After seconds/HTTP-date are honored within a 120-second per-wait budget; larger waits fail closed.

Every fetch, decode, schema check, completed-observation merge and output-size check precedes writes. A failed fetch, overflow, unsafe redirect, malformed last row or immutable conflict leaves **all existing archive file bytes unchanged**. A local file lock serializes writers. Each changed file is written to a same-directory temporary file, flushed/fsynced and atomically replaced; the index is published last. Caught I/O failures roll back already applied files. Repeating identical input leaves bytes and modification times unchanged.

A whole directory is not a filesystem transaction: abrupt process death/power loss between shard replacement and index replacement, or a disk failure that also prevents rollback, can leave hash inconsistency. Readers reject inconsistent history and retain valid current cards. Recovery: retain the failed run's diagnostics, restore the whole index-and-shard set from a known-good repository revision in an isolated checkout, run `--check`, then retry collection. Do not delete/rewrite a conflicting completed observation, silently change its method, or accept an unknown platform. Investigate the key in the error and its source hash. No automatic conflict reconciliation is implemented.

## Scheduled collection and UI

The new GitHub Action runs daily at 16:37 UTC (01:37 KST), plus manual dispatch. It has `contents: write`, non-cancelling concurrency, pre/post tests, read-only checks and scoped data staging. It checks for a normalized no-op, rejects pre-existing staged changes, commits only the index/LAST/AVG data paths, pulls with rebase, revalidates, then pushes. A rebase conflict stops the action for review; there is no forced push. This assignment did not execute the workflow or make any commit/push.

The durable `ui/patch.js` layer mounts directly after the NeoCloud heading, wraps both renderer functions and observes rerenders. It loads the same-origin index first, renders fallback cards, then attempts public current API enhancement. Only shards needed by the selected method/range are fetched; choosing all available history loads the selected layer's full archive. Monthly hashes are verified with Web Crypto. Chart.js is optional; an accessible SVG fallback and exact observation/source table remain available. Missing hourly gaps are disconnected, and current points are separate from completed observations. The four controls select family, region/SKU, range and LAST versus isolated AVG import. LAST is the default layer and is populated in the initial archive.

Browser requests omit credentials and referrers, reject redirects entirely, enforce the exact official host, stream with a 5 MiB cap and use a 12-second abort timeout. Live prices never persist from the browser. API failure retains archive cards; archive failure can still show official current cards. If both fail, `GPU spot 데이터 미로드` and retry remain local to this panel. A one-hour-old observation is labeled delayed; an old effective time alone is not treated as stale. There is no automatic polling or browser-side recent LAST history fetch; daily archival collection supplies history and manual refresh supplies another live current lookup.

## Verification performed

- Python: **81 passed** (52 collector contracts + 29 retained legacy updater tests).
- DOM/static: **14 passed** in a dependency-free Node DOM harness.
- `node --check ui/patch.js`: passed.
- Offline `--check`: **16,992 observations**, passed.
- Deterministic AVG + LAST imports: byte-identical; second publish changed **0 files**.
- `git diff --no-index --check` against the supplied snapshot: passed.
- `git apply --check`, patch application to an independent baseline and full-file comparison: passed.

The test harness is not a browser layout engine. Actual desktop/mobile screenshots, deployed CORS behavior and GitHub Action execution remain coordinator integration checks. No current hardware capacity or future price availability is inferred from these prices.
