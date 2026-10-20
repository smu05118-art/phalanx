# Nebius Spot Prices archive · 261021

This directory contains normalized, attributed observations from the public Nebius Spot Prices API. It does not contain the raw response envelopes.

- `index.json`: current per-SKU observations plus the hash-checked shard manifest.
- `history/`: official hourly `METHOD_LAST_PRICE` observations.
- `imported-average/`: separate hourly `METHOD_AVG_PRICE` evidence; never relabelled as LAST.
- `legacy-user-chart-261020.json`: isolated unverified values from the original user-supplied chart; never consumed by the official tracker.

Point timestamps from Nebius are interval ends. Each stored `interval_start` is one hour earlier, and month attribution follows the interval start in UTC. Missing intervals are not interpolated or forward-filled.

Run the authoritative offline validation from the repository root:

```sh
python3 tools/collect_neocloud_spot.py --check
```

Source contract, exact capture hashes, reproduction and recovery procedures are documented in `NEOCLOUD_GPU_SPOT_261021.md`.
