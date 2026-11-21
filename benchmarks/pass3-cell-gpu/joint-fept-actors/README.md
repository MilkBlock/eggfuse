# Factorial test of singleton class actions and multi-parent bucket actions

> **Metric clarification.** Both actors emit descriptions from which the receiver expands source parents. The grouped-arm figures below quantify external transport yield and alternative decision costs. The source checks establish the correctness of that expansion; a correct expansion supplies no evidence that the model named each parent. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

This native benchmark combines two generative actor formats in one executable. Both use the same frozen verified-wave source matcher, scalar-negative filtering, packed-singleton recurrence and original commit order. The four primary arms independently switch each actor on or off. The singleton actor emits a 64-byte rule/table action before reading membership. The multi-parent actor can issue a nine-word descriptor naming a bounded public signature bucket and a verified left source. It uses the donor-fitted three-coefficient policy, selected before the held-out runs. The optional fifth arm retains the pair actor and uses the predeclared donor-trained 113-parameter `reinforce-8` dispatcher to choose a class action or ordinary per-row issuance for each eligible singleton call.

Each action can trigger many receiver operations. For singletons we count all public header visits, eligible sources, scalar rejections, internally generated receipts, two-logit evaluations and recurrent feedback. For pairs we count public-index rebuild decodes and reuses, externally issued descriptors and literals, recomputed receiver postings, raw parent tuples, verified matches and all attempted group gates. Every expanded raw multi-parent source tuple, the ordered root and child proof streams, recurrent decision digest, final constructor witnesses and every source Run must agree. Two corruption controls per workload test the combined native execution with one invalid issuer at a time.

**Denominators.** Let (V) be the number of constructor e-nodes born under verified roots whose original identity remains visible at final export. Forward transport yield divides (V) by class actions, residual singleton packets, bucket actions, residual multi-parent packets and selected children. Each selected nested child receives its own birth; other births are credited to the immediate group or literal that generated their verified root. Bidirectional transport yield also charges one feedback packet per class action. A stricter decision count charges each singleton mask, every unfactored per-row threshold event before scalar rejection, every evaluated pair gate including negative decisions, each residual multi-parent proposal, every child score including declines, and each learned singleton dispatch when active. Low-level head evaluations, public receiver scans and internal join visits are separately reported; the output counts alone cannot establish faster inference.

**Physical bytes.** The new actor and feedback fields use actual fixed-size native byte representations. To give the unchanged native objects a comparable cost, the audit uses eight u64 header words per singleton page, 37 bytes per residual singleton record, six u64 header words per residual multi-parent page, four u64 fields per externally issued multi-parent reference, and length-prefixed compact issue-time JSON per selected child. Group-generated receiver postings and internal materialized root receipts remain charged as execution work. The reported size describes the declared representation in a single process, not network transfer throughput.

**OS memory.** Separate fresh native processes run macOS libproc RSS sampling at one-millisecond intervals during inference, using the shared native-window profiler. Three baseline calibration runs determine the common absolute 50% and 90% baseline-rise thresholds for each workload. Each arm has three new measured processes. The separate frozen-gate comparison gets its own baseline calibration and paired baseline. A sample that starts above the threshold or never reaches it is reported explicitly. Raw traces retain their observed timestamps and KiB values. Charged proposal counts and RSS remain separate measurements.

## Full native results

| Workload | Visible originals | Packed transport yield | Singleton only | Pair only | Both | Frozen singleton dispatch + pair |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 2,691 | 0.2125 | 0.3463 | 0.2140 | 0.3502 | 0.3588 |
| conjugate-gradient | 34,595 | 0.1587 | 0.3824 | 0.1593 | 0.3855 | 0.3890 |
| 3mm | 92,658 | 0.1660 | 0.3984 | 0.1667 | 0.4024 | 0.4050 |

| Combined arm | External packets | Transport yield with feedback | Origins per charged decision | Max packets for ≥2 origins per transport packet | Further reduction needed |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits · both | 7,685 | 0.2878 | 0.3436 | 1,345 | 6,340 |
| sum-bits · frozen dispatch | 7,499 | 0.3014 | 0.2705 | 1,345 | 6,154 |
| conjugate-gradient · both | 89,729 | 0.3611 | 0.3793 | 17,297 | 72,432 |
| conjugate-gradient · frozen dispatch | 88,927 | 0.3693 | 0.3198 | 17,297 | 71,630 |
| 3mm · both | 230,239 | 0.3871 | 0.3943 | 46,329 | 183,910 |
| 3mm · frozen dispatch | 228,764 | 0.3931 | 0.3584 | 46,329 | 182,435 |

