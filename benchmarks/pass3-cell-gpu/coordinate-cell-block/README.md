# Consume the model's page coordinates in the compiled verifier

Each immutable role dictionary gives a physical word for an address and its source version. The native verifier reads a candidate's coordinates directly. It validates an entry once against its source atom, physical address, version, literals and repeated fields. The checked source row is indexed directly by role and coordinate for subsequent candidates. Cross-role equalities and the outcome of each deterministic suffix remain tuple-specific. The ordered source root still has its original page and serial. The lazy treatment loads only reached words; the eager control checks every dictionary entry up front. At most 32,768 parent words may be retained for one page. An oversized page keeps the complete previous verifier.

For a deterministic point whose entire key derives from one parent, the compiler can additionally address its checked result (including absence) by that parent's coordinate. Up to 4,096 coordinate-indexed results are allocated across the eligible point steps. Other requests retain their original exact call or bounded hashed memo. Forced dictionary mode gives each distinct physical word one coordinate per role. Selective and streamed modes can instead choose a direct column with one coordinate per tuple. Repeated physical addresses in a direct column therefore need not produce a coordinate-cache hit. The source stream and verified outcomes agree even when optimization counters differ.

| Program | Default CPU | Original learned | Dictionary, original verifier | Dictionary, hashed block | Coordinate words | Coordinate words + ports | Streamed selective + ports, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.25 | 32.99 | 33.73 | 34.71 | 34.64 | 33.57 | 34.98 |
| conjugate-gradient | 372.78 | 665.46 | 656.00 | 666.03 | 646.54 | 630.41 | 678.41 |
| 3mm | 878.59 | 1,910.30 | 1,909.25 | 1,853.92 | 1,933.31 | 1,938.09 | 1,916.48 |

| Program | Parent lanes | Distinct shared words | Source words actually read | Later-role word hits | Compiled per-step port maps |
|---|---:|---:|---:|---:|---:|
| sum-bits | 13,260 | 10,602 | 10,602 | 1,556 | 144 |
| conjugate-gradient | 189,794 | 131,493 | 131,480 | 32,728 | 463 |
| 3mm | 526,429 | 325,691 | 325,607 | 112,418 | 587 |

Four rotated resident samples follow a warmup at seed 1703. The full online neural stream, all ordered source evidence, actual winner parents and fresh physical Cell ledgers match. For the synthetic source, original, hashed and coordinate paths saw the same winning tuples across a missing function key, a later insertion and an actual union. Local predicates include a repeated variable and a source literal, and the final independent native check requires all four expected output facts. An invalid coordinate fails before full source completion. [Full measurements](results.json) · [Fixture](ports.egg) · [Native failure and exact source receipts](fixture.json)

```sh
d=benchmarks/pass3-cell-gpu/coordinate-cell-block
python "$d/build.py" "$EXP/coordinate-block"
python "$d/study.py" "$EXP" "$EXP/coordinate-block/session" "$EXP/small-coordinate-runs"
python "$d/study.py" "$EXP" "$EXP/coordinate-block/session" "$EXP/large-coordinate-runs" --cases 3mm --arms encoded hash-block words ports stream
python "$d/fixture.py" "$EXP" "$EXP/coordinate-block/session" "$EXP/new-coordinate-source"
python "$d/verify.py"
```
