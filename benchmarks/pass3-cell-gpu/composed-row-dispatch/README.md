# Row dispatch after shared headers and lazy arithmetic

This study tests the two frozen contextual-bandit row controllers on the combined port configuration of the standalone Cell CPU executor. The earlier training study captured four distinct programs with at most 245 candidate addresses per invocation. Sum-bits and conjugate-gradient are evaluated at seeds 1703 and 1709. A larger frozen 3mm Pass 3 is evaluated at 1703. None supplies training labels, costs or model updates. [Original row training and frozen weights](../adaptive-row-policy/README.md) · [Composed CPU source configuration](../composed-cpu/README.md)

## Baking a one-row decision

The eight actions choose a width in {1, 2, 4, 8} and whether to reuse equal-input scores inside each row. A 120-parameter policy scores them from five inputs. On the certified actor profile, these inputs have workload-independent bounds:

| Feature | Inclusive bound | Source contract |
|---|---|---|
| log2(1 + offered address count) / 12 | [0, 6] | The count fits the native 64-bit address space. |
| LHS atoms / 16, input slots / 16 | [0, 2] each | Both static counts are clipped to 32 before scaling. |
| Certified-input flag | {1} | Read from the frozen source actor configuration. |
| Previous first latent component | [−1, 1] | The initial value is zero and each recurrent update uses tanh. |

For each hidden neuron, the Bake computes a rational interval for the affine preactivation using the frozen binary32 coefficients. At each multiplication and addition it bounds roundoff by 2⁻²⁴ times the magnitude plus one minimum binary32 subnormal. It rejects intermediates outside the conservative finite range. A preactivation with stable sign maps to either [0,1] or [−1,0] using tanh's sign and range. To compare actions, both output scores must use the *same* hidden vector. The bound first subtracts their coefficients coordinate by coordinate, then subtracts an independent accumulation-error allowance for each output. Strict positive margin against every other action certifies a constant choice.

The minimum proven score margin of action 4 is 0.240530 (seed 1703) and 0.276435 (1709). Thus the policy chooses one row with within-row reuse over the whole certified domain, even for graphs with more candidates than any training graph. A host can compile that controller to a fixed action and omit its separate worker pool. The underlying generator still reads the preceding hidden state, evaluates model logits, generates addresses and verifies them. Both independently fitted supervised heads remain dynamic under this sufficient test. A tied head, an uncertified actor and a training-capture request keep their existing configuration. [Certificate and lowering](certify.py) · [Frozen coefficient digests and margins](certificates.json)

## Experiment contract

The original composed binary serves all learned variants. Fixed direct scoring computes a fresh score for each address. Shared scoring caches exactly equal inputs separately within each row. The two eight-worker variants dispatch actual Rayon jobs, and an eight-row single-worker arm measures partitioning without worker synchronization. The policy-8 arm runs the trained network with all eight choices enabled. The fixed shared one-row configuration (archived as `off`) is identical to the previous composed baseline and to the configuration returned by the certified lowering. The compiled pool is created during engine setup outside the normal inference timer. Native source verification, ordered RHS, repair and publication run inside that timer.

The independent vanilla executor supplies ordered RHS inputs, effective writes, Spine, union sequence, schedule and final graph. Separate heavy audits compare raw single scores and addresses including abstentions, multi-parent receipts, winners, relevant allocated physical Cell IDs and downstream children across each configuration. Four interleaved resident samples per program and arm follow warmup, with rotated order. Three additional profile samples per arm at seed 1703 collect phase breakdowns. The profiled API round trip includes per-request setup, response and telemetry serialization and local JSON decoding.

## Timings and work

| Program / seed | Vanilla ms | Single shared ms | Direct 1 / 8 workers ms | 8 shared rows, 1 / 8 workers ms | Trained cap 8 ms |
|---|---:|---:|---:|---:|---:|
| sum-bits / 1703 | 23.26 | 35.22 | 34.17 / 75.00 | 35.61 / 73.95 | 34.97 |
| conjugate-gradient / 1703 | 369.99 | 673.26 | 689.34 / 967.40 | 639.91 / 964.72 | 673.43 |
| 3mm / 1703 | 917.23 | 1,946.31 | 2,006.61 / 2,377.61 | 1,914.25 / 2,418.36 | 1,910.80 |
| sum-bits / 1709 | 22.21 | 34.01 | 33.18 / 72.40 | 33.33 / 71.59 | 33.18 |
| conjugate-gradient / 1709 | 350.77 | 660.04 | 650.94 / 966.79 | 655.77 / 963.61 | 652.52 |

On 3mm, the model considered 845,168 single-parent addresses in 9,100 invocations. The compiled one-row dispatch evaluated 8,611 logits. Splitting the input into eight contiguous slices made 50,109 evaluations because each slice restarted its equal-input cache. At 8 workers, 5,280 invocations used multiple physical worker threads, eight at peak. The eight-worker shared arm lost all four whole-pass pairs to the compiled one-row arm. A one-worker, eight-row arm and the dynamic controller each won only two of four. Variation among identical scoring decisions does not demonstrate a speed gain. On conjugate-gradient the corresponding evaluations were 5,531 and 32,487 for 243,383 addresses. All programs preserved the original addressed single-parent decision digest and actual source and allocation ledgers. [Native seed 1703](seed1703.json) · [Second seed](seed1709.json)

| Single-parent phase at 1703, median ms | sum-bits | conjugate-gradient | 3mm |
|---|---:|---:|---:|
| Headers, filters and dispatch selection, compiled one | 1.69 | 48.68 | 164.66 |
| Score, compiled one | 0.18 | 0.92 | 1.89 |
| Score, forced shared eight workers | 25.41 | 173.95 | 269.50 |
| Issue and seal tokens, compiled one | 0.32 | 8.33 | 26.00 |
| Verify and assemble bindings, compiled one | 2.55 | 98.19 | 315.92 |
| Complete profiled inference, compiled one | 32.73 | 672.48 | 1,929.41 |

Even deleting the measured scoring interval would recover only 0.10% of 3mm's current time. Subtracting *all four* profiled single-parent intervals from their own complete sample gives a median remainder of 1,420.94 ms on 3mm. This is an accounting ceiling for removing just these measured intervals with all other costs fixed. Workload interactions could change those costs. The independent CPU control took 917.23 ms in the uninstrumented matrix. Reaching parity needs gains beyond this single-parent path. These row actions share one rule occurrence and state. They do not measure rows independently proposing distinct rules, concurrent exact checking, or parallel ordered commits. [All four phase clocks, inference and API times](phases.json)

## Reproduction

Use the existing composed build and distinct empty output directories. The dispatch weights and certificate verifier are in this checkout.

```sh
d=benchmarks/pass3-cell-gpu/composed-row-dispatch
bin="$EXP/composed-cpu-profile-v1/session"
python "$d/study.py" "$EXP" "$bin" "$EXP/row-run"
python "$d/study.py" "$EXP" "$bin" "$EXP/row-repeat" --seed 1709 --cases sum-bits conjugate-gradient
python "$d/study.py" "$EXP" "$bin" "$EXP/row-phase" --phases --repeats 3
python "$d/certify.py"
python "$d/verify.py"
```
