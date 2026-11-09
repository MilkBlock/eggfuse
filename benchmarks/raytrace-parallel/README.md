# Raytrace lookup diagnosis and bounded fixes

This measures the **standalone Cell CPU**, not native egglog. Two avoidable
constructor-lookup costs were removed from `d03b69e9`: repeating the same lookup
after a dynamic constructor miss, and enumerating every input domain just to
choose one candidate domain. The fixed local-congruence path completes Raytrace
in about 26 seconds; the original serial and four-worker experiments both failed
to finish within their 180-second diagnostic limits. It still loses to the
ordinary fast baseline. No whole-pipeline parallelism or overall acceleration is
claimed.

The original request was a real multithreaded Raytrace measurement. The first
trials exposed a serial bottleneck; the user then prioritized fixing it and
single-threaded compiler/Bake work. The completed two/four-worker pilot is
retained, but the expanded parallel campaign was stopped. All final paired
measurements here are single-threaded.

## What the execution revealed

`lookup_port_key` can accept an immutable birth-hint hit, but a miss must search
current equal input ports. Previously, choosing that search domain copied each
bound input's boundary signals into a `BTreeSet`, traversed every shared slice,
and checked live fields to find the smallest exact count. It then enumerated the
selected domain a second time. A constructor miss could pay this cost twice:
`dynamic_construct -> lookup` followed by `construct -> construct_inner ->
lookup_canonical`.

A one-second macOS sample of the original four-worker process at 152 seconds
found all 92 main-thread samples under `lookup_port_key`, 91 under
`owned_candidates`. Of these, 41 were in the first dynamic lookup and 44 in the
second. The four guard workers were parked during this interval. The process
was using approximately one core (99% CPU, 152.43 CPU seconds, 1.88 GiB RSS).
This is evidence of active serial lookup work, not a deadlock or a whole-run
utilization measurement. The serial local control also reached the 180-second
limit, last entering source Run 16,529 of 16,883.

The same 256-Run source prefix already exposes the amplification, before any
merge-program constructor calls. These are execution-only counter deltas:

| Local-congruence prefix | Before | Fixed |
| --- | ---: | ---: |
| Domain queries | 62,920 | 62,920 |
| Signals visited while selecting a domain | 6,734,014 | 0 |
| Slice steps visited while selecting a domain | 18,325,324 | 0 |
| Selected-domain signal visits | 1,017,750 | 1,006,744 |
| Selected-domain slice visits | 3,943,797 | 4,189,725 |
| Candidate domain results | 45,583 | 155,015 |
| Diagnostic prefix execution | 0.501 s | 0.241 s |

The cheaper heuristic returns more candidates here; that tradeoff is charged,
not hidden by the eliminated planning counters. Prefix state and schedule hashes
match in fast, local, and both worker modes. Prefix timings are single diagnostic
observations, not full-workload performance or admission evidence.

## Changes and proof obligations

The first dynamic lookup now canonicalizes into an inline key. On a miss it
creates the same empty frame and inserts using the already-checked key.
Allocating that frame changes neither Parents nor the constructor index, so the
absence proof remains valid. Constructor request/reuse accounting, output slots,
IDs and publication remain unchanged. The regression compares this path directly
with the former two-lookup sequence through alias misses, hits, deletion and
recreation. Full Raytrace lookup calls fall from 4,420,726 to 4,330,682: 90,044
redundant lookups removed. Sum-bits removes 104.

Domain selection now reads existing boundary bucket sizes, native-signal
presence and legacy-use counts. This is a cheap heuristic, not an equality proof
or a row-count upper bound. Only the chosen bucket is borrowed and traversed;
no temporary signal set is built. Candidate results still use an ordered set,
retain legacy entries, check current fact liveness and table identity, and pass
the existing exact port comparisons. No persistent consumer list or reverse
index is added. `candidate_count` independently returns the conservative table
witness count, preserving its upper-bound contract.

