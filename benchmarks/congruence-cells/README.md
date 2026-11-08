# Congruence as persistent completion expressions

This experiment continues from `abd3e583` on `codex/union-digest-matching`.
`--congruence-cells` executes constructor congruence through explicit application,
equality and completion nodes in the **standalone Cell CPU runtime**. It does
not time native egglog. The existing `--union-digest` and ordinary modes remain
available as controls; the new mode is opt-in.

## Opportunity and execution contract

The previous Unit experiment coalesced notifications, but constructor equality
still changed keys, probed the interning directory and emitted more unions for
each equality event. Its repeated local work was not available as an expression
that could wait, share premises and complete across source Runs.

The new primitive expressions are:

```text
App(table, [immutable typed arguments], result)
Eq(left, right)
Complete(App1, App2, [argument Eq ports], result Eq)
Source(Eq)
```

The table identity, arity and exact primitive arguments constrain a completion
recipe. Every equality argument is a correlated port; repeated arguments can
refer to the same Eq node. A cell keeps its unsatisfied premises between Runs.
Only committed connectivity satisfies a port. A queued result or a cyclic
dependency cannot satisfy its own premise. Two different operators can share
the same argument Eq nodes while retaining distinct completion cells.

The runtime discovers candidates when applications share an argument class at
the same column and typed scalar shape. A union joins the two classes' argument
port groups. A new application also joins existing equal ports. Scalar-only
applications use their exact scalar shape. This is complete for this fragment:
when all arguments eventually agree, at least one equal argument either existed
at insertion or arrived through a class merge. Matching application pairs are
interned, so later ports resume the existing cell. This avoids an unconditional
all-pairs table scan, but a dense shared port can still create quadratically
many partial cells. That cost has not been solved.

Completing a cell proposes its result Eq. Union-find is retained as the
connectivity index and supplies transitive equality to waiting ports. All
constructor congruence proposals come from these cells. The graph's canonical
constructor keys do not participate in deriving those proposals.

After closure, a compatibility publication pass updates each affected row once,
reindexes complete keys, forwards duplicate receipts and delivers ChangeBatch
to the existing shared Entry scheduler. Equal keys at this point **must already
have equal results**; otherwise execution fails instead of falling back to a
repair union. Unit functions use the previous coalesced presence-key pass.
Activation already publishes a canonical new row. The final version only queues
that row again at birth if its interning bucket suggests a possible duplicate;
this hint cannot derive equality. The separate `expression_publication_births`
counter records those queued births, including false hash collisions. The first
measurement session unnecessarily queued every birth; both sessions are kept.
This implementation still has RHS publication, canonicalization,
union-find and the original Run barriers.

The admissible fragment is unchanged: scalar constructors, Unit relations and
scalar Unit functions with absent/`old` merge. Value functions, custom merges,
containers, deletion and subsumption reject the program. Monotonic constructor
facts justify retaining immutable historical application nodes after a physical
witness is retired. This would require another lifetime contract for deletion.
Runtime numbers identify references; they are not learned equivalence rules.

## What is integrated, and what remains

The expression engine actually supplies constructor closure in the Cell CPU;
it is not a trace of closure already performed by ordinary rebuild. Setting
all constructor fingerprint bits to zero preserves correctness. The independent
proof replay checks each cell using prior source equalities and congruence
steps, without using runtime representatives or trusting final completion bits.

This is a new primitive expression executor inside the runtime, not yet a set
of ordinary source-rule Cell templates mined or composed by iterative Bake.
The current source-program Bake, Spine and shared Entry still run around it.
Thus cross-Run repair-cell completion is demonstrated, while general
cross-stage RHS completion through baked repair expressions remains future work.
No GPU or multithreaded backend is added.

The prototype retains applications, equality nodes, cell pairs, argument
postings and a proof sequence for the entire run. Its port directory duplicates
part of the graph's existing reverse incidence information. Reports include
these counts; `live_packets` still refers to graph virtual facts, not the size
of the expression graph. The mutable digest key-packet count remains zero;
immutable application fields are reported under `congruence_cells.applications`.
These storage and candidate costs are the next obstacles to address before
claiming a cheaper RHS publication path.

## Validation and measurements

The integration tests run both digest and expression modes with 0/64-bit
constructor fingerprints. They compare per-Run rows, bindings and schedules
with ordinary Cell and native egglog, reverse initial allocation and rename
identities, cover actual selected Bake markers and compact-port retirement,
and check incremental insertions/unions against an exhaustive congruence oracle.

