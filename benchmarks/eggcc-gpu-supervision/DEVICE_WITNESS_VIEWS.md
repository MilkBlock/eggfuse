# Constructor witnesses projected from resident GPU Cells

The result resolver no longer needs a manually prepared witness list in its
resident-Cell integration test. `device_witness_views.py` compiles template
occurrences and projects transient views directly from Cell slots on GPU.
No persistent constructor registry, copied fact store or consumer list is added.

## Projection contract

For each requested table/arity, Bake records constructor query occurrences and
constructor/set result occurrences, their source rule, field slots, effect
completion position and first later overwrite. At runtime, matching visible,
present source Cells contribute an occurrence only after its producing effect
has completed (query occurrences require the established initial match).

An inactive continuation owner may still hold a live fact and remains eligible.
Invisible sources do not contribute. Missing slots, unsupported literal operands
or overwritten source fields do **not** mean the fact is absent: they invalidate
the view-completeness flag, preventing constructor allocation. Original input
bindings lost by overwrite are not recovered from an invented history.

The view additionally requires explicit external-coverage and settled-Eq
premises from the surrounding runtime. The current tests use closed snapshots.
They do not prove these premises for a real Eggcc graph; independent fact
retirement/deletion and nonresident initial facts still need integration. A Cell's
visibility flag alone is not a general per-fact lifecycle certificate.

## Stable identities versus equality roots

Optional `slot_roots` stores current representative values separately from actual
returned witness identities in `slots`. Keys use current argument roots; result
reuse returns the actual witness identity and its current root separately. New
identities initially root to themselves. Without this array, the caller must
supply already representative-valued slots in the frozen snapshot.

Root values are propagated with actual values through constructor execution,
compiled consumer projection, context completion and alias completion. Admission
rejects proposals that would lose an existing authoritative root-slot layout.
This is metadata plumbing, not a union algorithm: no code here computes root
updates or validates a claimed settled-Eq boundary. The extra array is a charged
prototype cost, not an additional semantic fact graph or memory-saving claim.

## GPU evidence

A first Cell produces F(7) with fresh ID 100. Its result remains in its own slot.
A later Cell activates, projects all relevant resident witnesses on GPU and
requests F(7); it receives ID 100 without increasing the allocator. Both steps
execute inside one compiled invocation with no intermediate CPU read. The later
source need not share the first source's activation ownership.

Additional tests cover missing/overwritten slots, unsupported literal occurrences,
inactive versus hidden sources, external coverage gaps, unsettled Eq and distinct
raw witness/current-root values. A context completion test verifies actual ID 999
and current root 11 both survive the consumer projection. The related suite has
39 passing tests, including Metal execution. No end-to-end Eggcc runtime or native
semantic acceptance is claimed.

## Static recipe inventory and costs

For the unchanged dot-product recipe, constructor sites request 138 table/arity
layouts. They contain 2,732 occurrence records, of which 2,565 have supported
slot projections and 167 require unsupported handling. Static arrays total
78,540 bytes. These counts do not establish dynamic view completeness: only
currently existent occurrences require coverage, and nonresident facts remain
an explicit obligation. Exact source hash is in `device-witness-layout-results.json`.

Projection currently materializes capacity x occurrence arrays; resolution still
performs pairwise comparisons. No speedup, GPU memory saving or large-workload
suitability follows. The data is reconstructed from authoritative slots each
request, and the cost must be reduced with proven template grouping/shared slices,
not by silently omitting foreign or overwritten witnesses.

## Bake reference update

Reference branch is `566923cc`, `closure-frontier.md`. Its observed cross-component
provenance is shared, not an ownership tree; a few sources have large fan-out,
while some individual port slices have a single receiver. It recommends separating
shared boundary inputs from owned completion suffixes. GPU source deactivation
therefore must not remove shared witness visibility, and a candidate that allocated
a result first does not acquire exclusive ownership of all its consumers. Current
real-catalog transfer flags remain conservative; no native branch merge occurred.

## Reproduce and next work

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_device_witness_views test_device_constructor_results \
  test_context_effect_projection test_device_alias_completion \
  test_lower_device_entries test_device_token_commit \
  test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/device_witness_views.py TRACE OUTPUT.json
```

Next integrate these views with actual initial-state bootstrap and a stage
controller that preserves unknown coverage, then implement Eq completion rather
than assuming settled roots. Copy/literal/scalar/mutable effects, multi-source
matching, complete ownership transfer and autonomous cross-stage fixed points
remain part of the unfinished target. The float/ridge Cell-state path is still
not the full device execution state in these mechanism tests.
