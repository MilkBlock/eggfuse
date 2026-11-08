# Cell-local union completion and maintenance accounting

This experiment extends `39211ce8` on the **standalone Cell CPU runtime**.
Native egglog is a semantic oracle for focused fixtures; these are not native
egglog performance measurements. The frozen source catalogs remain 208 units
for sum-bits and 316 for Raytrace.

## Opportunity and remaining obligations

The preceding repair-template experiment kept the entire reverse dependency
index. It removed recipe decoding, but generic Cell execution increased cost.
The current opportunity comes from the **whole source Cell's own equations**:
copies, explicit unions and their constructor congruence closure predict which
new constructor rows will change before the next source Run boundary.

The compiler derives symbolic classes over typed slots, with no runtime eclass
IDs. It closes congruence before and after the explicit unions and identifies
affected scalar constructor ports. Each affected row also receives a finite
list of local equality obligations, deduplicated by pre-union classes. The
loader rederives this proof and rejects a differing artifact. Templates with
delete/subsume or panic are excluded; functions, containers and unsupported
constructors retain the existing path.

With `--local-unions`, a newly created covered row enters the ordinary exact-key
and membership directories, but **does not create its reverse subscriptions**.
A finite list of these births owns completion. It is not an eclass-to-parent
watcher map. Its cached body is removed before pending unions commit, so other
readers cannot use stale ports. After each actual union batch, completion projects
the ports through committed connectivity:

- A changed key enters the original ordered repair queue. A duplicate can be
  retired without ever subscribing. A surviving key restores subscriptions.
- An unambiguous result-only change publishes directly and restores the external
  boundary subscriptions.
- An unchanged row exits when its own local equations hold. A proof cursor avoids
  rechecking an already equal prefix. If the RHS stopped before a predicted union,
  the final Run boundary restores subscriptions without assuming the union.

The existing reverse index also accelerates partial queries. Tables containing
unsubscribed rows temporarily use their complete membership directory for these
queries. The fallback queries and rows are charged. Exact lookups retain their
normal directory. Focused tests cover querying and deleting a pending row.

Actual union commitment, exact whole-key comparison, collision survivor order,
hidden state, custom merges, receipts and publication order remain obligations.
Existing rows and external boundaries still use reverse dependencies. No claim
is made that this removes all rebuild, replaces union-find, or enables parallel
execution by itself.

## Metrics and admission

`maintenance` records subscription calls and recursively visited values, actual
reverse insertion/removal attempts, union frontier probes and wake visits,
physical merge insertions, exact-key probes and candidate comparisons.
Created/removed/coalesced edges and live/peak edge occupancy are separate gauges.
The report independently sums the physical index and asserts the live count.
Logical edge redirection is not counted as a physical insertion.

`local_union_cells` records attempted and owned births, preparation reads,
completion allocations, row visits, projected ports, obligation checks/reads,
failed/missing obligations, boundary restoration, and rows retired while still
unsubscribed. Congruence retirements are distinguished from external deletion.
Per-template counts distinguish births, unsubscribed retirement and surviving
boundaries; they are diagnostic support, not additive marginal credit.
Pending ownership must be zero at the final boundary.

`bake-local-unions` executes the baseline and the complete candidate family from
the same initial state. Final graph, semantic schedule, ordered RHS inputs,
effective writes and continuation resumes must agree before credit is computed.
Credit includes failed dispatch, completion, proof reads and query fallback,
alongside existing matching, publication and repair counters. Occupancy gauges
receive no additional reward. One observed operation has weight one: this is an
explicit heuristic, not a complete hardware model or calibrated time estimate.
Compilation and replay/hash time are separate from inference timing.

This first admission pass tests one whole-family candidate, not a subset search.
A nonpositive score writes an empty selection, which disables local dispatch.
An unsupported family is not made profitable by assigning credit to matches or
union requests. Actual committed unions remain separately counted.

## Measured work

Each application has 15 statically eligible source templates. Only three execute
owned births on sum-bits and six on Raytrace. These are source template counts,
not 15 new shared repair schemas or committed graph mutations.

The first implementation waited for the entire repair fixpoint. Metrics exposed
4,361,416 Raytrace row visits for only 23,425 owned births. Local completion
obligations reduced this to **115,063 visits (97.4% fewer)**; sum-bits fell from
699 to 222. The first implementation's counters and rejected score are retained
in `global-wait-diagnostic.json`; its elapsed replay time is not a timing claim.

| Counter, control → local obligations | sum-bits | Raytrace |
|---|---:|---:|
| New-birth dispatch attempts | 0 → 3,611 | 0 → 820,311 |
| Owned births | 0 → 222 | 0 → 23,425 |
| Unsubscribed congruence retirements | 0 → 0 | 0 → 90 |
| Reverse insertion attempts | 13,418 → 13,358 | 3,808,194 → 3,799,808 |
| Reverse removal attempts | 2,871 → 2,846 | 913,772 → 909,708 |
| Union wake visits | 2,441 → 2,256 | 704,057 → 685,607 |
| Physical reverse merge insertions | 2,369 → 2,184 | 688,189 → 669,768 |
| Completion row visits | 0 → 222 | 0 → 115,063 |
| Local equality-port projections | 0 → 474 | 0 → 323,358 |
| Obligation comparisons / operand reads | 0 → 37 / 74 | 0 → 96,655 / 193,310 |
| Exact-key repair probes | 1,046 → 1,046 | 224,478 → 224,478 |
| Repaired dependencies | 1,496 → 1,496 | 479,589 → 479,589 |

