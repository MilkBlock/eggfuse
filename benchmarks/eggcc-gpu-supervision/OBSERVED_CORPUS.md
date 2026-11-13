# Eggcc observed Cell corpus

`collect_observed_corpus.py` expands the real input source across the existing
96 eggcc pass-3 captures. This is data collection for the GPU model, not a speed
benchmark and not a change to the CPU executor. The native capture executes the
full CPU program and checks observer/reference equality and Run-control counts.
The local-label extraction retains the narrower contract in
`OBSERVED_CELL_TARGETS.md`; it does not recover all actual constructor outputs,
mutable reads, global novelty, scheduling legality or saturation.

Whole workloads receive fixed partitions before collection. Previously used
holdouts remain held out. Other case names use SHA256 modulo ten (0 test, 1
validation, others train). The manifest includes every case, including failures
and timeouts, source/program/trace fingerprints, input counts and the two capture
binary fingerprints. The default 30-second subprocess limit bounds each capture
operation; a timeout is a recorded failure, not evidence of unsupported semantics.

Cached traces are reused only for identical source bytes, then checked against
the program fingerprint and stored native audit flags. Large raw files and
per-input targets are not committed. Interrupted collection can reuse completed
artifacts on rerun. Failed workloads remain explicit in reports.

## Bake-local information

Every supported input sample contains `input_local_roles`. These are derived from
matched query operations and direct effect argument positions. Copy aliases refer
to the same matched input. Runtime Eq partitions combine the roles of aliased
ports; typed scalar values remain visible in the corresponding input symbol.
Fresh effect outputs are not mistaken for matched inputs. No post-Run roots,
completion facts or novelty labels enter these features.

This produces an inspectable basis for later floating feature projection:
constructor/argument roles, direct effect use, alias sharing and scalar input.
It is not yet a claim that this basis improves ridge accuracy. It is also not a
second runtime fact graph: these are offline training artifacts derived from
existing Cell operations and actual observations.

`profile_observed_corpus.py` measures how much finite structure is actually
repeated. It counts conservative compiler-layout families, unique local input
states and role patterns, and reports exact training-input overlap in validation
and test workloads. It also checks whether the proposed local role signature
maps to multiple exact local completion targets within a family. Such collisions
would demonstrate that this feature alone is insufficient; zero observed
collisions would not prove injectivity outside the collected data.

Large overlap is useful for a Bake-scoped compiler model, but must not be reported
as unseen-state generalization. The compiler-layout key is intentionally
conservative and does not prove semantic or alpha equivalence. Full successor
closure, perturbation recovery and reliable stop decisions remain unmeasured.

## Storage and reproduction

Current bulk artifact location:
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/observed-corpus-20261113`.
The worktree's `out/eggcc-observed-corpus/CASE` entries retain symlink access.
Only this task's new artifacts were moved, with byte verification before deleting
the redundant local copies. Existing experiment directories were not moved.
Early completed program/trace JSON files may be gzip-compressed;
`read_bytes` transparently loads either representation and hashes uncompressed
bytes. `archive_observed_corpus.py` is an optional verified compressor for this
collector's own completed artifacts, not a general cleanup utility.

```sh
python3 benchmarks/eggcc-gpu-supervision/collect_observed_corpus.py CAPTURE_ROOT OUTPUT_ROOT --cache OLD_TRACE_ROOT
python3 benchmarks/eggcc-gpu-supervision/profile_observed_corpus.py OUTPUT_ROOT/manifest.json COVERAGE.json
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_observed_corpus.py
```

The feature tests check fixed holdouts, copy alias invariance, actual Eq-role
aggregation and avoidance of stale input roles after a destination is overwritten.
Use the corpus to train transitions within known families and assess new actual
states separately. Do not replace exact output and boundary checks with corpus
size, emission counts or vector error.

## Position-aware role refinement

The first corpus pass exposed exact-target collisions in the unpositioned role
signature. Rule 422 has multiple `Get` occurrences: swapping their scalar indices
can preserve the multiset of (constructor, argument position, direct effect use)
while changing which result is required. This is a specific structural attachment
loss, not a lack of training observations.

`role_features(..., positions=True)` also records the template-local query
occurrence and non-copy effect occurrence. These positions are static Bake
coordinates, not physical node IDs. Copy instructions do not shift effect role
coordinates, preserving copy-alias invariance. The coverage report compares both
signatures against exact local targets. No observed collision is not a proof of
sufficiency for arbitrary graphs or hidden external context.

`boundary_cell_ridge.py --positioned-roles` exposes an optional numerical ablation:
fixed dense projections combine these roles and literal inputs into the request
code. Eq identities are not converted to floats. This uses no post-Run facts and
no backpropagation. Its readable feature provenance does not by itself make every
coefficient of the dense random projection directly interpretable.

On the old 21-chain rule-family-held-out test, exact final selections are 15 with
these features versus 16 in the baseline. All 21 emit, with six wrong selections.
Thus the feature correction has not demonstrated an overall accuracy improvement.
That small held-out-family experiment is distinct from the intended known-Bake-
family, cross-workload corpus evaluation. The latter has not yet been trained on
this expanded corpus. `positioned-role-results.json` records the ablation.

## Completed first collection pass

All 96 workloads were attempted: 85 complete, 11 hit the per-command timeout.
The complete workloads contain 3,159,604 actual bindings; the conditional local
teacher supports 1,932,864 of them. Per-workload deduplicated states sum to 29,827;
that sum is not globally unique. Across workloads there are 296 conservative
compiler-layout families, 133 with multiple input states, with a maximum of 198
states in one family. The full failure list remains in the external manifest
and committed summary; timed-out cases are not counted as semantic failures.

Training has 1,604,320 supported observations and 1,880 distinct local input
states. Test has 158,078 supported observations and 850 distinct input states;
157,588 observations (about 99.69%) have an exact local input already present in
training. This supports measuring finite covered-family execution separately
from new-state generalization. It says nothing about unrepresented external
egraph context or all possible dynamic scalar states.

The unpositioned local role signature has three collision groups covering 24
observations; the position-aware signature has zero *observed* collisions. All
stored original role features match recomputation (zero mismatches). The summary
and collision-source references are in `observed-corpus-results.json`; complete
examples are preserved in the external `coverage.json`.

The expanded corpus has not yet been used for a full GPU model retraining or
full successor-state coverage. The small optional feature ablation above is
reported separately and did not improve exact-target count. Collection volume,
feature distinguishability and learned correctness are separate measurements.
