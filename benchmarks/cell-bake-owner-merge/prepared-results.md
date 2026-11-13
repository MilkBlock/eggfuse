# Prepared constructors retain their actual result Entries

The requested line contains `d0d8ee33`, on `codex/cell-parallel-admission`.
Its saved checked-prefix catalog observes useful constructor witnesses before
an uncovered RHS suffix. Extending that catalog cannot repair a missing runtime
handoff: the worker prefix previously retained only downstream publication
results, while ownership composition also needs some non-exported witnesses.
The preceding fix therefore disabled multi-constructor preparation on these
rules and retained single-result preparation plus source continuation.

This change compiles the missing result demands into the existing `EffectPlan`.
Only eligible prefix constructors with an owned output port gain a demand;
already exported results reuse their slot. The query worker fills that layout,
the source boundary checks the entire prefix certificate, and composition reads
the actual witnesses from that same buffer. The buffer then moves into RHS
effects/publication. Existing joint frames still import their required results
and charge those accesses; this change does not claim to remove that copy.

There is no new binding array, result history or per-producer consumer list.
Constructor results may belong to an older foreign Cell. Before the first new
source birth, composition uses those actual witnesses and the known template,
without inventing a `(future source, operation)` result address. The operation
positions and result-slot demands are shared template data.

This removes the blanket ownership exclusion from multi-constructor preparation
and the repeated source-prefix interpretation within valid coverage. Constructor
queries still happen in workers; transferring them is not eliminating them.
The new `constructor_prefix_entry_reads` counter is charged by work-credit v8,
along with existing query/slot initialization, allocation, composition and
result-transfer counters. Entry joins and prefix counts alone are not speedups.

Run visibility, pending completion, table readiness and the sealed union epoch
remain authoritative. All checks precede composition writes. An invalid prefix
uses the existing fallback, preserving completed scalar work and clearing
speculative Eq slots. Enabling ownership, training or catalog tracing reconciles
the compiled plans at configuration time. If a previously compiled prefix did
not retain the newly required witnesses, that rule selects existing single-result
preparation before the workers run. Ordinary prefixes pay no per-instance check
for this configuration change, and late observation does not speculate/reject
the same incompatible prefix repeatedly.

Tests compare exact Run snapshots, ordered bindings and final states for one
and two reused foreign results, canonical ownership and stable ports, and one
and four workers. Composition writes/joins and baked hits must match serial
execution. Separate tests check union-epoch invalidation before any composition
write and late training/tracing. These are standalone Cell CPU tests. Jobs 266–267 pass
112 integration tests, 215 runtime tests and no-default compilation after fixing
the optional execution-plan lookup for the existing synthetic EffectPlan test.
Job 256 also passes all six work-credit tests, including the v8 required counter.

The workload check freezes control and candidate, validates ordinary sum-bits
and Raytrace with ownership enabled, and can additionally audit the unchanged
saved learned sum-bits catalog. The latter has a different source artifact;
its differential check is explicitly separate from native semantic acceptance.
The ordinary sum-bits export must match the existing reviewed choice proof.
Timing uses the established whole-control-then-whole-candidate queue job.

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/owner_workers.py ACCEPTED TARGET CONTROL_CHECKOUT OUTPUT --learned-program SAVED_CATALOG
eggfuse-job run --kind timing -- python3 benchmarks/raytrace-parallel/quick.py OUTPUT/control/checked OUTPUT/candidate/checked OUTPUT/timing OUTPUT/timing.json
```

The first version (`0a58f12b`) checked that configuration condition at every
prefix seal. Its ordinary work counters were identical to control, but job 272
recorded sum-bits 21.811→23.625 ms (+8.32%) and Raytrace 4.742334→4.811298 s
(+1.45%). This did not pass the speed gate. The grouped trial cannot attribute
all of that difference to the added check; it motivated removing the unnecessary
hot-path work before a new trial.

The saved learned catalog has no result-entry joins in these executions. It
does exercise restored preparation on other Entry-sensitive rules: 492→2,540
prefix constructor operations, 8,832→6,784 composition Entry reads, and unchanged
1,099 baked hits. Generic lookups increase 14,506→14,962; worker result capacity
grows 1,248→39,200 cumulative allocated bytes, and buffer moves 48→876. Job 274's
separate learned-catalog diagnostic records 21.033→20.263 ms (-3.66%). Seven
samples per binary, one warmup each, all control then all candidate; no native
acceptance or significance claim. These figures do not establish that retaining
the extra buffers always pays off. Actual result-Entry retention remains covered
by the short multi-result tests; its workload coverage must not be invented.

The final configuration-only adjustment and its fresh trial are recorded below.
