# Actual cost of the equal-settled-state candidates

The previous analysis found 154 saturated extensions with the same settled
constructor structure and inherited port maps. Before adding another runtime
sharing mechanism, this experiment connects them to existing executable plans
and **actual per-event result capture work**.

## Result: most proposed sharing already exists

Of the 154 events, 153 already have an installed direct-completion plan.
`Results::project_complete` composes static layouts and `ResultFrame::retain`
keeps a fully inherited donor owner without allocating a new Trail. Therefore
ordered-contract inequality did not imply another result-state allocation.

| Consumer | Events | Installed plan | Zero capture allocations | Capture allocations | Capture slot writes |
| --- | ---: | --- | ---: | ---: | ---: |
| 137 | 140 | yes | 120 | 20 | 0 |
| 143 | 13 | yes | 13 | 0 | 0 |
| 103 | 1 | no | 1 | 0 | 0 |

All 154 have observed capture work. The 20 allocating rule-137 events also have
transient, unregistered source frames containing 20 logical slots in aggregate
and zero retained facts. This correlates with ordinary execution but is not an
instrumented direct-completion failure reason. Do not infer the specific stale
receipt or lifetime cause from this correlation alone.

The remaining 134 events already allocate no capture owner; all 154 write no
capture slots. Shared output frames still exist and are not counted as free
physical storage merely because capture moves them without slot writes.

Across all 4,920 completed observations, nonzero immediate capture allocation
is confined to:

| Rule | Observed events | Capture allocations | Capture slot writes | Shared result slots |
| --- | ---: | ---: | ---: | ---: |
| 143 | 220 | 206 | 0 | 660 |
| 55 | 70 | 70 | 70 | 0 |
| 137 | 199 | 26 | 0 | 585 |

These total 302 allocations and 70 slot writes. They exclude publication,
matching, deferred-root materialization, source frame allocation and final live
storage. This is not the whole-egraph memory distribution, nor a speed result.

## Consequence for the next change

Do not add a settled-state runtime cache or claim 154 new owner eliminations.
The existing source/consumer projection machinery already does most of that
work. The remaining target is actual-result ownership: whether the allocations
above retain a second owner for information already accessible from a live Cell,
and what lifetimes require the two to remain separate. Rule 143 dominates the
remaining immediate capture allocations; saturated event frequency alone would
have pointed at a mostly optimized path instead.

Any proposed replacement must preserve returned foreign constructors, receipt
retirement/forwarding, consumer continuation routing, delta ownership and source
Run publication. Closing only the remaining 20 candidate captures cannot by
itself establish large whole-egraph compression.

## Implementation and validation

`Started::remember` returns its existing CaptureWork to the bounded training
archive. No extra fact lookup, binding copy, runtime cache or reverse dependency
was introduced. Observation fields are populated only for retained completed
trace events; disabled or dropped events cannot overwrite another event. An
absent capture observation is reported separately, never interpreted as zero.

This is the actual standalone Cell runtime with the same saved catalog as the
prior settled-state analysis. The diagnostic run passed all 1,428 saved graph
and ordered RHS/write/resume checks. Its final export exactly equals the saved
semantic input; choice diagnosis reports pass. All 149 runtime unit tests and
seven offline analysis tests passed. This commit observes costs, not savings.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/capture-history.json --closure-history 8192
python3 benchmarks/cell-structural-compression/analyze_settled_capture.py out/cell-structural-compression/capture-history.json out/cell-structural-compression/settled-history.json out/cell-structural-compression/closure-existing/program.json benchmarks/cell-structural-compression/settled-capture-results.json
python3 -m unittest discover -s benchmarks/cell-structural-compression -p 'test_settled_*.py'
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/settled-capture-semantic.json
```
