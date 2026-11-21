# Share preconstructed Cells among authenticated lanes of a rule

The compiler's existing whole-Run predictor produces a count for each active rule and its Cell template before any source parent verification. A largest-remainder allocation limits the full vector to 8,192 private records per Run. The original pooled control hands a free record to an accepted fresh root of that rule. One-to-one named issuance instead attaches the first K actual offered serials to the K reserved records, checking the precise original page and parents at commit. If one of those early candidates is rejected or reuses an existing Cell, a later accepted candidate cannot claim that reservation.

Group issuance freezes the same private count, template, page payloads, root order and graph-visible publication schedule. For every issued page of a rule with a positive grant it retains the original immutable handle, the epoch, rule, template, first serial, lane count and one claimed bit per lane. The grant belongs to the rule and template as a group. A verified fresh parent may redeem a later offer from the same group as long as one of the genuine preconstructed Cells remains. Before taking a free slot, the original source binding must name that exact page lane. Its source epoch, rule, template, serial, origin and ordered physical addresses/versions must agree with the already consumed root proof. The per-page bit is set only after this succeeds. No rejected or merely offered lane enters the graph or receives an ordinary source Cell ID. Private Cell fact-state backing is moved into the live map only at its original source allocation. Unused records and all voucher metadata are released at the original Run boundary.

The page bitmap size is rounded up to whole 64-bit words. It is allocated for pages of rule groups that actually have a grant. Direct record/header and payload capacities are held equal across the three active arms. The extra bitmaps and potentially longer lifetimes of original page handles are additional implementation costs. The reported bitmap size counts its allocated words; it excludes the immutable pages, rule/page metadata and allocator overhead. All page retention, matching, checks and recycling are charged in full resident timing.

The policy is the frozen coverage return head from [the allocation-policy study](../speculative-allocation-policy/README.md), at seed 1703. The default exact CPU is independently run. The remaining four arms use one binary and one complete learned model. A whole-Run wave with staging disabled is the off arm. Every staged arm sees the same pre-verification source candidate stream, per-Run watermarks, physical Cell targets and private cap, then runs the original exact verifier, RHS, Spine and repair. Four rotated full inference samples follow warmup; source compilation, detailed audit and export are outside the inference interval.

## Held-out execution

| Program | Staging off | Pooled | One-to-one named | Group authorized | Vanilla, ms |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient | 634.02 | 670.21 | 673.82 | 655.75 | 338.57 |
| 3mm | 1,860.30 | 1,937.51 | 1,948.71 | 1,993.46 | 894.70 |

| Program | Staged records | Fresh primary demand | One-to-one used | Group used | Pool used | Group serials beyond first K | Authorized lanes | Peak / cumulative bitmap B |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 97,293 | 96,535 | 36,907 | 59,752 | 59,752 | 24,750 | 250,404 | 1,032 / 51,784 |
| 3mm | 232,796 | 228,095 | 78,955 | 137,864 | 137,864 | 63,978 | 897,379 | 2,144 / 141,144 |

Every successful early claim retained its original physical fact-buffer address at publication. Group authorization supplied 22,845 / 58,909 extra real insertions compared with the one-to-one assignment. Its number of claims beyond the first K offers can exceed the additional insertions because source commit order may let a later-issued winner consume the quota before an earlier-issued winner. Unused staged records on 3mm fell from 153,841 to 94,932. Group took less time than named in three of four CG pairs and zero of four 3mm pairs. Holding the same record budget and authenticating a fungible group solves the observed utilization loss. The two timings do not support a general latency gain. [Paired sample/receipts](results.json) · [Frozen program and model identities](manifest.json)

On sum-bits, the unperturbed gate physically used 2,140 records. Replaying the same authentic voucher after its successful redemption triggered exactly 2,140 duplicate rejections without consuming an additional record. Replacing a page lane by a foreign receipt, changing the epoch or withholding the page evidence made zero early claims. Each arm preserved the independent source Run, effective-write, Spine and union ledgers, all winning parent identities, fresh Cells and final graph. [Negative controls](faults.json)

```sh
d=benchmarks/pass3-cell-gpu/group-named-cells
weights="$EXP/speculative-allocation-learning-v1/policy.json"
python "$d/build.py" "$EXP/group-build"
python "$d/study.py" "$EXP" "$EXP/group-build/session" "$weights" "$EXP/group-study"
python "$d/study.py" "$EXP" "$EXP/group-build/session" "$weights" "$EXP/group-faults" --faults
python "$d/verify.py"
```
