# Integrate original-workload iterative Bake into worker continuation

Merge the complete committed `codex/cell-parallel-admission` lineage through
`d911ff49`, which contains the user-specified `d0d8ee33`, into
`codex/cell-result-routing` after `2fcb9c56`. Seven non-merge commits since the
previous integration bring original-workload observation/selection, optional
diagnostic apply receipts, admitted context-plan storage, and physical pooling
of newly completed short compositions. This is a full branch integration, not
selected cherry-picks; the other worktree's uncommitted files are untouched.

No manual conflict resolution was needed. Worker chunk selection and the
actual-witness prefix layout are preserved. Job 315 passes 152 compiler
integration tests (including 70 ownership tests), two selector tests, 233
runtime tests, the no-default runtime compile, and 48 experiment-script tests.
The pooled-owner test performs union, deletion and regeneration after sharing
storage, rather than checking final size alone.

The incoming original-workload round-one/round-two programs have the same
`source_core` as the ordinary performance input. `multi_stage` metadata differs
and a checked ownership-fragment catalog is added; therefore their own Run and
worker execution checks are still required before crediting those compositions
to the ordinary performance lane. They are distinct from the previously timed
882-Run learned artifact. Incoming memory savings and sequential source audits
do not prove worker speed or saturated-RHS execution.

The next useful takeover is to feed that actual 1,428-Run composition evidence
into worker continuation and identify the retained query/result/publication work
inside admitted combinations. Source order, visibility, delta ownership,
mutable effects and returned-witness lifecycle remain authoritative. Do not add
the incoming component/storage savings to the 558 existing witness hits as if
they measured the same input or eliminated the same operations.

Post-merge frozen workload validation and timing will be recorded below. Prior
chunk results belong to `364d9a91`, not automatically to this merge.
