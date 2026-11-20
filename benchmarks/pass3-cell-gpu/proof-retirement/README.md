# Retiring generated proofs at their source boundaries

Figure 63 follows the frozen GPU-generated root and child streams from the [paired pending-parent study](../recurrent-generator/compound_study.py). It measures two distinct claims. A **Spine input** names the exact parent output and publication ticket. A **constructor-presence claim** says that a particular constructor record was produced at a particular Run. Two different rule applications can establish the second claim while publishing distinct tickets. The verifier preserves the original ticket wherever the first claim is required.

## Pending child retirement on the full Pass 3 executor

The study replays only the model's token payload into the real GPU verifier. Both policies inherit the original schedule, ordered commit, union/rebuild and exact completion. The input contains no reference RHS or source winners. Each child can wait across source Runs. At the original boundary the verifier checks its parent, the physical row, the publication ticket and the residual compiled rule. Two rows issue a batch. The policies differ only in which unresolved children they discard when a parent has no accepted root mark or a pending child's source becomes hidden or has a new ticket.

- **Batch.** Retire that child plus any still-pending sibling from the same issue Run. Already published RHS remain in source order.
- **Dependencies.** Retire only the child of the failed root or the exact invalidated input ticket. Independently sourced siblings continue until a valid original publication boundary or a subsequent failure.

Both policies run on the same online-generated stream. We check complete ordered RHS inputs, writes, Spine events, unions, roots and the final typed graph against the source-aligned reference. Neural-origin coverage in this replay refers to the bindings supplied by frozen neural tokens. Live neural forward overhead is outside the comparison. Six paired, alternating resident samples include verification, retirement, ordinary GPU residual search, commit and synchronization. Each timing sample starts from a reset graph. A separate audit checks every surviving child against the frozen root token, the original parent RHS, its effect port, the publication ticket actually consumed by the matching source event, and the distinct ordered RHS ordinal. [Source audit](source-audit.json)

**Observed invalidations** use only source activity that really occurred. The second series **injects an invalid physical parent** in the first genuine fork where both independently sourced children originally won. The sibling's token, parent, program and boundary are unchanged. A per-fork audit also records how many coarsely retired children actually won under dependency-sensitive retirement. [GPU pending checks](retire.metal) · [Full-source replay and per-Run checks](study.py)

| Real source stream | Distinct child RHS, batch vs dependencies (1703 / 1709) | Whole replay median ms, batch vs dependencies (1703 / 1709) |
| --- | --- | --- |
| sum-bits | 23 / 15 vs 25 / 26 | 923 / 927 vs 940 / 935 |
| dot-product | 17 / 14 vs 17 / 16 | 952 / 969 vs 971 / 1012 |
| gemm-bias-relu | 23 / 12 vs 23 / 20 | 2930 / 2899 vs 2965 / 2946 |
| stable-argmax | 16 / 14 vs 17 / 18 | 983 / 963 vs 932 / 960 |

Across these eight trajectories, whole-batch invalidation retired 39 still-pending siblings, including 28 whose original proposals won under dependency-sensitive retirement. The two seeds and four programs are repeated conditions, so this sum is a count of replay events. Fine retirement retained more useful work on six trajectories; wall-clock improvement appeared only on the two stable-argmax trajectories. On the dependency-sensitive path, 20 pending children lost a physical source row forwarded by rebuild, 24 lost their publication ticket after a new publication, and none became stale solely through subsumption. Children without an accepted root mark are counted separately. [Per-boundary invalidations and six paired samples](retirement.json)

## Preserving alternate fact proofs

The original child pointer has one parent. The support experiment also reconstructs a second observed edge type. When a later submitted root selects a physical row already published by an earlier committed neural proof, it checks the reference winner's anchor, pivot, versioned ticket and actual producing RHS. These edges allow deeper dependencies across source Runs. Only the observed anchor is traced; the other checked LHS conditions are held fixed. The policy has not learned an arbitrarily long explicit parent-pointer chain merely because such an anchor connects two waves.

For every constructor publication by a submitted neural binding, the audit groups the evidence by source Run, typed table and physical row. A separate source-aligned GPU replay observes each proposed view after that Run's publication and rebuild, before the following Run searches. Only physical rows actually visible at this boundary enter the constructor-membership comparison. A published-then-forwarded row is recorded in the publication count and excluded from the live membership set. [Boundary capture](visibility.py) An output shared by distinct RHS ordinals has independent *candidate supports*. Whether one support survives a particular withdrawal is determined by its own ancestors. Two tokens with the same source ordinal count once. Repeated effects of a single proof count once. Neither the backing exact engine's alternative proofs nor equivalent-looking rows are added as neural supports.

