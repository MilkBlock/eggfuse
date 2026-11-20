# Forward feasibility for sealed multi-parent proposals

The compiler knows exactly which values are available after each independent neural parent. For every remaining table atom it constructs a projection from the known source slots and literals. One-, two- and three-column variants form a directory key by concatenating the learned ten-bit key-side signatures. Each directory records existence and the maximum visible epoch. No directory returns a witness. A parent address is still proposed by the learned source operator, sealed in its original order and independently checked against the Rust graph.

An absence in any necessary projected relation can discard a partial tuple. For seminaive rules, an old partial tuple can also be dropped if every remaining source has an upper epoch below the watermark. If a relation is unkeyed or excluded by the budget, its full table maximum remains in this upper bound. The signature can conflate unequal values, leaving extra proposals for the verifier. A directory is reusable only on the matching table and union generation. The bounded experimental implementation prepares all directories on an immutable rule occurrence. The 4 MiB limit charges a conservative per-source-row size to retained lookup directories, not process RSS or a claim about the rest of the runtime's allocations.

This overlay runs on the real Rust CPU Pass 3 executor, on top of the integrated single-parent frontier, multi-parent pages, trained port projections and ordinary source scheduler. Exact search is disabled for neural ticket attribution. Two-parent rules retain their existing directional guard. The study uses seed 1703, single-threaded CPU, one warm-up and six interleaved full-inference samples. Every arm preserves ordered RHS, effective writes, Spine, union, schedule, graph and each surviving winning source proof and physical Cell ID. The stale-control arm ignores all directory evidence and reproduces the entire original raw issuance digest.

| Workload | Original → both two-column raw tuples | Original → both two-column median (ms) | Vanilla (ms) |
|---|---:|---:|---:|
| sum-bits | 9,956 → 9,384 | 33.99 → 32.79 | 21.98 |
| dot-product | 12,099 → 9,955 | 31.95 → 30.25 | 19.12 |
| jacobi-1d | 122,523 → 84,705 | 220.15 → 184.92 | 106.34 |
| conjugate-gradient | 765,670 → 531,346 | 928.47 → 746.91 | 338.67 |

Three columns rejected only four additional CG tuples and required 761.88 ms. Existence alone ran in 857.60 ms and the epoch bound alone in 803.59 ms. The baseline root-only and fresh Cell coverage denominators and all repeat timings are in the accompanying text data. The results do not establish parity with the default CPU.

```sh
python benchmarks/pass3-cell-gpu/learned-prefix-feasibility/build.py "$EXP/forward"
python benchmarks/pass3-cell-gpu/learned-prefix-feasibility/study.py "$EXP" "$EXP/forward/session" "$EXP/forward-small"
python benchmarks/pass3-cell-gpu/learned-prefix-feasibility/study.py "$EXP" "$EXP/forward/session" "$EXP/forward-cg" --cases conjugate-gradient --arms off future2 fresh2 both2 both3
python benchmarks/pass3-cell-gpu/learned-prefix-feasibility/verify.py
```
