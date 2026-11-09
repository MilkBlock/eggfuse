# Shared condition compiler pilots

These experiments measure the **standalone Cell CPU**, with one runtime thread
and `--local-congruence`. They compare frozen executables on the same frozen
artifact. Native egglog is not measured. The marker campaign includes the
archived fastest runtime as a concurrent lane; other campaigns explicitly
identify references to it as historical comparisons.

## Column routes: first candidate

The baseline is the lookup-fix executable from `50f7694b`, preserved at
`out/raytrace-parallel/runtime-fixed`. The first candidate, preserved at
`out/condition-bake/runtime-columns`, retains the bound field's column and uses
shared static slice positions for that column. It excludes irrelevant field
positions before checking instance liveness, table identity and exact equality.
The candidate hash is
`b12b8ecbf5eb98cd8dc1d090baf80f9a6ce93fdb4bd2f9a6946e533818b1f1de`.
Its build uses `sparse-cells,view-ports,storage-metrics`, without allocator or
trace instrumentation. The parent ran 39 focused tests and Bake replay tests
before freezing this candidate; source edits after freezing do not change the
measured executable.

One warmup precedes seven interleaved pairs on sum-bits and two on Raytrace.
Every completed invocation has the same exported-state and source-schedule
hashes as its baseline. Timings use blocking `waitpid` with a separate timeout
watchdog, equal-length executable/input links, and numeric output directories.
No Cargo build or another benchmark overlapped these measurements.

| Workload | Baseline inference | Columns inference | Baseline process | Columns process |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 32.078 ms | 32.054 ms | 192.191 ms | 193.978 ms |
| Raytrace | 16.011 s | 15.619 s | 25.846 s | 25.222 s |

Sum-bits has no clear inference improvement: the paired-median ratio is 1.006,
with descriptive bootstrap interval `[0.986, 1.024]`. Its whole-process ratio
is 1.015, interval `[1.008, 1.015]`. Thus this candidate does not meet a
two-workload improvement criterion. The extra load/setup time is visible:
median load increases from 113.301 to 114.273 ms and setup from 3.058 to
3.397 ms.

Raytrace improves approximately 2.45% in inference and 2.41% in process time by
ratio of medians. Each of its two pairs is faster, but two observations are a
pilot, not a robust general admission result. The candidate remains far slower
than the preceding experiment's historical fast measurement (7.754 seconds
inference, 10.010 seconds process), which was not rerun concurrently here.

| Operation | Sum baseline | Sum columns | Raytrace baseline | Raytrace columns |
| --- | ---: | ---: | ---: | ---: |
| Signal visits | 58,494 | 58,494 | 55,413,157 | 55,413,157 |
| New route probes | 0 | 58,494 | 0 | 55,413,157 |
| Slice visits | 116,905 | 59,462 | 105,558,365 | 63,490,061 |
| Domain results | 6,690 | 5,693 | 10,000,938 | 6,235,405 |
| Key candidates | 18,459 | 17,491 | 12,161,275 | 8,475,767 |

Column routes reduce slice visits and candidate comparisons, but every signal
is still visited and now requires a route probe. The sizeable counter reductions
produce only a small Raytrace timing improvement and no sum-bits inference win.
This pilot supports further reducing actual instance-directory accesses and
construction cost; it does not justify scoring removed slice visits as equal
units of elapsed-time savings.

`columns-*.json` records every sample, counters, phases, hashes and descriptive
paired intervals. Large reports and raw logs remain in `out/condition-bake/`.
Reproduce with preserved binaries and fresh output directories:

```sh
python3 benchmarks/raytrace-parallel/measure.py benchmarks/condition-bake/columns-sum-bits-manifest.json out/condition-bake/repeat-columns-sum --repeat 7 --warmups 1 --timeout 10
python3 benchmarks/raytrace-parallel/measure.py benchmarks/condition-bake/columns-raytrace-manifest.json out/condition-bake/repeat-columns-ray --repeat 2 --warmups 1 --timeout 90
python3 benchmarks/condition-bake/collect.py out/condition-bake/repeat-columns-sum out/condition-bake/repeat-columns-sum.json
python3 benchmarks/condition-bake/collect.py out/condition-bake/repeat-columns-ray out/condition-bake/repeat-columns-ray.json
```

## Typed conditions and direct stable-node lookup: second candidate

