# Nebius relationship data v1

Standalone, manually reviewed dataset prepared against Phalanx baseline
`844588f9abdd553e3555c721642c71b21292dafe`. It contains exactly Meta and
Microsoft, using the supplied approved seed contract. No network collection,
schedule, autonomous promotion, product integration, or deployment is included.
Python 3.10+ and the standard library are sufficient (tested on Python 3.14.6).

## Source and rights

Evidence links are the two first-party Nebius newsroom URLs in `reviewed.json`.
The source captures were collected on `261021`. Review cadence is manual, on
admission of new independently verified first-party evidence; no freshness or
currently active/live relationship is implied.

Only the approved original Korean factual paraphrases, source metadata, and
links are distributed. Source titles are retained verbatim as provenance
metadata but are not rendered as product claims. The factual summaries exclude
contract amounts, terms, capacity, GPU types, delivery dates, revenue claims,
page bodies, quotations, logos, screenshots, and Atlas material.
`source_license` is `UNKNOWN`; `provider_terms_apply` is true;
`redistribution_scope` is `FACTUAL_PARAPHRASE_AND_LINK_ONLY`. This metadata is
not a license grant. Browsers must use URLs as evidence links only, never fetch
or proxy these external sources.

The response hashes and byte counts were independently matched to preserved
private source captures before integration. Raw captures are not redistributed.
Artifact hashes verify local dataset bytes; the response hashes preserve the
source-capture identity and are not a license grant.

## Files and wire contract

- `reviewed.json`: hand-reviewed canonical input; never rewritten by the builder.
- `index.json`: generated manifest containing `schema_version`, `dataset`, total
  `record_count`, a `source` descriptor and a one-element `shards` array.
- `shards/<sha256>.json`: generated content-addressed records document. In v1,
  its bytes equal the reviewed document, so the source and shard hashes coincide.
- `../../tools/nebius_relationships.schema.json`: documentation for all three
  JSON documents; Python is the authoritative strict runtime validator.

Source and shard descriptors each carry `path`, `sha256`, `bytes`, and
`record_count`. Shard paths are exactly `shards/<lowercase SHA-256>.json` relative
to this data directory. The source descriptor always names `reviewed.json`,
regardless of the local CLI input filename. For a fresh explicit output
directory, the builder atomically stages those exact reviewed bytes before
publishing the shard and manifest. If an established bundle's public reviewed
source is missing or differs, the build fails before writing instead of
repairing or replacing it.

Records are sorted by stable lowercase `id` (Meta first). Every field is required;
unknown fields and unrecognized enum values fail validation. `UNKNOWN` is the
only missing-value sentinel. Category, service, workload, delivery mode,
disclosure/evidence classes, relationship status, service-live status, event
role and change kind have strict enumerations in the schema and Python module.
V1 deliberately permits only the two approved IDs and a count of two; expansion
requires a reviewed contract and test change. Schema validation alone cannot
check duplicate keys, exact source binding, ordering, date relationships or
artifact integrity.

`event_date` is the relationship announcement date, matching source publication
for these seeds. `display_date` is exactly the date's `YYMMDD` form; it is not an
independent timestamp. `source.published`, `updated`, and `collected` are UTC
source-page publication, source-page modification and capture timestamps, in
that order. Page modification does not represent a new relationship event.
`locator`, `effective`, and `expires` remain `UNKNOWN`. `change_kind` is
`INITIAL_PUBLICATION`, an editorial dataset admission label, not a claim that
service went live. `category`, `service`, `workload`, `delivery_mode`, and the
status/class fields are normalized editorial classifications, not source-native
taxonomy. A consumer may sort events by `event_date` descending with
`id` as a deterministic tie breaker; it must not label those dates as collection
or dataset publication dates.

## Build and validation

Run from the integrated repository root (or from this deliverable's `output/`):

```sh
python3 -B tools/build_nebius_relationships.py
python3 -B tools/build_nebius_relationships.py --check
python3 -B tools/validate_nebius_relationships.py
python3 -B -m unittest discover -s tools/tests -p 'test_nebius_relationships.py' -v
```

Explicit paths are supported by both CLIs:

```sh
python3 -B tools/build_nebius_relationships.py \
  --input data/nebius_relationships/reviewed.json \
  --output data/nebius_relationships --check
```

Canonical JSON uses UTF-8 without BOM, sorted keys, two-space indentation, and
exactly one final newline. Noncanonical reviewed input is rejected, not silently
normalized. Duplicate JSON keys, floats/nonfinite numbers, null, unsafe control,
format/bidi, surrogate and line-separator characters, dangerous object keys,
invalid dates, bad counts/hashes, unknown keys, and unsafe URL authorities are
rejected. Exact lowercase HTTPS authorities `nebius.com` and `www.nebius.com`
are allowed; userinfo, explicit ports, suffix domains and backslashes are not.
Files are limited to 5 MiB. Parent traversal and symlinks anywhere in
input/output paths are rejected; use physical normalized paths (for example,
`/private/tmp` on macOS).

`--check` reads only and returns nonzero for missing files or any byte drift in
the reviewed source, manifest or declared shard. Import bytecode writes are
suppressed by both CLIs. Normal builds validate before writing, preserve bytes
and modification times on no-op, write and fsync sibling temporary files, stage
the public reviewed source for a new bundle, replace the shard atomically, and
publish the manifest last. Existing corrupt
content-addressed shards are rejected rather than overwritten. Normal builds
can replace stale manifests; use `--check` for auditing integrity.

Use a single writer in a trusted local directory and publish reviewed source,
manifest and referenced shards together in a repository commit. There is no
multi-process lock or defense against an adversarial concurrent filesystem
mutation. A failure before manifest replacement preserves the old published
bundle; an unreferenced new shard may remain and is safe to retain. Referenced
shards are not garbage-collected automatically. A directory fsync failure after an
atomic replacement reports failure although the replacement may already be
visible; this is not a multi-file transaction or an unconditional power-loss
rollback guarantee. Check ignores unreferenced shards so older snapshots can
remain available.

## Promotion gates and integration limits

Admit new data only after independent first-party fact checking, capture hash
and byte-count verification, rights/terms review, precise date-role review,
original factual paraphrasing, enum review, and independent functional/security
review of the frozen change. Do not infer service activity. Rebuild and run the
contract tests and read-only validation before integration. The coordinator
must run repository-wide regressions and any release gates.
