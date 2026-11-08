# Union digests as incremental constructor matches

This is an opt-in experiment in the **standalone Cell CPU executor**, forked
from `codex/sparse-cell-storage` at `27f098a2`. That branch is the retained fast
CPU baseline in the local experiment history; this work does not establish a
fresh speed ranking of every branch. The immutable `egglog-baseline` import and
the original working tree are untouched.

The prototype is correct on the checked constructor fragment but slower than
ordinary repair. It is not a GPU implementation, a neural network, an egglog
runtime optimization, or a completed Bake transformation.

## What changed

With `--union-digest`, each live constructor witness has a correlated packet
`(operator, ordered arguments, result)`. An equality event changes only the
argument positions subscribed to its displaced binding. Changed packets join
on their complete operator/key, and an exact match emits another result union:

```text
F(xs) = u, F(ys) = v, xs == ys  ->  request u == v
```

These requests feed the equality-event stream until it settles. Hashes only
choose candidate buckets: the matcher checks the full operator and ordered
tuple before emitting a request. Independent columns never substitute for a
correlated tuple. Equal results alone never justify deleting different keys.

The old constructor collision-repair branch is bypassed. Physical publication
still updates interning, receipts, row epochs, reverse subscriptions and query
notifications at the original Run boundary. Ordinary source-rule matching
still observes those boundaries. This is a separate internal congruence join
engine; it has **not** been fused with the shared Entry matcher.

The matcher has no rule selected by an observed e-class number. Renaming
bindings changes bucket placement, not the equality rule. Nevertheless, this
implementation still uses union-find and canonical representatives to route
events. It does **not** satisfy a stronger requirement to eliminate canonical
representatives altogether. It also retains the original publication dirty
set, so a zero old-repair counter is not evidence of zero maintenance work.

The mode accepts immutable constructor tables with scalar fields. Functions,
markers, containers, deletion and subsumption are rejected before creating the
output directory. In particular, the frozen sum-bits and Raytrace artifacts
are rejected because they contain marker tables. The default execution path
is unchanged apart from the disabled-mode checks and an extra report field.

## Opportunity assessment before optimization

The previous catalog's actual executions already identify constructor
signatures, argument positions and recurring Cell/Spine shapes. These are
plausible inputs for compiling shared digest subscriptions. The existing
repair-forwarding survey in [SPARSE_CELL_CPU.md](../../docs/SPARSE_CELL_CPU.md)
also distinguishes keys made equal by an explicit union prefix from those
requiring later congruence consequences. Such observations can nominate a
block; they cannot certify an unseen future equality.

A scheduled block spanning Runs could reuse its argument subscriptions and
correlated keys. Typed constructor purity and exact complete-key equality
prove a result union is valid. They do not discharge source visibility,
consumer watermarks, winning receipts, function merge order or retirement.
This first experiment isolates constructor congruence, retains publication,
and rejects those unsupported effects. It neither trains a new catalog nor
precomputes the repair cascade in Bake. Generated fixtures intentionally use
the typed frontend and Recipe compiler directly, without marker Bake.

## Measurements

Apple M3 Max, standard release build, Rust 1.94.0, with
`sparse-cells,view-ports,storage-metrics`. No PGO or CPU/LTO overrides. Each
fixture has 256 independent pairs and depth/fanout 32. Three lanes ran in
alternating forward/reverse order, each with a separate warm-up and seven
fresh-process samples. Audit runs are separate from timings. Export time is
excluded; setup time and peak RSS through inference are recorded separately
in [results.json](results.json), along with executable/source/artifact hashes.

| Fixture | Parent inference | New binary, mode off | Digest inference | Digest/off | RSS off → digest |
|---|---:|---:|---:|---:|---:|
| chain | 19.150 ms | 18.922 ms | 36.852 ms | 1.95× | 41.91 → 54.33 MiB |
| fanout | 21.565 ms | 22.028 ms | 32.760 ms | 1.49× | 43.06 → 53.50 MiB |
| stable/no effective unions | 19.394 ms | 18.965 ms | 27.061 ms | 1.43× | 64.28 → 79.34 MiB |

These are medians of a synthetic experiment, not application speedups. The
small differences between parent and mode-off are not a claimed improvement.

Both union workloads commit 8,448 class merges: 256 explicit leaf merges plus
8,192 congruence consequences. The digest matcher finds 8,192 exact matches
and retires 8,192 duplicate rows. It updates 8,448 key packets. In the chain
case the ordinary repair counter falls from 8,796 to zero, **but 8,796 physical
publication visits remain**. Fanout retains 11,648 publication visits. No
repair work should be inferred to have disappeared merely from its counter
moving to another component. A match/output request can also be a no-op;
`stats.unions` counts effective merges separately.

The stable case commits no unions and still slows down. That isolates a real
cost of maintaining the new packet and argument indexes even without a
repair cascade. The measured implementation duplicates key storage and
reverse incidence, while still paying for ordinary publication. The results
support combining these representations and wake-up routes before expanding
to markers; they do not support claiming that encoding repair as digest
matching is itself a speed optimization.

## Correctness and limits

- Native egglog versus ordinary Cell versus digest Cell at every explicit Run:
  cascades, a previously false repeated-variable join, late insertion, cycles,
  distinct operators, correlated compound keys and equal outputs with distinct
  keys. A complete row bijection is checked after class renaming. Initial row
  order and external class labels are changed in a second execution.
- Same-input Cell runs additionally compare rule bindings and schedule.
  Both normal hashes and forced zero-bit hashes pass.
- Six deterministic 128-operation streams compare the entire handle equality
  partition and live row count after each operation against an independent
  exhaustive fixed-point congruence algorithm. Inserts, reused constructors,
  arbitrary unions and post-union inserts are interleaved.
- Two matcher unit tests cover tuple correlation, repeated columns, collisions,
  retirement and operator separation. Unsupported effects and invalid hash
  widths are rejected.
- All-feature workspace tests pass: 157 passed, four existing tests ignored.
  The four integration tests also pass with the default, non-sparse runtime.
- Benchmark audits compare initial/per-Run/final rows, bindings and semantic
  schedules across parent, mode-off and digest. Every timed sample checks the
  schedule too. These fixtures do not exercise ordered merge callbacks.

The full frozen workloads are only ordinary-path regression checks, not digest
benchmarks: see [checks.json](checks.json). They compare final rows/anchors,
semantic schedules and counters against the parent. They do not claim a full
per-Run state audit of Raytrace.

## Reproduce

From the repository root, use fresh output directories:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports --example union_digest_fixture
mkdir -p out
python3 benchmarks/union-digest/run.py --output out/digest-study --repeat 7

cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --test union_digest
```

To include the parent lane, build `27f098a2` in another worktree with the same
runtime feature flags, copy its executable outside that worktree's target
directory, and pass `--baseline /absolute/path/to/copied-executable` to the
Python runner. The runner never builds or changes another worktree.

A single fixture can also be run directly:

```sh
target/release/examples/union_digest_fixture out/digest-small chain 8 4
target/release/eggfuse-cell-runtime --program out/digest-small/program.json --union-digest --audit-stages --output out/digest-small-run
```

`--union-digest-hash-bits 0` forces every fingerprint into the same bucket for
correctness testing. It is intentionally expensive and requires the digest
flag. Generated artifacts, binaries, logs and snapshots remain under `out/`;
only experiment sources and text results are committed.
