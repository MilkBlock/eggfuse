# Device-resident token admission and continuation ownership

This is a bounded numerical GPU kernel, not the completed Eggcc GPU runtime.
`device_token_commit.py` adds device-side proposal generation for a restricted
closed-entry layout and device-side admission, duplicate elimination and activation
ownership replacement. No performance or native semantic acceptance is claimed.

## What executes on device

`closed_entry_proposals` enumerates the fixed capacity x compiled-entry tensor.
It matches current semantic template IDs, active/present state and stage, projects
exact boundary keys, and computes floating successor payloads with a batched
matrix multiplication and tanh. Success masks are not supplied separately by CPU.
Changing the initial template changes which continuation executes. Static candidate
shape does not contain a precomputed successful dynamic route.

`commit` validates current source visibility, activity, generation, settlement and
finite payload. It compares exact integer semantic keys with retained keys and
with earlier eligible candidates. Prefix ranks assign novel candidates to free
rows. It never compares dense floating vectors to prove semantic equality.
Candidates that cannot fit produce capacity marks and cannot retire their source.

A compiled transfer-coverage flag is necessary but insufficient: activation
ownership is moved only for a uniquely eligible successor of a settled source
without outstanding readers, after admission succeeds. Multiple candidate readers
keep the source active. The source retains its semantic key and payload, while
its continuation ownership bit becomes inactive. Old key retention suppresses
repeated derivations. New token completion is explicit; it is not inherited from
float similarity. An unsettled source cannot activate a proven closed successor.

This is an **activation responsibility transfer**, not payload reclamation, not
exclusive ownership of all future rule activations, and not the native full
ownership-transfer contract. The caller must provide a valid complete-query and
transfer-coverage proof. Neither kernel may invent these bits from observations.
The current entry generator only supports input-key projections and fixed boundary
widths; constructed-result keys, literals, multi-source joins, mutable reads and
external Eq updates require further lowering. Test float maps are fixed matrices,
not a newly trained ridge model. The earlier trained model is not yet integrated.

## Checks performed

Five tests exercise duplicate proposals, repeated derived keys, stale generations,
invalid indices, invisible sources, nonfinite proposals, capacity exhaustion,
unsettled source completion, readers, missing transfer coverage and competition.

Two tests execute through MLX Metal:

- Four rounds inside one compiled invocation produce accepted counts `[1,1,0,0]`
  and move the active owner through two successor templates. Changing the initial
  template changes the generated path. Wrong stage yields no candidates.
- Two successive floating transforms consume prior GPU state without an intermediate
  host read. Final GPU arrays match a NumPy reference; changing initial floats
  changes the second successor's payload. This proves numeric device dependence,
  not graph semantic correctness.

Together with continuation catalog tests, 14 tests pass. Only after the full
compiled invocation do tests read masks and payloads on CPU. Static Python
unrolling builds the graph; no per-round success-dependent Python branch is used.

`no_new_admission` means precisely that; it is not named saturation.
`needs_attention` preserves stale/nonfinite/unsettled/capacity failures even when
no candidate is admitted. The outer stage controller must also know coverage,
pending effects, novel external Eq facts and completion obligations before advancing.

## Costs and boundaries

The current exact duplicate checks allocate proposal x capacity and proposal x
proposal comparisons. This is deliberately bounded and is **not** a scalable
large-Eggcc solution or an efficient neural-style matrix substitute. Physical
payload arrays are functional snapshots, and retired rows are not reclaimed.
No saved-bytes or speedup claim follows from clearing an activation bit. A real
runtime must charge these arrays and lower static candidate groups to avoid global
pairwise comparisons; it also needs growth, generation-safe reuse and late updates.

Next connect the existing `cell-continuation-contract/v1` compiler output to this
layout with explicit rejection of unsupported projections and effects. Then
integrate actual returned witness slots and learned float completion, rather than
claiming this manually assembled test plan represents full Eggcc. Multi-source
matching and legal cross-stage fixed-point control remain required by the goal.

Reference Bake branch now ends at `731188d2` (via `43cd9e07`, `794a2afd`). It exposes
source-owned fields through the parallel CLI; checked Entry address/lifetime rules
still apply. No native branch code has been merged here.

Reproduce with the NumPy/MLX Python environment:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_device_token_commit test_continuation_contract test_cell_token_successors
```
