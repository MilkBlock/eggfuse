# Read sharing and root projections in ordered CPU effects

The normal minimal engine already compiles single-function writes, executes constructor prefixes up to the first miss, reserves the original Cell identity on a hit, reuses statically proved RHS results and checks transferred source slots. This experiment adds two optional native paths on the complete signed CPU configuration. The four frozen Pass 3 inputs use the same source ordering, same allocator and the same checked-slot policy, including changed ports, incremental source epochs, sparse source directory construction and packed multiroot pages.

## Physical read reuse

The compiler admits immutable constructor tables whose rule templates contain no explicit set or visibility mutation to that table. During ordered RHS execution, each admitted table can retain its most recent successful canonical key/row result. A hit requires the exact key including length, the same source Run epoch, table generation and cumulative committed union generation and an empty dirty-fact set. Other reads use the original lookup. The source retains the original physical fact address and hidden bit. The nullary arm selects only constructor tables with zero inputs. The full arm also admits keyed constructors. Both share across adjacent or non-adjacent source effects while the proof remains valid. Revalidation audits independently call the ordinary lookup on every claimed hit and compare the full row, source address, visibility and epoch.

| Source | Vanilla ms | Same-build exact ms | Integrated ms | Integrated with all admitted reads ms | Saved lookups | Ordered RHS before / after ms | New physical Cells both arms |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.05 | 22.44 | 34.49 | 34.26 | 467 | 6.62 / 6.64 | 5,868 |
| dot-product | 18.65 | 19.90 | 31.54 | 31.94 | 611 | 5.91 / 6.01 | 5,682 |
| jacobi-1d | 115.57 | 114.33 | 224.50 | 226.42 | 2,558 | 36.49 / 36.34 | 32,819 |
| conjugate-gradient | 353.08 | 379.34 | 974.02 | 971.44 | 6,080 | 120.38 / 121.67 | 97,139 |

In the largest workload, the plan admitted 64,892 lookups and hit 6,080 times. The original lookup already reaches a direct member for nullary constructors and a stored canonical row for clean hash buckets. A guarded successful lookup is real work avoided, but checking and maintaining the extra result did not yield a consistent full-pass improvement. The native default runtime has no dependency on this experimental directory. [Physical witnesses, exact lookup rechecks and six paired timing samples](constructor-results.json)

## Compiler-checked root slot transfer

The checked-slot verifier already reconstructs and owns a validated source slot buffer for every applied root. The grouped layout stores both the unique projected table atoms and the complete sorted list of RHS slot IDs once per compiled rule. On a match with exactly that slot domain it checks each distinct source header once, honoring the atom/epoch checks already paid by the independent parent witnesses. It takes a single owned copy of the canonical matcher slot vector. Ordered RHS consumption compares the complete immutable values once and then consumes the checked buffer. A binding with a different slot domain retains the original field-by-field proof. The original recipe, constructor choice, parent ordinals and all graph mutations remain checked. Removing a sealed slot was rejected on every program before commit.

| Source | Complete winning slot buffers | Source header checks | Inference ms | Ordered RHS ms | Resident API round-trip ms |
|---|---:|---:|---:|---:|---:|
| sum-bits | 7,265 | 50,745 → 15,371 | 32.48 → 32.91 | 6.20 → 6.38 | 68.7 → 64.1 |
| dot-product | 6,704 | 48,051 → 15,477 | 30.10 → 29.43 | 5.52 → 5.46 | 68.8 → 63.1 |
| jacobi-1d | 41,319 | 288,077 → 93,990 | 226.38 → 226.66 | 37.25 → 37.70 | 298.0 → 278.7 |
| conjugate-gradient | 131,371 | 853,372 → 297,248 | 975.45 → 963.21 | 123.95 → 124.41 | 1069.5 → 1086.3 |

Jacobi avoided 194,087 source header checks and conjugate gradient avoided 556,124. All winning roots used the grouped path. The treatment did not consistently improve inference or the complete resident API request; the latter includes fresh graph/model setup, final graph export, JSON transport and Python decoding. The cache and slot treatments were isolated. Their reference medians come from separate paired studies and should be compared within each table. The experiments did not measure RSS or CPU energy. [Source/physical audits and corruption control](projection-results.json) · [Four additional paired API measurements](wall.json)

## Headroom for a 2× complete pass

Setting ordered RHS time to zero, keeping other measured work, would improve the integrated path by at most approximately 1.24×, 1.23×, 1.19× and 1.14× on these four programs. Conversely, setting search time to zero leaves the following measured costs. Each residual is the median of full inference less that same sample's native search time. This is an accounting floor for an intervention limited to one phase; an architectural change could affect several phases at once.

| Source | Residual if search were free, ms | Half of vanilla, ms | Remaining time budget for all search, ms |
|---|---:|---:|---:|
| sum-bits | 11.25 | 11.02 | −0.23 |
| dot-product | 9.04 | 9.32 | +0.28 |
| jacobi-1d | 59.72 | 57.79 | −1.93 |
| conjugate-gradient | 197.71 | 176.54 | −21.17 |

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/ordered-rhs-reads
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-ordered-rhs"
python "$d/study.py" "$e/NEW-ordered-rhs/session" "$e" "$e/NEW-rhs-read-study"
python "$d/study.py" "$e/NEW-ordered-rhs/session" "$e" "$e/NEW-root-study" --projection
python "$d/wall.py" "$e/NEW-ordered-rhs/session" "$e" "$e/NEW-root-study/results.json" "$e/NEW-rhs-wall"
python "$d/verify.py"
```