`runtime-typed` adds conservative disjoint-operator pruning, removes reflexive
and repeated Eq guards, and uses the authoritative stable-node directory for
candidate liveness/table checks instead of first consulting Cells and facts.
Its frozen SHA-256 is
`09d386354f5687be31fd7b353a9cceaa893242827e4790f33b2f9cb949341e8a`.
The three-lane pilot compares lookup-fixed, columns and typed concurrently:
seven sum-bits pairs with one warmup, and two Raytrace pairs without an additional
warmup. Every state/schedule hash matches. Raytrace baselines were already warm;
the typed executable had first run on sum-bits. These remain bounded pilots.

| Workload / lane | Inference median | Process median |
| --- | ---: | ---: |
| sum-bits, lookup-fixed | 32.106 ms | 194.660 ms |
| sum-bits, columns | 32.196 ms | 194.206 ms |
| sum-bits, typed | 31.444 ms | 192.656 ms |
| Raytrace, lookup-fixed | 16.272 s | 26.055 s |
| Raytrace, columns | 15.588 s | 25.165 s |
| Raytrace, typed | 14.084 s | 23.663 s |

Typed improves Raytrace by 13.45% inference and 9.18% process time relative to
lookup-fixed, and both pairs improve. Sum-bits points in the same direction, but
its paired intervals still include one (`[0.971, 1.005]` inference and
`[0.972, 1.001]` process). **A two-workload improvement is not established.**
The next marker candidate is tested before expanding this uncertain result.

The separate, untimed `typed-plan-sum-bits.json` diagnostic confirms real
compiler/runtime effects: shared conditions decrease 2,176→1,576; condition
visits 611→407; operator guards 420→288; shared-symbol guards 87→0. Equality
guards remain 312 and completed conditions remain 108. Removing 600 static
pairs does not imply saving 600 runtime checks.

For Raytrace, columns and typed have the same slice visits and port reads, yet
typed is faster. Counted stable-node lookups actually increase from 63,339,680
to 83,433,347 because inactive positions now directly query that directory.
The old Cells/facts lookup layers disappear. This is another reason to assess
the actual operation sequence and measured cost rather than optimize a single
counter in isolation. These intermediate pilots did not run final allocator or
ordered-effect audits. The retained shared-code version was subsequently
validated as the semantic/cost checkpoint described below.

## Concrete-template operator markers: third candidate

`runtime-marker` keeps a concrete template identity in the existing Frame field
and rejects an incompatible operator before consulting stable-node liveness.
It still reads the template's Op representation at each checked position.
The normal binary hash is
`63c9be3e2f78cb1cdfeaa494f0b47c0e8fc043a5f7b3991c13aa8da5aa926955`.

This pilot returns the archived-fast runtime to the **same interleaved campaign**
as lookup-fixed and marker. Sum-bits has 15 pairs after one warmup; Raytrace has
two pairs and no additional warmup. Every state and schedule hash matches.

| Workload / lane | Inference median | Process median |
| --- | ---: | ---: |
| sum-bits, lookup-fixed | 31.820 ms | 195.176 ms |
| sum-bits, marker | 31.533 ms | 194.889 ms |
| sum-bits, archived fast | 21.366 ms | 144.059 ms |
| Raytrace, lookup-fixed | 16.361 s | 26.168 s |
| Raytrace, marker | 13.059 s | 22.816 s |
| Raytrace, archived fast | 7.732 s | 10.027 s |

Raytrace improves approximately 20.2% inference and 12.8% process time relative
to lookup-fixed. Marker still loses clearly to archived fast. Sum-bits remains
inconclusive: paired ratio intervals are `[0.9826, 1.0001]` inference and
`[0.9796, 1.0089]` process. A two-workload improvement is still **not established**.

Raytrace checks 63,490,061 candidate positions against their concrete operator
and rejects 53,395,879 before consulting instance-node liveness. The compiler
has made these rejections cheap, but the runtime still decodes template Ops and
uses a wider marker lookup to recover the shared PortProgram. The next candidate
compiles compact shared program/operator arrays to remove that remaining work.

The allocator build for this version was cancelled when that next experiment
was selected, before producing a diagnostic binary or starting the ordered audit.
These intermediate timing reports therefore do not claim a completed final
allocation or ordered-effect admission. Normal state/schedule checks and the
parent's focused/workspace tests remain separate evidence.

## Shared typed code: fourth candidate

`runtime-code` replaces per-position template-Op decoding with compact shared
operator constants and recovers PortPrograms from a compact shared pointer
array. The existing Frame field holds a shared code ID; the 24-byte Frame does
not gain a field. Code is shared by `(program ID, operator sequence)` and
prepared during setup. Static array slots are storage, not executed work or
performance credit. Its frozen SHA-256 is
`a3459621655df175206708da53f6bdfef1011b87f476e24aee534433d54cb0ff`.

