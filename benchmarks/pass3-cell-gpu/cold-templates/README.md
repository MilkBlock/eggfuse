# Zero-update scoring of cold Bake combinations

Figure 47 tests a shared scorer at three real snapshots of the iterative sum-bits Bake artifact. Each library starts with 32 leaf entries. The first 40, 48 and 64 catalog units admit **8, 9 and 15** certified binary joins whose inputs are leaves. The other grown units include longer paths. This study measures one model-generated parent pointer and one next rule per child. The 64-unit catalog does not give the network 64 different two-step actions.

## What the model sees

| Head | Template representation | Adding a previously unseen join |
| --- | --- | --- |
| ID | One learned width-12 vector per *training* join and a fixed all-zero code for an unknown join. | Every unknown join reads the same code. The ordinary typed legality mask, port identity and stable tie order still apply to the action. |
| Graph | A two-round shared message-passing encoder over the joined port graph. A directed effect-to-pivot edge and aligned column links connect the two sides. | Construct the new typed graph; encode the selected output, consuming pivot, retained ports and pooled leaf regions; cache the resulting score parameters. |
| Compose | The same message transforms, role vocabulary, region readout and number of learned parameters. Encode leaves separately and cache their pooled representations, retained ports, individual effect vectors and pivots. | Select the producer effect and child pivot from the immutable leaf bank, combine their codes with retained ports, and cache only the new join's score parameters. |

The graph uses compiler table/operation names, types, argument positions, binding/use edges and the Bake boundary projection. It contains neither a learned vector indexed by a rule/combined-template ID nor a runtime e-class graph. All arms map their width-12 representation through the same shape of decoder to **24 float32 values per join**. The real Metal child kernel consumes this cache directly. A second 18-float global block supplies the two null biases and row latent offsets. The per-instance scorer, original ordered commit and residual exact engine are the same. [Typed graph and incremental leaf bank](graph.py) · [PyTorch training and cache export](policy.py)

## Frozen training split

All three heads train on four program families and the 40-unit compiler snapshot for 480 updates of twelve eight-Run windows. The starting single-leaf proposer is shared and frozen per seed. It previously learned leaf bindings on those four families without any combination targets. The whole-family holdout applies to the *combination head*: every combination whose left rule is 55 is removed from supervised candidates and outputs. The head has no examples of that family being composed. The root may still select rule 55 as a standalone leaf. This distinction allows the online experiment to measure selection and subsequent completion separately.

The source-order split takes the second left-rule family, the first combination of the remaining family, and its self-composition. The training units are 33, 36, 37 and 39. Units 32 and 38 are held-out combinations; 34 and 35 are the held-out left-rule family. Every unit added in a later snapshot remains cold. The model receives the available static compiler descriptions of cold units at evaluation. Historical frequencies and workload names are excluded from their feature vectors.

Training unrolls its own generated token/latent. A separate auxiliary readout learns the conditional task with up to two eligible **training-only** parent addresses. This loss never writes a root into the recurrent input. At inference the neural root and child are both generated on the device. No program-family test trace, future source RHS or evaluator-selected parent enters an online forward. [Training procedure](policy.py)

## How coverage and time are counted

* **End to end.** Sum-bits, dot-product and the two held-out families GEMM-bias-ReLU and stable-argmax actually run full Pass 3. We credit a child at its committed source ordinal after checking its emitted parent, exact producer effect, physical publication ticket and typed target. Remaining ordinary bindings are charged to the exact GPU engine. A complete nonempty Run requires all its RHS to be accounted for by generated roots or children. Each run is checked against ordered RHS, writes, Spine resumes, union sequence, e-class roots and all typed final records. Largest-library controls disable exact completion. Isolated workers get only six compiled input files.
* **Reference opportunity.** For each cohort count the distinct source-winning child RHS with a compatible template, an observed parent publication and a root visible in the eight-address bank. One action can consume one parent and select one join. Each source Run has at most two child slots. Several future RHS may be associated with the same source root/join, so the two-slot opportunity is calculated on distinct issue-Run root/join pairs. Any valid alternative origin is credited as online work and recorded separately. Cohort bounds compete for the same slots and must not be added. Each cohort also reports how many winners actually required choosing between multiple admissible joins on the selected parent; activation of a lone typed successor is a separate outcome. A second bound restricts these issue opportunities to parent ordinals actually won by this policy, including its original leaf and rank. This shows where a scoring head could still have made progress after the root stage.
* **Given the right root.** An explicitly offline diagnostic forces one eligible source root and a null peer into the frozen root readout at zero previous latent. The child head must select joins from the full snapshot. It reports distinct correct and spurious choices, missing choices, and complete nonempty root queries per cohort. It is possible to choose a legal template conditionally while reaching none of those roots during autonomous proposal. These counts are excluded from online RHS attribution. The fixed-logit counterfactual reverses only the join enumeration order per parent; it exposes cold-ID ties without changing a coefficient.
* **Cost.** All online policy arms run inside the same full executor on device. Timed repetitions alternate their order, use the same device snapshot, synchronize before reading the timer, and recheck ordered effects and raw tokens afterwards. At the largest snapshot an exact-only GPU comparator joins the rotation. For the isolated scoring diagnostic, the exact deployed kernel body consumes archived online parent tokens in one GPU grid. Its child outputs are checked against live inference, and timing explicitly includes dispatch and synchronization. This independent-batch readout cannot substitute for full-pass latency. Compiler-side metrics include cold and warm graph construction/encoding plus incremental extension from cached previous native coefficients. The compose arm separately pays for constructing the persistent 32-leaf port bank. It does not re-encode old leaves when compiling additional joins. [Native readout](score_cost.py) · [Whole-source evaluation](study.py)