With each real stream completely generated, the GPU withdraws each submitted root individually at its issue boundary. Every withdrawal is an **injected counterfactual**. The pending or accepted state of other proofs is checked against their original issue and publication bounds. Coarse retirement also removes still-unpublished siblings. Dependency retirement follows the exact provenance edges. If any constituent proof is lost, a constructor view without support counts is dirtied and must check its alternative sources. The third policy maintains counts of invalidated distinct supports and keeps the view available whenever any valid proof remains. This changes both the actual GPU memory reads and the measured number of alternate-source checks. A separate CPU worklist derives the loss epoch and surviving membership for every scenario.

This study accounts for constructor-presence views on the captured proof stream. Its membership timing measures the grouped counterfactual GPU computation with resident evidence, including state reset and synchronization. It does not replace the full Pass 3 timing in the preceding section. It cannot replace a source-specific Spine ticket with a proof for a different publication. [Source reconstruction and independent oracle](supports.py) · [GPU support propagation](support.metal)

In sum-bits seed 1703, 13 same-Run constructor records had more than one neural producing RHS, and 10 remained visible after that Run's rebuild. Nine of the 10 had a common proof ancestor. One had disjoint support. At Run 486, withdrawing #3136 leaves constructor row 2462 in table 223 supported by #3133. Both exact policies retire the original proof if its source is invalid. The support ledger can preserve the separate constructor view. Across the 603 individual root withdrawals on the eight streams, 16 scenario–fact pairs retained independent support after some of their evidence was removed. Neither dot-product seed observed such a survivor. End-to-end timing for the full inference system is given only in the pending retirement comparison above. [Versioned post-rebuild observations](visibility.json) · [Checked GPU support closures](supports.json)

## Equal constructor results with different source tickets

For each **previously successful** child at its exact release boundary, the probe looks for another visible constructor row of the same table. The original raw result identifiers must differ, both rows must have a published cursor, and canonicalization under the *current* union-find must give the same e-class. When such a row exists the fault injection offers the different row with the original ticket. Exact source verification must reject it. The exact fallback still has to restore the whole source output. This is an injected wrong parent using two real rows in the same current graph; its frequency is reported separately from spontaneous stale tickets. The scan is a diagnostic instrument and its time is not reported as verifier cost. [GPU injection at the actual graph boundary](union_probe.py)

43 of the 162 originally winning children across the eight frozen streams encountered such an impostor at their release boundary. All 43 were rejected; each full replay matched the source. For example, in sum-bits seed 1703, the accepted child with RHS #1552 consumes row 1284 and ticket 2105 at Run 133. Row 1209 and ticket 2102 were simultaneously visible with the same canonical constructor result. [Per-case adversarial challenges](union-probes.json)

## Reproduction

Use the external workspace's PyTorch MPS environment with CPU fallback disabled. The source pairs are the Figure 62 real neural streams. Each destination directory must be new.

```sh
dir=benchmarks/pass3-cell-gpu/proof-retirement
exp=/Volumes/EggFuseWorkspace/experiments
families="$exp/repair-bake-families-20261120"
ref="$exp/pass3-atlas-integration-20261120"
reader="$exp/rotary-axes-20261119/packed-1703/final.pt"
policy="$exp/compound-pending-pass3-v1"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/study.py" "$families" "$ref" "$reader" "$policy" "$policy/paired" "$exp/NEW-retirement"
python "$dir/audit.py" "$families" "$ref" "$exp/recurrent-compositions-20261120" "$exp/NEW-retirement" "$exp/NEW-retirement/source-audit.json"
python "$dir/visibility.py" "$families" "$ref" "$reader" "$policy" "$policy/paired" "$exp/recurrent-compositions-20261120" "$exp/NEW-visibility"
python "$dir/supports.py" "$families" "$ref" "$exp/recurrent-compositions-20261120" "$policy/paired" "$exp/NEW-supports" --visibility "$exp/NEW-visibility/results.json"
python "$dir/union_probe.py" "$families" "$ref" "$reader" "$policy" "$policy/paired" "$exp/NEW-union-probe"
```

The two source-run experiments install their shader changes into a temporary sibling layout. They do not modify the production shader or packet. The only switched source is the retirement portion of the pending children kernel; the union probe further instruments it to find the injected wrong source. All other executor code comes directly from the same checkout.
