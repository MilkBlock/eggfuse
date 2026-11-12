# Repeated completed RHS projections across Runs

The prior work reduced instance fields and duplicate constructor indexes but did
not eliminate additional RHS execution. The saved application history describes
paths, not enough actual bindings to count repeated RHS projections. Rule 58 is
a concrete candidate: it matches `Get(x,i)` but constructs `Add-Gets(x,x,0)`.
Different matched `i` values can produce the same RHS.

The new opt-in bounded observer compiles a diagnostic projection for pure virtual
constructor/Copy bodies. It uses existing completed-dead-input analysis, retaining
inputs used by operations, result aliases or cross-stage consumers. After actual
completion, before binding retirement, it records those values, completed Run,
committed-union revision, output-table query versions and existing execution work
counters. This observation never controls execution or stores a runtime reuse
index. Unavailable inputs are explicit failures; dropped archives cannot support
analysis. Default execution retains no trace. Single-write fast paths, already
direct completions and non-pure bodies are outside this observer's scope.

## Actual standalone runtime evidence

2,587 eligible completions, 2,563 unsupported generic completions, zero drops and
zero unavailable projections. All 1,428 saved Run graph and ordered RHS/write/
resume hashes pass. Final state, Graph work and source storage exactly match the
prior derived-class execution. Semantic acceptance passes using the equal saved
export. Observation reads add 369 stable-node lookups, 367 port reads and 405
parent probes; these are diagnostic costs, not an execution improvement.

Within identical Run, union revision, output-table versions and projected input:

| Rule | Completions | Repeated constructor requests |
| --- | ---: | ---: |
| 58: `Get(x,i) -> Add-Gets(x,x,0)` | 220 | 84 |
| 518: `Get(e,i), HasArgType(e,ty) -> HasArgType(Get(e,i),ty)` | 175 | 51 |
| 65: `Bop(...) -> Not-Just-Concat(...)` | 32 | 3 |

All 138 repeats have zero new facts, function updates or union requests. They are
small relative to the workload and cannot justify a new maintained binding cache
as the main compression approach. Equal observations also do not discharge the
original publication, actual-result retention, delta ownership or history work.

A second, explicitly unproven category finds **197 cross-Run repeats** and nine
same-Run repeats with the same projected inputs but changed revisions. Across
these 206 events, 169 have changed union revisions and 205 changed output-table
versions; these counts overlap. They also create no facts/updates/union requests
in this execution. Whole-table invalidation is therefore too coarse to answer
whether a particular Cell remains saturated. These observations are opportunities
for local evidence, not permission to ignore deletion, visibility or coalescence.

The next structural obligation is to preserve the particular established facts
and actual results through a shared Cell completion state. A global epoch cache
would reject these cross-stage cases; an unversioned input cache would assume the
very liveness and publication proof still missing. This observer does not claim
that either cache, or skipping the 138 requests, achieves large egraph compression.

Tests: bounded trace loss/unavailable-input unit test; three offline tests for
Run/revision separation, unknown inputs and malformed/incomplete archives; default
runtime Cargo check. No performance campaign was run.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/rhs-projection-versioned-audit.json --natural --shared-owners --parent-takeover --port-domains-only --rhs-projection-trace
python3 benchmarks/cell-structural-compression/analyze_rhs_projection.py out/cell-structural-compression/rhs-projection-versioned-audit.json benchmarks/cell-structural-compression/rhs-projection-results.json out/cell-structural-compression/domain-classes-derived-audit.json
python3 benchmarks/cell-structural-compression/test_rhs_projection.py
```