New focused checks inspect a pair of cells before and after separate source
epochs: both share premises, keep the same cell IDs, and complete only after
the second equality arrives. A recursive example stays unfinished until an
external equality arrives. A separate source-scheduled fixture compares these
stages with native egglog. The proof checker also rejects a staged audit with
its source-equality evidence removed.

Final checks: 162 workspace tests passed, four existing tests ignored; all
11 digest/expression integration tests also pass with the default non-sparse
runtime. [checks.json](checks.json) retains proof-replay counts, the actual Bake
fixture audit, executable hash and CLI rejections. Complete sum-bits and
Raytrace programs still reject this fragment at `DUMMYCTX` before output creation.

[example-nodes.json](example-nodes.json) contains the complete 17-application,
six-cell graph from one staged group, with its source and table-name mapping.
Cells 0 and 1 retain their two argument ports from epoch 3 to epoch 5. Both use
the same Eq nodes. The remaining cells carry the resulting equality through
`F` and `Seen`. It can be checked directly with `verify.py`.

The benchmark compares ordinary mode, the current digest, the saved `abd3e583`
digest, and completion cells. It uses Apple M3 Max, Rust 1.94.0, standard release
with `sparse-cells,view-ports,storage-metrics`, 256 groups, depth/fanout 32,
separate warm-ups and seven fresh-process samples in alternating lane order.
No compilation, tests or competing benchmarks ran during timing. Inference
excludes setup and export. These are direct typed-IR fixtures, not automatic
Bake training workloads. Audits run separately from timing.

| Fixture | Ordinary | Digest | Completion cells | Cells vs digest | Initial cells vs digest |
|---|---:|---:|---:|---:|---:|
| chain | 19.285 ms | 20.037 ms | 30.091 ms | +50.2% | +76.6% |
| fanout | 20.843 ms | 18.993 ms | 25.838 ms | +36.0% | +65.9% |
| stable | 18.396 ms | 20.247 ms | 25.334 ms | +25.1% | +47.9% |
| unit-chain | 75.209 ms | 73.826 ms | 91.206 ms | +23.5% | +35.0% |
| unit-fanout | 75.887 ms | 70.193 ms | 86.202 ms | +22.8% | +28.5% |
| unit-stable | 34.129 ms | 34.582 ms | 40.136 ms | +16.1% | +35.8% |
| staged | 136.209 ms | 113.225 ms | 187.021 ms | +65.2% | +79.1% |

The final expression mode remains slower on every fixture. The initial session
queued all newly activated rows for another publication; skipping those redundant
visits reduced work but did not recover the expression/index storage costs.
Both sessions and every raw sample/executable hash are in [results.json](results.json).
The parent-digest lane is retained there; no speedup or application-wide benefit
is established.

In the staged case, 16,384 cells retain a missing premise across source Runs,
then complete on the same cell identities. There are 49,152 completed cells,
49,664 equality nodes, 99,584 retained applications and 132,096 argument postings.
The 16,384 repeated cell candidates reuse existing cells. The graph commits
49,664 effective unions (512 source unions plus 49,152 derived ones on this
fixture); a completed cell or source request is not generally an effective union.

The final staged run uses 129.86 MiB peak RSS in digest mode and 200.73 MiB
in cell mode. Its compatibility publication still visits 72,384 rows, versus
66,560 for the digest, which can retire duplicates earlier. Stable fixtures
now have zero compatibility publication visits, yet still pay for retaining
application expressions and port indexes. These counts locate remaining work;
there is no isolated profile assigning all slowdown to one component.

All seven fixtures preserve initial/per-Run/final states, binding audits and
semantic schedules across all four lanes. Their logical fact creation, function
updates, logical bindings and effective-union counts also agree. In expression
mode, ordinary repaired-dependency visits, per-event key-packet updates and
key-join-generated result-union requests are all zero. Canonical publication
work remains and is reported separately.


## Reproduce

From the repository root, with fresh output directories:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports --example union_digest_fixture
python3 benchmarks/union-digest/run.py --output out/congruence-run --congruence-cells --repeat 7 --shapes chain fanout stable unit-chain unit-fanout unit-stable staged
python3 benchmarks/congruence-cells/verify.py out/congruence-run/staged/cells-audit/congruence-cells.json --reject-missing-sources
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --test union_digest
```

Supply the saved parent executable using `--previous-digest` to include that
lane. Run an existing compiled program with `--congruence-cells --audit-stages`
to export `congruence-cells.json`. Both experimental flags together are rejected.
The `--union-digest-hash-bits` option also applies to the compatibility index in
cell mode; it does not alter the Eq-node or argument-port hash maps.
