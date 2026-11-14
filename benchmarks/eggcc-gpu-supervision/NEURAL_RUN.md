# Sealed source-Run query input

`device_neural_run.execute` is a standalone GPU execution building block for
the existing `device_schedule` control representation. It does not introduce
a second source schedule or claim native Eggcc execution.

The prior cumulative experiment queries the evolving state after every
admission. That is useful for one monotone saturation experiment, but does not
preserve a source Run's requirement to match before applying its effects.
The new path seals the input Cell state for all queries of one Run. Each
admission still writes to the evolving state and checks current source
lifetimes and constructor witnesses. A following Run seals that resulting
state, keeping the same tokens, stable slots and source-context references.
No CPU bindings or graph re-import occur between these calls.

The plan supplies the original rule order and stable rule IDs. A fixed attempt
budget is used per rule, with device masks suppressing further admissions once
its snapshot candidates are exhausted. If a rule exhausts its budget or needs
attention, later rules are not admitted out of order. There are no intermediate
host reads of candidate values; MLX evaluation still synchronizes allocations.
This is not a fused GPU kernel or an efficiency result.

The returned `query_exhausted` is deliberately not `run_done` or a saturation
certificate. Exact completion, stage-boundary verification, model compatibility
across rulesets, and the existing source schedule remain outstanding. In
particular, `admitted` counts actual token instances, not necessarily new
logical facts; it must not be passed blindly as `run_changed` to the schedule.
The path currently supports the same constructor/copy/union/set-lowering subset
as speculative frames, not arbitrary mutable effects.

Validation uses actual MLX calls and slot-backed facts:

- Run one applies `F -> G`; its later `G -> H` rule sees no new G yet.
- Run two directly consumes the retained G Cell and produces H.
- Run three admits no new instance.
- Disabled and budget-exhausted runs cannot claim query exhaustion.
- Single-step tests independently check the same visibility boundary.

These synthetic checks are not full Eggcc multi-stage acceptance. The old
cumulative benchmark remains explicitly separate and unchanged by default.
