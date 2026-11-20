# A 98% target on complete Pass 3

Count each **committed RHS occurrence in its original Run** once. A model emission can win more than one occurrence when the selected compiled Cell executes several source steps. Every credited occurrence must resolve to a real emitted certificate, survive native validation/deduplication and land at its measured global source ordinal. Static initialization, lookups that merely verify a positive, and additional RHS discovered by exact enumeration are separate. Multiple origins for the same occurrence never increase the numerator. Measure each workload separately. Required count is ceil(0.98 × full source count).

A complementary physical measure attributes Rust Cell allocations to the source RHS that actually allocated them. `--audit-cell-origins` records changes to Graph::stats.cells_created across each committed binding. All allocations after the initial graph enter the denominator, including allocations outside the RHS path. This measures allocation events attributable to a model-won RHS. It does not by itself show the network selected the final physical layout, that all allocations stayed live, or that RSS fell. Logical fact births are separately recorded.

| Workload | Source RHS | Neural RHS required | Maximum other RHS | Zero/one independent witness | Minimum needed from 2+ | Fixed slots/Run needed if one token covers one RHS |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 7265 | 7120 | 145 | 2677 | 4443 | 141 |
| dot-product | 6704 | 6570 | 134 | 2899 | 3671 | 216 |
| gemm-bias-relu | 15462 | 15153 | 309 | 5901 | 9252 | 454 |
| stable-argmax | 8190 | 8027 | 163 | 3278 | 4749 | 269 |

The witness count is structural under a stated interface. A proposed relational row supplies its slots. A complete table key selects at most one visible row; ready primitives can be evaluated forward. Breadth-first search closes these dependencies and finds the minimum independent proposed rows for the source query. It does not exploit inverse primitives, observed accidental uniqueness, prior multi-member Cell proofs, or additional indexes. Current source ordinal counts weight each rule. The per-Run slot lower bound separately assumes perfect choices anywhere in the graph; it sums min(budget, Run RHS). Multi-RHS certificates and adaptable Run budgets require their own measurement. [Per-rule actions and full histograms](source.json)

## Final native acceptance

The joint CPU/Rust executor passes both thresholds in the **same execution**
for four full programs, two seeds and two policies. Selective high recall wins
99.83–99.97% of committed source RHS; the certified single-policy cutoff and
sealed three-view multi-parent policy win all source RHS with residual matching
disabled. Physical coverage uses the allocator-consumed binary root and dependent
merge recipes: new ids must actually be created from the verified recipe's
template and bound ports. With the certified cutoff the fractions are
5,867/5,868 (sum-bits), 5,666/5,682 (dot-product), 12,866/12,869 (GEMM) and
6,841/6,841 (stable-argmax), on both seeds. Withholding matching recipes
eliminates their direct allocation credit. Learning is not required to recover
equal values under a tied encoding or to prove that a statically stale row
cannot match. All of these cases are distinguished by explicit controls.
[All 16 acceptance rows](final.json) · [Rust deployment and distribution of work](../joint-witness/README.md) · [Physical construction evidence](../joint-root-cells/README.md)

## Earlier baseline with two statically partitioned rows, four waves

| Workload / seed | Actually neural RHS / source | Missing to target | Cell allocations in neural RHS / all new allocations |
|---|---:|---:|---:|
| sum-bits/1703 | 325 / 7265 | 6795 | 277 / 5877 |
| sum-bits/1709 | 355 / 7265 | 6765 | 309 / 5877 |
| dot-product/1703 | 260 / 6704 | 6310 | 284 / 5708 |
| dot-product/1709 | 285 / 6704 | 6285 | 311 / 5708 |
| gemm-bias-relu/1703 | 293 / 15462 | 14860 | 304 / 12911 |
| gemm-bias-relu/1709 | 312 / 15462 | 14841 | 326 / 12911 |
| stable-argmax/1703 | 236 / 8190 | 7791 | 241 / 6849 |
| stable-argmax/1709 | 264 / 8190 | 7763 | 268 / 6849 |

The table is a single joint native execution for each program/seed. It is a baseline for measuring expanded vocabularies. In particular, sum-bits alone requires at least 69 three-or-more-witness bindings even if every zero-, one- and two-witness binding is supplied, and dot-product requires at least 244. These are attainable-domain calculations rather than network predictions. [Source-matched allocation and RHS audit](observed.json) · [Native row-admission experiment](../row-admission/README.md)

To reproduce, run `addressability.py REFERENCE CORPUS OUTPUT` on the frozen source programs and `score.py REFERENCE CORPUS ROW_ADMISSION_PLANS AUDITED_BINARY OUTPUT_DIRECTORY` with a new output directory. A baseline that claims 98% must check ordered RHS, effective writes, Spine and the final graph, distinguish all supplementing exact work, report actual elapsed time, and show the unassisted run independently.
