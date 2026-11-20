# A fixed device budget for root subscriptions (Figure 41)

A region is a 32-row interval in physical order. The bounded engine can keep 32 regions indexed at once, including regions whose last word is still growing. At each 32-Run boundary the GPU can admit, retain or evict them. An admitted region builds reverse subscriptions from its actual current live constructor keys and results. External tables keep ordinary ordered repair. On eviction all its rows reenter the ordinary scan. A reused index slot gets a new generation so old roots cannot wake unrelated rows. Source Run and collision order remain authoritative. This experimental directory is opt-in.

The full directory covers all eligible scalar constructors on insertion. The static arm calibrates a density/dirty threshold over the four train families. The learned arm uses one shared ridge predictor of next-window clean scans minus per-slot notification probes. Inputs are the live eligible row count, equality-port count, recent births, previous dirty inspections, previous repair passes and their interaction with live rows. All features are available at the decision boundary. Both bounded policies pay the same admission proxy for a new region. The coefficients and static threshold were frozen before reading the development and held-out evaluations. Model scores, selection, registration, eviction, notifications, ordered effects and closure all run on Metal. [Fitted policy](policy.json) · [Complete timing and observed costs](results.json)

| Resident inference, ms | Full | Bounded static | Bounded learned | Priced hindsight replay |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 586.6 | 862.5 | 862.7 | 846.2 |
| dot-product | 702.5 | 931.7 | 941.6 | 912.4 |
| gemm-bias-relu (held out) | **2,008.4** | 2,965.6 | 3,010.3 | 3,006.9 |
| stable-argmax (held out) | **640.5** | 923.6 | 935.4 | 914.4 |

On gemm-bias-relu the full directory reserves 33,949,696 bytes. The 32-region arms reserve 4,253,696 bytes including mapping/epoch state, an 87.5% reduction in this index allocation. The learned policy inspected 858,797 repair rows versus 861,857 for the static one and 266,173 for full indexing. It made 160 admissions and 128 evictions and processed 4,840 live rows during setup of regions; static made 32 admissions, zero evictions and processed 1,003. These costs are included in the whole-pass median. Counts reflect all builds, including initial builds. They do not isolate an individual migration's elapsed time.

**Upper bound and causal replay.** For each window, the offline optimizer chooses at most 32 eligible regions. One price unit credits a clean row inspection avoided and charges one resident slot probe per effective union, one eligible live row per admission, and one unit per exit. The minimum-cost integral flow has a slot for each unit, a capacity-one edge for each region/window, and separate carry, exit, idle, and admission edges. Its optimum is exact *for those work prices*. It supplies a hindsight scheduling arm only. Device execution of that arm still performs all actual registrations, generation transitions, scans and notifications. Its measured time can exceed that of the static arm. This work-price optimum is not an upper bound on wall-clock speed. A small exhaustive enumeration independently tests the flow solution.

The full scan capture records features at the **start** of the following window and realized labels when repair actually runs. In the bounded run, every region selected by the GPU agrees with a separate implementation, and realized avoided clean-row counts must equal the actual reduction in scans. Post-hoc [fanout strata](strata.json) separate regions with no observed constructor wake in the preceding window, one affected row per touching union, up to two, and more than two. The static and learned policies use the same candidate set and full online budget. The source identity, ordered RHS, writes, Spine and graph are checked against the previously audited real Pass 3 traces for every arm. Eight fresh-state resident samples per arm rotate the order. Timed samples have work counters off.

```sh
ws=/Volumes/EggFuseWorkspace
r="$ws/experiments/NEW-repair-corpus"
ref="$ws/experiments/pass3-atlas-integration-20261120"
weights="$ws/experiments/rotary-axes-20261119/packed-1703/final.pt"
dir=benchmarks/pass3-cell-gpu/region-admission
python "$dir/capture.py" "$r" "$ref" "$weights" "$r/regions"
python "$dir/study.py" "$r" "$ref" "$weights" "$r/regions" "$r/region-study"
python "$dir/strata.py" "$r/regions" "$r/region-study" "$r/profiles" "$r/region-strata.json"
```
