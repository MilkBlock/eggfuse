# Unit-presence markers in the union-digest path

This iteration continues from `31979aff`. Digest mode now accepts scalar
constructors, plain Unit relations, and scalar-key Unit functions whose merge
is exactly `old` or absent. Marker names do not grant eligibility: the typed
schema and merge expression must satisfy the same check. Functions returning
other values, custom Unit merge expressions, containers, deletion and
subsumption still reject the entire program before output creation. There is
no silent fallback to a mixed effectful repair engine.

This is the **standalone Cell CPU executor**. Native egglog supplies Bake and
correctness oracles; it is not the timed runtime. The work does not add a GPU
backend, remove union-find, or train a new repair predictor.

## Why this fragment can be scheduled differently

The last iteration's actual executions showed repeated constructor-key updates
and retained Entry snapshots. The frozen application declarations also contain
34 marker views with scalar keys, Unit outputs and `:merge old`. Their result
cannot create another equality. This typed fact lets the engine collect Unit
notifications during constructor closure and join their keys once afterward,
while source-rule consumers continue to wait for the original Run boundary.

This discharges repeated Unit-key canonicalization within a Run. It does not
discharge consumer watermarks, correlated tuples, witness forwarding, view
ownership or source checks. It also does not justify postponing a merge that
reads another function or constructs a new term. Even a Unit-valued custom
merge is rejected if it could perform such work. A separate regression checks
that case.

The remaining obligations are implemented as follows:

1. Constructor deltas still update shared row fields and emit exact-key result
   unions. Plain Unit relations use the same virtual-row index, but matching
   their keys emits no result union.
2. Affected Unit functions enter a deduplicated witness set. Their cached fields
   are invalidated immediately. No source matcher sees the in-progress state.
3. After constructor closure, all affected Unit rows are read canonically and
   all their old keys are detached before probing any new key. This prevents a
   stale directory entry from becoming a false keeper. Complete tuples remain
   correlated throughout.
4. Exact Unit-key matches retire the duplicate and forward its receipt. Both
   results are checked to be the unique Unit value, so no merge callback is
   needed. Remaining rows are reindexed and enter the existing ChangeBatch.
5. A compact Unit port detaches and restores its existing alias directory entry
   using shared canonical fields. It does not acquire a separate owned key
   vector. Retirement updates both alias counts and the ordinary ownership/
   receipt bookkeeping.

The small typed column plans and current indexes are reused across Runs. This
is a scheduling proof from compiler types, not a prediction learned from e-class
numbers. Canonical representatives and source Run barriers remain in use.

## Actual Bake and compact-port check

The checked fixture is
[union-digest-ports.egg](../../tools/cell-compiler/tests/fixtures/union-digest-ports.egg).
It goes through the normal native Bake, marker selection and Cell compilation
pipeline. The compiler selects one `CellSpineView` marker and one separate
`Ticket` producer/consumer view block. Thus selected markers and compact Unit
ports are both exercised, without claiming they are the same table.

The test compares ordinary and digest Cell states at every emitted Run and
compares their binding audits. Both normal and zero-bit constructor fingerprints
are checked. Native egglog independently executes the original and marked
source checks, and its final marked graph is compared with digest Cell's graph.
The fixture includes later unions that rekey surviving compact ports and a
later collision that retires a compact port. Ordinary repair promotes all four
compact ports. Digest mode performs four compact rekeys, retires one duplicate,
and leaves the other three compact, with zero promotions. Detailed counts are
retained in [unit-checks.json](unit-checks.json).

The hash-width flag forces the virtual-fact fingerprint buckets to collide.
Unit function indexes retain their existing exact-key containers; the flag
does not replace those containers' hashing implementations.

## Measurements

Apple M3 Max, Rust 1.94.0, standard release with
`sparse-cells,view-ports,storage-metrics`, no PGO or CPU/LTO overrides. Each
synthetic fixture has 256 pairs and depth/fanout 32. Unit markers contain the
whole `(level, child, result)` tuple. The schedule is
`make → mark → consume → alias → consume → mark → consume`, exercising cached
consumers, post-union lookup and reinsertion.

