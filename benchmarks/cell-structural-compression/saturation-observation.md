# Observing saturated Cell RHS coverage

The installed-catalog observer now visits the common Cell execution entry,
before RHS preparation and effects. The earlier observer only visited unmatched
owned births, missing applications whose constructors were all reused.
Ordinary and batched execution use this entry; a pending peer prevents a
coverage claim. Observation is disabled unless catalog tracing was requested.

Each application contributes once to a `(rule, shape, cross_epoch, outcome)`
aggregate. Available query receipts identify candidate live components.
Alternative components do not multiply application counts. `cross_epoch` means
the chosen component contains an earlier-epoch frame, not a proof that a
particular witness crossed a ruleset boundary.

For each candidate, the observer starts with only the current matched inputs,
excluding prepared RHS results, and checks the ordinary source operations:

- Copy projects an already known operand.
- An immutable constructor must have a visible, owned, live fact with equal
  canonical inputs inside this component; its actual result feeds later ops.
- Union is covered only if both current equality operands are already equal.
- Missing constructors, nontrivial union, mutable reads, scalar primitives
  without a supported proof, writes, visibility changes and failure effects
  stop the proof and retain a distinct reason.
- Outstanding ownership completion or queued peer work blocks the proof.

The longest proved prefix is recorded when no whole RHS is covered. Inputs
alone can prove a copy/trivial-union RHS, reported separately from a component
witness. No new runtime fact graph, subscriptions or source-history copies are
kept. Temporary proof bindings and local fact scans belong only to this
diagnostic; component and fact checks report its extra work.

`rhs_covered` is a smooth-rule **candidate for this matched application**, not a
claim that the whole Cell is saturated for every possible input. Whole-rule
skipping still needs compiled entry coverage, delta/visibility ownership,
future invalidation and ordered-effect audit handling. Unsupported cases are
unknown, not proven coarse rules. Query atom counts and covered prefix lengths
are workload opportunities, never saved operations. This change skips no work.

Reproduce against saved original Run graph/RHS/write/resume checks:

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/baked-lean/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/saturation-current.json
python3 benchmarks/cell-structural-compression/analyze_saturation.py out/cell-structural-compression/saturation-current.json benchmarks/cell-structural-compression/saturation-results.json
```

This measures the actual standalone Cell runtime, not native egglog. It is an
instrumented semantic/workload observation, not a timing or compression result.
The focused tests cover birth-free constructor reuse, input-only trivial union,
new constructors, unsupported writes and a nontrivial union that must execute.

## Audited sum-bits observation

All 1,428 saved Run graph and ordered RHS/write/resume checks pass; specified
native-choice semantic acceptance is `pass`. Of 7,265 observed applications,
151 have whole RHS coverage from a local Cell component (250 RHS operations),
and 222 are covered by current inputs alone (638 operations). These 373
candidates are not eliminated rule executions. The local witnesses all reside
in components containing an earlier-epoch frame.

The leading unresolved frontiers are 4,569 applications missing a local
constructor witness, 1,703 blocked by writes, 358 by unsupported primitive proof,
157 by nontrivial union, 75 by visibility effects, and 30 without a usable local
component. A missing local witness does not prove a new constructor is needed:
it may live outside the selected component or need a larger saturated template.
The next Bake analysis must distinguish those cases before calling them coarse.

Observation itself made 10,654 component checks and 118,826 fact checks. This
scanner is intentionally not a proposed runtime fast path. Reusable skip guards
must be compiled from shared Cell wiring. No speed or memory benefit is claimed.

Validation also passes 30 ownership integration tests plus the added focused
nontrivial-union test, 85 default runtime tests, and all-feature runtime checking.
The saturation change is independent of the previously uncommitted borrowed
field-layout experiment present in the measured working tree; those storage
changes are not part of this feature's commit or claimed benefit.
