# Evaluate Cell arithmetic ports only when another learned parent can use them

The compiler's two-parent scalar equation still defines exactly the same signature test. The eager control builds the numerical projection for a complete source version. A late-array control runs the same precomputed comparison only after the existing freshness and other learned-column guards. The requested arm computes the projection for the surviving left source once on first use and shares it across that source's remaining candidates. The direct arm uses the same checked i64 implementation as the source runtime. An additional 256-slot direct-mapped table remembers a signed integer's trained tag. The key contains the full scalar value; colliding memo slots trigger recomputation. This is safe across source Runs because the frozen tied projection is a pure function of that value. Undefined checked arithmetic rejects only the corresponding parent pair. Unproven operands retain source evaluation.

This is measured on the complete native Rust CPU schedule with no residual search, including the numerical request, memo/table access, source verification, ordered RHS and original graph maintenance. All projected treatments have the **same complete raw neural tuples**, source parents, versions, winners, union, writes, Spine and real Cell allocations. The unmodified vanilla executable and a no-equation integrated control are timed separately. Seed 1703; six repeats on the four initial cases and four on the larger transfers.

| Workload | Vanilla | Original | Eager | Late arrays | On-demand memo (ms) | Actual arithmetic computations | Trained integer encodings / memo hits |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.19 | 32.46 | 32.08 | 32.83 | 32.00 | 947 | 7 / 3,230 |
| dot-product | 18.02 | 29.58 | 28.99 | 29.32 | 29.12 | 636 | 9 / 2,222 |
| jacobi-1d | 111.40 | 184.47 | 182.29 | 183.27 | 185.31 | 5,426 | 13 / 23,547 |
| conjugate-gradient | 344.37 | 690.71 | 683.12 | 689.29 | 663.13 | 16,083 | 14 / 63,013 |
| 3mm | 856.50 | 2094.33 | 2092.91 | 2060.91 | 1932.55 | 70,190 | 25 / 337,340 |
| deriche | 1471.46 | 3846.91 | 3820.29 | 3675.56 | 3549.84 | 69,120 | 26 / 346,479 |

For 3mm, 267,175 pairs reached the computed check and only 25 scalar signatures required an actual encoding. 196,985 later points reused the left result. This is an execution-granularity effect; it does not add parameters or change the learned policy. The small-case clock differences are mixed. [Static compiler plan and fixture](../pair-source-frontier/README.md)

```sh
python benchmarks/pass3-cell-gpu/lazy-equation-ports/build.py "$EXP/lazy-ports"
python benchmarks/pass3-cell-gpu/lazy-equation-ports/study.py "$EXP" "$EXP/lazy-ports/session" "$EXP/lazy-core"
python benchmarks/pass3-cell-gpu/lazy-equation-ports/study.py "$EXP" "$EXP/lazy-ports/session" "$EXP/lazy-large" --cases 3mm deriche --arms eager late memo --repeats 4
python benchmarks/pass3-cell-gpu/lazy-equation-ports/verify.py
```