| Workload | Native inference ms, packed / singleton / pair / both | Native inference ms, separate packed / frozen dispatch + pair | Caller wall ms, separate packed / frozen dispatch + pair |
| --- | ---: | ---: | ---: |
| sum-bits | 34.00 / 34.98 / 33.98 / 35.50 | 33.54 / 34.81 | 71.26 / 71.90 |
| conjugate-gradient | 605.08 / 658.19 / 628.98 / 665.07 | 634.84 / 684.02 | 755.63 / 804.71 |
| 3mm | 1,782.36 / 1,924.65 / 1,831.41 / 1,989.14 | 1,790.99 / 1,910.50 | 2,046.16 / 2,167.97 |

The original effective-node numerators, full raw multi-parent source stream, actual root identities and descendant receipts agree across all arms. The bounded pair actor removed 749 forward packets beyond the singleton actor on CG and 2,341 on 3mm. The learned singleton dispatcher further decreases forward packets on both workloads while introducing its own decisions. Its post-filter transport yield improves, while the stricter yield per decision decreases relative to always enabling both actors.

After always enabling both actors, CG still issued 82,293 ungrouped multi-parent packets (64,413 with zero visible births); 3mm issued 217,830 (165,597 zero-visible). On CG the largest residual multi-parent source rulesets are always-run (32,798), type-analysis (11,844) and context (9,504). On 3mm the same sets account for 100,519, 28,332 and 16,468. Rule 90 (Get and BodyContainsExpr) alone accounts for 6,428 CG and 13,753 3mm residuals. On 3mm rule 243 (BodyContainsExpr, DoWhile, Single, is-inv-Expr) emits 18,823 and rule 249 (DoWhile, two ContextOf atoms, Const, HasArgType) emits 12,448. Even removing the full packet cost of all three largest rulesets’ residual multi-parent traffic would leave 35,583 CG and 84,920 3mm packets. The exact budgets at unchanged numerators are 17,297 and 46,329.

## Fresh-process RSS and common-threshold times

| Workload and comparison | Calibrated 90% absolute threshold, MiB | Sampled peak RSS MiB, packed → actor | First crossing ms, packed → actor | Crossings reached (of 3 per arm) |
| --- | ---: | ---: | ---: | ---: |
| sum-bits · both | 269.47 | 270.64 → 270.58 | 29.5 → 30.9 | 3 / 3 |
| sum-bits · frozen dispatch + pair | 269.46 | 270.66 → 270.56 | 27.5 → 30.7 | 3 / 3 |
| conjugate-gradient · both | 431.51 | 443.80 → 444.23 | 434.8 → 490.2 | 3 / 3 |
| conjugate-gradient · frozen dispatch + pair | 431.55 | 443.86 → 443.73 | 435.3 → 460.0 | 3 / 3 |
| 3mm · both | 669.07 | 697.86 → 692.75 | 1,138.2 → 1,318.0 | 3 / 3 |
| 3mm · frozen dispatch + pair | 667.87 | 698.08 → 692.83 | 1,091.8 → 1,311.5 | 3 / 3 |

The threshold is common within each packed/actor comparison. It is an absolute process-RSS level calibrated from separate packed runs. Crossing it measures memory growth timing; it does not independently identify when later source effects became valid. Full raw OS traces and 50% thresholds are archived with the measurements. [Factorial](results.json) · [Frozen dispatcher](gated.json) · [Factorial RSS](rss.json) · [Frozen-dispatch RSS](gated-rss.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/joint-actor-build"
python3 study.py "$exp" "$exp/joint-actor-build/session" "$exp/joint-actor-factorial"
python3 rss.py "$exp" "$exp/joint-actor-build/session" "$exp/joint-actor-factorial/results.json" "$exp/joint-actor-memory"
python3 study.py "$exp" "$exp/joint-actor-build/session" "$exp/joint-actor-gate" --only-gate --single-policy single-policy.json --gate-model reinforce-8
python3 rss.py "$exp" "$exp/joint-actor-build/session" "$exp/joint-actor-gate/results.json" "$exp/joint-actor-gate-memory" --single-policy single-policy.json --gate-model reinforce-8
python3 verify.py
```

The first and third arms use the same scalar-filtered, packed-singleton issuer. The pair classifier was trained on sum-bits and dot-product. The singleton dispatcher used sum-bits, dot-product and jacobi-1d. CG and 3mm are held out from both training sets. Sum-bits is included as a donor sanity check.