## Measured outcomes

Across four real source programs and two seeds in the 64-unit snapshot, the ID / full graph / child-composition policies delivered **30 / 31 / 31 child RHS**. Their corresponding submitted root counts were 374 / 381 / 377. These sums count repeated trajectories. Newly grown units supplied **2 / 3 / 4** child RHS, all with a single compatible join for the chosen parent. None of the three heads produced an online child from held-out units 32/38 or left-rule family 55. Every policy was slower than the matched exact-only GPU engine on each of the eight largest-library comparisons. [Per-program source counts, closures, timing samples and native scoring](results.json)

| Real Pass 3 | ID child RHS | Full graph child RHS | Composed children child RHS | Exact GPU median ms | Composed policy + verifier median ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 3 / 2 | 4 / 2 | 4 / 3 | 866 / 863 | 1005 / 994 |
| dot-product | 0 / 0 | 0 / 0 | 0 / 0 | 878 / 887 | 1037 / 1065 |
| gemm-bias-relu | 8 / 7 | 7 / 8 | 7 / 7 | 2774 / 2485 | 2986 / 2845 |
| stable-argmax | 5 / 5 | 5 / 5 | 5 / 5 | 857 / 898 | 995 / 1019 |

The two holdouts failed for different reasons. In the whole left-rule family, roots actually selected allowed only **2** correctly sourced child opportunities across these eight trajectories for each head. In the known left family with unseen combinations, roots already reached **61 / 60 / 59** available issue slots respectively. All three still produced zero of them. The conditional diagnostic eliminates root reach as a confound: on all **602** held-combination root/join targets counted across these cases and seeds, each head proposed from a different **producer effect port** than the required one. No miss in this cohort came from both rows abstaining. A frozen, equal-budget follow-up can balance the producer's distinct output ports in the four training families or explicitly predict the producer port before the consumer. These remedies have not been evaluated here.

In sum-bits seed 1703, the two structural policies actually contributed newly grown unit 56. In Run 651, RHS #4044 of rule 502 (`terms`) published effect 6. A pending child of rule 506 (`terms-helpers`) won RHS #4077 in Run 654. The parent had exactly one admitted join in this snapshot, so the example demonstrates transferred activation and verified wiring, with no evidence of successful selection between multiple possible continuations.

**Compile cost.** At seed 1703, the 40 → 48 transition compiles one new pair in 0.354 ms with the full graph and 0.008 ms from cached child ports. Extending 48 → 64 compiles six new pairs in 2.142 vs 0.016 ms. The composed encoder initially takes 2.92 ms and 9,120 bytes for its 32-leaf bank. The ID arm learns 378 parameters, and both structure arms learn 3,558, in addition to the same 783 frozen root parameters. All 11 cold joins in the largest library compile to one identical 24-float coefficient row under ID; both structure encoders compile 11 distinct rows. The runtime coefficient cache occupies 1,440 bytes for all 15 pairs plus 72 global bytes under every head. Distinct codes alone did not solve conditional port selection. [Training split, parameter counts and cache hashes](training.json)

## Reproduction

Use the same external workspace Python environment with CPU fallback disabled. Each output directory must be new.

```sh
dir=benchmarks/pass3-cell-gpu/cold-templates
exp=/Volumes/EggFuseWorkspace/experiments
families="$exp/repair-bake-families-20261120"
ref="$exp/pass3-atlas-integration-20261120"
reader="$exp/rotary-axes-20261119/packed-1703/final.pt"
root="$exp/recurrent-leaf-corpus-v2-20261120"
models="$exp/NEW-cold-cache"
results="$exp/NEW-cold-pass3"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/policy.py" "$ref/sum-bits/program.json" "$root" "$exp/recurrent-receipts-20261120" "$exp/recurrent-composition-targets-20261120" "$models"
python "$dir/study.py" "$families" "$ref" "$reader" "$exp/recurrent-compositions-20261120" "$root" "$models" "$results"
python "$dir/isolate_growth.py" "$families" "$ref" "$reader" "$models" "$results" "$exp/NEW-cold-isolated"
python "$dir/package_results.py" "$families" "$ref" "$exp/recurrent-compositions-20261120" "$root" "$models" "$results" "$exp/NEW-cold-summary"
```
