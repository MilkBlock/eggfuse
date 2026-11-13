# Grow the executed Raytrace catalog without activating more rules

The first 32-transition catalog removed 12,123 binding creations, but enabled
109,985 ownership Entries, 273,448 Entry reads and 88,235 actual-result writes.
It left 132,376 transition probes without an installed continuation. This
iteration learns from that catalog's own audited execution instead of adding
more rules with uncharged activation costs.

`extend_observed_owners --reuse-activation` takes two masks from the typed seed:
rules with active composition Entries and rules capturing RHS results. Every
hop in a proposed path must fit those existing masks. An already active rule
does not authorize new result capture. After selection, the Program loader
rechecks typed wiring, all old transitions must still exist, and both compiled
masks must remain exactly equal to the seed. This is a selection constraint;
larger dispatch tables, more shapes and actual execution work still cost time.
It is not a calibrated time model or a proof of a speedup.

The default selector is preserved. Four selector tests pass (job 381), including
rejection of a high-scoring new rule, new result capture on an active rule, and
an inactive intermediate hop followed by an active final hop. The installed
seed paths remain covered. The full source/catalog binding checks still apply.

## Actual iteration and validation

Job 382 selects 32 additional paths from the previous catalog's 13,002 proposals.
Twenty replace shorter seed prefixes, leaving **44 maximal paths and 64 checked
transitions**, with 418 shapes. Four examined proposals are skipped by the new
activation constraint before the 32-addition budget is reached; that is not a
count of all ineligible proposals in the trace. Exactly 18 Entry rules and six
result-capture rules remain enabled.

The candidate's full graph, ordered bindings and source summaries match the
seed at each of the 128 audited Run boundaries. Both complete Programs then
run on the same frozen `451058f3` four-worker runtime and preserve the previously
validated Raytrace final state, all 16,883 Run summaries and logical effects.
The checker now accepts a learned control Program only when it also preserves
the original accepted source definitions. The prefix stays explicitly bounded;
this is differential acceptance, not native Raytrace proof or full-program
per-Run graph coverage.

## Work on complete Raytrace

| Counter | 32 transitions | 64 transitions |
| --- | ---: | ---: |
| Ownership Entries | 109,985 | 109,985 |
| Actual-result writes | 88,235 | 88,235 |
| Entry reads | 273,448 | 272,276 |
| Transition probes | 143,571 | 142,399 |
| Unbaked fallbacks | 132,376 | 127,849 |
| Successful composed instances | 11,195 | 14,550 |
| Cross-Run joins | 10,841 | 14,069 |
| Signal bindings created | 2,139,542 | 2,136,133 |
| Boundary registration attempts | 1,827,856 | 1,824,310 |
| Static signal steps visited | 587,369 | 588,327 |
| Key lookups | 4,332,972 | 4,332,972 |

There are 3,355 more actual composed instances, 3,409 fewer binding creations
and 3,546 fewer registrations. Added static signal visits remain charged.
Bindings, incidences and handoffs are not counted as the same saving multiple
times. Original Run visibility, source order, actual foreign witnesses,
residual matching, mutable effects and native Eq addressing remain live.
This iteration does not remove a new query or enlarge worker mutation scope.

## Sequential timing

Job 385 takes one timing lease and finishes the entire no-catalog lane, then
the entire 32-transition lane, then the entire 64-transition lane. Each has one
warmup and three measured samples; all 30 process-boundary guards pass. The
binary is identical for all lanes.

| Median | No catalog | 32 transitions | 64 transitions |
| --- | ---: | ---: | ---: |
| Inference | 5.166448 s | 4.757945 s | 4.732102 s |
| Load | 411.561 ms | 475.107 ms | 474.488 ms |
| Whole process | 7.726055 s | 7.315490 s | 7.291990 s |

The no-catalog samples descend **5.649307, 5.166448, 4.764568 s**. That visible
instability makes the arithmetic 8.41% candidate/reference difference unsuitable
as a speedup claim. No samples are removed or replaced by a rerun. The newer
catalog is 0.54% faster in inference and 0.32% faster in process median than the
seed in this short trial; neither establishes a stable end-to-end advantage.
It remains an experimental artifact, not the default Raytrace Program.

The policy successfully bounds rule/result activation while increasing actual
reuse, but the benefit is small relative to the complete execution. The next
target is the **2,127 witness recipes** observed in the new catalog, of which
1,041 name already active receiver rules. They are candidate routes, not proven
query savings. Typed key proof and runtime lifetime/visibility checks must still
authorize each reuse, and all extra route selection work must be charged. The
goal is to reduce the unchanged 4.33 million key lookups, not merely grow the
composition-hit counter.

## Reproduce

Use the shared compute queue for builds, selection and validation; use one
timing lease for the final command. Build/freeze the updated selector with
`iterative-bake,cell-absorption,view-ports,parallel-publication`. The audited
prefix tool and measured runtime are the same frozen binaries as the previous
iteration.

```sh
extend_observed_owners round1/program.json round1-prefix128/trace.json \
  32 round2 --reuse-activation
worker_prefix_catalog_trace round2/program.json 128 round2-prefix128
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py check ACCEPTED_RUNTIME \
  round1-prefix128 round2/program.json round2-prefix128 round2-full \
  --control-program round1/program.json
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py time \
  round2-full round2-timing --repeats 3 --original-validated round1-full
```

Large files remain on the external disk in worktree 3063's
`out/cell-bake-routing-refresh/raytrace-prefix-learning`. Exact identities,
checks, work deltas and all timing samples are in `raytrace-activation-reuse.json`.
