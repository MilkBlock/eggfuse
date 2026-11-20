# Stable source-address postings for learned pair joins

A seminaive two-parent rule with no possible fresh suffix needs at least one fresh parent. This ablation builds a directory on the larger right source using the complete tuple of learned join-port signatures. Each posting contains original physical dependencies in source order and their current visible epochs. A matching bucket proposes addresses, while the graph still validates both actual parents, all source constraints, freshness and ordered effects. A conservative per-bucket epoch bound may leave extra checks after a retirement. It never establishes that a specific pair is fresh. Rules with an enabled cross-parent arithmetic equation keep that path.

The rebuild arm constructs the directory for a new source version. The patched arm can retain it across an exact, contiguous journal in the same union generation. The journal is charged at post-rebuild publication, not supplied from a trace. Missing generations, over-budget tables and high density keep the original route or rebuild the directory. In audit runs every constructed/updated posting is compared against the full immutable source snapshot, including address, value-derived signature, order and visible epoch. The whole original raw stream, actual winning source and physical allocations must also agree. Budget values in the report are conservative charges, not process RSS.

| Case | Vanilla | Original | Rebuild index | Patch index (ms) | Rebuilt right rows → after patching | Addresses patched |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.97 | 32.90 | 34.65 | 33.79 | 29,012 → 19,941 | 398 |
| dot-product | 18.31 | 30.42 | 31.67 | 31.05 | 29,040 → 19,754 | 183 |
| jacobi-1d | 108.56 | 180.58 | 202.26 | 195.87 | 276,891 → 153,211 | 1,519 |
| conjugate-gradient | 357.66 | 684.51 | 764.58 | 718.38 | 1,173,977 → 636,908 | 4,446 |
| 3mm | 918.72 | 2065.47 | 2384.67 | 2161.88 | 2,433,434 → 1,452,277 | 5,685 |
| deriche | 1596.56 | 3813.58 | 4052.44 | 3829.11 | 3,281,581 → 1,696,804 | 10,741 |

Updating journaled addresses improves on rebuilding these postings, but maintaining and probing them does not improve overall inference against the original in this six-program comparison. On 3mm the directory was active in 2,373 rule occurrences and still made 1,237,029 left-row probes for 63,915 issued pairs. Reducing construction work alone did not offset that cost. Each timing set is measured against its own original and independent unmodified vanilla; one frozen seed.

```sh
python benchmarks/pass3-cell-gpu/stable-pair-directory/build.py "$EXP/stable"
python benchmarks/pass3-cell-gpu/stable-pair-directory/study.py "$EXP" "$EXP/stable/session" "$EXP/stable-study"
python benchmarks/pass3-cell-gpu/stable-pair-directory/study.py "$EXP" "$EXP/stable/session" "$EXP/stable-big" --cases 3mm deriche --arms rebuild patched --repeats 4
python benchmarks/pass3-cell-gpu/stable-pair-directory/verify.py
```

## Follow the actual immutable frame transition

A separate control registers an address only after the ordinary source-frame updater successfully constructs a new version from the exact changed set. For the issuer these addresses are a complete description of the difference from the previous frame: every other row was transferred unchanged. Multiple transitions can be chained when the stored through-generation equals the next old generation. A missed link or oversized pending set triggers a rebuild. This permits reusing a directory even across unrelated global unions while validating its exact contents against the new source frame. A previous whole-frame rebuild breaks the chain.

| Workload | Original | Graph journal | Frame transition (ms) | Patched addresses | Rebuild rows, graph journal → frame transition | Cross-union patches |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 34.29 | 33.96 | 33.40 | 1,760 | 19,941 → 1,025 | 163 |
| jacobi-1d | 179.27 | 183.81 | 172.79 | 15,587 | 153,211 → 2,924 | 325 |
| 3mm | 2072.29 | 2231.79 | 2076.37 | 81,279 | 1,452,277 → 13,308 | 599 |

The frame transition greatly reduces rebuilding of learned postings. It did not produce a repeatable overall win over the original on all three programs. Four interleaved repeats, seed 1703. [Native source receipts and time](snapshots.json)
