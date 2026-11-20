# When should the CPU actor open more emission rows?

Two shared predecessor-state gates certify over 98% of the full Pass 3 result on the current source programs. This study keeps the accepted policy, source program, full Rust graph and ordered commit intact and places a scheduling decision in the single-independent-witness emitter. Every active row scores a disjoint subset of live typed addresses, then hands its own root tokens to the common source verifier. All rows in one rule occurrence see the same preceding neural state. Their actual emissions form the next state. The trained row controller chooses the resource assignment, not the source rule, candidate address or verification verdict.

The tested upper bounds are 1, 2, 4 and 8 rows. Each row owns a contiguous stable range of addresses. Its two execution choices are ordinary independent FP32 scoring or reusing a previous score within that row for exactly identical inputs. In the certified model only freshness varies within one rule occurrence, so each row can cache two logits. Rayon workers share an immutable typed table snapshot and never access the non-thread-safe native graph; merge order, publication versions, conflict handling and commit remain serial in the original executor. Changing row width preserves the generated addresses, even when two addresses share an e-class. The sensitivity of different proof roles or work-claim identities to RL was studied separately in [row ownership](../row-admission/README.md).

## Frozen controller training

The controller has five causal inputs: transformed candidate count, LHS length, number of source input slots, certified/high mode and one component of the previous actor latent. Outputs are eight joint actions (one width and one score-sharing choice). Two, eight or 32 tanh units give 36, 120 or 456 trainable parameters on top of the frozen generator. Training samples are real rule invocations from affine-twins, clamped-ramp, segmented-prefix and window-laplacian. They contain no labels, costs or windows from the evaluation programs. Each logged training invocation measures every width/score-sharing action at the identical causal state; even the diagnostic alternative evaluations must yield exactly the selected logits.

Since these actions preserve the generated tokens, they leave the next source state invariant. A one-step contextual bandit is sufficient for this scheduling objective. The policy-gradient arm samples one action and consumes that action's measured Rust time as its cost. The incumbent single-row memoized treatment supplies an action-independent baseline. An entropy term encourages exploration. A supervised arm uses the cheapest measured action as its class. All controllers take 360 updates, batch size 128, an Adam learning rate of 0.012, gradient norm clip 1, entropy coefficient 0.001 for policy gradient, and seeds 1703 / 1709. Each maximum width is masked during training and testing. At deployment the greedy small head runs in Rust; PyTorch fits it offline. Controls use fixed widths, an arithmetic size threshold, and eight logical rows on a single worker.

The captured training family windows contain 4,146 / 4,090 measured contexts per seed, shared by both policy methods. Across both seeds and each frozen generator regime the candidate sizes have median 15, 90th percentile 135, and max 245. For at least two candidates, real multiworker scheduling is slower on almost all training samples. At one candidate all nominal widths execute the scalar path, so apparent differences there are timer noise. The trained h8 policy-gradient controller overwhelmingly chooses a single row and memoizes scores. A fitted width that mostly abstains from opening extra workers is an observed outcome, not evidence of useful parallel speedup.

## Full-schedule validation

Each arm is compared with the original native policy and checked against gold *after* the run. The checker verifies:

* Ordered RHS and effective write digests for each Run, Spine resumes, union sequence, schedule, and final typed graph.
* Every actual neural root and child global ordinal, including the source rule, physical port and publication ticket recorded by the unmodified verifier. Each reported fresh physical id comes from an actually consumed primary/nested recipe. The audit compares the complete root-commit, allocated-id, merge-child and witness ledgers between semantically identical forward arms.
* A streaming hash over **all** single candidate score bits, decision bits, native handle and version in source order, including rejected/abstaining candidates. Multi-parent raw stream hashes also agree. The pre-issuance proof treatments deliberately change which raw candidates reach the network; their source alignment and physical/RHS coverage are checked separately.
* Timings are complete, resident Pass 3 inference, including real worker dispatch, observation maintenance, policy evaluation, validation, residual search, rebuild and ordered commit. Setup/teardown, worker creation, graph export and source audits occur outside this stopwatch. Paired order rotates and reverses. A feature-matched runtime with the policy disabled is labeled `exact`. The separate `vanilla` executable is the unmodified default-feature CPU; use the latter for the parity or 2× goal.

## What changes actual work

