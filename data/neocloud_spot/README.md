# Nebius Spot Prices archive · 261021

This directory contains normalized, attributed observations from the public Nebius Spot Prices API. It does not contain the raw response envelopes.

- `index.json`: current per-SKU observations plus the hash-checked shard manifest.
- `gpu-index.json`: append-only `Nebius GPU Spot Equal-Family Price Index (LAST)` levels, constituent catalogue and composition epochs.
- `history/`: official hourly `METHOD_LAST_PRICE` observations.
- `imported-average/`: separate hourly `METHOD_AVG_PRICE` evidence; never relabelled as LAST.
- `legacy-user-chart-261020.json`: isolated unverified values from the original user-supplied chart; never consumed by the official tracker.

Point timestamps from Nebius are interval ends. Each stored `interval_start` is one hour earlier, and month attribution follows the interval start in UTC. Missing intervals are not interpolated or forward-filled.

The derived index starts at 100 and chains completed-basket `METHOD_LAST_PRICE` relatives under methodology version `equal-family-chain-v1`. GPU families are equal-weighted; regions are equal-weighted inside each family; SKUs are equal-weighted inside each region. This hierarchy prevents a family from gaining weight merely because Nebius lists it in more regions or under more SKU aliases. It is a price index, not a performance, capacity, usage or market-share index.

The initial reviewed basket is a retrospective bootstrap exception and is applied to pre-publication history back to the first common endpoint. A newly discovered official GPU/SKU is recorded as pending, requires 24 consecutive completed hourly observations after its non-retroactive seasoning boundary and enters at the next UTC 00:00 composition boundary. For a late discovery carrying older backfill, seasoning starts only after the already published endpoint. Published levels are never backfilled with a later-discovered product. Composition changes are chain-linked, so a weight change by itself cannot move the index. A missing endpoint remains a visible gap; the next complete basket resumes from the last complete basket over the full elapsed interval, without interpolating or forward-filling a level.

An active SKU is considered for retirement only when it is absent from two consecutive complete `index.json.current` snapshots whose snapshot times are at least one hour apart and whose full source-index hashes differ. A missing LAST row alone is never retirement evidence. One absence keeps the SKU active, an identical payload is idempotent, and reappearance cancels that candidate; reappearance after confirmation or retirement fails closed. The first evidence promotes the derived document from schema v1 to v2 without changing the methodology version, and v2 never downgrades. Retirement takes effect at the first unpublished chainable completed hour after confirmation. A complete old basket uses its normal link; otherwise the link explicitly uses only surviving old constituents, never simultaneous additions. Empty or unpriceable survivor baskets fail closed, and published levels, epochs and deactivation times remain immutable.

Lifecycle replay is anchored outside the mutable working file. Capture the exact committed prior `gpu-index.json` and the same commit's `index.json`, then pass them with `--trusted-existing` and `--trusted-source-index`. The builder uses only that prior blob as state; the working GPU index is an exact-byte comparison/replacement target. A missing first document requires the explicitly reviewed `--bootstrap` path and is not automatic recovery. The browser independently hashes the exact fetched `index.json` bytes before rendering the derived index.

Collector archive validation is capped at 5,000,000 aggregate rows and 1 GiB of shard bytes. A normal refresh reads and validates retained shards once, then reuses those rows for touched-group merging and exact family derivation.

Run the authoritative offline validation from the repository root:

```sh
BASE_SHA="$(git rev-parse HEAD)"
TRUST_DIR="$(mktemp -d)"
git cat-file blob "$BASE_SHA:data/neocloud_spot/gpu-index.json" > "$TRUST_DIR/gpu-index.json"
git cat-file blob "$BASE_SHA:data/neocloud_spot/index.json" > "$TRUST_DIR/index.json"
python3 tools/collect_neocloud_spot.py --check
python3 tools/build_neocloud_gpu_index.py --check \
  --trusted-existing "$TRUST_DIR/gpu-index.json" \
  --trusted-source-index "$TRUST_DIR/index.json"
```

Source contract, exact capture hashes, reproduction and recovery procedures are documented in `NEOCLOUD_GPU_SPOT_261021.md`.