The opportunity does not require retraining the frozen catalog: an empty frame
cannot invalidate a lookup miss, and domain choice does not prove equality.
Cross-Run switching still owes actual equalities, lifetime checks, ordered
effects and boundary publication. At the tested base revision, iterative Bake
replay did not configure stable ports, port keys or local congruence; adding
ledger fields alone therefore did not train this execution path. That compiler
configuration gap and further shared-template specialization are separate work.

## Final serial timing

All lanes use the same frozen ownership-baked artifact per workload. Normal
release features are `sparse-cells,view-ports,storage-metrics`, with no allocator,
trace or overlap-probe instrumentation. `fast_archived` is the historical
`8fffff65` ordinary runtime; `fast_before` is `d03b69e9`; `fast_current` includes
these two fixes. All fast lanes use `--repair-ports --entry-publications`.
The local lanes use `--local-congruence`.

| Workload / lane | Inference median | Complete process median |
| --- | ---: | ---: |
| sum-bits, archived fast | 21.607 ms | 144.303 ms |
| sum-bits, current fast before fixes | 21.930 ms | 182.435 ms |
| sum-bits, current fast fixed | 21.771 ms | 180.424 ms |
| sum-bits, local before fixes | 39.814 ms | 202.550 ms |
| sum-bits, local fixed | 31.958 ms | 192.760 ms |
| Raytrace, archived fast | 7.754 s | 10.010 s |
| Raytrace, current fast before fixes | 7.892 s | 10.263 s |
| Raytrace, current fast fixed | 7.860 s | 10.266 s |
| Raytrace, local fixed | 16.393 s | 26.137 s |

Sum-bits uses one warmup and 15 interleaved fresh processes per lane. Local
inference improves 19.73% by ratio of medians; whole-process time improves 4.83%.
Paired-median ratio intervals from a 10,000-resample bootstrap are
`[0.7909, 0.8147]` and `[0.9213, 0.9793]`. The fixed local path still takes
1.48 times archived-fast inference and 1.34 times its process time. The ordinary
fast path's small sum-bits changes do not exclude noise.

Raytrace uses three interleaved fresh processes per completed lane, after earlier
pilot runs warmed each configuration. Local inference spans 16.285–16.401 seconds;
process time spans 26.088–26.203 seconds. It remains 2.11 times archived-fast
inference and 2.61 times its process time. The three-sample bootstrap intervals
in JSON are descriptive and too small a sample for a broad performance claim.
The original local run has no completed timing: its 180-second timeout, with
progress logging, is retained as a censored diagnostic, not an exact speedup
denominator. The sampled four-worker timeout is likewise diagnostic.

Whole-process timing includes loading, validation, setup, inference, export,
report checks, serialization and teardown. Initial exploration used Python's
timeout waiter, whose POSIX polling can add up to 50 ms after exit. This was
corrected to blocking `waitpid` plus a timeout watchdog, and **all final serial
samples were rerun**. Exploratory wall values are not used in this table or its
intervals. Equal-length executable/input symlinks and numeric output names
control the known path-length sensitivity.

## Parallel pilot and remaining cost

Before the final serial campaign, one full fixed pilot measured local serial
14.580 seconds inference, two workers 15.449 seconds, and four workers 15.114
seconds. These values are from the same interleaved pilot and should not be
mixed with later serial medians. The two/four-worker lanes executed
`[95,308, 73,448]` and `[54,936, 54,119, 40,889, 18,812]` completion tasks,
respectively, so the threads did real work. The mechanism parallelizes guard
reads with ordered serial commits; matching, effect publication and constructor
lookup still retain a writer. It did not demonstrate a speedup. Pure epochs were
not enabled, so the prior independent-frontier proof is not exercised here.

After the fixes, full local Raytrace still visits 55,413,157 signals and
105,558,365 selected-domain slice steps, producing 10,000,938 domain results and
12,161,275 checked key candidates. It also performs 37,495,361 port reads. These
are remaining real enumeration and equality costs. They motivate compiling
table/column restrictions into shared slices; eliminating the planning counters
has not made constructor matching free.

