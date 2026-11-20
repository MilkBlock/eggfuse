# Can a recurrent proposer use the verifier's reply?

Each source Run on the actual Pass 3 GPU executor gets four emissions. Two rows propose concurrently, the verifier checks those two proposals, the same two rows each generate a second token, then the executor searches the residual and commits in source order. The weights are shared across waves. The first wave of the next source Run consumes the second wave's generated tokens on device. A Run boundary reopens tasks even if their leaf and address match the preceding Run.

**What the verifier proves.** A task is a certified Bake leaf at one physical anchor in the current Run. A valid scheduled leaf and live cursor lead to exact checks of the remaining LHS. Only successful verification can insert an RHS candidate and close that entrance for residual search. Final commit independently deduplicates candidates. We credit a neural row only if its verified candidate wins an actual global RHS ordinal. A rejected proposal leaves its obligation open. All experiments use the same 32-leaf library and up to eight typed addresses per leaf. The generator cannot choose ordinary joins or an empty-LHS rule with this action vocabulary.

**What was learned.** Three PyTorch actors start from the same initial weights for each of seeds 1703 and 1709. Each takes 480 identical batches of twelve 12-Run windows from four training program families. Both waves receive unordered set supervision on reference winners still open after earlier proposals. The training verifier uses offline outcomes of physical routes, including successful routes that later lost RHS dedup. The next input token always comes from the actor. Online Metal independently evaluates the learned equations. The reference observations and winner maps are inaccessible to the online actor. Sum-bits donates the library. Dot-product is the second anchor. GEMM-bias-ReLU and stable-argmax are held-out program families.

| Arm | What the next row reads from verification |
| --- | --- |
| blind | Its generated token only. |
| bits | Acceptance of its previous proposal and the peer's previous proposal. |
| ids | Own/peer acceptance, rejection, stale and duplicate flags plus keyed score adjustments for the previously verified leaf and physical address. Separate learned coefficients apply within a Run and across a Run boundary. |
| shuffled | Frozen IDs checkpoint with the two source addresses exchanged, statuses held fixed. |
| masked | The same frozen checkpoint with the entire reply masked. |
| exact | Ordinary exact GPU search with no recurrent neural waves. |

The verifier records four int32 words per row in every neural arm for retrospective audit. Blind logically reads zero reply bits, bits uses two acceptance bits per wave shared by both rows, and IDs can read the previous 32-byte two-row record. These figures describe distinct fields consumed by the policy. The runs do not measure a packed wire protocol or physical memory transactions. All neural arms retain the same 131,072-byte diagnostic verdict buffer at a 2,048-Run budget. A separate frozen intervention excludes a wave-one accepted address from both rows in wave two. It leaves rejected proposals eligible and never carries the exclusion across source Runs.

[Full-schedule feedback results](feedback-results.json) · [Closed-address exclusion](guard-results.json) · [Bootstrap control](bootstrap-results.json) · [Composed certificates and variable waves](composable-proposals.md)

## Reading the measurements

Measurements come from the complete CPU-aligned GPU trajectory with residual completion enabled unless explicitly named. Every positive arm checks ordered RHS fields, effective writes, Spine resumes, union sequence, roots and the final typed graph. Every credited neural RHS has its own checked source rule, physical anchor and unique global ordinal. An independent PyTorch rollout starts at zero, advances its own latent and reconstructs its own replies from an offline route capture. Its discrete tokens, verdicts and rejection reasons must match every GPU decision. Online execution does not consume the audit. Paired resident timings include feature construction, both policy waves and verifier calls, residual matching, ordered commit and synchronization. Each arm starts from the same device snapshot. Six-way comparisons use twelve time samples, four-way frozen exclusion comparisons use eight. Cold CLI performance and phase-specific GPU counters are outside this comparison.

**Coverage denominators.** All RHS includes every committed rule input on the source schedule. Presented reference winners are the subset traceable to a candidate in the 32-by-8 bank. Missed presented winners are counted once per source Run. The second wave's cross-wave reclaims count proposals for an address already accepted by wave one. Same-wave collisions count separately in the verifier's duplicate total. A stale retry repeats a first-wave rejection caused by the watermark. A full nonempty Run requires every RHS to have a neural origin. The independent bootstrap control records the first mismatching schedule row, ordered RHS, effective write or Spine event, then classifies the missing bindings at that boundary.

**Observed work.** With seed 1703 on sum-bits, the blind policy committed 88 of 7,265 actual RHS, acceptance bits committed 91, and typed receipts committed 106. Of the 106, exactly 50 came in the second wave. Cross-wave reclaims fell from 42 to 2. Swapping row identities on the last receipts left second-wave choices unchanged for this case. The second row supplied no additional RHS in either wave with typed receipts. The frozen blind policy plus a deterministic closed-address exclusion committed 105. Seed 1709 gave 59, 117 and 112 for the three trained arms, and 110 with frozen blind exclusion. Different trained policies can reach similar coverage through different row assignments.

**Wall clock.** In the separate launch-boundary comparison, combining proposal and verification into one group reduced sum-bits seed 1703 from 1,072 to 1,029 ms, with identical emitted float32 tokens, receipts and ordered RHS ordinals. Exact GPU search took 888 ms. Dot-product measured 1,118, 1,077 and 901 ms respectively. Eight resident runs per arm include residual completion. The same graph observations and exact verification remain necessary in the fused arm. [Paired timings](exchange-results.json)

## Reproduction

Use the external workspace's PyTorch environment with MPS fallback disabled. The first command captures all ten programs and the second trains the six policies. Each output directory must be new.

```sh
dir=benchmarks/pass3-cell-gpu/recurrent-generator
data="$EGGFUSE_ARTIFACT_ROOT/NEW-receipt-capture"
ref="$EGGFUSE_ARTIFACT_ROOT/pass3-atlas-integration-20261120"
families="$EGGFUSE_ARTIFACT_ROOT/repair-bake-families-20261120"
reader="$EGGFUSE_ARTIFACT_ROOT/rotary-axes-20261119/packed-1703/final.pt"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/capture.py" "$families" "$ref" "$reader" "$data" --receipts
python "$dir/feedback.py" "$data"
python "$dir/feedback_study.py" "$families" "$ref" "$reader" "$data" "$data/paired"
python "$dir/feedback_study.py" "$families" "$ref" "$reader" "$data" "$data/guard" --mask-study
for seed in 1703 1709; do
  python "$dir/isolate.py" "$families" "$ref" "$reader" "$data" "$data/isolation-$seed" --checkpoint "train-$seed-2/actor.json"
done
python "$dir/exchange_study.py" "$families" "$ref" "$reader" "$data" "$data/exchange"
python "$dir/bootstrap_check.py" "$families" "$ref" "$reader" "$data" "$data/bootstrap"
```
