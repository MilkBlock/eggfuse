# Five-implementation throughput checkpoint

The batch does **not** establish a 2× speedup, or a throughput win over the
historical fastest configuration. Shared first reads eliminate real queries,
but this change alone also has no demonstrated speedup on both workloads.

Frozen candidate: `c00c8233`; immediate parent: `aeb059e0`. The historical control
is the verified frozen rebuild of `8fffff65778cf8a20de5abdf9b21af69d0358449`
recorded by the adjacent branch's locality-speed experiment. Its binary SHA256
is checked before the campaign. This measures the standalone Cell CPU, not
native egglog. All lanes use the same historical fast v1 program per workload,
`--repair-ports --entry-publications`, and grain 64 when workers are enabled.
The frozen programs have the same recipes as the short checks.

Seven sum-bits and five Raytrace samples follow one warmup per lane, in
fixed-seed shuffled order with fresh processes. Compilation and source edits
are absent during measurement. Native allocation/profiling instrumentation is
disabled. One worker means inline execution; four workers use a pool plus the
coordinator. Every sample preserves the exact final graph and all ordered Run
records: 1,428 sum-bits Runs, 16,883 Raytrace Runs. The timed sum-bits state hash
also equals the export with native choice acceptance `pass` / exit 0.
Raytrace has no independent native semantic proof in this campaign.

| Lane | sum inference ms | sum process ms | Raytrace inference s | Raytrace process s |
|---|---:|---:|---:|---:|
| Historical fastest | 17.284 | 122.693 | 6.337 | 8.628 |
| Parent, four workers | 18.107 | 126.619 | 6.333 | 8.618 |
| Current, workers off | 17.951 | 124.523 | 6.352 | 8.665 |
| Current, inline one | 18.512 | 127.227 | 6.445 | 8.754 |
| Current, four workers | 18.004 | 129.206 | 6.384 | 8.696 |

These are medians. The current/parent paired inference ratios are 0.9987
(sum-bits; bootstrap 95% interval [0.9849, 1.0162]) and 1.0023 (Raytrace;
[0.9934, 1.0240]). Corresponding process ratios are 1.0358 [0.9759, 1.0851]
and 1.0047 [0.9967, 1.0199]. They establish neither a win nor a large regression
for this change. No sample is discarded. Small-sample intervals and workload
results are not a cross-machine guarantee. Historical load/report measurements
that are absent remain null, rather than being imputed as zero.

## What the full workload changes about the next action

Full Raytrace lookups fall from 4,195,491 to 4,156,647: 38,844 fewer, or 0.926%.
The shared path performs 39,400 Entry probes, 556 fills and 556 clears. It does
not reject any Entry early in this workload. All 1,076,546 queued Entries,
387,764 completion headers and 4,015,919 winner comparisons remain.

The first-read key-field work falls from 1,608 to 29. Since every eliminated
nonempty-key read has at least one key field, at most 1,579 of the 38,844 removed
reads can have nonempty keys. At least 37,265 (95.9%) are zero-argument reads.
The canonical reader already resolves these through direct table membership;
removing them is not comparable to avoiding a large constructor candidate scan.
This is why raw lookup counts cannot serve as a uniform latency score.

Current serial Raytrace phase medians are search 2.849 s, query update 1.245 s,
RHS 1.746 s and repair 0.478 s. Medians need not add exactly to the total. Under
the assumption that every other cost stays fixed, eliminating repair alone
could save only about 7.5% of execution time. That does not rule out a Cell
transformation which also deletes query/publication work; it rules out treating
repair removal alone as the route to 2× for this configuration.

The next target should therefore come from expensive actual matching and
Entry/index maintenance, not more zero-argument sharing or catalog size alone.
This checkpoint says nothing decisive about general graph sparsity. It does
show that the chosen reusable operations are too small a fraction of the work,
and that expanded worker coverage has not yet translated into a throughput win.
The default worker-off path stays authoritative.

## Reproduction

Create a manifest with the five named lanes in checkpoint.json, frozen runtime
paths, the identical program path and the listed arguments. Reuse the harness:

```sh
python3 benchmarks/cell-query-workers/raytrace_measure.py measure SUM_MANIFEST OUT/sum --repeat 7 --warmups 1 --timeout 90
python3 benchmarks/cell-query-workers/raytrace_measure.py measure RAY_MANIFEST OUT/ray --repeat 5 --warmups 1 --timeout 90
python3 benchmarks/cell-fixed-reads/checkpoint.py out/cell-fixed-reads/checkpoint benchmarks/cell-fixed-reads/checkpoint.json
```

The collector requires completed samples, validates all state/schedule hashes,
checks lookup and worker ownership accounting, and records every inference,
wall and CPU observation plus paired ratios. It retains input/binary/raw-sample
hashes and first-sample work. The ignored checkpoint directory contains manifests,
full samples and logs; the harness removes large duplicate graph exports only
after checking and recording their hashes.
