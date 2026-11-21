# Learn which compiled, coordinate-addressed page programs to activate

The source compiler gives an eligible rule an alpha-normalized structural signature including repeated relation identities, key positions, bound slots, field types and primitive operations. Relation names and concrete row IDs are unnecessary. The frozen Pass 3 family contains 341 eligible entries and 242 distinct shapes. Each selected shape activates real role-dictionary issuance, direct coordinate lookup, checked local and cross-parent conditions and the compiled deterministic suffix in the native CPU executor. Others keep the original learned proposer and source verifier.

Training uses sum-bits, dot-product and Jacobi. Forced native configurations execute identical source programs, with five paired timing repetitions after warmup. Per-rule clocks cover frame preparation, issuance and validation; the whole-pass benchmark includes additional setup/dispatch costs. Shapes must be observed in at least two training programs and have positive summed median marginal timing benefit to enter a measured library. The first pass freezes up to eight beneficial shapes, or up to sixteen for the one-pass control. In iteration two the native executor actually runs the previously selected eight versus all, revisits the remaining shapes and admits up to eight additional programs. This experiment learns library membership at a fixed template depth. It does not grow the length of the rule itself.

A second comparison fits shared 9- and 81-parameter PyTorch return heads on the same first-round observations. Both use eight static shape features, the signed time difference per invocation, frequency weights and 200 updates. At compile time a positive predicted gain selects the optimized program. An unseen receiving shape can be scored directly. No timing or label from a deployment workload is used to alter its selection. Separate post-training forced measurements estimate work-weighted coverage. Those per-shape returns describe timings from two independent complete passes; only actual mixed deployment can establish an end-to-end result.

| Held-out program | Default CPU | Original | All blocks | First eight | One pass ≤16 | Two rounds ≤16 | Return head 9 / 81, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 343.12 | 628.49 | 619.60 | 616.64 | 645.09 | 638.27 | 633.64 / 643.43 |
| 3mm | 920.21 | 1,870.47 | 1,916.00 | 1,852.41 | 1,918.33 | 1,896.70 | 1,893.77 / 1,953.59 |

One pass selected 15 shapes and two rounds selected 16; they shared 9. On conjugate-gradient the sum of observed positive shape returns was 2.45 ms and the iterated library's estimated net return was 0.46 ms. On 3mm the sum of observed positive shape returns was 6.77 ms and the iterated library's estimated net return was -1.19 ms. Four rotated timing samples, seed 1703; conjugate-gradient also repeats at 1709. Exact source/physical winners, complete raw streams and final graphs agree. A new source program contributed one previously unseen eligible shape and exercised a later union; neither fitted return head selected that shape, while forced deployment executed it and reproduced the source. [Donor measurements and weights](learning.json) · [Holdout](results.json) · [Second seed](seed1709.json) · [Conditional opportunity](weighted.json) · [Unseen source](unseen.json)

```sh
d=benchmarks/pass3-cell-gpu/iterative-page-library
python "$d/build.py" "$EXP/page-library"
python "$d/train.py" "$EXP" "$EXP/page-library/session" "$EXP/page-train"
python "$d/study.py" "$EXP" "$EXP/page-library/session" "$EXP/page-train/learning.json" "$EXP/page-test"
python "$d/study.py" "$EXP" "$EXP/page-library/session" "$EXP/page-train/learning.json" "$EXP/page-test-1709" --seed 1709 --cases conjugate-gradient --arms one-pass iterated return-8
python "$d/evaluate_returns.py" "$EXP" "$EXP/page-library/session" "$EXP/page-train/learning.json" "$EXP/page-costs"
python "$d/unseen.py" "$EXP" "$EXP/page-library/session" "$EXP/page-train/learning.json" "$EXP/new-coordinate-source" "$EXP/page-unseen"
python "$d/verify.py"
```
