# Compiler-planned entrances for a single fresh relation

For each possible source pivot, compile a connected sequence of independent neural parent pointers followed by uniquely determined reads. On a seminaive rule with a positive watermark, select a variant only when exactly one original source atom can supply a visible fresh row. Multiple possible fresh sources keep the existing sealed plan. The compiler can admit an additional neural parent in the third treatment. All selected parents are sealed together before exact source reads. No successful bindings or expected RHS are used to select an entrance.

The study uses the full Rust research executor on real Pass 3 with the tied learned projection, one view and radius zero. Gold source executions come from the unmodified default-feature vanilla executor. Each distinct seed and workload is audited before resident interleaved timings with the CLI allocator. No residual source matcher is enabled for these certificates. Width changes can lead to a different sealed witness representation; both still cover the committed source sequence. The shared-plan-only arm must have identical raw receipts as well.

| Workload, seed 1703 | Sealed tuples, fixed → extra pointer allowed | Freshness switches with an extra parent | Fixed / shared fixed / same width / extra allowed (ms) | Vanilla (ms) |
|---|---:|---:|---|---:|
| sum-bits | 22,707 → 19,342 | 49 | 56.17 / 55.77 / 54.57 / 52.65 | 20.77 |
| dot-product | 22,840 → 21,851 | 17 | 54.75 / 55.78 / 53.37 / 53.26 | 19.04 |
| jacobi-1d | 274,827 → 245,700 | 52 | 483.46 / 480.44 / 481.22 / 476.22 | 116.67 |

This experiment isolates the plan switch relative to a fixed learned entrance. The table does not stack the independent reverse two-parent traversal or the higher-order guard experiment.

Run from the worktree after preparing the inputs in compact-recipes and the tied tables in baked-port-codes. Set EXP to the directory containing those artifacts and choose new build and output directories.

```sh
python benchmarks/pass3-cell-gpu/fresh-entrances/build.py "$EXP/entrance"
python benchmarks/pass3-cell-gpu/fresh-entrances/measure.py "$EXP/entrance/session" "$EXP/vanilla" "$EXP/bundles" "$EXP/lookup" "$EXP/entrance-study"
python benchmarks/pass3-cell-gpu/fresh-entrances/verify.py
```
