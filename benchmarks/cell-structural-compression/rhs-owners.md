# Existing component reachability of pre-boundary results

Actual standalone Cell runtime, same audited sum-bits program and settings as
`rhs-before.md`. This follow-up records the **pre-operation** resolved receipt,
not just the operation's later return, and snapshots existing owner locations.
It does not change witness demands, keep source frames alive or add execution
subscriptions. All records are behind the existing bounded diagnostic switch.

| Observation | Same Run | Cross Run |
| --- | ---: | ---: |
| Old receipt visible before boundary | 698 | 1,074 |
| Donor has composed owner | 698 | 1,074 |
| Current executing Cell has composed owner | 6 | 10 |
| Current ownership Entry present | 559 | 780 |
| Some current receiver/Entry/query/parent source shares donor component | 62 | **264** |
| No observed same-component source | 636 | **810** |

The observer also finds 1,490/2,110 already retained query witnesses out of
1,703/2,672 query atoms respectively. Missing witnesses remain unknown; absence
of an observed same-component source is not proof that every possible source
lies elsewhere. Entries and query receipts are read as already configured.

All returned non-null receipts in this visible-prior sample equal the checked
pre-operation receipt (689 same-Run and 976 cross-Run). The other 107 boundaries
do not retain a returned receipt. This now distinguishes missing output capture
from an actual different constructor owner, without guessing a producer address.

For each completed Cell require every distinct constructor site to be observed,
successful and reachable from an existing source component. **55 Cells**, including
**49 with a cross-Run donor**, qualify. They still perform 55/49 constructor
requests. Rule counts are 518:20, 58:18, 523:8, 122:4, 522:3, 486:2. Each site is
checked when reached, not all simultaneously at entry; same-component membership
is an address opportunity and not a full-key/effect/visibility certificate.

The diagnostic emits shared pattern candidates keyed by rule, RHS operation,
source kind/atom, shape, source ordinal and donor ordinal/operation. Component IDs
are compared only within a snapshot. An eventual compiler must prove the key
relation from ordinary typed Cell wiring and retain lifecycle guards; trace
frequency cannot substitute for that proof.

## Decision

An existing-component direct path has a concrete bounded opportunity, but it
cannot account for the majority of observed cross-stage reuse or establish the
requested large runtime compression. In particular, optimizing these 49 complete
Cells alone would be another small optimization. Bake must learn which missing
cross-stage connections should share completion state, and charge any added
retained state against eliminated source frames and maintenance. Do not add a
per-producer consumer list or increase every component's frame limit blindly.

The implementation currently creates/extends a composition frame during fact
initialization (`ensure_composition_frame`). An application that only returns
existing constructors therefore need not establish a new component connection.
This explains why counting logical applications or catalog rules overstates
runtime completion connectivity; it is not by itself proof that recording every
such application would save memory.

All 1,428 saved Run graph and ordered RHS/write/resume checks pass. Final graph,
Graph work and source storage equal the unobserved control; the saved semantic
export is identical and choice diagnosis passes. No memory/speedup claim. The
four offline tests check full constructor-site coverage and distinguish an anchor from an uncreated receiver, identical
shape IDs in different components, and a missing pre-operation receipt.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/rhs-owner-audit.json --natural --shared-owners --parent-takeover --port-domains-only --rhs-projection-trace
python3 benchmarks/cell-structural-compression/analyze_rhs_owners.py out/cell-structural-compression/rhs-owner-audit.json benchmarks/cell-structural-compression/rhs-owner-results.json out/cell-structural-compression/domain-classes-derived-audit.json
python3 benchmarks/cell-structural-compression/test_rhs_owners.py
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/rhs-owner-semantic.json
```
