# Absorption before a Cell's constructor-domain expansion

Control: `e1610f4c`. This is an **opt-in standalone Cell CPU experiment**,
not a native egglog optimization. It is disabled by default, including when
compiled with the `cell-absorption` feature. There is no timing result for this
change, general sparsity proof, or 2× result.

The [rejection-reuse follow-up](#reuse-the-actual-rejecting-output) below reduces
the guard's acquisition cost without increasing its takeover scope or storage.

## Opportunity and completed takeover

The [previous actual-execution census](../cell-change-locality/README.md)
found small one-step Get fanout in selected hot windows, but repeated scalar
changes. Many min writes were already absorbed at the start of their Run.
The relevant reuse is an inequality that survives input changes, rather than
an identical-input match cache or a longer Cursor alone.

The existing typed query and single-write instruction now derive this narrow
condition for a Cell:

```text
Cost(x) = n; C(x, other distinct slots...) -> y
effect: Cost(y) := min(Cost(y), n)
```

Admission requires two query atoms, a seminaive one-expansion kernel, distinct
constructor slots, an integer min merge, no remaining computed RHS prefix or
additional effects, and no deletion/subsumption of the attribute anywhere in
the executable program. No workload names or rule IDs occur in admission.

For an existing cached constructor domain, the first eligible visit reads the
current output values and retains their maximum `T`. If `n >= T`, the entire
domain's writes are absorbed. Output decreases preserve the old upper bound;
they need no new subscriptions. A failed bound is cleared for a later refresh.
The condition lives in the existing `Neighborhood`, not a new fact graph,
binding copy, or per-producer consumer list.

On success the runtime skips the row loop, binding construction, single-write
RHS, and that application's completion/publication bookkeeping. The logical
match count includes the proven domain size; `executed_bindings` does not.
Neither count is a committed mutation count. Unused physical Cell identity
positions are reserved in bulk to preserve later constructor numbering;
these reservations create no live Cells or effects.

This goes beyond the [previous publication optimization](../cell-absorbed-publication/README.md):
it deliberately does **not** publish a new no-op source. The existing actual
result and valid Entry source remain available; original residual enumeration
remains authoritative. Cursor/root provenance can therefore differ even though
logical facts and required effects agree. No history is invented for an omitted
application. The earlier optimization preserves the latest producer when an
application actually executes; that requirement alone did not justify dropping
the application, so this experiment separately checks the source-Run behavior.

## Live obligations and fallback

- The constructor table version, retained domain identity, rule, and input Eq
  key must match. Every row must match that input; a superset candidate bucket
  cannot certify the domain or its match count.
- Every constructor row must precede the rule watermark. Fresh constructors
  keep ordinary delta ownership and winner selection. Late members, union,
  deletion, and recreation invalidate through the existing query lifecycle.
- All outputs must exist; attribute visibility changes reject admission.
  Deletable or ordered-merge outputs have no static proof.
- Only global completion is supported. Scoped/deferred completion falls back.
  Normal Run ordering, structural repair, and residual matching remain.
- This uses only existing cached domains. Singleton and over-budget domains
  are uncovered. It does not enlarge Ripsat templates or add Bake credit yet.

## Measured work and costs

Complete Raytrace, same frozen program, four query workers and grain 64:

| Observation | Before | After |
|---|---:|---:|
| Executed bindings | 3,447,491 | 3,240,309 |
| Single writes | 2,273,182 | 2,066,000 |
| Cached constructor rows visited | 592,688 | 385,506 |
| Entry publication writes | 2,305,276 | 2,098,933 |
| Publication slot probes | 2,950,152 | 2,742,970 |
| Point queries | 2,555,377 | 2,555,377 |
| Allocation calls | 20,174,808 | 19,967,543 |
| Reallocation calls | 2,586,171 | 2,585,625 |
| Cumulative requested bytes | 6,683,647,285 | 6,556,743,403 |

The 207,182 omitted bindings, writes, and completions describe the same
takeovers, not three independent savings to add together. Captured pending
contexts stay at 1,914,263: the preceding optimization had already removed
these applications' ordinary pending contexts. Resumed steps stay at 577,650.

New costs: **142,008 eligible cached-domain checks, 110,009 bound builds,
389,878 output probes**, and 31,999 bound reuses. There are 32,831 absorbed
groups. Output probes are separate from the unchanged point-query counter.
Their count exceeds the omitted scalar writes; cheaper allocation does not
prove that total execution is cheaper.

Each cached Neighborhood gains 32 bytes on this target, including neighborhoods
that cannot use the condition. With the feature compiled but disabled, complete
Raytrace requested bytes increase by 247,936; allocation calls are unchanged.
The enabled net reduction above includes this layout cost. These bytes are
cumulative allocator requests, not peak memory, RSS, or measured memory traffic.
The guard also repeats a cached-domain lookup. `checks` counts eligible domain
checks, not every earlier eligibility dispatch; those dispatches remain uncounted.

sum-bits (1,428 Runs) and the first 1,280 Raytrace Runs have zero takeovers and
zero bound probes. Their existing cached-parent visits are also zero. They
retain the feature's storage cost: +1,152 and +72,000 requested bytes respectively.
This is late-Raytrace coverage, not a demonstrated gain on both workloads.

## Validation and limits

- All 16,883 Raytrace logical Run signatures and actual graph-operation counts
  agree. Complete exported state is exact against the frozen prior branch.
  A separate full rooted comparison passes for 1,034,514 rows and 524,655 Eq
  values, with no excluded tables.
- In the same 14 selected source windows, before/after snapshots, visibility,
  unions, and ordered effective writes agree. Remaining matches are an ordered
  subsequence after removing only source ordinal. Every omitted match is a
  non-direct Get whose output already absorbs its input at Run start.
  This is relative Raytrace evidence, not independent native acceptance.
- The unchanged sum-bits `choice_diagnosis.py` returns `pass` / exit 0, bound
  to the candidate export. sum-bits does not exercise the new guard.
- Positive integration coverage checks every source Run with scalar decreases,
  later consumers, late constructors, union, deletion/recreation, and serial/four
  worker configurations. Negative cases reject deletable and ordered outputs.
  A unit test checks rule/input identity, watermark, and domain generation.
- 98 runtime unit tests and 49 selected compiler integration tests pass.
  No-default-features compile and README compile/run/bench (repeat 1) are command
  smoke checks only. No workload timings are taken from diagnostic binaries.

## Reproduction

Use fresh output directories and the frozen inputs identified by
[results.json](results.json). Preserve the prior branch binary before building
the feature. The saved full control uses the same query-prefix exporter, four
workers, grain 64, repair ports, and Entry publications, with the option absent.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,allocation-metrics --example query_prefix
target/release/examples/query_prefix SUM_PROGRAM ROOT/sum 2000 4 64 canonical --repair-ports --entry-publications --cell-absorption
target/release/examples/query_prefix RAY_PROGRAM ROOT/ray1280 1280 4 64 canonical --repair-ports --entry-publications --cell-absorption
target/release/examples/query_prefix RAY_PROGRAM ROOT/ray-full 20000 4 64 canonical --repair-ports --entry-publications --cell-absorption
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,slot-transfer-audit --example cell_change_windows
target/release/examples/cell_change_windows RAY_PROGRAM benchmarks/cell-change-locality/windows.json ROOT/windows observe --cell-absorption
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-absorption-guard/collect.py ROOT RESULTS.json
```

Prepare the semantic inputs using the existing
[sum-bits contract](../marker-handoff/choice-diagnosis.md). `collect.py` reads
saved exports and observations; it does not run a performance campaign. It
expects `ray-before`, same-feature-disabled `ray-control`, the full-equality
proof, frozen diagnostic binaries, and the neighboring prior experiment folders
used in the recorded results. Raw files stay under ignored `out/`.

The next admission question is whether an actual completed Cell can supply this
bound without rescanning outputs. Until that acquisition cost is reduced or a
normal-binary timing comparison passes, this remains an opt-in experiment.

## Reuse the actual rejecting output

Follow-up control: `91cfda31`. The preceding implementation scanned the whole
domain even after one output had already refuted absorption. It then discarded
the maximum it had just computed. On later attempts, it often rediscovered the
same counterexample through another key lookup.

The guard now stops on the first rejecting output and retains its **actual
function result index** in the existing condition slot. On a subsequent attempt,
one direct live-result read suffices to reject the optimization if its value is
still greater than the new input. If it has improved, retired, or is unavailable,
the ordinary full proof is retried. This reference cannot authorize absorption:
only the existing exact whole-domain proof can omit source work. A stale negative
hint can at worst miss an optimization. Domain/rule/input checks still run first.

The condition is an enum of empty, positive upper bound, or rejecting result.
It remains **32 bytes**, with no extra allocation, binding field, consumer list,
or write subscription. It does not maintain every output's current value.
No statement that a matched rule has already committed an effect is introduced.

| Complete Raytrace diagnostic | `91cfda31` | Follow-up |
|---|---:|---:|
| Output key/hash probes | 389,878 | 43,058 |
| Direct rejecting-result reads | 0 | 100,816 |
| All output observations, unweighted | 389,878 | 143,874 |
| Whole-domain checks | 142,008 | 142,008 |
| Absorbed groups | 32,831 | 32,831 |
| Omitted bindings and corresponding writes/completions | 207,182 | 207,182 |
| Allocation calls | 19,967,543 | 19,967,543 |
| Cumulative requested bytes | 6,556,743,403 | 6,556,743,403 |

All 100,816 rejecting-result reads still reject the proof attempt. A further
2,047 scans stop at their first counterexample. `bound_builds` now counts only
the 7,146 scans that finish successfully; in the prior implementation it also
included complete scans that were immediately rejected. Compare output probes
and direct reads, not that changed scan-completion count as independent savings.
The 88.96% reduction is in output **hash probes**, not execution time; including
direct reads gives 63.10% fewer output observations. These operations have
different costs. Admission dispatch and the extra group lookup still remain.

Why not obtain every bound from the previous write instead? For this min-copy
Cell, knowing only that every output is at most the previous input is insufficient
when the next input is smaller. A stronger positive bound would require the
actual final outputs, full-domain completion, and cheap linkage back to the
condition. Adding a token or a second binding map to every match has not been
justified. Reusing a single counterexample addresses the measured repeated work
without that new handoff. Direct RHS-derived positive bounds remain unfinished.

sum-bits and the early Raytrace prefix still have no eligible cached-domain
takeovers and no new output observations. sum-bits allocations are unchanged.
The Raytrace prefix records one extra worker scratch growth: 14 → 15 frame
growths, one extra reallocation and 192 requested bytes. Worker assignment and
per-worker capacities differ; the recorded cost is retained, including in a
short repeat. Full Raytrace has no allocation/reallocation/byte difference.
For all three runs, complete graph exports,
logical and executed Run signatures, graph counters, Entry work, and Spine work
agree exactly with `91cfda31` (diagnostic clocks are not compared). All 14 selected
source captures agree in full, including source ordinals and provenance; only
their enclosing Run's elapsed/phase clocks are excluded from comparison.
The unchanged sum-bits validator passes; Raytrace remains a relative proof.
98 runtime unit tests and 49 selected integration tests pass, including a
counterexample that becomes satisfied and must reopen the proof. The unit test
also checks that the condition representation has not grown. README command
smokes and the no-default-features compile pass.

Use the same diagnostic commands above with fresh `ROOT` paths and the current
binary, saving it as `ROOT/prefix` and the observer as `ROOT/observer`. The
follow-up's saved files are under `out/cell-absorption-rejection`, next to the
prior `out/cell-absorption-guard` control. Recheck without executing workloads:

```sh
python3 benchmarks/cell-absorption-guard/collect_rejections.py ROOT RESULTS.json
```

[rejections.json](rejections.json) records input/output hashes and both cost
classes. This remains opt-in; there is no new timing campaign, automatic Bake
credit, global sparsity claim, or 2× result.