1. **Snapshot and score ownership.** An immutable ordered snapshot of source handles is retained while its input table generation stays current. General gates include the exact original feature values. The certified gate needs only a visible row epoch and static plan shape. Distinct scoring rows own disjoint ranges; they never make overlapping claims. Sharing a logit inside a row saves arithmetic; each address still receives its own real emission decision.
2. **Page of dynamically selected addresses.** After scoring, a row seals one immutable page for all of its activated candidates. The page shares template, epoch, originating rule and pivot, and explicitly writes every dynamic (kind, address, publication version) triple. A token is its page reference and position. Every row's page is finished before the first suffix check; decompression and source version validation use the original graph. Runtime storage for the pointer and allocator is distinct from measured wire bytes.
3. **Register verifier and delta frontier.** The normal proof generator remains unchanged. A dense reusable native slot array checks repeated operands and source literals and projects typed RHS inputs, using original primitive semantics. On seminaive rules, an old root can be rejected at once if no suffix relation has a visible epoch at the watermark. Additional arms cache checked source rows, point reads and entire old verification outcomes by table generations and union generation. For the exact-proof cache, the current watermark must be at least the earlier watermark. Only pure known primitives are admitted; old positives recheck their epoch.
4. **Zero-row eligibility.** A later ablation eliminates whole impossible input blocks before the model runs. If a query table has no source members it abstains outright. If only the pivot can be fresh, it exposes just the fresh part of that table. This changes the actor's observed bank and recurrent history. Separate source-winner, raw score and directly allocated-cell counts apply to this arm.

## Measured complete-pass costs

At seed 1703 on sum-bits, eight repetitions of the fixed-width comparison gave 85.1 ms for one worker with shared scores. Two, four and eight real workers took 106.3, 124.4 and 160.1 ms. Eight logical rows constrained to one worker took 85.5 ms. The four/eight-worker paths report simultaneous participation in actual source invocations, but these are small per-rule barriers. They do not amortize wakeup time. For all 3,244 sampled training observations per regime with at least two addresses, the fastest measured kernel used one worker. Fixed eight-row worker microtimings on one-address calls measure the same one-row implementation and should not be ranked.

Across four held-out/anchor programs and two seeds, the 120-parameter policy-gradient controller with maximum eight improves the original full neural path by a median 9.4% (certified) or 8.2% (selective). A single statically memoized row improves the same paired runs by 9.6% or 9.5%. Increasing the controller to 456 parameters did not establish any additional benefit. The policy learned to avoid parallel dispatch, rather than learning new source matches. [Fixed width](width.json) · [RL and parameter sweep](policy.json)

On sum-bits/1703 certified, row page construction reduced encoded root payload from 6,924,704 bytes to 3,934,848 bytes and complete inference from 83.6 to 81.1 ms in its own paired run. All five verifier controls were exercised on both anchor programs and four root encodings. Wrong version, wrong template, withheld and shadow roots produce no directly allocated primary Cells when source fallback is allowed. [Paged roots](pages.json) · [Failure controls](controls.json)

For the four original programs the register/checkpoint study compares (0) native per-row unique point verifier, (1) dense registers, (2) register verifier with table freshness frontier, (3) versioned row/key decode caches, (4) whole typed binding/negative caching. Across the certified pairs, the median improvement relative to (0) is 2.4%, 5.0%, 4.1% and 2.1% respectively. On sum-bits/1703 the freshness proof retires 20,405 verifier checks. The proof cache resets 2,567 times in 2,569 source invocations and has no positive or negative hits. The study therefore uses mode 2 for the compact candidate on the larger workloads. [Verifier ablation](verification.json)

| Certified CPU, complete median ms 1703 / 1709 | Vanilla default CPU | Joint learned (checked slots) | Batched rows + register/frontier | Source RHS / directly created physical ids |
|---|---:|---:|---:|---:|
| sum-bits | 22.0 / 22.2 | 90.0 / 90.7 | 75.0 / 75.7 | 7,265/7,265 RHS, 5,867/5,868 ids |
| dot-product | 19.1 / 18.9 | 90.5 / 91.1 | 78.0 / 77.2 | 6,704/6,704 RHS, 5,666/5,682 ids |
| gemm-bias-relu | 43.6 / 43.5 | 264.6 / 283.0 | 219.6 / 231.4 | 15,462/15,462 RHS, 12,866/12,869 ids |
| stable-argmax | 23.7 / 22.7 | 91.8 / 90.6 | 75.8 / 75.3 | 8,190/8,190 RHS, 6,841/6,841 ids |
| jacobi-1d | 119.3 / 119.9 | 1063.2 / 1037.6 | 944.5 / 932.8 | 41,319/41,319 RHS, 32,721/32,819 ids |
| conjugate-gradient | 356.7 / 345.4 | 6412.7 / 6333.4 | 5749.6 / 5712.3 | 131,371/131,371 RHS, 97,026/97,139 ids |

