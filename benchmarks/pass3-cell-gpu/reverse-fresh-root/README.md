# Reverse fresh-source routing for the independent root domain

A seminaive rule needs a sufficiently fresh source somewhere. If every fresh remaining relation has a projected key at the root, reverse its learned signature directory to collect possibly useful old root positions. Include all genuinely fresh root positions, sort and deduplicate, and visit the surviving positions in the original trained generator. A table without a usable key and a sufficiently high epoch prevents this optimization. A matching literal-only key can have the same effect. An over-budget or dense reverse expansion keeps the original source-order enumeration. A signature match never claims that the source rule holds.

The forward, sparse (64 rows / 20%), middle (32 / 50%) and broad (16 / 80%) controls use the same two-view kernel. Every learned proposal, winning parent, source occurrence and actual physical Cell identity matches. The 4 MiB reverse budget accounts conservatively for stored root postings; the auxiliary sorted view of each forward directory is tracked separately by its contents, not measured as process RSS.

| Program | Original / sparse / middle / broad (ms) | Eligible root rows before → after, sparse | Vanilla (ms) |
|---|---:|---:|---:|
| sum-bits | 34.12 / 34.42 / 34.49 / 34.84 | 63,252 → 2,507 | 21.89 |
| dot-product | 31.14 / 31.13 / 31.98 / 31.60 | 19,509 → 615 | 18.85 |
| jacobi-1d | 178.40 / 177.68 / 184.62 / 182.87 | 678,197 → 18,305 | 106.56 |
| conjugate-gradient | 700.44 / 688.04 / 699.62 / 690.86 | 4,001,376 → 101,693 | 356.72 |

The denominator in the root column is limited to occurrences where the sparse reverse plan ran. Setup, dependency scans and retained directories are charged to the timed inference. Savings on total latency are small compared with the main prefix check. Six interleaved native samples per arm, seed 1703.

```sh
python benchmarks/pass3-cell-gpu/reverse-fresh-root/build.py "$EXP/reverse"
python benchmarks/pass3-cell-gpu/reverse-fresh-root/study.py "$EXP" "$EXP/reverse/session" "$EXP/reverse-study"
python benchmarks/pass3-cell-gpu/reverse-fresh-root/verify.py
```
