# Routing a fixed physical allocation budget

The native Cell CPU engine predicts the original per-rule Run budget with the frozen donor-trained entry head, applies the existing global cap, and groups granted headers by the fact-buffer capacity produced by the normal Cell constructor (one to four entries). Every arm physically constructs exactly this many headers and exactly this many fact-buffer bytes in each Run. A quiet Run with an entry forecast still pays for and drops its grants. No fresh-allocation labels are available when routing.

The entry control uses the original rule quotas at Run entry. The delayed original control installs those same rule quotas at the first verification boundary. The other arms redistribute the same four physical budgets to rule groups after proposals have been sealed. They rank demand using the offered-lane count, the original forecast clipped to offers, the donor-trained occupancy fraction or the donor-trained 0.8 count quantile. All four alternatives were chosen before their held-out measurements.

Within each class, oversubscribed demands receive largest-remainder proportional shares with source-order ties. If predicted demand is too small, the router next fills still-unserved offered lanes proportionally. Surplus beyond all available lanes goes back to original donors whose quotas decreased. Physical construction still uses the receiving rule's exact template. At the original source commit each grant requires a matching sealed receipt bound to that rule, template, epoch and instance.

The audit records the original and actual class totals for every Run. From later source commits it computes a retrospective ceiling by summing min(original class budget, same-class fresh demand) over Run and class. An omniscient within-class router could place that many headers if each needed receipt were available. The observed semantics check additionally compares each rule's min(allocated headers, fresh demand) against the number of authenticated physical redemptions. Neither the future label nor the ceiling feeds back into inference.

## Held-out results

| Policy | CG published | CG inference ms | 3mm published | 3mm inference ms |
| --- | ---: | ---: | ---: | ---: |
| At Run entry | 59,752 | 670.48 | 137,864 | 1,933.38 |
| Original after seal | 59,752 | 671.82 | 137,864 | 1,983.61 |
| Offer count | 51,212 | 670.34 | 121,807 | 1,924.95 |
| Clipped prior | 64,467 | 671.31 | 149,920 | 1,926.70 |
| Learned fraction | 63,310 | 669.83 | 148,304 | 1,893.36 |
| Learned 0.8 quantile | 65,896 | 675.28 | 152,991 | 1,944.82 |

CG physically constructed 97,293 headers in every arm. The class-constrained ceiling was 69,855 authenticated hits. On 3mm those figures were 232,796 and 161,160. Compared with original quotas, the learned quantile reclaimed 6,144 of 10,103 possible extra hits on CG and 15,127 of 23,296 on 3mm. Clipping the original forecast and redistributing surplus already reclaimed 4,715 and 12,056 respectively. Within a fixed byte budget, offered lane count alone lost hits on both workloads. Four measured rotated samples per arm put the quantile policy slightly above the original entry median on both workloads, even as it delivered more verified Cells. No stable inference speedup is established.

conjugate-gradient recorded 2,896 Runs, with cumulative preconstruction of 12,453,504 header bytes and 17,770,240 private payload bytes per arm.

3mm recorded 4,260 Runs, with cumulative preconstruction of 29,797,888 header bytes and 43,078,528 private payload bytes per arm.

Seven sum-bits receipt controls preserved source-level RHS, writes, Spine, union and graph. The routed fraction policy authorized 2,734 physical redemptions. Withheld, foreign, stale, unsealed and reissued receipts authorized zero. Replaying valid receipts rejected 2,734 duplicate attempts and kept the originals. [Native results](results.json) · [Fault controls](faults.json)

## Reproduction

Run from this directory with the native Pass 3 workload and donor weights used by the wave-demand-policy study.

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/budget-routing-build"
python3 study.py "$exp" "$exp/budget-routing-build/session" "$exp/budget-routing-faults" --faults
python3 study.py "$exp" "$exp/budget-routing-build/session" "$exp/budget-routing-holdouts"
python3 verify.py
```
