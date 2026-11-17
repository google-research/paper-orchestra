# Experimental log (example input; replace with your own numbers)

## Setup
- Hardware: one server, 1 NVMe SSD.
- Software: an LSM-tree key-value store, default configuration.
- Workload: 90% reads / 10% writes, uniform keys, 30-minute runs, 3 repetitions.

## Results

| Configuration | p99 read latency (ms) | Write throughput (kops/s) |
|---|---|---|
| Baseline (no throttle) | 4.8 | 52 |
| Throttle, T = 8 | 1.9 | 49 |
| Throttle, T = 32 | 2.7 | 51 |

- Variation across the 3 repetitions: at most 6% for every number above.
- Calibration chose T = 8.

## Limits
- One device model; read-heavy workload only.
