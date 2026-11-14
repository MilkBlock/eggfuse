# Share boundary float preparation within a GPU query batch

`run_round` evaluates all candidate rules on the same pre-commit state. Previously
each rule separately encoded that boundary, including token/role matmuls and shared
Eq-root propagation. The raw-context and shared-context encoders also separately
formed the same initial per-port messages.

Bake now groups plans whose boundary encoder fields are exactly identical, apart
from query port indices and port sorts. The identity includes roles, types,
weights, width, propagation modes and root capacities. Shared-context and
raw-only modes do not mix. This happens on host arrays before the single final
device upload; obsolete uploads of intermediate plans were removed.

The raw encoder exposes `prepare`, and the shared encoder consumes those same
messages before preparing propagated messages. Query-specific masks, pooling,
matching and predictions are evaluated separately. A call-local dictionary during
graph construction shares tensor expressions for each group, not a new GPU fact
registry. Every `run_round` starts fresh from its own state argument. No cache
crosses a Run, ownership transfer, visibility change or commit boundary, so no new
invalidation or reverse-dependency maintenance is required. Groups are a static
compiler decision, with no data-dependent GPU control branch.

Ungrouped callers remain supported. Even within one proposal, the two encoders
reuse their common initial messages. Grouping across proposals removes repeated
preparation without evaluating unused boundary paths eagerly. Shared intermediates
live until the batch consumes them; runtime memory and speed benefits have not
been measured. Captures still include their per-query boundary observations.

Tests verify exact grouping except for query ports, rejection of differing
weights, two preparations becoming one for compatible queries, fresh preparation
on a later call, equality of complete outputs/captures, and compiled GPU parity.
Existing context/mean/scatter/invalid-root, classifier and normalized-head tests
also pass: 43 tests in total.

Actual GCD uses one group for three rule plans. The graph and independent label
audits pass. It still produces 41 Cells, releases 33 owners, and has Run changes
`[true,true,false]`. Predicted tokens, targets, target Eq classes, rules and source
origin arrays are identical to the preceding captured run; feature differences
are at most 3.58e-7. Prediction correctness remains 36/41. This is not evidence of
end-to-end throughput improvement or full Eggcc coverage.

The first run failed only when writing the report because a later capture loop
shadowed the plan variable; it produced no accepted artifact. The counter is now
computed at compilation and the run was repeated successfully. That failed log is
retained. Exact runtime/label commands and successful captures are
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/matched-entry-gpu-v1/gcd-shared-boundary-*`.
Tracked evidence: `shared-boundary-results.json`.
