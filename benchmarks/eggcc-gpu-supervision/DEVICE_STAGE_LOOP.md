# Bounded device loop over explicitly covered stages

`device_stage_loop.run` combines bootstrap completion, snapshot Entry matching,
joint admission, ordered effect completion and token refresh. A device stage
cursor advances only on a quiet round with no new tokens, no executed effects,
no refreshed tokens, no query/admission failures, no pending completion, settled
Eq, complete external coverage and explicit query coverage for that stage.
Capacity failure or round-budget exhaustion cannot manufacture a fixed point.

The fixed Python round loop unrolls GPU dataflow; stage cursor decisions use
array masks. There are no host reads between rounds. Completed schedules stop
admitting matches and preserve state for remaining budget lanes. This still
computes masked work and is not claimed efficient. The controller's `finished`
means only the supplied covered stage list completed, not that it independently
proved whole-program semantics.

`compile_controls` takes existing lowering coverage, which currently has
`closure_authorized=False`. Therefore controls generated from real current
catalogs cannot advance a stage. A true coverage vector in a test is an explicit
local-family assumption; it must not be used as an inferred real-workload proof.
The controller does not perform CPU auditing, validate arbitrary supplied proof
bits, implement rollback or prove ownership transfer.

## Tests and limits

78 mechanism tests pass. A two-stage local GPU fixture produces counts
[1, 0, 1, 0, 0] with stage history [0, 0, 1, 1, -1], executes actual constructor
effects, and retains actual result IDs. It receives no intermediate CPU bindings.
The fixture explicitly assigns its compiled Entry blocks to two stages and
assumes complete enumeration of its tiny family. It does not demonstrate current
cross-stage lowering or Eggcc schedule translation. Tests also verify that real
lowering controls remain blocked after zero-new rounds, and capacity, external
boundary and budget failures prevent advancement.

The saved dot-product recipe stores its schedule under `control`, not `schedule`.
It contains nested `sequence`, `repeat` and `saturate` forms, including nested
saturation around type helpers and outer multi-ruleset saturation. Flattening
these into independent saturated rulesets changes semantics. This initial flat
controller must be extended with the actual compiled control structure and the
outer loop's accumulated change condition; it is not yet that implementation.
Original Run visibility, effect order and residual matching obligations remain.

Reference Bake tip `9ee7070d` retains only admitted executable context cuts while
preserving residual enumeration. The corresponding GPU lesson is to compile
covered control/execution blocks without falsely discarding uncovered work.
This commit adds no new instance binding graph or apply log, but it does not yet
remove the CPU runtime's full matching/scheduling path. No actual Eggcc runtime,
speedup, prediction-accuracy or ownership-completion claim is made.
