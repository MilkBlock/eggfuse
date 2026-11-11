# Constructor preparation in the owned Cell query invocation

Control: `38c39c56`. This measures the standalone Cell CPU executor, not native
egglog performance. The full execution-ownership goal remains unfinished.

## Opportunity and remaining obligations

The preceding complete executions already have zero remaining scalar suffix
dispatches. Raytrace still reaches 2,503,393 constructor boundaries and 1,428,463
write boundaries in the ordinary continuation path. These event counts include
operations later elided or supplied by existing proofs; they are not timings or
counts of fresh mutations. Moving scalar work again cannot discharge them.

When experimental Cell execution is configured, the checked typed recipe selects
one constructor per rule whose key is available from captured inputs and safe
input-derived scalar results. It skips statically elided constructors and stops
selection at Hide/Panic. No new serialized authority is introduced. Selection is
reconstructed after loading the existing aliases and dependency cuts.

Point queries, expansion queries and already-matched/deferred instances use the
existing Run invocation and sealed constructor reader. Each instance retains one
actual FactRef inline. It never writes a speculative Eq into the formal result
slot: deletion followed by a miss must allocate the original fresh source result,
not reuse the identity of a now-invalid speculative result. No extra binding,
runtime fact graph, consumer list or full operation log is maintained.

At its original RHS position, the constructor builds the ordinary current key,
checks receipt forwarding, table readiness, liveness, visibility and all key
fields. A valid witness supplies the actual result and eliminates that serial
lookup. Rejection uses the same built key for ordinary lookup. Source constructor
prefixes use the same handler and retain their existing frame-avoidance path.
Earlier Bake handoffs can already discharge the operation; unused prepared
evidence is reported separately. A snapshot miss never proves absence at commit.

This does not execute fresh construction or writes concurrently, remove the Run
query barrier, or independently schedule parked executions. Source effect order,
actual foreign-owner results, union/completion separation, deletion and Entry
publication remain authoritative. The ordinary continuation stores the witness
with its existing owner; persistent graph Cells do not acquire another field.

## Accounting and validation

[results.json](results.json) records the complete executions against the frozen
control. Both final exports are byte-identical; all 1,428 / 16,883 ordered Run
summaries and all prior graph work counters are unchanged. Native sum-bits
acceptance is `pass`, exit 0.

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Added constructor probes | 5,117 | 913,319 |
| Probes executed on pool workers | 3,637 | 898,878 |
| Snapshot hits | 3,151 | 587,939 |
| Snapshot misses | 1,966 | 325,380 |
| Source lookups removed by validated actual witnesses | 2,874 | 556,868 |
| Source witness rejections | 0 | 1,087 |
| Found evidence discarded before source execution | 20 | 1,878 |
| Found evidence unused by source lookup (including other completion takeovers) | 257 | 28,106 |
| Total key lookups, before → after | 12,235 → 14,478 | 3,694,211 → 4,050,662 |
| Additional validation field checks | 5,250 | 1,027,684 |
| Net saved equally weighted operations | −41,649 | −7,502,264 |

The instance header increases from 128 to 144 bytes and the ordinary RHS owner
from 440 to 456 bytes. The bounded inline evidence is 12 bytes before enclosing
alignment. The 366 selected rule plans add 33,312 payload bytes on each program.
Admission also expands: Raytrace matched-preparation groups grow 1,447 → 5,025,
chunks 2,071 → 11,480 and total worker invocations 4,977 → 5,737. It reuses the
source Run invocation when there is one, but can activate a previously empty
invocation for newly eligible constructor-only instances. These added costs are
part of the result, not hidden behind the successful source-lookup count.

This establishes real constructor work transfer and source-path removal, but
the broad initial selection adds work. It remains opt-in with Cell execution.
No speedup or full utilization is established. Subsequent Bake selection should
avoid already-covered handoffs and weak reuse candidates, and use typed source
effect/lifetime evidence to reduce validation. A queued union or a snapshot miss
alone cannot authorize skipping required source resolution.

`cell-constructor-preparation/v1` records selected rules and inline/instance
storage. Worker accounting includes attempts, key fields/spills, lookups,
hits/misses, unavailable evidence and writes. Source accounting includes accepted
inputs, validation checks/fields and accepted/rejected evidence. Per-worker lookup
counts distinguish actual pool work from inline execution. All speculative
lookups enter the existing total lookup counter, including misses and losing
candidates. Existing constructor domain/candidate scratch work is retained.

The Bake work reader charges new preparation and validation once, recognizes
historical reports, rejects missing current counters, and gives no credit for
coverage/hit outcomes. Lookup and row decode costs are already in their original
counters. Equal operation weights are uncalibrated and do not establish speed.

The tests compare ordered bindings, every source Run state and final exports.
Targeted cases include foreign reuse, constructor-only source prefixes, scalar
keys, canonical and stable-port readers, deleted/hidden/re-keyed evidence, union,
snapshot misses followed by earlier source births, and failure/early-stop paths.
The focused unit test verifies that speculative evidence does not assign the Eq
slot and that invalid evidence invokes the ordinary lookup exactly once.

125 runtime unit tests and 93 compiler/integration checks pass; a separate final
fixture checks all eight scalar/prefix × canonical/stable × inline/pool cases.
Compiler/integration checks force hash and Sieve collisions. All-feature and
no-default-feature compilation pass. The first compiler suite exposed a new
work-ledger check incorrectly requiring worker counters in disabled reports;
the reader now checks explicit worker enablement. The focused unit fixture also
needed an actual later source epoch for Hide's return contract. Neither fix
relaxes semantic comparisons. Original rejected logs remain in the raw output.
The README Cargo compile, run and bench commands also pass, using repeat 1 for
the minimal-branch bench smoke. The first default build exhausted temporary disk
space; after reclaiming old reproducible package/test executables, the same
commands pass. Frozen controls and raw experimental results were preserved.

Full work results are checked by [check.py](check.py), including exact final
exports, ordered Run summaries, unchanged prior graph work and the conservation
equation `total lookup delta = speculative lookups - accepted source witnesses`.
The native sum-bits acceptance uses saved native exports and the repository's
reviewed choice contract. Raytrace comparisons remain regression evidence against
the control. No new timing campaign is part of this checkpoint.

## Reproduction

Use fresh output directories and preserve the feature runtime before README
commands build the default runtime. The original frozen workload programs are
the ones recorded in the preceding timing manifests; the program hashes must
match the control reports.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals --test joint_results --test entry_publications --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-constructor-preparation/check.py ROOT PRIOR RESULTS.json
```