## Semantics and allocation

The workspace passes 329 tests, with four preexisting ignored tests. The sparse
focused suites pass 79 tests; non-sparse ownership/stable-port suites pass 38;
the runtime also passes `--no-default-features` checking. Candidate coverage,
sorted uniqueness, upper bounds, stale routes, aliases and deleted/recreated
facts remain checked.

Separate allocator/trace builds compare exact ordered RHS, effective writes,
resumes, exported state, schedule and Spine hashes on both complete workloads.
Sum-bits also matches the pre-fix diagnostic executable. These are executed
effect audits; logical rule matches are not treated as committed mutations.

| Execute allocation accounting | Before local sum-bits | Fixed local sum-bits | Fixed fast Raytrace | Fixed local Raytrace |
| --- | ---: | ---: | ---: | ---: |
| Allocation calls | 252,581 | 213,720 | 26,931,718 | 50,334,671 |
| Reallocation calls | 38,910 | 20,731 | 3,025,102 | 3,344,769 |
| Requested bytes | 50,585,522 | 36,191,042 | 8,940,176,664 | 11,013,735,784 |

The allocator build additionally enables `slot-transfer-audit,spine-shapes,
allocation-metrics`; its timings are excluded. Requested bytes measure allocator
requests during execute, not RSS. No expensive pre-fix local Raytrace allocator
run was attempted after the normal executable exceeded the time limit.

## Reproduction and evidence

`metadata.json` records machine, features, source file and executable hashes;
`timing-*.json` contains every final timing sample and comparisons;
`diagnosis.json` retains the prefix counters, censored trials and parallel pilot;
`allocations-audit.json` contains ordered audit hashes and allocation results;
`validation.json` records checks and log hashes. Raw logs and large outputs stay
under untracked `out/raytrace-parallel/`.

The machine is an Apple M3 Max, 12 performance plus four efficiency cores, 48 GiB
RAM, macOS 27.0.1, rustc 1.94.0. CPU affinity was not pinned. Parent work avoided
Cargo and CPU-heavy tasks during timing; normal background services remained.

Preserve the frozen artifacts and archived executables before building a new
candidate. The normal baseline for subsequent local-congruence experiments is
`out/raytrace-parallel/runtime-fixed`, source hash
`bf39edb235f52c7617e660560ef3c842c02f57ec2722137cc40c01ade61ca7c4`.

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics -j 2
python3 benchmarks/raytrace-parallel/measure.py benchmarks/raytrace-parallel/timing-raytrace-manifest.json out/raytrace-parallel/repeat-raytrace --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/raytrace-parallel/measure.py benchmarks/raytrace-parallel/timing-sum-bits-manifest.json out/raytrace-parallel/repeat-sum-bits --repeat 15 --warmups 1 --timeout 10
python3 benchmarks/raytrace-parallel/collect.py out/raytrace-parallel/repeat-raytrace out/raytrace-parallel/repeat-raytrace.json
python3 benchmarks/raytrace-parallel/collect.py out/raytrace-parallel/repeat-sum-bits out/raytrace-parallel/repeat-sum-bits.json
```

Manifests reference the preserved binaries; building a new candidate does not
silently replace them. To reproduce a prefix, temporarily copy `probe.rs` into
`engine/cell-runtime/examples/raytrace_parallel_probe.rs`, build that example
with the normal feature set, and invoke it as `PROGRAM OUTPUT_JSON MODE 256`.
Remove only that temporary example after building. Its modes configure the same
ownership/stable/key/condition layers as the runtime. The prefix runner never
changes lookup or repair implementation.

The full diagnostic audit uses the normal features plus the three diagnostic
features listed above, then runs `benchmarks/result-port-repair/audit.py` with
`audit-manifest.json`. Compiler and runtime builds remain separate. No artifacts,
binary mutation streams or generated executables are tracked; no published site,
remote branch or `egglog-baseline` tag is changed.
