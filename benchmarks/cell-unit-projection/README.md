# Borrow Unit keys from the Cell's compiled operand projection

The previous catalog (`6a8ea4ac`, runtime `bc3e2d19`) executes 149,817 exact
Unit probes on Raytrace, finds 100,195 existing rows and saves 99,910 source
lookups. Its workers still materialize every key and store small witnesses in
records sized for an entire candidate Function. The measured 18,940,416 bytes
of temporary key spills and 19,231,152 bytes of prepared fields/vectors identify
redundant representation work; the preceding short checkpoint did not establish
a speedup.

The existing Cell definition already provides each operand's slot or literal,
the Unit table, total old/new merge and completed scalar/constructor prerequisites.
The lookup now hashes and compares through that immutable operand projection,
borrowing the actual values. Missing slots reject preparation; hash collisions
still require exact length/field equality. Typed scalar directories keep their
existing direct access. No additional query, index or binding state is added.

On a miss the worker produces only the final shared field allocation. Prepared
records carry that allocation or the existing row's actual witness. Source-only
origin/epoch and fixed storage metadata are assembled during adoption, where
they were previously overwritten anyway. Adoption transfers the same fields;
it does not rebuild the key or replay the RHS. Records are now 40 bytes including
the operation position. The ordinary Instance, mixed holder and source Execution
retain their existing sizes.

Union generation, pending unions, deletion/recreation, canonicality, row epoch,
source order, merge accounting and receipt/publication checks remain live. The
existing cross-Run Entry projects actual results at the same visibility boundary.
This removes key copies and oversized handoff records within already proven
coverage; it does not claim a new cross-Run takeover or concurrent shared-index
mutation. Hashing and candidate comparisons still read slots and may repeat a
slot access, which must be paid for in actual timing.

## Work and semantic results against `6a8ea4ac`

| Work/storage | sum-bits control → candidate | Raytrace control → candidate |
| --- | ---: | ---: |
| Worker Unit probes | 74 → 74 | 149,817 → 149,817 |
| Existing witnesses found | 32 → 32 | 100,195 → 100,195 |
| Source exact lookups skipped | 28 → 28 | 99,910 → 99,910 |
| Physical field rows prepared | 42 → 42 | 49,622 → 49,622 |
| Temporary key spill bytes | 6,528 → 0 | 18,940,416 → 0 |
| Prepared field/vector bytes | 11,840 → 7,696 | 19,231,152 → 10,841,400 |

Probe, hit, miss, prefix, source adoption/rejection and merge counts are checked
unchanged. The eliminated key storage and smaller records save 10,672 /
27,330,168 counted requested bytes in these executions. These counters exclude
allocator metadata and internal collection temporaries; they are not total
allocator traffic or peak memory. The final field allocation is still necessary
for a new row. Its iterator may reread slots after a lookup miss.

Each outcome is now 40 bytes including its operation position. The Instance
remains 160 bytes, inline evidence 32, mixed holder 48 and source Execution 512.
Compiled payload and 800-byte query task counters are unchanged. Existing
constructor-prefix coverage and all source Unit work are unchanged.

All 1,428 sum-bits and 16,883 Raytrace ordered Run summaries, exact final states,
logical effects, merge counts, iterative evidence and live reverse occupancy
match the control. Native sum-bits acceptance is `pass`, bound to the fresh CPU
export. 205 runtime tests pass both normally and under forced collisions;
97 integration tests, additional collision reruns, storage checks,
all-features/sparse/legacy compilation and README compile/run/bench smoke pass.
The initial Result-alias compile error and publication-fixture collision failure
are retained in `validation_attempts`; neither was accepted or suppressed.

## Reproduce

This is the actual standalone Cell CPU, not native egglog. Compare exact final
states, source Run summaries, logical effects, merge accounting and maintained
incidence against the unchanged four-worker control. The reviewed native sum
gate must pass and match the fresh export hash. Raytrace remains differential.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-unit-projection/run.py out/cell-unit-witness FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-unit-projection/check.py out/cell-unit-witness FRESH_OUTPUT RESULTS.json
```

Run the checks recorded in `results.json`, retaining exits in `validation.json`
and `readme-checks.json` and failed development attempts separately. Runtime
tests compare projected keys with ordinary inserted keys for zero-length,
scalar, text, collection and wide keys, forced hash collisions, missing slots
and retired rows. Integration checks cover wide keys and mixed existing/new
outcomes, as well as the established union/deletion/error/Run-boundary cases.

The expanded full collision sweep exposed an existing publication fixture that
expected a fingerprint delta even with all hash bits masked out. That fixture
now explicitly verifies both 0-bit and 64-bit behavior and the actual new row
value. This changes no publication runtime code or semantic acceptance rule.

After validation and the runtime commit:

```sh
python3 benchmarks/raytrace-parallel/quick.py out/cell-unit-witness FRESH_OUTPUT FRESH_TIMING_OUTPUT benchmarks/cell-unit-projection/timing-results.json
```

All control sum-bits and Raytrace runs finish before any candidate run. The
timer checks full executable names at each sample boundary and stops if another
compiler or Cell workload appears. Keep every attempt and sample; do not merge
unaffected pieces of interrupted attempts. Boundary guards cannot exclude all
system load or work entirely between observations. Grouped timing is not a
statistical-significance or full worker-utilization claim.

## Sequential quick checkpoint

Control `6a8ea4ac`, candidate runtime `483e379b`, four workers, identical frozen
programs and flags. This attempt completed on its first run, with no compiler
or other Cell workload detected at 48 sample/group boundaries. All 20 warmup
and measured executions pass frozen-state, Run-order and effect checks. No
samples were discarded; the order is control sum, control Ray, candidate sum,
candidate Ray. Native sum acceptance remains tied to the fresh CPU export.

| Inference median | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| sum-bits, five samples | 24.205 ms | 25.382 ms | +4.86% |
| Raytrace, three samples | 5.227398 s | 4.985200 s | −4.63% |

Individual Raytrace ranges are 5.218226–5.270761 s / 4.954621–5.604177 s;
sum-bits ranges are 24.145–28.723 ms / 24.109–26.325 ms. The Raytrace median
improves in this short grouped checkpoint, but candidate variation, grouped
order and system load prevent attributing the entire change to this code.
Sum-bits regresses, so this is not a general speedup.

The candidate's accumulated source-Run phase medians remain roughly 1.847 s
RHS, 1.707 s search, 0.991 s query update and 0.413 s repair. These are wall
intervals that can contain worker work or waits, **not** isolated serial CPU
costs. They motivate returning to the larger RHS/publication/wait boundaries
after removing this preparation overhead. Do not use the storage reduction
as proof that those boundaries or full worker utilization are solved.
