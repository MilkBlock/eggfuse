# Workers start constructor roots and continue their actual Cell

This measures work in the actual standalone Cell CPU, not native egglog
performance. The control is frozen runtime `916ebf7c` at checkpoint `83ac944b`.
Programs, catalogs, release features and arguments are unchanged. This is
implementation **one** of the next five-change timing interval. These work and
semantic executions do not establish an end-to-end speedup.

## Opportunity and compiler proof

The preceding Raytrace execution had 1,287,802 source constructor boundaries.
Workers performed 127,059 local constructor operations; registration covered
65,630 of 820,439 logical fact births. The existing fresh cone plan generally
needed the source to create an anchor before dispatch. Further shrinking its
registration buffers would not remove that prerequisite.

The ordinary Cell definition now derives eligible root positions. Every later
constructor must consume that result or a result derived from it. The region
must reach the template end, optionally through its already-compiled Unit tail.
A union, mutable read, fallible suffix, unsupported backend or outstanding repair
keeps the ordinary path. Earlier pure operations must already have succeeded.
History transfers still delimit the region.

At admission, an empty **authoritative constructor hash bucket** proves absence
from the current graph. Nonempty buckets use ordinary exact lookup. A pending
input value or a potentially equal root in an earlier in-flight wave retains
its dependency boundary. A hash/Bloom match never proves constructor equality.
Workers lease the original instance slots; there is no second binding, runtime
fact graph or producer subscriber list.

Within the bounded group, existing peer result slots resolve duplicate roots in
source order before constructing descendants. A worker uses the actual winner's
result, including a result owned by another Cell. Independent evaluations may
duplicate computation; exact publication discards the losing evaluation. Workers
write actual constructor row allocations, subsequent slots and covered Unit rows.
Source adoption uses these allocations without replaying covered constructors
or Sets.

Distinct root hashes, together with the compiled complete-local-tail proof,
allow independent execution through the existing local executor. Those jobs
omit peer slots and recursive helping. Equal hashes retain exact sharing.

Across admission waves, only a bounded sorted root-hash list accompanies the
existing pending Cell identities. Unrelated keys continue admission. Bindings,
actual rows and result slots stay in the original jobs. Across Runs, existing
Shared Entry projections, source publication order and visibility boundaries
remain authoritative. The old all-hit source prefix is retained when no peers
are outstanding; this leaves the source bootstrap of some groups in place.

## Actual work and additional costs

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Ordinary graph key lookups | 14,012 / 13,028 | 4,027,756 / 3,830,073 |
| Worker constructor operations, including reuse | 386 / 1,335 | 127,059 / 324,431 |
| New worker-root admissions | 0 / 984 | 0 / 198,025 |
| Root births / peer-root reuse | 0 / 926 + 58 | 0 / 194,448 + 3,577 |
| Root jobs proven independent | 0 / 890 | 0 / 192,861 |
| Source execution frames | 5,173 / 5,176 | 1,020,508 / 1,020,600 |
| Local RHS dispatch regions | 72 / 247 | 3,406 / 9,062 |
| Queue capacity, cumulative bytes | 578,616 / 2,252,384 | 95,107,248 / 247,559,152 |
| Completion-event capacity, cumulative bytes | 520,208 / 1,882,208 | 141,081,552 / 387,020,504 |
| Peer-sharing capacity, cumulative bytes | 37,960 / 86,192 | 11,139,376 / 16,544,024 |

Lower ordinary lookup counts are **not** net hash operations removed. Raytrace
adds 278,895 root-bucket probes, including 80,759 fallbacks, and 32,796 pending-root
boundary checks. Admission keys are still constructed on the source. Root hashes
require 1,850,528 cumulative capacity bytes, separately charged. Original slot
leases increase from 81,223 to 210,835. The increased dispatch and completion
traffic remain part of the performance gate; adopted roots or fewer source
boundaries cannot substitute for it.

Root admission/birth counts include jobs executed inline below the existing
dispatch threshold. Only `worker_operations` requires an actual worker context.

An initial implementation over-flushed unrelated keys and produced 47,077
Raytrace dispatch regions. Restricting waits to actual key/value dependencies
and preserving the all-hit prefix reduced that to about 9,000. An intermediate
uniform peer path used 128,900,400 cumulative sharing bytes; independent-root
proofs reduced it to 16,544,024. Intermediate executions remain under
`out/cell-root-births/initial` and `before-isolation`; they are not timing samples.
Event arrival can change coverage and capacity while source effects remain exact.
Capacity is not peak memory or a full allocation trace. These counts are not CPU
utilization measurements.

## Validation and remaining ownership

173 runtime tests and 88 integration tests pass. Tests cover duplicate roots and
descendants, actual foreign aliases, independent cones, hash/Bloom collisions,
deletion/recreation, late union, source errors and Run snapshots. Forced collision
checks and all-feature, sparse-only and legacy builds pass. README compile/run/
single-repeat bench commands pass as smoke checks.

Frozen final exports, all 1,428 / 16,883 ordered Run summaries and logical effects
exactly match the control. Reverse-index occupancy and iterative Bake evidence
are unchanged. Native sum-bits choice diagnosis returns `pass`; the saved proof
input's CPU export hash equals the new export. Raytrace remains differential
validation, not an extension of the native proof. Run-summary equality does not
replace the integration fixtures' intermediate graph snapshots.

Worker root completion is implemented; shared graph/index registration is not
universally parallel. Existing owners cover eligible registration regions. Other
row adoption, subscriptions and source lifecycle work remain. Small Runs now
carry more jobs and events. The next integration must let larger Cell-owned
execution chunks amortize or delete those handoffs, rather than equating more
worker operations with a speedup.

Features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-root-births/run.py out/cell-fact-lease FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-root-births/check.py out/cell-fact-lease FRESH_OUTPUT RESULTS.json
```

The checker also requires successful validation and README command records, as
shown in [results.json](results.json). Large predecessor exports were losslessly
gzipped after verifying their original SHA-256 hashes; the checker accepts either
representation. The frozen manifest records input and runtime paths. Use fresh
output directories for reproductions.
