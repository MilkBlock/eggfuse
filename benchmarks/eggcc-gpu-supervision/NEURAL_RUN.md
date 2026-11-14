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

## Full Run audit and schedule gate

`audit_neural_run.audit` independently executes every original rule against
the supervisor's pre-Run reference graph, with all matches before effects.
It compares the complete expected output with slot-backed GPU facts and Eq
roots. This catches omitted proposals, which replaying only accepted GPU
instances cannot catch. Expected values are never injected into GPU state.

`run_done` requires full graph agreement, decoded coverage, query exhaustion
and no budget/attention condition. `run_changed` is derived from reference
constructor/union effects only after a passing audit; logical matches and token
admissions are reported separately. The supervisor must not advance its
reference or schedule on failure. Tests connect this gate to the existing
`device_schedule.tick`: two different stages directly share GPU state, and a
silent model cannot advance the schedule. This test uses a synchronous CPU
verdict; it does not establish asynchronous multi-stage production execution.

The actual canon-template audit is available via `audit_neural_gpu_rhs.py`
with `--sealed-run-attempts 8 --follow --interface-only --eq-readout WEIGHTS`
and optional `--witness-context-depth 1`, separately from cumulative mode.
The 61 selected synthetic entries give 60 passing first Runs. Pair (7,6)
passes with 6 admitted instances and 33 final facts. Pair (5,7) now exposes a
distinct first-Run failure: after 3 admissions a token-refresh condition stops
execution; full graph comparison finds inconsistent result classes and missing
facts. This is not explained away by that input's later productive expansion.
Its `run_done` remains false. The overall report remains `difference`.

`sealed-run-results.json` retains the results. CPU audit time totals about
0.245 seconds across the 61 cases, a diagnostic measurement rather than a
speedup comparison. Original full Eggcc schedule execution, asynchronous audit
epochs/recovery and wider model coverage remain outstanding.

## Captured floating-state readout calibration

Admission diagnosis retains selected Eq scores and result roots, then labels
legal admitted inputs by independent CPU effects after execution. It stops
identity propagation at the first incorrect installed frame. The (5,7) failure
starts at its third admission: rule 7 predicts slots (0,10), LessEq and Add,
equal with score +0.644. Two other wrong pairs follow transitively. The first
two admitted frames have correct local Eq relations.

`--capture-sealed OUTPUT.npz` saves only synthetic post-run floating tokens,
requests and independent Eq labels; it supplies no correction to execution.
`fit_sealed_readout.py CAPTURE OLD_EQ_WEIGHTS OUTPUT.json --steps 300` freezes
the token generator and fits the Eq head to this covered execution set. Input
manifest and weight hashes are checked. This is training-set fitting, not a
claim of held-out generalization. Binary datasets/weights live in the external
artifact archive, not Git.

The first captured set contains 215 states. Exact Eq states improve from
207 to 215, with zero false or missed pairs on those captured inputs. Re-running
all 61 first Runs with the resulting head passes all 61 and the complete
first-Run audit reports `pass`, with 216 actual admissions. Subsequent recurrent
and larger finite-domain checks are required before promoting this candidate.
`audit_finite_readout.py` compares old and new heads on the same generated
finite-domain tokens without retraining either head.

The recurrent check retains 61 correct final graphs and 60 verified fixed
points; (5,7) is still productive at the twelve-sweep boundary. However, the
larger finite-domain regression rejects this head: exact states fall from
4,170/4,258 to 3,809/4,258, and 411 states acquire false merges (previously zero).
Therefore this candidate is **not promoted**, despite the 61/61 first-Run pass.
The next fitting dataset must jointly retain finite-domain and resident-token
states; this result demonstrates forgetting of already covered inputs, not a
need to optimize for arbitrary unseen programs. See
`sealed-calibration-results.json` for all three evaluation scopes and hashes.