This final normal pilot compares lookup-fixed and shared-code with 15 sum-bits
pairs after one warmup and two Raytrace pairs without another warmup. State and
schedule hashes match throughout. It does not rerun the fast baseline or marker
lane, so comparisons to them remain historical.

| Workload | Lookup-fixed inference | Shared-code inference | Lookup-fixed process | Shared-code process |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 31.580 ms | 31.270 ms | 190.955 ms | 191.828 ms |
| Raytrace | 15.709 s | 13.049 s | 25.565 s | 22.865 s |

Sum-bits inference improves approximately 0.98%, with paired ratio interval
`[0.9831, 0.9962]`, but complete process time **regresses 0.46%**, interval
`[1.0002, 1.0102]`. Its setup median grows from 3.046 to 3.487 ms; load is nearly
unchanged. Moving work into shared code has not made cold execution free.

Raytrace improves 16.93% inference and 10.56% process time against the concurrent
lookup-fixed control. Its 13.049/22.865 seconds are nearly the same as marker's
historical 13.059/22.816 seconds: this experiment does **not** establish an
additional speedup over marker. The previously concurrent archived-fast results
of 7.732/10.027 seconds remain well ahead, but are not a new paired comparison.

The final normal result therefore still **fails the two-workload, two-metric
improvement criterion**. Shared-code has measured inference benefits relative to
lookup-fixed, a clear Raytrace process benefit, and a small sum-bits process
regression. Its subsequent semantic/allocation checkpoint below does not change
that failed performance gate. The complete normal samples and operation counters
are in `code-*.json`.

## Incoming-Cell absence proof: fifth candidate, rejected by timing

`runtime-absence` adds a sound negative lookup certificate to shared-code.
After exhausting the exact birth-hint bucket, it can return absent if every
canonical Eq input's Cell has never received an incoming parent edge. With
immutable scalar fields and singleton Eq inputs, an existing equal constructor
could not have migrated from a different birth key. The check applies only to
ordinary clean-table lookup, never the completing-collision branch. Recursive
Eq containers are already excluded from covered constructor keys.

The coordinator-only bitmap initializes from existing base/overlay parent
edges, marks every later target, and is not copied into reader snapshots. A
partial Parents clear permanently invalidates this certificate because old
birth keys can survive while equality is revoked. Large external IDs decline
the proof without expanding the bitmap. The frozen binary hash is
`a5884c4dd618dfd55e720cc70b615d1baae42d98b9a28c0330b4bd231d8d6242`.

The normal pilot compares lookup-fixed, shared-code and absence in the same
campaign: 15 sum-bits pairs after one warmup, two Raytrace pairs without another
warmup. All state/schedule hashes match.

| Workload / lane | Inference median | Process median |
| --- | ---: | ---: |
| sum-bits, lookup-fixed | 31.783 ms | 193.361 ms |
| sum-bits, shared-code | 31.545 ms | 192.494 ms |
| sum-bits, absence | 31.372 ms | 195.175 ms |
| Raytrace, lookup-fixed | 16.192 s | 26.078 s |
| Raytrace, shared-code | 13.034 s | 22.814 s |
| Raytrace, absence | 13.128 s | 22.908 s |

The new proof does **not** improve on shared-code: sum-bits inference is
inconclusive and process time is worse by the median; both Raytrace pairs are
slower (approximately 0.72% inference, 0.41% process). Its improvement relative
to lookup-fixed belongs to the preceding shared-code changes. No further fast
comparison or allocator/ordered-audit build was started for this candidate.

| Certificate / domain work | sum-bits | Raytrace |
| --- | ---: | ---: |
| Certificate field checks | 6,687 | 2,074,580 |
| Accepted absent lookups | 1,019 | 242,997 |
| Declined absent lookups | 5,136 | 1,714,675 |
| Declines in imported Cell 0 | 414 | 37,297 |
| Bitmap target writes | 1,039 | 226,523 |
| Bitmap growths | 6 | 12 |
| Bitmap capacity bytes | 1,280 | 925,696 |
| Shared-code domain queries → absence | 6,165→5,146 | 1,962,583→1,719,586 |
| Shared-code signal visits → absence | 58,494→56,560 | 55,413,157→53,760,976 |
| Shared-code slice visits → absence | 59,462→57,108 | 63,490,061→62,678,951 |

