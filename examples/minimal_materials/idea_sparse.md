# Idea (example input; replace with your own)

## Problem
Key-value stores lose tail latency when background compaction competes with foreground reads on the same SSD.

## Hypothesis
Pausing compaction for a few milliseconds whenever the read queue is longer than a threshold keeps p99 read
latency low while costing little write throughput.

## Approach
- A queue-length monitor samples the device read queue every 100 microseconds.
- When the queue exceeds a threshold T, compaction threads yield until it drains.
- T is chosen from a short calibration run.

## Contributions
1. A simple, device-aware compaction throttle.
2. A measurement of its effect on tail latency and write throughput.

## Scope and what not to claim
- One SSD model and one key-value store; do not claim the result generalises to all storage devices.