Both applications have zero membership-query fallback during the measured run.
No unresolved obligation needs forced final restoration. The Raytrace final
reverse index stays at **2,796,816 edges**; its peak also stays unchanged. The
optimization reduces transient work, not the final graph or index size.

Whole-family net credit improves from −4,944 to **−3,624** on sum-bits and from
−13,914,716 to **−1,465,709** on Raytrace. Both candidates are rejected; the feature
stays opt-in. The full deltas are in `credit.json`. No profitable-subset or
held-out generalization claim follows from these two rejected whole families.

The evidence points to limited ownership coverage and expensive generic
dispatch/completion. On Raytrace only 2.86% of births are owned, and only 0.38%
of those retire before subscribing. Returning proved-complete survivors earlier
also trades away ten unsubscribed retirements relative to waiting globally.
The current data does not establish that egraph density is the limiting factor.
The next useful targets are removing selection lookups from uncovered constructor
instructions and extending compiled local completion to existing Cell bodies and
their shared internal equations, with external boundaries explicit.
Simply increasing the catalog or deferring more rows adds work without proof
that it removes subscriptions.

## Validation and timing

All six application lanes (control, local, local plus Entry publication ownership)
must preserve graph, schedule, ordered RHS, effective writes, continuation resumes
and normalized Spine traces. Timing uses a separate executable without trace
audit instrumentation: one warmup per lane, 31 sum-bits samples, seven Raytrace
samples, deterministic interleaving across parent, same-binary control and local
lanes. Every timed run independently compares graph and semantic schedule.
Builds and training do not overlap timing; workstation background load remains
uncontrolled. See `audit.json` and the complete `timings-*.json` samples.

All six audit lanes passed. All 114 measured inference runs (plus six warmups)
also matched graph and schedule. On an Apple M3 Max with Rust 1.94.0:

| Case / lane | Median inference | Median peak RSS through inference |
|---|---:|---:|
| sum-bits / parent | 21.132 ms | 169.078 MiB |
| sum-bits / control | 20.998 ms | 168.172 MiB |
| sum-bits / local | 20.839 ms | 168.188 MiB |
| Raytrace / parent | 7.464 s | 1,860.219 MiB |
| Raytrace / control | 7.410 s | 1,864.547 MiB |
| Raytrace / local | 7.444 s | 1,871.625 MiB |

Local/control median inference changes **−0.76% / +0.45%**; within-round paired
median changes are −0.54% / +0.80%. Raytrace times drift downward during the
interleaved run, with overlapping control/local ranges of 7.192–7.719 s and
7.280–7.728 s. These descriptive results do not demonstrate a reliable application
speedup. The 97.4% reduction above concerns the experimental completion scan,
not total inference. Control/parent medians also move by −0.64% / −0.72%, so this
run does not isolate the cost of accounting instructions from other layout and
workstation effects.

The parent is `39211ce8` with `--repair-ports`, archived as
`out/repair-cells/runtime`. Comparing against this parent also exposes accounting
and inactive dispatch overhead; comparing local against the same-binary control
isolates enabling the experiment.

Workspace checks: **192 passed, four preexisting ignored** with all features.
The five focused tests also pass without `sparse-cells`. The runtime passes
`cargo check --no-default-features`. The fixtures cover a three-level congruence chain,
external unions, custom merge, deletion/reinsertion, renamed initial identities,
corrupt plans, pending-row query coverage, and an unexecuted predicted union.

## Reproduction

Use the frozen program catalogs described in `../entry-publications/README.md`.
All commands run from the repository root; output directories must be new.
Rebuild the parent at `39211ce8` if its archived binary is unavailable.

```sh
mkdir -p out/local-unions
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cp target/release/eggfuse-cell-runtime out/local-unions/runtime
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes
cp target/release/eggfuse-cell-runtime out/local-unions/audit-runtime
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake
cp target/release/eggfuse-cell-compiler out/local-unions/compiler
out/local-unions/compiler bake-local-unions --program out/producer-receipts/learn-sum-bits/program.json --output out/local-unions/learn-sum
out/local-unions/compiler bake-local-unions --program out/producer-receipts/indexed-audit-learn-raytrace/program.json --output out/local-unions/learn-raytrace
python3 benchmarks/result-port-repair/audit.py out/local-unions/audit-runtime benchmarks/local-unions/audit-manifest.json out/local-unions/audit
python3 benchmarks/leaf-completion/measure.py benchmarks/local-unions/timing-sum-bits-manifest.json out/local-unions/timing-sum --repeat 31
python3 benchmarks/leaf-completion/measure.py benchmarks/local-unions/timing-raytrace-manifest.json out/local-unions/timing-raytrace --repeat 7
python3 benchmarks/local-unions/collect.py out/local-unions benchmarks/local-unions
```

Relevant checks (the final focused release runs also cover rejection of
`--entry-publications true` in a non-sparse compiler):

```sh
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test local_union_cells -j 2
cargo test --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test local_union_cells -j 2
cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2
```