These scaled fixtures use typed IR and an explicitly designated `Mark` table;
they do **not** run automatic marker Bake. The actual Bake check above is a
separate correctness experiment. Each timing session has three lanes, separate
warm-ups and seven fresh-process samples in alternating forward/reverse order.
Audits are outside timing. Inference excludes setup and export.

| Fixture | Final mode off | Final digest | Change | First-session change |
|---|---:|---:|---:|---:|
| Unit chain | 76.277 ms | 72.743 ms | −4.6% | +0.2% |
| Unit fanout | 79.473 ms | 71.354 ms | −10.2% | −6.7% |
| Unit stable/no effective unions | 32.998 ms | 34.888 ms | +5.7% | +4.6% |

The first session preceded a compact-retirement counter correction and CLI
help clarification. Both sessions, raw samples and executable hashes are in
[unit-results.json](unit-results.json). There was no timing-based parameter
tuning between them. The variation in the chain result prevents a strong
speedup claim there. Fanout improves in both sessions, while the no-union case
consistently slows down. This remains opt-in.

Final peak RSS through inference is 88.61 / 87.16 MiB for mode-off/digest chain,
93.70 / 92.88 MiB for fanout, and 83.70 / 83.70 MiB for stable. There is no large
memory reduction in these non-compact synthetic Unit tables.

Both union fixtures receive 16,384 Unit notifications. These coalesce to 8,284
rows in chain and 11,136 in fanout. Each retires 8,192 duplicate Unit rows and
avoids 8,192 repair-time Unit merge calls. Explicit source writes still execute
their ordinary merges; their counters are not removed. Logical matches,
notifications and key probes are not counts of committed mutations.

The original five constructor fixtures also retain identical per-Run graphs,
bindings and schedules against `31979aff`. Their median inference changes
range from about −7% to +6%; this does not establish a uniformly free extension.
Those regression samples are included in the same results file.

`publication_visits` retains the constructor/virtual-row meaning from the prior
iteration. Unit work is reported separately as `unit_notifications`,
`unit_rows_rekeyed`, `unit_key_matches`, `unit_rows_retired`,
`unit_compact_rekeys` and `unit_compact_retired`. `live_packets` counts virtual
facts, not the separately stored Unit functions. Zero ordinary-repair visits
therefore does not mean zero maintenance work.

## Application boundary and checks

The frozen sum-bits and Raytrace schemas each contain 241 eligible scalar
constructors, 141 eligible Unit-presence tables (including all 34 marker views),
18 other functions and one container constructor. Their rules contain 19
visibility-changing operations. These are declaration counts, **not** measured
repair coverage. Both complete programs still reject digest mode, initially at
`DUMMYCTX`; the other exclusions remain live as well.

Mode-off execution matches the `27f098a2` final graphs/anchors, schedules and
graph counters on both frozen applications. This is not a per-Run native audit
or a digest performance result for those applications.

All-feature workspace tests pass: 159 passed, four existing tests ignored. The
eight digest integration tests also pass with the default non-sparse runtime.
They retain the previous renaming, full-tuple, repeated-variable, cycle,
incremental-oracle and Entry snapshot checks, and add native Unit-presence,
real Bake-marker and compact-port retirement checks. Full check provenance is
in [unit-checks.json](unit-checks.json).

## Reproduce

Use fresh output directories from the repository root:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports --example union_digest_fixture
mkdir -p out
python3 benchmarks/union-digest/run.py --output out/unit-digest --repeat 7 --shapes unit-chain unit-fanout unit-stable
target/release/eggfuse-cell-compiler compile --source tools/cell-compiler/tests/fixtures/union-digest-ports.egg --output out/unit-ports
target/release/eggfuse-cell-runtime --program out/unit-ports/program.json --union-digest --audit-stages --output out/unit-ports-run
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --test union_digest
```

To include the saved `31979aff` executable, pass it with `--baseline`: that lane
runs with digest disabled because the older digest rejects Unit tables. For the
constructor-only regression, use `--previous-digest` instead. Artifacts, binary
executables and snapshots stay under ignored output directories.
