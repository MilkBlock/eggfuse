# Retain only executable admitted context cuts

The receipt-omission experiment regenerated a source without the original
artifact's admission policy. The original selects four rules from earlier
paired execution evidence. The regenerated source has 1,481 candidate cut
orientations but no admission. `Contexts::new` enables general cut execution
only when an admission policy exists. Previously loading the unfiltered source
nevertheless compiled all candidate orientations into resident Cell queries.
This is unused executable state, not additional live query facts.

`Program::load` now validates every source cut certificate as before, then
compiles general cut instructions only when an admission policy exists, and
only for admitted rules. Without admission it retains empty per-rule lists.
Ordinary local contexts and residual query execution are unchanged. Admission
discovery and installation now derive candidate selections directly from typed
source rules, independent of resident executable cuts. No new runtime index,
fact graph or bindings are introduced. `context_cut_counts` reports executable
orientations; an unadmitted source now correctly reports zero.

The prior catalog's historical evidence remains usable: the existing `bake` and
`install` functions select families even from a Program with no compiled general
cuts. The integration test checks discovery, renamed/reordered query transfer,
empty-policy filtering, subsequent widening, and execution of the admitted
query. Corrupt cut certificates and stale recipe policies still fail loading.
The source Run boundaries, guard ordering, delta handling, visibility and
fallback obligations are not discharged by this memory change; their execution
paths remain live. No saturated-stage skip is claimed.

## Actual runtime evidence

Job 283 passes the targeted integration test. Job 284 passes all 18 compiler
library tests and measures two unchanged artifacts with the same completed-owner,
port-domain and Cell-field configuration as job 280. This is the actual
standalone Cell runtime, not a standalone storage prototype or a speed test.

| Artifact | Program before | Program after | Graph after |
| --- | ---: | ---: | ---: |
| Omitted receipts, no admission | 120,103,556 | 115,826,307 | 1,925,591 |
| Original artifact, admitted cuts | 115,168,530 | 115,168,530 | 2,038,485 |

All **4,277,249 saved bytes** are attributed to `context_cuts`. Process requested
heap high-water in the omitted lane falls from 127,223,401 to 122,946,146 bytes.
Neither lane changes Graph teardown bytes or field charges, actual completion
and ownership-query counters, or ownership structure. Each executes 1,428 Runs.
Both final exports are byte-for-byte identical to the corresponding job 281
semantic acceptance inputs, so those accepted final states are preserved.
No new full-workload per-Run graph comparison was performed. The original lane's
diagnostic owner-layout estimates differ by eight bytes; these estimates are
not used for the actual teardown saving.

See `admitted-cuts.json` for artifact/binary/report hashes and exact scope. Build
`runtime_storage_peak` with `iterative-bake,sparse-cells,storage-metrics`, and
use the job 280 commands documented in `application-receipts.md` against the
same saved Programs. All builds and runs use the shared compute queue.

This removes most of the regeneration's resident-plan regression. The omitted
Program is still 657,777 bytes larger than the original artifact, which retains
different admitted/cross-stage plans. Comparing those artifact configurations
does not establish an isolated code-size result. Graph remains at 48.39% of
the historical original denominator; no Program savings are charged toward
the 30% Graph target. Cross-stage state takeover and saturated RHS completion
remain the main unfinished structural work.
