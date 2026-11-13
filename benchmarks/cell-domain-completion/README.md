# Existing-domain completion on workers

**Withdrawn after timing.** The experimental implementation remains in
`254cb07f`; runtime withdrawal is `9eb78c49`. It is not an accepted speedup. The worker absorption path
from `be290103` remains separate. See the final checkpoint below.

The initial execution evidence is `e8b28751` / runtime `be290103`, frozen at
`out/cell-worker-absorption`. Final control is the intervening committed branch
`b1ab039d`, built in an isolated detached checkout and frozen in
`out/cell-domain-control`. This includes restoration accounting and the
cross-stage observation-history change, keeping them out of the optimization
delta. The initial actual Raytrace execution performs 954,783 absorption output
lookups and 2,883,551 residual row reads. Moving the proof to workers lost the
source path's cross-Run grouped upper bound. Existing actual executions expose
this repeated work; adding more composed templates alone would not remove it.

The existing typed Cell proves a two-atom constructor query whose only effect
copies a permanent min attribute. The worker now retains the maximum actual
attribute value for an entirely checked single-column candidate bucket. A later
scheduled Run may skip that domain when its exact input/attribute, structural
version, member count, constructor freshness and scalar bound still match.
Ordinary query instructions and source Run visibility stay authoritative.

The condition lives on the existing query-index bucket. No extra key index,
producer-consumer list, copied row array or binding history is created. Building
it consumes output values already read by normal per-row proofs. Missing,
retired, fresh, differently keyed or delta-rejected members prevent a complete
proof; fingerprint collisions never establish exact membership. Updates to the
constructor table invalidate the version even if fingerprints do not change.
Input decreases can reopen the condition; output monotonicity follows from the
compiler's existing no-deletion permanent-min proof.

Workers read and publish a tiny condition with `try_lock`. Contention retains
ordinary evaluation and permits duplicate proofs; no task waits for this cache.
A cache hit replaces row enumeration/output lookups. Existing absorbed logical
matches are not counted again as new avoided committed mutations. The rest of
query completion, winner order, identity reservations and publication stays on
its established path.

Charge group probes, contention, condition writes/allocations, candidate rows
skipped, embedded field capacity and retained proof heap. The field is present
in all compiled buckets in this feature configuration, including buckets that
never use it; report that cost rather than only the small successful cache.
Answer/merge buffers are a separate remaining cost.

## Validation and measurement

This measures the actual standalone Cell CPU, not native egglog. Keep the native
sum contract unchanged, compare exact final states, all source Run summaries,
effects, reverse occupancy and Bake evidence. Test cross-Run reuse, new
constructors, input decreases, retirement, collisions and contention fallback.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-domain-completion/run.py out/cell-domain-control FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-domain-completion/check.py out/cell-domain-control FRESH_OUTPUT RESULTS.json
```

After committing the validated runtime, run the quick checkpoint with all
control workloads first, then all candidate workloads. No interleaving or
compilation/tests/sampling during timing. Background load remains a possible
confounder; the previous timing checkpoint did not establish a speedup.

The full-domain count is credited to `worker.candidates` as logical candidate
coverage; physical work is measured by `row_reads`, `probes` and `group_rows`.
A cache hit therefore does not invent output hash probes or count an absorbed
RHS a second time. A retained bound stores six scalar fields; its member rows
remain solely in the existing index. The version is the published constructor
table version, so invalidation is conservative when unrelated members change.

The initial implementation put an inline mutex in every bucket: 23,213,328
bytes of reserved field capacity for Raytrace. Its semantic checks passed,
and it removed 184,181 output probes, but the empty-slot cost was excessive.
Those artifacts remain in `out/cell-domain-completion/wide-proof-slot`.
The final representation uses `once_cell::race::OnceBox` (already present in
the workspace lockfile) to allocate only after a complete proof. Initializers
may race without waiting; losing allocations are dropped and charged. Existing
proof updates use `try_lock` and fall back on contention. No custom unsafe
pointer lifecycle is introduced.

## Validated work of `254cb07f`

The final candidate and `b1ab039d` control were built from isolated committed
sources. All related checks, README Cargo commands, exact final states, all
1,428 sum / 16,883 Raytrace Run summaries, effects, reverse occupancy and Bake
evidence pass. The unchanged native sum validator also passes. `results.json`
retains commands (including isolated working directory), binary/input hashes
and charged work; the other workload remains a differential contract.

| Raytrace work | Control | Candidate |
|---|---:|---:|
| Output hash probes | 954,783 | 770,602 |
| Residual row reads | 2,883,551 | 2,699,370 |
| Absorbed logical matches | 704,026 | 704,026 |
| Answer capacity bytes, accumulated | 363,177,024 | 363,177,024 |
| Merge capacity bytes, accumulated | 404,538,816 | 404,538,816 |

The candidate performs 158,771 group checks, gets 29,731 hits, writes 127,249
conditions and allocates 1,925 proof slots. It observes zero condition-lock
contention on these executions; that is not a whole-runtime waiting metric.
Its empty slot is 8 bytes, with 7,737,632 reserved bytes across index bucket
capacity and 119,040 retained proof bytes. These are payload measurements,
not allocator overhead or peak RSS. Sum has zero group hits, 15 checks, seven
allocations, 40,584 reserved field bytes and 448 retained proof bytes.

The first timing trial was stopped by the concurrency guard after control
Raytrace warmup when other compilation began. No candidate timing was run;
all evidence remains in `timing-attempts.json` and the original artifact root.
Do not reuse its control samples in a later trial.

A remaining cost is saving bounds too high to authorize current absorption.
The input attribute is permanent min: such a bound cannot become useful for a
later, lower input without new observations. Avoiding these writes can preserve
the same successful group reuse. Answer/merge storage remains independent work.

## Final sequential checkpoint and withdrawal

A fresh second trial finished all control workloads before all candidate
workloads. Sum has five measured processes and Raytrace three, each after one
warmup. All 48 boundaries observed no competing compiler or runtime. Every
sample preserved the exact graph, Run summaries and actual effects.

| Inference median | `b1ab039d` | `254cb07f` | Observed change |
|---|---:|---:|---:|
| sum-bits | 28.570 ms | 30.107 ms | +5.38% |
| Raytrace | 5.589 s | 6.004 s | +7.43% |

Ranges overlap (sum 25.818–30.403 / 27.419–33.389 ms; Raytrace
5.453–5.968 / 5.718–6.014 s), and background storage-management activity
remains a confounder. This is not a precise causal slowdown estimate, but it
provides no performance acceptance for the added cache. Both observed medians
worsen despite 184,181 fewer output probes. The extra field capacity, 158,771
checks and 127,249 proof writes are real costs; answer/merge buffers are not
reduced. The runtime change is withdrawn instead of accumulating another
unproven maintenance path. The successful row absorption/worker takeover from
`be290103` is not withdrawn.

The completed timing command initially failed only during final compressed
export verification: Python 3.8 in the isolated checkout lacks
`hashlib.file_digest`. The verifier now uses streaming SHA-256 and exposes a
finalization function. All four original `samples.json` hashes were checked,
and those same saved samples were finalized and verified against frozen
exports using both Python 3.14 and Python 3.8. No measurement was rerun,
replaced or pooled to recover this postprocessing failure. Both attempts and
the recovery are retained in the accompanying JSON artifacts.

This experiment shows that removed worker probes alone are insufficient credit
for this change. Further work must target elapsed critical-path work while
charging proof storage, maintenance and intermediate answer handling. The
existing isolated checkout and frozen binaries retain this valid but unaccepted
implementation for later comparison.
