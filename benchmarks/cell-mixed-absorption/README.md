# Complete absorbed members of mixed Cell domains

Control: `6e6f51dd`. This is an opt-in **standalone Cell CPU** change, not a
native egglog optimization. It extends the existing `--cell-absorption` path;
it does not establish a speedup or the 2x objective.

## Opportunity and takeover

The last full-Raytrace [absorption checkpoint](../cell-absorption-guard/README.md)
already omitted 509,296 bindings and their single-write applications. That
coverage belongs to the earlier implementation. In a mixed constructor domain,
one output needing an update still rejects the whole-domain proof. Previously
every member then formed a binding and executed its RHS, even when another
member's output already absorbed the proposed value. Only singleton domains
could use an individual proof.

The same compiler capability now applies to a checked member of a mixed domain:

```text
matched: Cost(x) = n; C(x, distinct arguments...) -> y
effect:  Cost(y) := min(Cost(y), n)
proof:   current Cost(y) <= n
```

The successful whole-domain fast path remains. After its failure, the ordinary
row, field and delta-owner checks run; a successful member proof then omits that
member's binding, single-write RHS and completion/publication. It adds neither
an instance field nor a per-output subscription, binding cache or fact graph.
The already-existing pending count reserves source Cell identity positions and
preserves logical-match accounting. These are not committed mutations.

The capability still requires the original two-atom Cell, a permanent integer
min function, a pure single write and no computed RHS prefix. A constructor
must precede the watermark; missing outputs, fresh constructors and unsupported
completion modes fall back. Deletion/recreation, union, residual enumeration,
visibility and source Run order retain the existing lifecycle checks. Because
the target function is permanent and only decreases, an absorbing output at
query time remains absorbing until its ordered RHS position. No history of an
unexecuted effect is invented.

## Costs and credit

Every eligible mixed member adds a dispatch/eligibility check and can add an
output hash probe. A failed proof still runs the ordinary write, so its probe
can duplicate the RHS lookup. A successful group proof avoids these per-member
costs. Six global counters are added; template, Neighborhood and instance layouts
do not grow.

`mixed_candidates`, `mixed_checks` and `mixed_output_probes` are charged by Bake
Work when `row_completion = cell-min-row/v1` is present. Missing versioned work
counters or an unknown version reject credit parsing. Historical reports have
zero new member work. `mixed_absorbed` is coverage only: the removed binding,
write and publication describe the same takeover and are not extra credits.
These counts are not a calibrated CPU cost or an allocation measurement.

## Short measured work

Four query workers, grain 64, the same frozen program in both lanes, canonical
storage, repair ports, Entry publications and absorption. The controls and all
counter values are recorded in [results.json](results.json).

| Complete sum-bits | Before | After |
|---|---:|---:|
| Executed bindings | 7,224 | 7,193 |
| Single-write applications | 1,080 | 1,049 |
| Actual function updates | 1,450 | 1,450 |
| Additional mixed-member completions | 0 | 31 |
| Mixed-member dispatches / eligibility checks | 0 / 0 | 61 / 61 |
| New output hash probes | 0 | 59 |

The small fixture removes three bindings and corresponding writes, at a cost
of 12 member attempts/checks and ten output probes. Two fresh rows decline the
proof. The first 128 Raytrace Runs have no eligible member attempts or savings.
Neither this prefix nor the earlier full-Raytrace result establishes the new
path's full-workload coverage or speed. In particular, 59 probes for 31 omitted
sum-bits applications must not be reported as a net CPU improvement.

Exact final states, all logical source Run signatures and committed effect
counts agree in all three cases. All 1,428 sum-bits Runs are covered; its
unchanged native choice validator returns `pass` / exit 0. The integration
fixture additionally checks each Run's state, late constructors, union,
retirement/recreation, scalar decreases and later readers with serial and four
worker execution. Deletable and ordered-merge outputs retain the negative tests.
102 runtime unit tests and 51 compiler/unit/integration tests pass, including
worker, Entry-publication and scoped-completion regression checks. The minimal
no-default-feature compile and README compile/run/bench commands pass; bench
repeat 1 is a command smoke check, not comparative performance evidence.
Full throughput remains on the existing five-implementation cadence.

## Reproduction

Use fresh output paths and freeze the control and candidate executables. The
source fixture is shared by the integration test and the short comparison:

```sh
cargo build --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports --example emit_cell_source
target/release/examples/emit_cell_source tools/cell-compiler/tests/fixtures/mixed-absorption.egg ROOT/fixture
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports --example query_prefix
python3 benchmarks/cell-mixed-absorption/check.py BEFORE_QUERY_PREFIX AFTER_QUERY_PREFIX ROOT/fixture/program.json SUM_PROGRAM RAY_PROGRAM SAVED_SEMANTIC ROOT/checks
```

The collector executes only the small fixture, complete sum-bits and a 128-Run
Raytrace prefix. It compares exact exported states, original logical Run
signatures and committed effect counts, while reconciling omitted executable
bindings with absorption. It invokes the unchanged sum-bits native acceptance
entrypoint with the saved inputs required by its existing contract. Raytrace is
a relative prefix check, not an independent native proof or a full workload
measurement. Raw artifacts remain under ignored `out/cell-multi-absorption`.
