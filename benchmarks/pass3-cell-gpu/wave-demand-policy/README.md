# Predict physical demand for an entire issued wave

A forecast made at Run entry can allocate a Cell for a rule that subsequently issues no candidates. This native CPU study moves the decision to the point at which every singleton page and multi-parent tuple in the first wave has been sealed. At this point the issuer can count its own proposals. No rule has begun exact validation. A shared model predicts one number per active nonempty rule. The allocator apportions the bounded physical budget and immediately initializes the private headers and their fact buffers. Each original authenticated winner can redeem a slot from its rule's group. The actual schedule still determines whether and when the Cell becomes visible.

The original eight-weight forecaster and all three new eight-weight heads consume previous Run statistics and static dimensions for the rule. The new heads also consume the current sealed size. Balanced and coverage optimize the median and upper (0.8) count quantile. Fraction uses binomial loss on actual births out of the issued candidates. We trained on sum-bits, dot-product and Jacobi, then froze the heads. Details and reproducible coefficients are in [training notes](TRAINING.md) and [policy.json](policy.json). CG, 3mm and Deriche were held out. The small programs in the second seed matrix check executor transfer with a different issuer; their programs were present in demand training.

Entry prebuilds at Run entry. Delay uses its original forecast, deferring allocation until the first wave. Entirely empty Runs incur no allocation in the delayed arms. Clip additionally limits each request to its actual number of proposed lanes before the ordinary 8,192-slot apportionment. Balanced, coverage and fraction also bound each local request by its issued lane count. They may change total reservations. This is a count/consumption ablation at a fixed maximum budget. Record and byte totals need not be identical. All deployment arms keep the same online parent issuer and exact validator. Detailed audit independently recomputes each Run's grants from reported features and the original tie order.

| Program, seed 1703 | Allocation | Granted | Used by a real fresh Cell | Full inference ms |
|---|---|---:|---:|---:|
| CG | Entry | 97,293 | 59,752 | 664.07 |
| | Delay | 92,710 | 59,752 | 664.51 |
| | Clip | 72,960 | 59,752 | 683.82 |
| | Balanced | 82,032 | 67,789 | 671.10 |
| | Coverage | 144,587 | 92,294 | 693.98 |
| | Fraction | 95,272 | 71,506 | 652.43 |
| 3mm | Entry | 232,796 | 137,864 | 1,950.82 |
| | Delay | 220,344 | 137,864 | 1,883.43 |
| | Clip | 172,575 | 137,880 | 1,957.28 |
| | Balanced | 189,115 | 156,095 | 1,983.62 |
| | Coverage | 346,293 | 213,922 | 1,924.58 |
| | Fraction | 232,068 | 168,804 | 1,981.24 |
| Deriche | Entry | 480,737 | 318,024 | 3,531.65 |
| | Clip | 400,568 | 318,992 | 3,648.59 |
| | Coverage | 660,171 | 417,156 | 3,593.16 |
| | Fraction | 458,570 | 346,056 | 3,598.94 |

The 3mm fraction head evaluated 11,934 nonempty groups. It served 30,940 more real births than entry while constructing 728 fewer records. Its cumulative header and fact-buffer capacity was 72.32 MB versus 72.88 MB for entry. Coverage served 213,922 of 228,095 actual fresh primary Cells (93.8%) but prebuilt 132,371 records nobody used. The same issuer without staging took 624.03 / 1,868.90 / 3,402.15 ms on CG / 3mm / Deriche; the default exact CPU took 328.12 / 869.29 / 1,530.53 ms. More accurate physical forecasting alone did not catch the default engine. Each timing is the median of four rotated inference samples after warmup. Per-pass record totals accumulate work across Runs; they do not measure resident memory or the number of live records at the endpoint.

For seed 1709, fraction on CG used 71,527 of 95,358 reservations, compared with 59,744 of 97,392 at entry. The two modes ran in 673.90 and 667.95 ms. The network selected the same parents in all allocation arms of each seed. All comparisons check ordered source RHS, effective writes, Spine continuations, union and final graph, winning parent identities and physical Cell IDs. Original exact matches do not supplement missing neural proposals.

To reproduce from this directory, use the shared experiment root and allocator-matched default CPU binaries from the original native witness study.

```sh
python build.py "$EXP/new-wave-demand"
native="$EXP/new-wave-demand/session"
python study.py "$EXP" "$native" "$EXP/new-wave-holdout"
python study.py "$EXP" "$native" "$EXP/new-wave-transfer" --cases deriche --modes clip coverage fraction
python study.py "$EXP" "$native" "$EXP/new-wave-seed1709" --seed 1709 --cases sum-bits dot-product conjugate-gradient --modes clip coverage fraction
python audit.py "$EXP" "$native" "$EXP/new-wave-curves" --cases sum-bits 3mm
python audit.py "$EXP" "$native" "$EXP/new-wave-tight" --cases sum-bits --cap 64 --modes clip coverage fraction
python controls.py "$EXP" "$native" "$EXP/new-wave-faults"
python verify.py
```
