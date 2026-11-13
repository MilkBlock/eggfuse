# Cross-stage admission audit

The existing final topology had many single-frame components, but it did not
explain their histories. The installed-catalog observer now records each newly
created composition frame and the attempted Entry alternatives, grouped by
consumer rule and template. This is opt-in diagnostic state, not a second
runtime fact graph or an instance-to-consumer index.

Frame counters partition births into joined and fallback. `joined_cross_stage`
is a subset of joined. Anchor attempts partition into non-fact, no longer owned,
missing source frame, frame limit, source order, missing compiled transition,
and successful join. Alternative counts must not be summed as saved instances.
`no_entry` and `entry_template_mismatch` describe frame entry context, not anchor
attempts. Initial frames created before tracing are outside this observation.
A later retirement or extension may change the final topology; these events are
not an attribution of final singletons.

The previous trace recorded proposed typed extensions only after filtering
anchors. It could not distinguish unavailable transitions from earlier runtime
rejections. These new reasons make that distinction without weakening checks.
No typed equality, mutable-read, source-order, visibility or residual matching
obligation is discharged by recording a failed admission.

## Validation

All 55 ownership integration tests pass. The bounded longer-catalog test compares
traced/untraced state, actual RHS/write/resume audits and instance inventory at
each Run. It additionally checks the birth/anchor partitions, cross-stage joins,
frame-limit rejection and agreement with existing transition counters. A first
assertion expecting initial births with no Entry was removed: initialization
precedes explicit tracing in that fixture, so that expectation was incorrect.

The batch replay uses unchanged `witness-multi` candidates copied into a fresh
`admission-audit` output variant. Its saved per-Run graph/effect checks and terminal
check are authoritative; it is not native egglog acceptance or a speed test.
The first replay was intentionally stopped after discovering that the minimal
witness exporter discarded the new fields. The exporter now preserves admissions
alongside saturation, and only the subsequent completed replay is summarized.

Reproduce after building `batch_cell_learning` with
`iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit`:

```sh
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch admission-audit witness-trace
python3 benchmarks/cell-bake-owner-merge/admission_results.py out/cell-bake-owner-merge/batch/admission-audit benchmarks/cell-bake-owner-merge/admission-results.json
```

The next iteration should rank the absent compiled transitions from successful
matched Entry anchors and their actual typed candidate proposals. Prefer reusable
short continuations before raising the maximum history length. A missing
transition alone does not prove a valid substitution, an entire saturated RHS,
or net storage savings; actual result ownership and restoration boundaries remain
necessary. Frame and port directory compression remains the objective, not making
the admission counter green.

## Completed batch result

All 2,652 saved Run checks and four terminal checks pass. Results describe the
frozen diagnostic binary built for this audit; concurrent query-worker edits in
the shared working tree are not included in this commit or its validation claim.

| case | new frames | joined across stages | fallback frames | missing-transition anchor attempts | frame-limit attempts |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 670 | 291 | 379 | 844 | 0 |
| loopfact | 581 | 243 | 338 | 778 | 0 |
| sum-bits | 2,557 | 1,099 | 1,458 | 3,468 | 56 |
| dot-product | 2,240 | 973 | 1,267 | 3,114 | 79 |

There are 10,945 total anchor attempts: 8,204 miss a compiled transition, 135
hit the frame bound, and 2,606 join. None in this batch reject a non-fact anchor,
non-owned fact, missing frame, or source order. Another 293 frame births have a
mismatched Entry template and nine have no Entry; those are outside anchor
attempts. The report includes the leading missing-transition rules separately
for each workload. These observations favor learning missing checked short
transitions over globally raising the frame limit. They do not yet prove a
compression gain or that all 3,442 fallback frames can be absorbed.
