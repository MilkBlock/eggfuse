# Training dispatch between complete parent providers

In some three-parent rules the compiler can replace one independent parent choice with a complete-key function read. This experiment lets a CPU policy choose between the original connected parent issuer and a provider which activates these requests from changed ports. Both providers use the frozen trained port projections, seal source addresses before validation, execute the original Run and retain exact source attribution. The dispatch policy does not generate, suppress or complete a source RHS by itself.

## Training observations and deployment contract

Two forced passes through the real standalone Rust Cell CPU engine supply each paired observation. At the first legal dispatch point, both see identical source Run, rule and causal features. Inputs are three integer log-size bins for the source, function and final parent tables, three booleans indicating whether each table can meet the watermark, whether the remaining suffix is old, and whether the function table has fewer rows than the source. The head has no rule number, program identity, cache-hit log or future binding outcome as an input.

The charging interval starts immediately after dispatch and ends at the return of the source proposal routine. It includes generation, current directory preparation, proposed-page verification and finishing the determinate suffix. Initial common frame and plan preparation, features, gate execution, later source effects and repair are outside this conditional interval; the independently timed full inference includes them. Each training program runs alternating forced arms with one warmup and five measured repetitions. The training return is the difference between median native nanoseconds for that same occurrence.

A nine-parameter affine head and an 81-parameter one-hidden-layer head are fitted in PyTorch at seeds 1703 and 1709. Each receives 250 full-batch updates. The contextual bandit directly optimizes the expected signed benefit of taking the request path, using its Bernoulli probability. A second loss regresses the signed benefit on the same observations. Both use the same training-only scale and weight penalty. The frozen Rust head chooses the request path on strictly positive output. The training and test workloads are disjoint. The deterministic size heuristic selects the request provider only if the suffix is old and its function table is smaller than the root.

A separate post-training capture interleaves three measured repetitions on each held-out workload. It estimates work-weighted coverage of measured positive returns and separately charges negative decisions. The sum of the positive per-occurrence observations is a retrospective opportunity estimate. Each timing came from a complete forced pass with its own cache history. Only deploying the actual policy measures the full-pass consequence of a mixed schedule.

## Held-out results

The capture collected 393 real eligible rule invocations across sum-bits, dot-product and Jacobi. Each bandit policy selected the request route on all 393. Interval propagation further proves this action is constant for any valid native feature vector: the minimum binary32 logit is at least 1.11 / 1.16 for the two affine policies and 0.60 / 0.57 for the hidden policies. The compiler can remove that gate while preserving dispatch on this ABI. The proof uses a rounding bound for ordered binary32 operations, independent boolean inputs and sign/range for tanh. Timing capture and audit requests retain the head. Neither return regression head is constant under the proof.

| Held-out source | Vanilla | Original | Always wake | Size heuristic | 9-parameter bandit / regression | 81-parameter bandit / regression, ms |
|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient, 1703 | 356.40 | 634.74 | 653.78 | 649.23 | 647.39 / 641.53 | 643.97 / 646.44 |
| 3mm, 1703 | 946.74 | 1,926.92 | 1,915.87 | 1,872.18 | 1,877.10 / 1,908.32 | 1,911.46 / 1,917.16 |
| conjugate-gradient, 1709 | 330.83 | 616.37 | 593.40 | 594.77 | 609.14 / 613.87 | 612.19 / 606.72 |

Four rotated resident measurements follow a warmup. Both bandits made identical decisions to always wake, so variation among those full-pass times cannot be credited to a different learned route. The 81-parameter regression policy admitted 115 / 177 calls on conjugate-gradient and 151 / 200 on 3mm at seed 1703. It captured 98.8% and over 99.9% respectively of the separately measured positive conditional opportunity. Its net conditional estimates are 3.2 and 9.1 ms. The sum of all observed positive deltas was only 3.75 and 12.75 ms. An ideal deterministic gate which saw these exact eight features acquired at most 3.60 and 11.97 ms on these measured labels. The conditional experiment exposes the small size of this decision surface; these amounts are not guaranteed savings in a mixed full execution.

The held-out original and all policy arms agree on source Run/RHS, effective writes, union, Spine, final graph, neural winner parents and physical Cell IDs; no residual matcher was enabled. A second seed changes both the projection and the dispatch checkpoint. [Training events](training.json) · [Frozen weights](policies.json) · [Constant-action certificates](certificates.json) · [Held-out runs](heldout.json) · [Second seed](seed1709.json) · [Weighted opportunities](weighted.json)

```sh
d=benchmarks/pass3-cell-gpu/request-route-policy
python "$d/build.py" "$EXP/route-build"
python "$d/capture.py" "$EXP" "$EXP/route-build/session" "$EXP/route-training"
python "$d/train.py" "$EXP/route-training/training.json" "$EXP/route-training/policies.json"
python "$d/study.py" "$EXP" "$EXP/route-build/session" "$EXP/route-training/policies.json" "$EXP/route-test"
python "$d/study.py" "$EXP" "$EXP/route-build/session" "$EXP/route-training/policies.json" "$EXP/route-repeat" --cases conjugate-gradient --seed 1709 --policy-seed 1709
python "$d/capture.py" "$EXP" "$EXP/route-build/session" "$EXP/route-costs" --cases conjugate-gradient 3mm --repeats 3
python "$d/returns.py" "$EXP/route-costs/training.json" "$EXP/route-test/results.json" "$EXP/route-costs/weighted.json"
python "$d/verify.py"
```
