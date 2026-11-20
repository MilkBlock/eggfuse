# Calibrating a physical Cell composition reward

The executor can switch a live parent to a proved larger layout and publish a new child member directly into it at the original Run. This path can avoid allocating a child owner and root hold. Under liveness rules the executor can also retire an existing public member view. These events have different lifetimes: several children can share one growing owner, an old public address can remain available, and a view may retire later when its last user disappears.

This experiment runs the actual pinned integral member store of the standalone Cell CPU engine. The original exact matcher and schedule drive every RHS. The experiment measures the physical effect of choosing a template catalog. It gives the neural proposer zero credit for these actions. The [legacy measured storage path](../online-storage/README.md) supplies the pinned source and the allocator/alias checks.

## Training and validation

* Four training families provide observations: affine-twins, clamped-ramp, segmented-prefix and window-laplacian. Candidate generation uses only first-round single-edge shapes observed with successful member publication in at least two training families. We keep the twelve most frequent candidates. A candidate pins a producer layout, member, producing operation and child layout.
* On each training family we execute the empty catalog and all twelve candidates individually with the same admitted source addresses, graph and visibility. For each candidate we record the change in terminal owner count, cumulative actually retired public views and charged bytes. All policies have a ceiling of four edges.
* Frequency takes the four most-published candidates. Owner reward maximizes the measured reduction in terminal owners; retirement reward maximizes additional retired public views. Ties follow training publication frequency then the static key. Net-byte reward admits up to four candidates with positive observed savings. The byte accounting charges instance arrays, owner vector capacity, root directory estimate, exceptions and compiled added layout payload. The held-out counted allocator independently measures full graph, library and instance teardown.
* On a new program, the compiler receives the frozen edge IDs and independently proves source/child port compatibility before the scheduler starts. A static incompatibility can drop an edge. The test corpus supplies no ranking, thresholds, success frequencies or actor actions. First we execute every frozen catalog unmasked. For an attribution comparison we then intersect actual address tuples and rerun all catalogs with the same source admission mask. Those latter masks are retrospective experimental controls.
* At each source Run an independent audit checks ordered RHS inputs, effective writes, actual Spine resumes and the semantic graph. Every still-issued old source fact address is resolved through the live view table. The audited executor also asserts that live integral members have no ordinary frame, completed standalone slots or completed standalone fact map. The final exported graph is compared structurally to the current reference.

The four training families ranked the same four edges highest by frequency and owner reduction, with a different order. An edge joining parent layout 1074114561's member 0, operation 0 to child layout 1074118657 avoided 209 terminal owners and produced zero additional public-view retirements in aggregate. None of the twelve single-edge candidates saved bytes under the specified training charges; net-byte admission therefore froze an empty catalog. [Training interventions, edges and frozen policies](frozen.json)

## Results on withheld programs

These rows use 2,260 identical original admissions on dot-product and 2,729 on stable-argmax, all from the native Rust matcher. The graph-and-library column sums three *measured* allocator teardown accounts: graph fields, integral instances and integral library. It includes ordinary indexes and forwarding state. Four uninstrumented inference samples per arm follow a warmup. The energy/accuracy of a neural policy is outside this experiment.

| Source and trained reward | Layout switches | Final owners | Old public views retired | Final live source handles | Graph and library bytes | Median inference ms |
|---|---:|---:|---:|---:|---:|---:|
| dot-product, empty | 0 | 975 | 1,215 | 1,045 | 2,526,933 | 34.81 |
| dot-product, owner reduction | 55 | 923 | 1,215 | 1,045 | 2,532,617 | 35.80 |
| dot-product, view retirement | 65 | 923 | 1,224 | 1,036 | 2,533,021 | 35.10 |
| stable-argmax, empty | 0 | 924 | 1,765 | 964 | 2,692,013 | 45.31 |
| stable-argmax, owner reduction | 129 | 824 | 1,765 | 964 | 2,699,121 | 46.04 |
| stable-argmax, view retirement | 94 | 861 | 1,771 | 958 | 2,696,693 | 45.00 |

Frequency selected the same four physical edits as owner reward and produced the same physical endpoints. The net-byte policy, frozen before evaluation, admitted zero edges and incurred the empty-catalog memory cost on both programs. The largest observed number of old readable fact addresses checked in one Run was 1,257 / 1,266 on all five arms. The additional nine / six retirements on the retirement-reward arm removed public views belonging to integral members; this count cannot establish that a previously independent physical owner was merged away. The owner count measures terminal slots, including child owners avoided at birth. A receipt for absorbing two already-live independent owners would require a further runtime action. All train/test intersections and measured variants are preserved in the [policy result](results.json), [complete allocator charges](heap.json) and [source audit](origin.json).

The unmasked application run matters because composition itself changes later admission opportunities. On stable-argmax the empty policy ended with 941 owners and 981 public handles. Owner reward ended with 935 and 1,075, while retirement reward ended with 940 and 1,037. Both created more publicly visible members in this unconstrained experiment. The larger owner reduction in the matched table measures representation under fixed admissions; it cannot be carried over to a deployment with endogenous admissions. On dot-product the natural and matched endpoints agreed.

## Model credit and missing interface

The current neural root issuer seals a source identity and typed proof before the Rust verifier reads the graph. Its allocation hook records a fresh physical Cell under that winner. The older integral executor receives already-accepted bindings and attaches members at a subsequent storage hook. The integral admission tuple carries source epoch, Cell ID, producing Cell/operation, base layout and member slot. It has no authenticated issuing token, optional transfer action or counterfactual role. Equal final state or equal numeric source IDs in separate executions cannot establish which network action caused an owner to disappear.

A joint implementation needs three observable outcomes. First the model would seal a transfer action naming the rule, owner generation and child boundary. Second the same executing runtime would accept or reject that stamped action before choosing the physical representation and emit an actual transition receipt. Third liveness would emit any later view retirement with its stable physical identity and generation. The reward can credit a directly avoided owner at attachment and debit later external references, re-materialization and maintenance. An already inevitable retirement receives no additional model credit. The no-proposal and incorrect-owner controls must keep the same legal source schedule.

## Reproduction

The observer compiles in a private copy of the pinned archive prepared by the online-storage experiment. Use fresh external output directories on APFS. The anchor program lives in the Pass 3 atlas adjacent to the split corpus. All four train programs and the stable-argmax holdout are stored in the split corpus itself.

```sh
d=benchmarks/pass3-cell-gpu/physical-composition-reward
e="$EGGFUSE_ARTIFACT_ROOT"
legacy="$e/online-storage-20261120"
corpus="$e/repair-bake-families-20261120"
python "$d/build.py" "$legacy" "$e/NEW-owner-reward-build"
python "$d/study.py" "$e/NEW-owner-reward-build/observe" "$legacy/target/release/examples/online_storage_trial" "$corpus" "$e/NEW-owner-reward-study"
python "$d/heap.py" "$legacy/target/release/examples/runtime_storage_peak" "$corpus" "$e/NEW-owner-reward-study"
python "$d/verify.py"
```
