# History-selected closure batch with an independent archive budget

## Opportunity and remaining obligations

The prior catalog observer stopped at 2,048 events after adding uncompiled root
observations. Candidate shape limits should not also limit diagnostic coverage.
`Executor::collect_iterative_history(EVENT_LIMIT)` now sets a separate bounded
archive budget without modifying the Program, candidate budgets or executable
switch. The original collection API and default cap remain available. Increasing
the cap after a drop does not reconstruct missing ancestry. Tests check this.

The actual standalone Cell runtime recorded 4,920 completed cursor events with
an 8,192-event budget and zero capacity drops. There are still 117 missing-parent
boundaries; archive completeness does not mean all runtime ancestry is known.
The analysis reports these separately. It never connects unrelated events.
3,251 events are successful roots outside the installed directory. The recorded
depths are 3,609 at depth 1, 975 at depth 2, 257 at depth 3, 70 at depth 4 and 9 at
depth 5. Executable candidates still obey the original depth/node budget.

Typed cross-Run proofs classify 280 events as internal completion, 163 as local
saturation, 309 as guarded and 559 as unsupported; 3,609 have no transfer.
These counts are coverage, not saved work or committed mutations. Saturation
applies to the covered fragment, not all program rules or future external input.

## Offline selection

With the same eight-unit admission budget, the compiler admits three units:

- A completed producer root for rule 60 and its continuation to rule 143,
  supported by 23 actual paths. The source establishes `Single(e)` and sets
  `Get(orig,n)=e`; after its Run, the consumer can reuse the Single result.
- The missing `137 -> 143` continuation, supported by nine paths. Its compiled
  completion reuses both constructor results and retains the source-position
  lazy union submission.

There are 23 comparison lowerings. Existing suffix-equivalent paths are rejected;
37 guarded and 49 unsupported candidate paths remain outside this admission.
The full selection, including rejected paths, is saved in
full-history-selection.json. No frequency or serialized certificate overrides
typed lowering, actual result checks, delta ownership or source visibility.

## Reproduction

Use the existing saved baseline and effective directory from publication-forwarding.md.
All commands run from the experiment worktree; generated archives stay untracked.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/root-history-full.json --closure-history 8192
python3 benchmarks/cell-structural-compression/analyze_full_history.py out/cell-structural-compression/root-history-full.json benchmarks/cell-structural-compression/full-history-results.json
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics -- bake-cell-completion --program out/cell-structural-compression/closure-existing/program.json --history out/cell-structural-compression/root-history-full.json --extra-units 8 --output out/cell-structural-compression/full-history-admission
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/full-history-admission/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/full-history-work.json
python3 benchmarks/cell-structural-compression/analyze_history_work.py out/cell-structural-compression/closure-forwarded-work.json out/cell-structural-compression/full-history-work.json out/cell-structural-compression/full-history-admission/program.json benchmarks/cell-structural-compression/full-history-work-results.json
```

## Actual batch result: not promoted as an optimization

Both the observation run and candidate execution preserve all 1,428 saved Run
graph and ordered RHS/write/resume hashes. Candidate saved-export semantic
acceptance is `pass`. Runtime unit tests: 143 passed; ripsat integration: 19 passed.
This validates semantics, not profitability.

Compared with the current effective v5 directory:

| Work | Before | Candidate | Change |
| --- | ---: | ---: | ---: |
| Constructor requests | 8,014 | 7,996 | -18 |
| Key lookups | 12,106 | 12,088 | -18 |
| Complete direct transfers | 183 | 183 | 0 |
| History allocations | 302 | 452 | +150 |
| History capture reads / slot writes (each) | 70 | 216 | +146 |
| History sealing reads | 272 | 310 | +38 |
| Effect slots initialized | 7,507 | 7,511 | +4 |

The new rule-60 root executes 146 times in the observation, but its proposed
continuation has support 23. The +146 captures show the cost of saving producer
results on every execution. The final retained history census also grows from
133 to 147 owners; result-array bytes remain 6,336. This census is not peak or
whole-egraph memory. The additional saturated route does not increase direct
completions in this workload. Do not equate support nine with nine saved RHSs.
The full comparison records every changed counter among the 515 existing work
counters, including regressions; overlapping counters are not summed.

The candidate remains an experiment, not a new default artifact. The next
structural target is to avoid creating an extra owner merely to retain a query
witness that already lives in an instance, and to investigate why the additional
saturated route supplies no extra direct completion. Expanding the directory
again before removing those costs is not justified. This experiment does not
establish a runtime speedup or large compression.
