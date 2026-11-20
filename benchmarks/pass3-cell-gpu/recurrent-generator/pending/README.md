# When must a generated Cell be checked?

The source schedule orders observable facts. The generator can finish a parent and its descendants before the verifier checks the parent. The verifier can also check several logical Runs in one device invocation if a certificate describes the complete observable boundary of those Runs. The network's latent can retain useful context across generation steps. Its emitted references, boundary premises and rule choices are what an independent verifier can check.

## Two generated levels on full Pass 3

Two root rows each emit a latent, a Bake leaf, a physical anchor and an activation. The next two rows read those generated parents and select a parent row, its typed effect port and a certified consumer leaf. The token encodes the source parent position as well as its effect index. The next source Run's root network directly reads the generated child tensor. The root actor scores an observed bank of at most eight typed addresses per leaf on each source Run. This experiment therefore generates batches within a full scheduled traversal.

The compiler admits 15 two-leaf joins from the donor library. Each prospective child occupies one of two output slots. An accepted neural parent must win an actual RHS ordinal before its effect can supply a port. Publication attaches the physical row and the specific publication ticket to the claim. At a later scheduled consumer, the verifier checks visibility, watermark, the exact ticket and outstanding LHS predicates. The verifier can close that typed entrance once, so the residual search skips it. Ordered commit can still discard a duplicate. Every credited child is joined to a distinct actual RHS ordinal.

* **Wave feedback** verifies root rows before generating children. Each child sees the actual status of both roots.
* **Pending-parent batch** generates both levels before checking the roots. Children see the generated parent token and an explicit pending status. Both arms have the same weights, budget, library and verifier. Training on four source families randomly masks the root reply; the graph information in training windows comes from the reference schedule. Each update uses the actor's own tokens throughout the unroll.
* **Frozen cross-replay** submits just the emitted floating-point token stream to each verification schedule. The device decodes the joins again from the emitted addresses. No stored verifier verdict or winner ordinal enters the replay. This diagnostic fixes the proposals, while the two online arms allow the proposals to change.
* **Mask the parent address**, **force all roots to abstain**, and **disable exact completion** are separate interventions. The first forbids a child from attaching to a genuine producer. The second also removes the roots. The last reveals whether the network can start and complete the source schedule by itself.

The checker can batch root validation, and the next neural call can proceed without waiting for these verdicts. Future writes and outside dependencies still matter. For example, a physical row can be published by a different later RHS; checking the final row's current producer would then identify a different origin. A certificate referring to the actual source effect retains the publication version. The paired experiment pays for these checks in full.

## What the network supplied

Numbers below are distinct source RHS ordinals. Every assisted arm matches the source schedule, ordered inputs, effective writes, actual Spine resumes, union sequence and final typed graph. The common exact GPU search completes the complement. Raw activations, refused/overwritten proofs, row shares, complete nonempty Runs and six interleaved resident timings are recorded separately. [Online measurements](results.json)

| Workload / seed | Root RHS | Children wave / batch | Exact residual in batch | Whole-pass resident ms, wave / batch / exact |
|---|---:|---:|---:|---:|
| sum-bits/1703 | 95 | 29 / 25 | 7145 | 1054.8 / 1019.1 / 878.4 |
| sum-bits/1709 | 91 | 33 / 26 | 7148 | 1033.0 / 1015.6 / 915.0 |
| dot-product/1703 | 88 | 18 / 17 | 6599 | 1076.5 / 1081.4 / 925.0 |
| dot-product/1709 | 74 | 18 / 16 | 6614 | 1096.2 / 1091.8 / 944.7 |
| gemm-bias-relu/1703 | 70 | 25 / 23 | 15369 | 3075.9 / 3082.4 / 2850.8 |
| gemm-bias-relu/1709 | 66 | 25 / 20 | 15376 | 2991.7 / 2995.8 / 2788.6 |
| stable-argmax/1703 | 60 | 18 / 17 | 8113 | 1058.4 / 998.2 / 887.2 |
| stable-argmax/1709 | 59 | 19 / 18 | 8113 | 1027.4 / 1009.0 / 912.5 |

For sum-bits, seed 1703, the two pending children rows independently supplied 15 and 10 RHS. Masking the source parent address suppressed every child winner. With exact completion disabled, both generation schedules diverged on Run 1 and produced zero RHS on these four programs. An isolated worker had only the source image, certified joins and weights. The empty-LHS initialization lies outside this actor's vocabulary. [Isolated seed 1703](isolated-1703.json) · [Seed 1709](isolated-1709.json)

The independent PyTorch rollout regenerates every latent and discrete field from zero. Each winning child resolves to the actual parent, effect and publication ticket on the reference trace. Cross-replaying both emitted streams under both verification schedules yields the same observed RHS and graph for a fixed stream. Altering a parent address removes precisely the child that depended on it in four sampled forks; its sibling still wins. [Frozen DAG audit](replays.json) · [Rejected-parent controls](rejected-parent.json)

Giving roots supervision about a usable continuation changes which two roots the generator emits. All other model, sampling, update and deployment settings were fixed. With supervision on immediate leaf winners only, the pending children won 4 / 4 RHS on sum-bits and 2 / 2 on dot-product. With downstream-aware supervision they won 25 / 26 and 17 / 16. The latter increases real child work; the full resident paired measurements do not establish a speedup over exact GPU execution. Early compound-run setup/total fields used an export-buffer offset as a start time. The independent resident stopwatch is the timing used throughout this comparison. The shared timer is now fixed. [Root-target measurements](root-targets.json)

## Reproduction

Use the MPS workspace environment. The raw corpora and source-aligned captures are documented in [the composable-proposals study](../receipts/composable-proposals.md). All output paths must be new.

```sh
dir=benchmarks/pass3-cell-gpu/recurrent-generator
e="$EGGFUSE_ARTIFACT_ROOT"
families="$e/repair-bake-families-20261120"
ref="$e/pass3-atlas-integration-20261120"
reader="$e/rotary-axes-20261119/packed-1703/final.pt"
data="$e/recurrent-receipts-20261120"
targets="$e/recurrent-composition-targets-20261120"
out="$e/NEW-compound-policy"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/compound_model.py" "$ref/sum-bits/program.json" "$data" "$targets" "$out"
python "$dir/compound_study.py" "$families" "$ref" "$reader" "$out" "$out/paired"
python "$dir/compound_replay.py" "$families" "$ref" "$reader" "$data" "$e/recurrent-compositions-20261120" "$out" "$out/paired" "$out/replays"
for seed in 1703 1709; do
  python "$dir/isolate.py" "$families" "$ref" "$reader" "$out" "$out/isolated-$seed" --checkpoint "train-$seed/policy.json"
done
```
