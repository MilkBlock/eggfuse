# Canonical ownership continues on constructor workers

**Worker admission experiment `674477c4` is rejected and restored.** The
source-prefix result-Entry repair remains; canonical ownership no longer admits
constructor worker tails. The implementation description below records the
experiment, not a newly enabled ordinary path.

The requested Bake line is `codex/cell-parallel-admission`, containing
`d0d8ee33`. This checkout fast-forwarded the entire committed line through
`b3322f9f`; it did not substitute the older structural-compression branch.

The preceding ordinary Raytrace execution used repair ports without Cell
ownership. Its workers executed 329,908 constructor operations, while the
ownership backend was categorically excluded from those jobs. Merging its
catalog and storage changes therefore did not automatically join the two paths.
The existing typed fresh-anchor and complete-tail proofs can discharge local
constructor lookup and source interpretation without another catalog iteration.
Observed cross-Run result Entries remain authoritative for composition; a deeper
catalog does not prove missing execution evidence or saturation.

## Implemented coverage

Canonical-key ownership now permits the existing local row executor. An ordinary
source constructor first establishes a fresh anchor and its ownership. The
compiled isolated tail must preserve that anchor's fresh cone and cannot choose
a foreign peer result. Workers lease the same instance slots and materialize its
actual rows; source adoption calls `activate_fields` without replaying those
constructors. This initializes the existing owned static wiring and subscriptions
at the original source boundary. Inline local completion can also reuse an earlier
fact in the same Cell.

The batch scheduler now begins the same checked ownership Entry as serial apply.
Its existing suspended context retains that Entry across worker execution, and
completion/error handling releases it before restoring the next source. The
single-result prepared continuation and an unpromoted source prefix report their
actual foreign witnesses before the first new owned birth. No new per-instance
binding, consumer list or result log is introduced.

An integration fixture initially retained exact states but lost all 48 result
joins: ordinary prefixes and batch admission had skipped this evidence. Both
paths now preserve it. The compact multi-result worker prefix saves only exported
witnesses, which is insufficient for these Entry-sensitive rules. Configuration
therefore selects the existing single-result preparation for those rules and
continues through the source prefix. It does not execute an optimistic prefix
then replay it. Reusing the full prefix needs demand-driven actual-result slots;
that integration remains unfinished and its lost coverage must be charged.

## Live obligations and costs

Worker roots, peer-dependent ownership tails, stable-field/port-key backends and
ownership registration on registry workers remain outside this proof. Both fast
constructor registration paths explicitly reject ownership because they install
legacy subscriptions. Pending ownership completion prevents a borrowed parent
epoch from crossing its repair boundary. Original Run visibility, effect/error
order, deletion, actual foreign witnesses and source lifetimes are unchanged.

More local jobs add leases, ready-queue entries and completion events; existing
capacity and operation counters charge them. This change adds no payload fields
to those transports. It neither turns ownership on for default runs nor claims
that canonical ownership is the final port representation.

## Validation

Compute job 237 passes 48 Cell execution, 47 ownership, 14 query worker and six
residual integration tests, 213 runtime unit tests and no-default compilation.
The short canonical-owner fixture checks exact Run snapshots, ordered bindings,
final export, constructor counts and owned registration through union and
deletion/recreation. Four workers perform 94 or 96 tail operations depending on
pre-existing foreign facts. Its serial owner control produces identical facts.

The learned-catalog fixture retains all 48 actual-result writes, joins and the
same binding/owned-birth counts; four workers perform its 48 tail operations.
These are standalone Cell CPU correctness/coverage results, not speed estimates
or native workload acceptance.

The workload driver freezes both binaries, uses unchanged accepted sum-bits and
Raytrace programs, adds `--cell-ownership` to both lanes, and checks exact final
states, source Run summaries and effects. Native sum-bits choice diagnosis must
pass with the fresh CPU export hash. Only after this check may timing run as one
machine-wide job, all control samples before all candidate samples:

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/owner_workers.py ACCEPTED TARGET CONTROL_CHECKOUT OUTPUT
eggfuse-job run --kind timing -- python3 benchmarks/raytrace-parallel/quick.py OUTPUT/control/checked OUTPUT/candidate/checked OUTPUT/timing OUTPUT/timing.json
```

The control checkout is pinned at `b3322f9f`. Do not treat these ownership-lane
results as a comparison against the historical fastest ordinary configuration.

## Workload result and restoration

Compute job 238 freezes both ordinary-feature binaries and validates exact
sum-bits/Raytrace states, all 1,428/16,883 source Run summaries and effects.
Both native sum-bits proofs pass with the fresh CPU export hash. The workload
programs have no learned ownership fragments: their composition hit counts are
zero. The learned-catalog integration fixture above supplies that separate
cross-stage coverage; these workload measurements do not demonstrate new Bake
transition hits.

| Work | sum-bits control → experiment | Raytrace control → experiment |
| --- | ---: | ---: |
| Ordinary key lookups | 14,653 → 14,086 | 4,332,972 → 4,177,781 |
| Local births + local reuse | 0 → 548 + 19 | 0 → 153,268 + 1,923 |
| Constructor operations on workers | 0 → 407 | 0 → 126,996 |
| Jobs / batches | 0 → 265 / 48 | 0 → 81,137 / 2,882 |
| Queue capacity, cumulative | 0 → 609,528 B | 0 → 67,893,184 B |
| Event capacity, cumulative | 0 → 254,448 B | 0 → 72,459,392 B |

Owned birth/live counts and signal binding creations remain equal. The lookup
reduction equals covered local operations; it is not a net count of all hashes
or dispatch operations. The added capacities are cumulative, not peak memory.

Timing job 240 completes all control groups before all candidate groups, with
one warmup and fixed five sum-bits / three Raytrace samples per lane. All 48
process guards are clear. Every sample is preserved in
`owner-worker-results.json`, along with frozen binary hashes and work data.

| Inference median | Control | Experiment | Change |
| --- | ---: | ---: | ---: |
| sum-bits | 21.287 ms | 23.270 ms | +9.31% |
| Raytrace | 4.833709 s | 5.046035 s | +4.39% |

The worker admission fails the speed gate and is restored, including its batch
Entry plumbing and fast-registration exclusions. This trial does not isolate
which added dispatch/ownership maintenance caused the regression. It shows that
the demonstrated local work reduction is insufficient for an end-to-end win.

The retained fix reports actual results from the source prefix into its existing
composition Entry, and avoids selecting compact worker prefixes that discard
required unexported witnesses. The regression test compares exact Run states,
ordered bindings, final exports and all 48 result joins with serial execution
while constructor preparation is enabled. No ownership worker admission or
speedup is claimed for that repair. Reproduce the rejected admission with a
checkout of `674477c4`; running the driver on the restored head tests the repair
instead.

After restoration, compute job 243 passes 47 execution, 47 ownership and 14
query-worker integration tests plus 213 runtime unit tests. The retained runtime
diff against `b3322f9f` is limited to source-prefix evidence, its shared Entry
helper and preparation selection; constructor jobs and their scheduler match
the control again.

The full Bake branch was subsequently integrated through `573903e5`, including
matched-port key proofs and retired-source payload release. Compute job 246 passes
all 48 ownership integration tests, the completed-source payload regression and
ten closure-frontier analyzer tests. These checks validate that merge; the timing
table continues to identify only its frozen `b3322f9f` / `674477c4` pair.
