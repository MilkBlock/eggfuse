# Existing-domain completion on workers

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