The proof removes 12.4% of Raytrace domain queries but only about 3.0% of signal
visits and 1.3% of slice visits. It mostly avoids cheap domains while adding
certificate checks and bitmap maintenance. Certificate hit count is therefore
not a useful standalone admission metric. Imported roots share Cell 0 and can
lose the certificate conservatively, but these measured declines are a small
minority; Cell 0 alone does not explain the result.

`absence-*.json` contains the full counters, including the new bitmap work and
storage. The `*-vs-code.json` files provide direct paired comparisons to
shared-code so that the failed addition is not credited for earlier gains.

## Retained shared-code semantic and cost checkpoint

The retained production source corresponds to the frozen normal `runtime-code`
executable (`a3459621655df175206708da53f6bdfef1011b87f476e24aee534433d54cb0ff`).
The absence proof has been removed from the runtime; it survives only as an
explicitly rejected source patch and measurement record. The checkpoint records
source hashes in `checkpoint-metadata.json` and confirms that runtime sources
did not change during checks and the diagnostic build.

The final source passes **333 workspace tests with four preexisting ignored
tests**, 41 non-sparse condition/ownership/stable-port tests, four iterative
compiler-library tests, and the no-default-features runtime check. Exact Cargo
commands, environments and log hashes are in `validation.json` and its metadata.

A new, separate diagnostic executable uses
`sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics`.
It is compared against the frozen lookup-fixed allocator executable with the
same features and artifact, both using `--local-congruence`. Both complete
sum-bits (1,428 Runs) and Raytrace (16,883 Runs). **Exported state, ordered RHS,
effective writes, resumes, source schedule, complete Spine file and
program-independent Spine shape hashes all match exactly across binaries.**
These are executed-effect audits, not equivalence inferred from logical-match
counts. The diagnostic executable's SHA-256 is
`76601002f228eb9af53e586294af3f875518287145f613c834e6819226999e2c`.

| Execute allocation accounting | sum-bits lookup-fixed | sum-bits shared-code | Raytrace lookup-fixed | Raytrace shared-code |
| --- | ---: | ---: | ---: | ---: |
| Allocation calls | 213,720 | 212,388 | 50,334,671 | 48,838,533 |
| Reallocation calls | 20,731 | 20,731 | 3,344,769 | 3,344,754 |
| Requested bytes | 36,191,042 | 36,043,378 | 11,013,735,784 | 10,753,237,208 |

Allocator counters cover execute with ordered-audit instrumentation in both
lanes. They exclude setup/export, and requested bytes are not RSS. Diagnostic
elapsed times are not used for performance admission. Lower allocations do not
erase the measured sum-bits whole-process regression: **the two-workload,
two-metric normal performance gate remains failed**, and the historical fast
baseline remains faster than this experimental local-congruence path.

The candidate source archive is explicit:

| Candidate source | Clean base | Status |
| --- | --- | --- |
| [`candidates/columns.patch`](candidates/columns.patch) | `d03b69e9` | Historical column-route ablation |
| [`candidates/typed.patch`](candidates/typed.patch) | `ff5e6bc4` | Historical typed-condition/direct-directory ablation |
| [`candidates/marker.patch`](candidates/marker.patch) | `ff5e6bc4` | Historical template-operator-marker ablation |
| [`candidates/absence.patch`](candidates/absence.patch) | `ff5e6bc4` | Withdrawn absence certificate, including its module and regressions |
| Current checkpoint source | This checkpoint | Retained shared-code implementation |

Patch hashes and sizes are included in `validation.json`; the archive's
[`README`](candidates/README.md) describes clean-base reconstruction. This archive
does not inject the rejected absence mechanism into the retained runtime.

To reproduce the retained semantic/cost audit, preserve the normal executables
and build the diagnostic binary separately:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics -j 2
python3 benchmarks/result-port-repair/audit.py out/raytrace-parallel/runtime-fixed-allocator benchmarks/condition-bake/checkpoint-audit-manifest.json out/condition-bake/repeat-baseline-audit
python3 benchmarks/result-port-repair/audit.py out/condition-bake/runtime-code-allocator benchmarks/condition-bake/checkpoint-audit-manifest.json out/condition-bake/repeat-code-audit
python3 benchmarks/condition-bake/collect-checkpoint.py out/condition-bake benchmarks/condition-bake
```

The audit commands use preserved binaries; copy a newly built diagnostic binary
to a new path and adjust the command when reproducing elsewhere. The collector
validates the recorded `checkpoint-*-audit` directories, check logs and metadata;
the `repeat-*` directories remain a separate reproduction. No benchmark source,
artifact or build output is silently substituted into the frozen timing lanes.
