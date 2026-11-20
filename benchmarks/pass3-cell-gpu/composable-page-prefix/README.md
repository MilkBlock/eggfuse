# Longest common prefixes in sealed multi-parent proofs

The frozen integrated Rust Cell CPU, seed 1703, issues an ordered page of complete learned parent choices before its verifier reads the source rows. This experiment measures how much *additional* work could be eliminated beyond reuse of the first verified parent. It runs the original full source schedule with the signed single-parent policy, incremental 256 KiB typed directory, two-column forward feasibility with existence/freshness, and compiled atom constraints. Two- and three-view variants use their corresponding projected signatures. Candidate generation does not inspect the recorded exact answer, certificate decoder or failed-prefix counters.

Within one immutable page, two parent references share a prefix position only if they have the same atom ID, the same tagged physical fact/function address and the same source row version, with all prior positions equal. The first tuple has prefix length zero. The depth histogram counts logical positions in all issued tuples and actual source row reads reached before the original typed verifier rejects a tuple. A later repeated prefix that was never visited in the control cannot contribute a saved read. Field opportunities count the arity of these rows, including the result column; they upper-bound field checks, since an individual check may fail early.

The diagnostic codec writes the exact LCP followed by the newly supplied parent references. The format records a one-byte prefix length and four little-endian 64-bit words per new reference (atom, address tag, address, source version). The native flat reference is also 32 bytes on the measured host. First-parent-only and arbitrary-LCP encodings use identical address and version formats. Sequential archives keep one restart at page start. Indexed archives restart every 32 tuples and retain a 32-bit byte offset for each block. Each nonempty archive has two charged data buffers. A reverse traversal seeks the last tuple of each block to exercise arbitrary receipt retrieval. Each tuple is also decoded in source order and compared to the originally issued atoms, physical references and versions. The governing source verifier still consumes the original page: these are exact archive and work bounds, without changing runtime root credit or skipping a source operation.

## Results

“Additional” counts opportunities beyond a previously verified first parent. The percentage divides by remaining native source row reads. Failed-prefix reuse means the same already-failing prefix was reached again by the actual source verifier. The last column uses a 32-tuple restart interval and sums allocated *payload capacities across pages over a pass*, rather than reporting simultaneous heap residency.

| Workload / views | Sealed tuples | Source parent reads | Saved by first parent, upper bound | Additional reads at greater depth | Additional checked fields, upper bound | Additional known-failure rejects | Additional indexed archive bytes saved |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits / 2 | 7,968 | 17,368 | 2,422 | 44 (0.29%) | 94 | 0 | 1,408 |
| sum-bits / 3 | 7,968 | 17,368 | 2,422 | 44 (0.29%) | 94 | 0 | 1,408 |
| dot-product / 2 | 8,658 | 20,376 | 3,451 | 424 (2.51%) | 1,864 | 0 | 13,344 |
| dot-product / 3 | 8,658 | 20,376 | 3,451 | 424 (2.51%) | 1,864 | 0 | 13,344 |
| jacobi-1d / 2 | 50,086 | 111,518 | 22,384 | 2,398 (2.69%) | 6,765 | 24 | 74,752 |
| jacobi-1d / 3 | 49,945 | 111,185 | 22,300 | 2,357 (2.65%) | 6,680 | 0 | 73,440 |
| conjugate-gradient / 2 | 126,667 | 275,807 | 56,181 | 4,337 (1.97%) | 12,552 | 0 | 134,656 |
| conjugate-gradient / 3 | 126,472 | 275,398 | 56,085 | 4,329 (1.97%) | 12,535 | 0 | 134,432 |

On conjugate-gradient with two views, a flat full pass writes 8,826,400 bytes of parent records. The first-parent indexed representation uses 7,227,391 bytes and the arbitrary-LCP representation uses 7,092,735. The second change saves another 134,656 bytes over 2,593 pages (1.86% of first-parent encoded data). Three views reduce the extra opportunity further. A page with a compact body and dedicated seek directory still makes two data allocations: the codec does not get credit for eliminating an allocation per tuple. Scratch and native allocator padding are excluded from the archive capacity measure.

The four workloads were exact against the independent CPU reference on every source Run, including RHS, effective writes, Spine, union and final graph. No model predictions were supplied by the codec. These counts bound reductions in actual row visits and encoded contents, not wall time. The existing issuer often varies the second source address immediately after fixing the first. With both static forward feasibility and learned projections already enabled, the deeper-suffix opportunity is 0.29–2.69% of *remaining parent reads*. We stop the performance experiment here and do not add an unmeasured streaming verifier to production. [All depth histograms, wire capacities, reconstruction checks and physical source evidence](results.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/composable-page-prefix
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-prefix-census"
python "$d/study.py" "$e/NEW-prefix-census/session" "$e" "$e/NEW-prefix-census-results"
python "$d/verify.py"
```
