# Typed constructor result ports

This experiment extends `48f73d70` on the **standalone Cell CPU runtime**.
It executes the complete sum-bits and Raytrace applications, including mutable
functions, containers and visibility changes. Native egglog supplies focused
semantic checks; it is not the runtime timed here. The experiment is opt-in
through `--repair-ports` and cannot be combined with the restricted union-digest
or congruence-cells backends.

## Opportunity and proof

The preceding producer catalog increased constructor receipt reuse but left
Raytrace's 643,609 dependency repairs unchanged. Its actual execution profile
spends about 0.73 s in repair and 1.80 s in query update out of 9.49 s inference.
That diagnostic run overlapped a build, so these figures identify work, not an
isolated performance baseline. Repair alone is not the dominant phase.

Ordinary repair invalidates and reconstructs a constructor row even when only
its result class changes. The compiler now emits an exact typed key footprint
for each eligible constructor: the key columns containing direct equality
values. Scalar and structural-key columns cannot contain equality references;
container and unknown key sorts are ineligible. The runtime independently
reconstructs and verifies the footprint. Legacy artifacts without it derive
the same footprint during setup.

For an equality delta `from -> to`, an eligible cached constructor row can
complete its result port locally when:

1. Its decoded fields were canonical before the delta; no prior key repair is
   pending. Ordinary key invalidation clears this cache.
2. No certified key column contains `from`, and the result contains `from`.
3. Its current intern bucket contains exactly that row. Ambiguous buckets keep
   ordinary collision processing, including duplicate imported keys.

The operation changes the cached result, stamps its epoch, invalidates query
caches and emits an ordinary table touch. Its key index and immutable Cell
body remain intact. The union dispatcher already redirects reverse incidences;
later subscription or retirement canonicalizes their old dependency IDs.
Shared field snapshots use copy-on-write, preserving earlier Entry packets.
If a later delta changes a key, the row falls back to ordinary repair.

For example, merging `F(a)` with `b` need not reconstruct the `F(a)` key when
`a` is unchanged. The proof is a property of the typed node ports, independent
of the numeric labels assigned to classes. Execution still uses the original
union-find representatives and queue order. This is not a complete representation
of union as nodes, a numbering-free executor, or removal of the Run barrier.

The singleton check is deliberately conservative. A dirty row rekeying into
this body later finds the same survivor; an existing ambiguous bucket retains
the original ordered repair. Hash equality never proves semantic equality.
Mutable function merges, key changes, recursive container repair, deletion and
subsumption retain their existing implementation. No logical match authorizes
a mutation or bypasses a source Run publication boundary.

## Complete application audit

Both lanes use the latest completed-producer catalogs: 208 units for sum-bits,
316 for the unpruned Raytrace audit. The compiler plan does not retrain them.
Across 1,428 / 16,883 Runs respectively, the following are byte-identical:
final graph export, ordered RHS-input digests, effective function-write digests,
continuation-resume digests and Spine shape traces. The semantic schedules also
match. [results.json](results.json) records the hashes and complete counters.

| Case | Ordinary repairs | With result ports | Result-port events | Field copies |
|---|---:|---:|---:|---:|
| sum-bits | 2,229 | 1,496 | 878 | 530 |
| Raytrace | 643,609 | 479,589 | 182,870 | 140,973 |

Ordinary repairs decrease by 32.9% / 25.5%. Result-port events are equality
incidence updates, not committed mutations or avoided repair counts: ordinary
repair can coalesce multiple deltas to one row. Raytrace retains 226,523 effective
unions, 34,063 successful constructor receipt reuses and 18,016 completed RHSs.
Most result events occur in `Smaller` (73,956), `Get` (27,302), `AddContext`
(25,751), and `SubTuple` (22,259).

Eager table touches have a cost. Some locally updated rows subsequently retire
during key collision repair. Delivery events rise from 7,493 to 7,638 for
sum-bits and 3,146,119 to 3,164,969 for Raytrace; distinct events rise from
6,718 to 6,764 and 2,798,026 to 2,805,065. All other graph counters and non-time
Spine counters remain equal. These additional touches do not change the audited
executions, but matter for performance and future publication coalescing.

