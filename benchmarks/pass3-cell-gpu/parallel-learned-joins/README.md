# Concurrent issuance of connected multi-parent neural tuples

The real standalone Rust CPU runtime runs the two-view, zero-radius learned join, its two-column forward feasibility tests, local atom constraints and the same typed port policy as the integrated reference. The worker path considers compiler plans with three or more independent parents. Every parent after the root must be joined through an existing neural slot. The issuer requires complete typed port columns and, in the initial ablation, at least 64 root rows. Two-parent plans keep their existing source operator. [Implementation](join.rs) · [Native integration](overlay.py)

## What a worker can read

The coordinator holds the original immutable rule occurrence. It supplies signed, packed query/key projections, typed per-row epochs, ordered signature-bucket offsets and read-only references to the directory used for lookahead. The directory returns existence and maximum visible epoch. Local repeated-column tests and the existing owner guard can be prepared as one allowed bit per candidate. Any original exact guard stays on the coordinator during preparation. Workers receive no physical graph, bindings, owner stream or mutable graph state. The native type system checks Send and Sync.

A persistent Rayon pool splits the original ordered root offsets into contiguous, non-overlapping ranges. Within a range, each worker runs the learned multi-parent join, extends only compatible learned signatures and checks the original watermark and forward viability after each chosen parent. A worker returns vectors of positional tuples in its original depth-first order, with a local proposal-attempt ordinal. The coordinator concatenates range results in root order, applies the source occurrence's global proposal cap, checks offsets against the issuing frames and calls the original neural page issuer. Exact parent/suffix verification, source RHS, union/rebuild, original visibility and Spine remain on their ordinary paths. Neither workers nor the coordinator add a missing match. The measured passes did not reach the cap.

The experiment observes actual worker starts and finishes, distinct native threads, overlap, submitted work, issuing-thread wait time and ordered page assembly. A one-thread pool performs the same numeric kernel and packet preparation as the parallel pool. The original production arm runs the preexisting issuer. A separate vanilla CPU executable runs the same source. One worker timed interval is elapsed wall time while that job owns its range. The sum across workers may include simultaneous execution and preemption. Issuer blocking includes dispatch and waiting and should not be added to that sum.

## Independent fresh preparation

Each reported time is a median of six rotating resident executions using frozen seed 1703. Every arm matches the source's ordered RHS, effective writes, actual Spine resumes, schedule, union sequence and graph. The raw learned issue digest, ordered source root parents, physical IDs, nested allocations, multi-witness tickets and single-witness decisions also agree. More than 98% of fresh physical Cells have a directly attributed learned owner. Offset and generation corruption on the two smaller programs caused a source error; the worker issuer supplies no replacement. [Per-arm native evidence](packed.json)

| Source | Eligible calls | Worker-issued tuples / all page tuples | Vanilla / original / 1 / 2 / 4 workers (ms) |
|---|---:|---:|---:|
| sum-bits | 460 | 557 / 7,970 | 22.59 / 35.32 / 42.64 / 43.38 / 50.96 |
| dot-product | 267 | 551 / 8,664 | 18.87 / 31.05 / 35.04 / 35.56 / 42.77 |
| jacobi-1d | 895 | 4,512 / 50,140 | 111.55 / 185.81 / 204.49 / 208.71 / 234.29 |
| conjugate-gradient | 1,921 | 8,815 / 127,051 | 357.21 / 693.78 / 741.67 / 763.68 / 774.43 |

| Four-worker source | Roots partitioned | Multi-parent attempts | Numeric packet preparation (ms) | Coordinator blocked (ms) | Sum of range work (ms) | Ordered merge/seal (ms) |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 76,368 | 5,165 | 0.65 | 7.72 | 1.14 | 0.32 |
| dot-product | 35,024 | 6,698 | 0.51 | 4.39 | 0.84 | 0.23 |
| jacobi-1d | 783,200 | 67,042 | 5.95 | 18.05 | 8.76 | 1.13 |
| conjugate-gradient | 4,392,748 | 209,969 | 25.59 | 49.46 | 39.48 | 2.63 |

