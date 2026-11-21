# Refill vacant Cell headers across Runs

This native EggFuse Cell CPU experiment keeps the group voucher issuer, forecast weights, complete Run budget (8,192), proposals and ordered commit checks identical. Both arms use the same executable and 64-slot maximum page width. The `off` arm allocates fresh slabs for each Run's grants. The `dense` arm first fills holes in partially occupied pages. Each newly accepted Cell receives its original logical ID and becomes visible at the same ordered commit in both arms.

On a nonempty forecast with available holes, the allocator enumerates current live pages. It orders partial pages by occupancy fraction, breaking ties by available space and physical page index. It constructs each private Cell in its destination lane and freezes its header address there. The Run's grant map translates the ordinary voucher ordinal to that slot. Remaining grants get new pages. Existing Cell headers stay at their original addresses. Partially occupied pages touched this Run are held until its last possible commit, even if an older resident retires during verification. At Run close each page drops unused private Cells and releases its allocation if empty. The next Run enumerates extant pages afresh, so freed page indices cannot appear as stale hole entries.

Counters distinguish placements into old holes, successful publications there, new pages actually allocated, grants requiring no new pages, and Runs with zero grants. A page avoided is the difference between the pure append allocator's page count for this exact grant vector and the new pages actually allocated. Hole-slot × Runs sums retained empty lanes at each close, including empty Runs. Profile metadata records directory scans, ranked partial pages, lane inspections and auxiliary grant-map capacity.

## Paired results

| Workload | Whole-Run grants placed in old holes | Published from old holes | New pages, append → dense | Terminal empty lanes, append → dense | Held empty lane × Runs, append → dense | Native inference, ms | Whole-process RSS, MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| conjugate-gradient | 67,592 / 97,293 | 45,341 | 2,396 → 802 | 40,721 → 1,004 | 60,379,173 → 1,090,998 | 678.49 → 654.97 | 469.19 → 462.88 |
| 3mm | 148,101 / 232,796 | 96,780 | 4,954 → 1,691 | 74,367 → 1,346 | 188,695,004 → 3,157,905 | 1,825.58 → 1,869.58 | 753.70 → 746.64 |

The four measured native times per arm overlap on both workloads. The observed medians move in opposite directions. The stronger result is reduced retained storage on both workloads. CG granted 758 nonempty Runs entirely from old pages and had 1,714 zero-grant Runs. The corresponding 3mm counts were 1,313 and 2,429. Rebuilding the density ranking on demand inspected 419,935 page-directory entries and 619,073 lanes on CG, and 1,184,039 entries and 1,918,868 lanes on 3mm. Those are operation counts. Their independent time contribution was not isolated.

[Full source checks and timing samples](results.json) · [RSS samples](rss.json) · [Fault controls](faults.json) · [Lifecycle fixture output](test.txt)

## Reproduction

Run from this directory with the frozen artifacts used by the resident-slab study. Timings come from repeated complete Pass 3 inference in persistent native sessions. Whole-process RSS uses fresh processes, including setup and export. The separate sum-bits fault runs exercise withheld, stale, foreign and duplicate grants. A native lifecycle regression exercises reuse of a retired physical address with a new logical ID, retirement while a page has unpublished grants, and stable neighbour addresses.

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/recycle-build"
python3 probe.py "$exp/recycle-build" "$exp/recycle-fixture"
python3 faults.py "$exp" "$exp/recycle-build/session" \
    ../speculative-allocation-policy/policy.json "$exp/recycle-faults"
python3 study.py "$exp" "$exp/recycle-build/session" "$exp/recycle-time"
python3 study.py "$exp" "$exp/recycle-build/session" "$exp/recycle-rss" "$exp/recycle-time/results.json"
python3 verify.py
```
