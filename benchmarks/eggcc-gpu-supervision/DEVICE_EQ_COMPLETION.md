# Bounded GPU union and congruence completion

`device_eq_completion.py` adds an exact, bounded Eq completion primitive over
resident Cell witness views. It replaces the assumption of already settled Eq in
its integration tests. It is not a fast full-runtime implementation, neural
inference, or proof that a whole source stage is saturated.

## Execution

Typed union operands are collected from current Cell effect slots when their
source effect position is due. Invalid IDs, unequal Eq sorts, missing arguments
and invalid starting labels cannot authorize completion. The prototype uses a
reserved dense identity range and monotonically decreasing representative labels.
New identity allocation must also initialize its sort/partition registry; that
full allocator integration is still required by the runtime.

Each static GPU round applies explicit unions, refreshes Cell `slot_roots`,
projects constructor witnesses, and derives result equalities when all corresponding
key fields agree. Multi-argument constructors require every field, never a digest
or one matching input. Subsequent rounds propagate these result equalities through
other constructor relations. Stable actual identities in `slots` are unchanged.
No reverse consumer index or canonical-key rewrite is introduced.

All loops build a fixed device graph; no round reads labels or a stopping decision
on CPU. A round limit is a budget. Settlement requires a final unchanged round,
valid identity/sort state and complete supplied witness coverage. Exhaustion,
invalid input or missing view coverage leaves attention/pending flags. Unknown
external constructors cannot be ignored. This is closure relative to the supplied
complete snapshot and plans, not an automatic proof that those plans cover a real
Eggcc stage.

Only after closure can a collected union advance its source effect position.
Other effects remain pending. A query match, proposed union, or partly updated
root array never counts as a committed source RHS. The outer controller must also
respect missing union operands, unresolved effects and source Run visibility.

## Floating token invalidation

Root changes mark affected Cells `token_dirty`. Existing floating payloads are
not silently treated as representations of the new Eq state. Token admission
rejects a dirty source and keeps attention pending even when no successor is
admitted. Exact Eq settlement and numerical token refresh are separate obligations.
No learned refresh adapter is implemented in this change; adding it is necessary
before these Cells can resume dense-float continuation autonomously.

## Verification

The Metal test performs an explicit input union, propagates congruence through
F and G views, and then reuses the existing G result rather than allocating a new
identity. Another compiled test gathers a union directly from source effect slots,
completes it, and advances the effect only after closure. A one-round budget leaves
the same source pending. CPU values are inspected only after the compiled call.

Additional tests cover multi-argument all-condition gating, unequal sorts,
invalid identities, missing external coverage, preserved raw slots, dirty-token
rejection, and ten deterministic random union graphs checked against an independent
CPU union reference. These do not establish broad Eggcc semantic acceptance.
The related suite totals 47 passing tests.

Recipe-only lowering of dot-product finds 52 slot-based typed union sites and no
unsupported union operand syntax. This does not establish runtime coverage of
constructors, scalar/mutable effects or the witness universe. Exact source hash
is in `device-union-sites-results.json`.

## Costs and remaining boundaries

This implementation allocates dense identity x union-pair comparisons and
witness x witness congruence conditions. Repeated fixed rounds may perform much
more work than necessary. It is a bounded correctness path, not evidence of
neural-style efficiency or a GPU speedup. The global identity/sort arrays, root
slots and temporary comparisons are new costs, not free Bake information.
Scalar slots must be excluded by the compiled Eq-slot mask. Non-minimal native
representatives need a validated import into the minimum-label convention.

The floating model, actual initial graph import, complete witness bootstrap,
mutations/deletion, multi-source matching, legal stage advancement and full
ownership transfer remain unfinished. The exact completion result cannot alone
supply their certificates. No performance benchmark or native acceptance run was
performed.

## Latest Bake reference

Reference branch is `573903e5`. Its port takeover census now joins candidate
ports to live facts and lifecycle exceptions. A single receiver is insufficient
for ownership; shared producers must preserve one authoritative fact identity and
static projections of internal relations. This supports keeping actual IDs stable
while updating Eq roots, but supplies no GPU ownership proof by itself. No native
code was merged.

Reproduce with the NumPy/MLX environment:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_device_eq_completion test_device_witness_views test_device_constructor_results \
  test_context_effect_projection test_device_alias_completion test_lower_device_entries \
  test_device_token_commit test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/device_eq_completion.py TRACE OUTPUT.json
```
