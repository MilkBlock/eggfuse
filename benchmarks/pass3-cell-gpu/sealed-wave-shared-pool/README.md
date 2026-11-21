# Allocate a shared physical Cell pool from a sealed Run

The entry model can allocate private records to a rule that later issues no lanes. The compatible pool can lend those records to another rule. Waiting until the wave has been issued lets the allocator suppress such allocations, and also tells it which rules really have offers. These mechanisms interact: suppressing an idle grant can remove backing that another rule would have borrowed.

The native CPU experiment crosses [four frozen demand policies](../wave-demand-policy/TRAINING.md) with the [layout-compatible pool](../cross-rule-cell-pool/README.md). The entry arm forecasts at the start of the Run. Clip keeps that forecast and limits it by each rule's actual offer count. Coverage estimates the fresh count from the sealed wave. Fraction estimates a propensity and multiplies by its offered count. All modes use seed 1703, the same 8,192-record maximum per Run and the same source order. Late prediction sees ephemeral proposal counts before any lane validation. No future fresh label enters the decision.

A delayed wave retains the original immutable candidate pages until the per-class budget is known. At that point every recipient with compatible physical capacity receives its own original voucher, including a recipient with zero personal grant. The class budget, rather than the donor's rule permissions, controls which physical buffer can be used. The original sealed binding, consuming rule, epoch, template, bitmap and pristine storage checks remain in force. The exact source continues to compute every original RHS, union, rebuild and Spine transition.

Each policy is also run with a private span per rule in this exact same binary. We compare its byte capacities, per-Run class budgets, physical backing identity and source evidence with the corresponding shared arm. The four forecasts intentionally need not allocate the same number of records. Source samples are checked against independent default-feature execution. A separate Python audit derives compatible ceilings from the compiled RHS widths and per-rule grant, offer and fresh-birth records. Timings are complete resident inference on fresh graphs. Four rotated samples follow one warmup; detailed audit and offline training are outside this interval.

## Held-out Pass 3 measurements

| Program | Policy | Prebuilt | Used with personal grants | Used with shared pool | From other rules | Unused | Whole inference, ms |
|---|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | entry | 97,293 | 59,752 | 69,855 | 13,809 | 27,438 | 634.53 |
| conjugate-gradient | clip | 72,960 | 59,752 | 64,241 | 9,009 | 8,719 | 624.31 |
| conjugate-gradient | coverage | 144,587 | 92,294 | 94,736 | 3,546 | 49,851 | 660.37 |
| conjugate-gradient | fraction | 95,272 | 71,506 | 80,312 | 16,366 | 14,960 | 652.77 |
| 3mm | entry | 232,796 | 137,864 | 161,160 | 30,149 | 71,636 | 1,963.75 |
| 3mm | clip | 172,575 | 137,880 | 147,392 | 18,032 | 25,183 | 1,979.30 |
| 3mm | coverage | 346,293 | 213,922 | 222,125 | 12,348 | 124,168 | 1,996.38 |
| 3mm | fraction | 232,068 | 168,804 | 189,197 | 34,285 | 42,871 | 1,938.27 |

Clipping the entry forecast removed 24,333 / 60,221 private records. Personal-grant hits changed by 0 / +16, but shared hits fell by 5,614 / 13,768. The entry arm borrowed 3,248 / 7,050 physical records from rules that issued zero lanes. Clipping eliminates these donors and caps nonempty grants that exceed the number of issued lanes. The measured drop includes both effects; this comparison cannot attribute the entire loss to zero-offer donors.

The learned fraction policy also eliminates zero-offer donors. Compared with entry, it prebuilds 2,021 / 728 fewer records yet uses 10,457 / 28,037 more prebuilt Cells. Cumulative header and fact-buffer capacity falls from 30,223,744 to 29,569,408 bytes on CG and from 72,876,416 to 72,317,568 on 3mm. Surplus records still move between nonempty rules. **Pooling remains useful after a model has seen the wave.** The independent layout ceiling equals the number of verified physical uses in all eight runs of the experiment.

The fraction policy was faster than entry in one of four CG pairs and three of four 3mm pairs. Coverage maximized physical hits but was slower than entry in all four pairs on each workload. Clipping was faster in three CG pairs and two 3mm pairs. In this matched series, staging off required 584.08 / 1,889.61 ms and the independent default-feature Cell CPU required 322.35 / 898.31 ms. Every staging policy took longer than staging off. [Full timings and allocation counters](results.json)

Within each policy, the personal and shared allocators consumed identical issued streams and allocated identical private header, fact-buffer and bitmap capacities. The independent source audits align per-Run RHS, effective writes, union, Spine and final graph. Parent identities, winning source serials, nested Cells, ordered commits and the physical ledger also align. With the delayed coverage head on sum-bits, the pool redeemed 5,566 records. Giving a cross-rule recipient the wrong width produced 264 denials and restored the 5,379 personal-grant hits. Wrong rule, stale epoch and reissued page each yielded zero claims. A second attempt after every successful claim triggered 5,566 duplicate denials. [Matched controls and fault evidence](paired.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/sealed-wave-shared-pool
python "$d/build.py" "$EXP/sealed-wave-shared-build"
python "$d/study.py" "$EXP" "$EXP/sealed-wave-shared-build/session" "$EXP/sealed-wave-shared-paired" --paired
python "$d/study.py" "$EXP" "$EXP/sealed-wave-shared-build/session" "$EXP/sealed-wave-shared-heldout"
python "$d/verify.py"
```