## Timing and limits

Seven interleaved fresh-process samples per lane, after one warmup, use the
same normal executable for `control` and `ports`. `parent` is the archived
`48f73d70` executable with the same features and program. There are no concurrent
compiler or training jobs. This is a shared workstation with uncontrolled
background load; the sample ranges overlap. [timings.json](timings.json) keeps
every timing sample and all execution counters. Invariant counters are compared
across every sample and warmup before being stored once per lane.

| Case / lane | Median inference | Median repair phase | Median peak RSS |
|---|---:|---:|---:|
| sum-bits / parent | 19.578 ms | 1.470 ms | 167.516 MiB |
| sum-bits / control | 21.326 ms | 1.623 ms | 167.500 MiB |
| sum-bits / ports | 19.335 ms | 1.247 ms | 167.547 MiB |
| Raytrace / parent | 7.572 s | 0.594 s | 1,863.172 MiB |
| Raytrace / control | 7.472 s | 0.587 s | 1,865.828 MiB |
| Raytrace / ports | 7.315 s | 0.506 s | 1,866.828 MiB |

Raytrace's median repair phase falls 13.8%; total inference falls 2.10%
relative to the same binary's control. The median per-iteration paired change
is -1.66%. Inference ranges are 7.302–7.723 s for control and 7.171–7.875 s
for ports. Query update remains about 1.43 / 1.41 s. This is a small measured
application improvement, not evidence that rebuild or publication is solved.

The first short-workload comparison also shows an unexplained 8.93% default
control/parent gap. To check that possible regression, a separate 31-sample
interleaved sum-bits run uses the same three binaries/programs, with no builds
or implementation changes between runs. [timings-short.json](timings-short.json)
records it in full:

| sum-bits lane | Median inference | Median repair phase |
|---|---:|---:|
| parent | 21.123 ms | 1.627 ms |
| control | 21.125 ms | 1.631 ms |
| ports | 20.755 ms | 1.333 ms |

The default control/parent difference is now +0.012%, and ports improves total
inference by 1.75% (paired median -1.91%). The initial short-run 9.34% apparent
ports speedup is not a stable estimate. Both datasets are retained. The path
remains opt-in: it removes redundant key work, retains substantial field-copy
and publication costs, and provides no demonstrated memory-compression win.

## Validation

171 all-feature workspace tests pass, with four existing tests ignored.
The 14 focused repair-port and union-expression tests also pass with the
non-sparse backend. Coverage includes later key merges, custom mutable merges,
deletion/reinsertion, subsumption, nested equality in Set keys, ambiguous initial
keys, cycles, transitive equalities, shared old Entry packets, renumbered and
reversed initial allocations, corrupted certificates and legacy artifacts.
Existing union-expression fixtures compare every source boundary against native
egglog and a full-scan congruence oracle where applicable.

## Reproduce

Use the preceding experiment's learned artifacts and fresh output paths.
`programs.json` maps case names to program paths. Build and save the audit
executable before building the timing executable.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes --bin eggfuse-cell-runtime
python3 benchmarks/result-port-repair/audit.py target/release/eggfuse-cell-runtime programs.json out/repair-port-audit
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test repair_ports --test union_digest
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime
python3 benchmarks/leaf-completion/measure.py timing-spec.json out/repair-port-timing --repeat 7
python3 benchmarks/result-port-repair/collect.py out/repair-port-timing/samples.json timing-results.json
```

The timing spec has shape `{case: {lane: {runtime: PATH, program: PATH,
args: [FLAG]}}}`. Compare the same program and executable with no arguments and
with `args: ["--repair-ports"]`. A third lane uses the archived parent executable
to check the default-path cost. The runner interleaves fresh processes after
one warmup, verifies each graph and schedule, and stores samples before deleting
only its generated exports. Inference excludes setup and export. Keep compiler
and training jobs out of timing runs.

For the short-workload followup, use only the sum-bits entry from the same
manifest and pass `--repeat 31`. `collect.py` rejects incomplete measurements
or changed counters rather than silently treating them as invariant.
