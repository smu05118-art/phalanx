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

Run the authoritative offline validation from the repository root:

```sh
python3 tools/collect_neocloud_spot.py --check
python3 tools/build_neocloud_gpu_index.py --check
```

Source contract, exact capture hashes, reproduction and recovery procedures are documented in `NEOCLOUD_GPU_SPOT_261021.md`.
