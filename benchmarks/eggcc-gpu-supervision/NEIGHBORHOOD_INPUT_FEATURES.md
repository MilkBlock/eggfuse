# Bake neighborhood features for multi-entry ridge continuation

The GPU runtime target is unchanged: stable-semantic Cell tokens, repeated
on-device production until certified closure, then the next source stage.
This experiment improves a supporting numerical model, not that runtime's
matching, ownership transfer, novelty or stopping protocol. All current replay
instances/routes still come from CPU observations.

## Missing representation and two explicit variants

Previous port roles encode operation names and operand positions but not their
neighboring operand wiring or literals. A regression test shows otherwise identical
`F(x, 2)` and `F(x, 3)` templates have identical original port roles.

`neighborhood_template` performs two **compile-time** message rounds over template
operations. Each operation combines its label, operand-position codes, neighboring
port roles and exact literal descriptions. It sends context back to its slots.
Dynamic Eq grouping uses only current input roots. Node identities never become
float magnitudes. There is no backpropagation or GPU graph traversal added.

- `class-history-neighborhood` replaces input/routing roles with these codes.
- `class-history-neighborhood-input` keeps the original seed, request prefix and
  routes, appending a 128-float neighborhood-aware current-input code plus a
  64-float static template request. Original output targets remain unchanged.

Both retain earliest-source fallback wiring. The second variant was investigated
following the replacement's poor token error; these are exploratory alternatives,
not a preregistered architecture search. Ridge penalties are selected using the
unchanged validation policies, never test labels. The enlarged model's fixed
random projection also changes with its input width, so this is not a perfect
single-feature causal ablation.

## Correctness evidence

Same 10 training workloads and token-validation euler workload; separate Eq
readout uses all five original validation workloads. Test remains dot-product:
5,553 complete states, 5,454 with equality queries. No new training labels or
examples, no threshold tuning. Numeric GPU/CPU audits and test readout checks pass.

| Variant | Validation macro exact rate, partition policy | Test exact partitions | False pair merges | Missed equalities |
|---|---:|---:|---:|---:|
| Earliest baseline | 80.4184% | 4,395 | 798 | 1,833 |
| Replace roles | 79.9489% | 4,280 | 762 | 2,023 |
| Append local inputs | 80.7081% | 4,404 | 613 | 1,815 |

All partition policies select Eq ridge alpha 0.1. Under MSE selection (alpha 100),
appended inputs yield 4,260 exact partitions / 276 false pairs / 2,038 misses,
versus baseline 4,231 / 460 / 2,043. These are improvements on this test, not zero
error or permission to commit predicted unions. Error-count reduction under the
partition policy is 23.2%; exact partition improvement is only 9 of 5,454.

Token RMSE is 0.036672 baseline, 0.072635 replacement, 0.041001 appended inputs.
It does not track Eq accuracy. Keep these separate rather than selecting by RMSE
alone or claiming the token is a complete semantic execution state.

The real trace check confirms all 5,935 instances retain identical baseline
output targets, input seeds, original request columns, edge addresses, edge
coefficients and routes in the appended variant. Unit tests also mutate RHS labels
without changing these new input features, and check slot renaming and runtime-ID
invariance. 32 focused tests pass across neighborhood, ridge, routing, Eq readout
and continuation contracts.

## Cost and limitations

Raw ridge input width increases from 1,216 to 1,408. Inference weights increase
from 499,840 to 573,568 floats (+14.8%). The current materialized input array adds
192 floats per instance (4,558,080 bytes for 5,935 instances), including repeated
static request columns. This is not a memory-saving claim.

Six alternating warm GPU replays in the same process give medians 5.805 ms
baseline and 5.857 ms appended inputs (ratio 0.991x). No speedup is established.
CPU dataset encoding increases from 898 ms to 1,239 ms; plan preparation is
48.5/50.1 ms. This implementation rebuilds template features per dataset, so some
extra work is Bake-time cacheable, but that work has **not** been removed here.
CPU NumPy numerical execution is 22.1/20.9 ms in one diagnostic call, not native
Eggfuse throughput. Final Eq readout, CPU semantic auditing and matching remain
outside warm replay timing. Models and source captures stay on external storage.

## Next integration

Keep appended features available, replacement experimental and defaults unchanged.
Use one Cell definition for matching contracts, local-feature construction and
owner-slot projection. Do not restore node-by-node traversal or duplicate a fact
graph merely to compute these features. Device continuation must produce its own
current-input groups and owner witnesses; CPU-observed grouping in this experiment
cannot be silently reused as the runtime implementation. More candidate token
production is not saturation until novelty and all pending obligations are resolved.

Reference Bake branch advanced to `794a2afd`; its checked Entry address is valid
only under anchor/shape/ordinal/liveness checks, not as a permanent result identity.

## Reproduce

Use the existing `multi_entry_ridge.py` and `select_eq_readout.py` commands from
`HISTORY_EARLIEST_EXPERIMENT.md`, replacing the model stem and `--encoding` with
either variant above, retaining `--channels 4` and the same datasets. Run
`compare_history_replay.py TRACE class-history-earliest.npz
class-history-neighborhood-input.npz OUTPUT.json` in the NumPy/MLX environment.
Committed `class-history-neighborhood*-results.json` and
`neighborhood-input-timing-results.json` preserve all hashes and measured results.
