# Pass the checked block itself into root binding

Once all independent parent coordinates, local constraints, cross-role predicates and the exact source suffix have succeeded, the verifier holds the complete slot environment and physical witness array. The new internal proof borrows the very same immutable graph and sealed page, names its exact lane, and exposes only those checked values. Its fields are private to the source verifier. Root binding checks page allocation identity, exact lane, serial, source epoch, rule, actual template, active compiler layout, withholding and version-fault status. The production path can now skip decoding the parent vector again and skip looking up source headers that were just checked. In the separate detailed run those original source validations are executed explicitly and the original parent array is retained for the commit audit.

Both variants retain an independent checked slot buffer in the root recipe. The buffer control clones the already verified slot map directly only when its cardinality and ordered slot sequence match the static projection exactly. The subsequent source commit still compares and consumes the checked values before constructing the physical Cell. Omitting a root never authorizes an unstamped physical allocation. Apart from the explicitly measured controls, the trained parent issuer and physical source scheduler are unchanged.

| Program | Vanilla | Original joint | Coordinate verifier | Pass verified page | Plus exact buffer, ms | Eliminated duplicate parent / projected-field header checks |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.13 | 32.50 | 33.35 | 32.42 | 32.14 | 10,198 / 27,637 |
| conjugate-gradient | 327.30 | 589.96 | 607.89 | 592.12 | 597.87 | 133,269 / 339,316 |
| 3mm | 844.87 | 1,889.70 | 1,852.52 | 1,779.50 | 1,819.79 | 362,744 / 919,103 |

On 3mm, 146,965 checked multi-parent bindings avoided 1,281,847 duplicate source header checks. A forged checked lane fails explicitly. Changing the issued version or template, or withholding the page root, fails at the same original Run and RHS as ordinary coordinate verification. The complete raw and physical winner ledgers and all Run events agree. Four rotating resident samples follow a warmup at seed 1703. [Measurements and corruption controls](results.json)

```sh
d=benchmarks/pass3-cell-gpu/block-root-transfer
python "$d/build.py" "$EXP/root-handoff"
python "$d/study.py" "$EXP" "$EXP/root-handoff/session" "$EXP/root-handoff-results"
python "$d/verify.py"
```