The new Jacobi and conjugate-gradient programs are completely withheld from training. The direct coverage and complete source state still pass on 41,319 and 131,371 RHS respectively. Jacobi received the full learned / fixed worker comparison as well. Single and multiple workers both participate in generation; the single Rust verifier continues to publish all verified bindings in source order. This placement is still substantially slower than vanilla and does not establish parity or justify a public Python dependency. [Paired vanilla comparison](integrated.json) · [Larger source schedules](large-integrated.json) · [Width on Jacobi](larger.json)

On held-out Jacobi and conjugate-gradient the largest single-witness banks have 1,011 and 2,748 candidates. Across the two seeds, each of the 4,628 timed multi-address contexts has a single-worker action as its fastest measured choice. On conjugate-gradient/1703 the 1,024+ bucket does benefit from splitting naïve independent scoring across eight workers (124.3 to 63.8 µs). Equal-input reuse on one worker takes 1.64 µs for the same bucket, which explains why parallel dispatch loses once the scoring computation is shared. [Held-out action costs](heldout-cost.json)

Moving the empty-table/frontier proof *before* scoring materially changes the amount of certified work offered. Across the four original programs and two seeds, adding both checks to the page/register/frontier executor reduces the input addresses by a median 48.8% and emitted roots by 32.7% in certified mode or 44.2% in selective mode. Median paired complete-time savings are 2.2% / 4.5% respectively. In certified mode all RHS retain neural tickets, with at least 99.72% of fresh physical ids directly attributed to verified recipes. Selective minima are 99.81% and 99.68%. For sum-bits/1703 certified, 70,366 offered addresses become 27,299; 48,529 emitted roots become 27,299. Complete inference goes from 76.2 to 74.2 ms, versus 21.9 ms vanilla in that group. The source-proof prefilter saves actual emission/verification work without overcoming the full-path gap. These prefilter timings cover the four original evaluation programs. [Pre-issuance ablation](prefilter.json)

## Reproduction

Use the external EggFuse workspace, native Rust and Python/PyTorch offline. Build the pinned benchmark crate through the shared [joint witness harness](../joint-witness/build.py); all output directories below should be new.

```sh
d=benchmarks/pass3-cell-gpu/adaptive-row-policy
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-row-runtime"
bin="$e/NEW-row-runtime/session"
python "$d/runner.py" capture "$bin" "$e" "$e/NEW-row-capture" --rounds 3
python "$d/train.py" "$e/NEW-row-capture" "$e/NEW-row-weights"
python "$d/runner.py" evaluate "$bin" "$e" "$e/NEW-width" --cases sum-bits dot-product --regimes certified --rounds 8 --arms exact native direct-1 direct-2 direct-4 direct-8 shared-1 shared-2 shared-4 shared-8 serial-8 cohorts
python "$d/runner.py" evaluate "$bin" "$e" "$e/NEW-policy" --weights "$e/NEW-row-weights" --rounds 6 --arms exact native shared-1 policy-gradient-h8-r1 policy-gradient-h8-r2 policy-gradient-h8-r4 policy-gradient-h8-r8 supervised-h8-r8 policy-gradient-h2-r8 policy-gradient-h32-r8
python "$d/runner.py" evaluate "$bin" "$e" "$e/NEW-verifier" --rounds 6 --arms native exact verify-0 verify-1 verify-2 verify-3 verify-4
python "$d/negatives.py" "$bin" "$e" "$e/NEW-negative"
vanilla="$e/compact-vanilla-20261121"
holdouts="$e/compact-holdouts-20261121-v1"
python "$d/runner.py" evaluate "$bin" "$e" "$e/NEW-prefilter" --vanilla-timed "$vanilla/vanilla" --encoding checked_slots --rounds 6 --arms vanilla verify-2 prefilter-1 prefilter-2
python "$d/runner.py" evaluate "$bin" "$e" "$e/NEW-large" --vanilla "$vanilla/vanilla-audit" --vanilla-timed "$vanilla/vanilla" --encoding checked_slots --large "$holdouts" --cases jacobi-1d conjugate-gradient --regimes certified --rounds 4 --arms vanilla native verify-2
python "$d/shift.py" "$bin" "$e" "$holdouts" "$e/NEW-heldout-cost"
python "$d/verify.py"
```

The [runner](runner.py) accepts `--large` for separately frozen compiled bundles, `--vanilla` for the default-runtime audit worker, and `--vanilla-timed` for the normal binary. `--encoding checked_slots` applies the same immutable candidate schema and owned-slot transfer on each arm. The archive keeps one independent [source schedule and graph digest](source-hashes.json) per workload. The native output contains the original ledgers and saved scores. `package.py` archives the compact matrices after all production trials finish.
