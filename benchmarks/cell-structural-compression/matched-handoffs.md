# Matched cross-stage handoffs: executable experiment, not accepted compression

This opt-in catalog extension executes in the actual standalone Cell runtime,
not native egglog. Existing artifacts have no `matched_entries` and retain their
previous paths. The accepted compression artifact remains `domain-classes-derived`.

## Opportunity and live obligations

The audited View8 trace has 98 exact links into rule 507 from rules 286, 502,
504 and 505. Ordinary query planning cannot enter this consumer from its View
pivot because the TCPair reverse lookup is not a functional-key query. A matched
entry instead waits until the ordinary matcher finishes all query atoms, mutable
reads and guards. It uses the captured anchor receipt and existing publication
directory to dispatch a typed Cell composition, then the ordinary receipt checks
validate actual RHS results. There is no inferred universal result address or
new producer-consumer index. Late inputs, deletion, generations, visibility and
source Run ordering retain their existing checks.

Each selected route is a bounded catalog extension using the existing combine
and lowering machinery; multiple routes are applied sequentially. The experiment
rebinds ownership provenance to the candidate artifact only after verifying exact
prepared ownership shapes and transitions. Execution admission is still required.

## Measured result

All 1,428 Run boundaries have equal graph state, RHS input audit and ordered
writes. The baseline additionally matches the complete historical audit, including
resumes; candidate resume history intentionally differs in 138 Runs. Final exports
are exactly equal to the saved CPU semantic input, and choice diagnosis passes.
154 runtime unit tests plus matched-handoff, query-receipt and ripsat-completion
integration suites pass. The focused tests cover late inputs, deletion/recreation,
mutable guards, shared Entry publication and two query workers.

| Work/storage | Baseline | Candidate |
|---|---:|---:|
| Actual key lookups | 12,106 | 12,004 |
| RHS constructor requests | 8,014 | 7,912 |
| History allocations | 302 | 644 |
| Retained history owners | 133 | 341 |
| Absorbed root completions | 228 | 100 |
| Graph-owned teardown bytes | 2,617,317 | 2,617,317 |
| Execution growth above setup | 5,570,091 | 5,624,235 |

The 102 successful handoffs remove 102 actual constructor lookups (no prepared
constructor operations in this lane). They add 102 anchor reads, 612 field checks,
342 history allocations/captures and 128 output registrations. Source storage,
logical facts and created Cell counts do not improve. This candidate is rejected
as a compression baseline. Lower total process peak comes from a smaller retained
Program, not a smaller runtime egraph. No speedup is claimed.

New producer roots seed retained result history. This also turns some previously
absorbed roots into live completion contexts. Increasing hit coverage with this
representation therefore amplifies the wrong storage. The next change should use
all-writer constructor invariants to project a proven result value directly from
existing Entry slots, avoiding history capture for value-only use. A View receipt
must never be relabeled as a constructor receipt. Receipt-dependent consumers,
mutable reads and source effects still require their existing handling. Only then
can ownership replacement retire intermediate instance storage and maintenance.

## Reproduction

Use `CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target` and Cargo features
`sparse-cells,iterative-bake,storage-metrics` for the examples below. Inputs are
produced by the existing View8 trace and domain-classes experiments.

```sh
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example bake_matched_handoffs -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/closure-existing/program.json benchmarks/cell-structural-compression/view8-handoff-results.json out/cell-structural-compression/view8-handoff-trace.json out/cell-structural-compression/matched-handoffs
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example audit_matched_handoffs -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/matched-handoffs/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/matched-handoff-audit.json
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/matched-handoffs/program.json out/cell-structural-compression/matched-handoff-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_matched_handoffs.py out/cell-structural-compression/matched-handoff-audit.json out/cell-structural-compression/completed-symbolic-heap.json out/cell-structural-compression/matched-handoff-heap.json benchmarks/cell-structural-compression/matched-handoff-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/matched-handoff-semantic.json
```

Before reusing semantic exports, assert the new audit's `final_state` equals
`/private/tmp/eggfuse-structural-semantic/run-legacy/state.json` exactly. The summary
records both artifact hashes; raw generated programs, traces and heap samples stay
untracked. Matches/handoffs are not counts of committed mutations.