All four passes exhibited four simultaneous worker intervals. On conjugate-gradient, the coordinator saw 4,392,748 root positions over 1,921 eligible calls. Only 8,815 complete tuples in this shape reached issuance. The four worker intervals consumed 39.48 ms in aggregate, while their coordinator blocked for 49.46 ms. The high fraction of calls with little useful continuation work limits this partition.

On conjugate-gradient, rule 501 illustrates the eligible shape. The source contains Concat(x,y,out), two ExtractedExpr relations keyed by x and y, and two TCPair relations whose results join the extracted values. Its frozen plan picks five independent physical rows in the order Concat → first ExtractedExpr → first TCPair → second ExtractedExpr → second TCPair. Across 43 eligible calls this plan partitioned 39,616 roots and admitted 38,391 learned non-root pointers, but only 381 complete source-ordered tuples. The worker returns those five offsets. The coordinator seals their original physical identities and the source still checks the actual RHS for PotentialExtractedExpr.

## Reusing the worker input and selecting expensive calls

The second matrix retains immutable per-table epoch columns and per-table/port signature bucket offsets under a 4 MiB accounting budget. Entries are stamped by source table version and frame union generation. Typed port columns and forward directories are borrowed from the existing issuer. A refused cache admission produces the same per-call snapshot. The local arm runs the same numeric depth-first search on the calling thread. A separate one-worker arm uses the pool and the identical columns. Cache accounting includes estimated index and offset storage. It does not measure process RSS. [Cache and version checks](cache.rs) · [Paired counters and timings](resident.json)

The cost gate observes the previous actual approximate candidate visits for each source rule. Its estimate takes the larger of the latest measurement and half the old estimate. A score below 128, or a globally stale occurrence, stays on the original typed issuer. No holdout labels, future matches or rule numbers enter that decision. The fine-grain arm submits four contiguous ranges per worker and merges all results in source order.

| Source | Vanilla | Original | Local numeric | Cached 1 / 2 / 4 workers | Admitted 2 / 4 workers | Admitted 4 workers, four ranges each |
|---|---:|---:|---:|---:|---:|---:|
| jacobi-1d | 115.06 | 192.35 | 188.79 | 213.67 / 217.61 / 235.32 | 200.60 / 209.01 | 204.80 |
| conjugate-gradient | 345.13 | 684.09 | 666.06 | 708.04 / 698.30 / 726.15 | 683.00 / 699.75 | 720.41 |

On conjugate-gradient the cache reused 6,304 epoch columns and 4,467 learned bucket directories in the local arm, with 1,038,472 bytes charged at peak. The cost gate sent 398 of the original 1,921 eligible calls to the worker path; those calls produced 4,977 of the 8,815 eligible tuples. Under this gate two workers completed the pass in 683.00 ms against 684.09 ms for the ordinary issuer, while Jacobi took 200.60 ms against 192.35 ms. Four workers did not improve either full pass. Direct use of the compact input on the calling thread took 666.06 and 188.79 ms respectively. The results favor the data representation for these two workloads and do not support enabling pool dispatch as the default.

## Reproduce

The builder pins the native engine base and typed production policy. The verifier rechecks both frozen matrices. Timings include preparation, lazy pool creation, dispatch, numeric search, ordered sealing and the rest of the original inference. Export follows the timer. [Native build fingerprints](builds.json)

```sh
dir=benchmarks/pass3-cell-gpu/parallel-learned-joins
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-parallel-joins"
python "$dir/bench.py" "$e/NEW-parallel-joins/session" "$e" "$e/NEW-packed"
python "$dir/bench.py" "$e/NEW-parallel-joins/session" "$e" "$e/NEW-resident" --matrix resident --cases jacobi-1d conjugate-gradient
python "$dir/verify.py"
```
