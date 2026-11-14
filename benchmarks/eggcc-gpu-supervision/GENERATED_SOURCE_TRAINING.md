# Training on actual generated-source continuations

The previous two training programs supplied 75 accepted Cell instances but only
5 consumed GPU-generated sources. The GCD validation program supplied 15 such
instances. This change adds a reproducible training-only collector and measures
whether more real continuations improve the same fixed ridge model.

This remains a standalone selected-family GPU prototype, not full Eggcc, native
egglog acceptance, or authoritative learned completion. No backpropagation is used.
CPU oracle labels are produced after the GPU run. The GPU chooses its matches,
generates Cells, performs supported exact effects and transfers physical owners.
The exact completion kernel still supplies completed source tokens.

## Selection and execution

The collector verifies the original training partition and program/trace hashes,
requires saved reference execution at most one second, then chooses the Run
immediately before the first observed rule-290 continuation. It does not select
by validation accuracy or the largest future batch. All selected programs keep
the existing rules 283, 290, 293 and the same boundary encoder. The observed CPU
history selects an initial snapshot only; it does not supply later GPU matches.

| New training program | Snapshot | Generated Cells | Consuming generated sources | Completed Runs | Released owner rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| dead-branch | 415 | 34 | 24 | 5 | 20 |
| sum-check | 484 | 6 | 3 | 3 | 8 |
| sum-sq-diff | 489 | 14 | 3 | 3 | 17 |

Every completed Run's graph and per-rule match counts pass the independent
unlowered CPU reference. Owner releases are physical storage events; generated
Cells and logical matches are not counts of distinct committed graph mutations.
No capacity or termination gate was weakened. All runs use capacity 128,
24 fixed scheduler ticks, flush interval 1 and statically ordered queries.

Including Pascals and Euclid gives **129 training instances, 35 generated-source
consumers**. GCD remains validation only. Each program is admitted once; duplicate
or validation programs are rejected by the calibration script.

## Fixed-alpha comparison

Ridge alpha remains 10 and Eq threshold remains 0.5. The decoder trains on correct
CPU training tokens independently of the predictor. The same five-program corpus
is evaluated with and without the 512 boundary columns:

| GCD validation | Two-program boundary | Five-program boundary | Five-program without boundary |
| --- | ---: | ---: | ---: |
| Exact partitions | 20/41 | **35/41** | 36/41 |
| False pair merges after closure | 42 | **0** | 2 |
| Missed pair equalities | 6 | 16 | 10 |
| Direct-source exact | 14/26 | **23/26** | 22/26 |
| Generated-source exact | 6/15 | **12/15** | 14/15 |

The new boundary model reaches 85.37% complete-partition accuracy on this
validation program. Zero observed false merges is not a correctness guarantee.
The no-boundary model has a higher exact count but produces two false merges.
Neither is installed as authoritative execution. In particular, suppressing
positive predictions can improve false-merge counts while missing real work;
missed equalities and saturation completeness remain mandatory checks.

Training diagnostics are now reported separately. The boundary candidate has
122/129 exact training partitions (94.57%), including 35/35 generated-source
instances. The training result is not the held-out result and must not be reported
as having reached 90% validation accuracy. Remaining validation errors require
further context/generalization or decoding work, not merely more copies of these
same samples. The complete report includes the resident decoder ablation too.

Across all 170 training+validation samples, resident inputs retain 13 conflicting
label groups with an empirical maximum 147/170. Extended floating features and
one-hop structural signatures have no conflicting targets in this set. Their
respective distinct counts are 166 and 165: floating equality is not a universal
semantic identity, and the structural signature deliberately omits sharing away
from the boundary. None of these grouping statistics is predictive accuracy.

## Costs and provenance

New GPU compile/upload/execute diagnostic times are 36.717, 38.518 and 47.699 s;
CPU reference plus graph audit takes 0.144, 0.063 and 0.089 s respectively. Full
observer capture includes additional original-program graph audits. These are not
production speed comparisons. The dense boundary encoding cost from the previous
report still applies and has not been optimized away in this change.

`generated-source-training-manifest.json` retains exact commands, capture hashes,
original short-reference timings and observer binary hash. `generated-source-executions.json`
retains the full three GPU execution reports. Model comparison and input ambiguity
reports are saved separately. Binary datasets and weights stay on the external disk.

Latest inspected Bake is `883b1547` on `codex/cell-parallel-admission`, adding
completed RHS result witnesses to owner joins. That path requires an actual visible
returned FactRef; a producer operation position alone is not sufficient. It also
preserves pending-fact, frozen-reader and dirty-state restrictions. The GPU sampler
continues reading actual shared owner slots and checking their generations. It has
**not** ported the new result-only owner-join capability: that remains work beyond
the existing query-witness takeover and must not be inferred from these releases.

## Reproduction

With ROOT = `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`, use the project MLX Python:

```
python collect_boundary_training.py ROOT/rhs-training-expanded-20261114/manifest.json ROOT/observed-corpus-20261113/manifest.json ROOT/cargo-target/debug/examples/capture_rhs_results ROOT/class-history-neighborhood-input.npz ROOT/boundary-training ROOT/boundary-training/manifest.json
```

The default case list is the three programs above. Verified snapshots are reused;
failed or incomplete GPU outcomes remain investigation records. The manifest is
not marked passed until every requested case has finished successfully.

Use `calibrate_semantic_family.py` with Pascals training, GCD validation and the
same base model/decoder as `BOUNDARY_CONTEXT.md`. Supply `--boundary-context` and
four `--extra-training` arguments: Euclid plus the three `.labeled.npz` paths in
the collection manifest. Repeat without the boundary flag for the controlled
ablation. No alpha sweep, threshold search or partition reassignment is performed.

The candidate is now connected to live GPU inference, with a separate nonvacuous
predicted-source feedback experiment documented in `LIVE_PREDICTION_FEEDBACK.md`.
Exact matching and effects remain authoritative; neither experiment establishes
complete learned execution or broad held-out correctness.
