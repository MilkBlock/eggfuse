# Restoration boundaries for cross-stage composition

Scope: the standalone Cell CPU in this worktree, not native egglog. This change
observes the opt-in completed-owner store; it removes no logical fact, query,
publication or allocation. The ordinary parallel lane does not enable this store.

The previous installed-catalog audit (README.md) found 821 fully witnessed RHS
applications. A stage switch could reuse their actual results under the compiled
Entry and effect-order proofs. That opportunity does not prove it safe to merge
all source storage into a single restoration unit. Mutable reads, new union-enabled
matches, residual enumeration, visibility and external readers remain live.

## Amplification boundaries

- Owned union dispatch traverses activated static signal uses and key candidates;
  stable Eq fields do not need canonical-ID rewriting.
- Last scalar provider retirement invokes `preserve_completed_scalars`, which
  can unseal an entire source frame to recover a small number of bindings.
- Last component fact retirement scans component signals and source frames,
  restoring symbolic slots still required by external readers.
- `extend_completed` copies the old owner prefix plus the new suffix. Repeated
  growth can accumulate quadratic movement independently of union.

Template composition should retain independently restorable source slices. Do not
turn a shared template DAG into an indivisible recursively expanded storage tree.
A useful Bake score must charge retained boundary interfaces, restoration size and
old-prefix movement as well as removed duplicate slots and publication work.

## Added observation

`completed_profile().restoration` reports events, reconstructed slots and facts,
summed container capacity bytes, and the largest single event with its template.
It records successful `unseal_completed` calls only. Missing/already-unsealed
frames do not increment counters; deleted facts are not reconstructed. The maximum
is container capacity, not a bound on all memory caused by a union.

Excluded: later scalar insertion, source arena growth, retained old owner arrays,
component teardown scans, temporary query rows and allocator overhead. No event
is attributed to union merely because it occurred during execution. All callers
are aggregated; this report alone does not identify a triggering union or cause.
Counters occupy fixed per-store state and do not add per-instance history or an
index. This observation does not change stage admission or publication order.

## Validation

The existing multi-stage owner test now checks one-source restoration, unaffected
siblings, exact container-capacity accounting, missing-source non-events and a
second restoration after its fact was deleted. Five fact-state tests pass with
`sparse-cells,storage-metrics`; the full runtime library suite also passes all
200 tests under those features. No timing or compression benefit is claimed.

Reproduce:

```sh
CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,storage-metrics --lib fact_states
```

The next comparison must replay identical installed catalogs and report both
storage savings and restoration/extension work. Previously saved measurements
from another branch are not measurements of this worktree.

## Current-branch batch evidence

Measured with runtime source at `09fe0691` plus the existing, unrelated query
completion working-tree edits (neighbor/query/query snapshot/worker/runtime).
Those edits were present before this audit and are not included in its commit.
Inputs are the four frozen `out/cell-bake-owner-merge/batch/*/candidate.json`
files; file hashes and full Graph teardown attribution are in
`restoration-results.json`. No source/catalog retraining occurred.

| case | Graph owned bytes | restoration events | restored container capacity | maximum event | old slots moved | old facts moved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 779,975 | 0 | 0 | 0 | 154 | 186 |
| loopfact | 678,385 | 0 | 0 | 0 | 110 | 159 |
| sum-bits | 2,054,923 | 6 | 1,968 | 360 | 688 | 943 |
| dot-product | 2,030,643 | 0 | 0 | 0 | 2,087 | 1,265 |

All four final graph digests match the saved catalog executions, over respectively
418, 398, 882 and 954 Runs. This run checked final hashes and Run counts, not each
intermediate Run or native egglog semantic equivalence. Restoration is aggregate
across causes. These results supersede neither other-branch results nor worst-case
bounds for future large indivisible frames.

Stable ports, components, boundary routing and frame directories together occupy
41.7%, 37.1%, 46.2% and 44.9% of Graph heap. These are storage categories, not all
redundant bytes. Cell storage occupies another roughly 26%–28%. This supports
prioritizing duplicate instance/address representation while retaining small
restoration boundaries; it does not support building a new fallback mechanism
merely to eliminate the currently observed 1,968 bytes of restored containers.
The ordinary barrier history alone retains 98,304 bytes in each of sum-bits and
dot-product. The structural branch already has an explicit-observation version
(`a3269a73`); its integration must preserve opt-in trace consumers.

Do not skip scalar preservation solely because `parent_users == 0`. Already
matched but not yet executed same-Run bindings can still read old source recipes;
`release_empty` explicitly keeps ancestors until the Run boundary. A future
skip requires an admission/visibility proof covering these pending readers.

Reproduce the memory runs (one process per case, no latency comparison):

```sh
CARGO_INCREMENTAL=0 cargo build --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_peak
mkdir -p out/cell-restoration-boundaries
for case in fact loopfact sum-bits dot-product; do
  target/debug/examples/runtime_storage_peak out/cell-bake-owner-merge/batch/$case/candidate.json out/cell-restoration-boundaries/$case.json inherited-owners --port-domains-only
done
python3 benchmarks/cell-bake-owner-merge/restoration_results.py out/cell-restoration-boundaries out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/restoration-results.json
```

## Explicit barrier history integration

Adapted the structural branch change `a3269a73`: ordinary execution now retains
only cumulative ownership counters. Explicit barrier tracing, catalog observation,
fragment training and Executor audit retain boundary records. A late explicit
request records its missing prefix; repeated requests do not reset that prefix.
This avoids allocating history proportional to source Run count in production.

48 ownership integration tests pass, including equal exported state for ordinary,
audited, catalog-traced and late-traced execution. Four frozen memory replays
match all prior `completion_work` and `source_storage` fields exactly, including
restoration counters, plus final hashes and Run counts. The sole changed Graph
teardown field is `ownership.barriers`:

| case | Graph before | Graph after | released bytes | fraction |
| --- | ---: | ---: | ---: | ---: |
| fact | 779,975 | 755,399 | 24,576 | 3.15% |
| loopfact | 678,385 | 653,809 | 24,576 | 3.62% |
| sum-bits | 2,054,923 | 1,956,619 | 98,304 | 4.78% |
| dot-product | 2,030,643 | 1,932,339 | 98,304 | 4.84% |

This is observation-state removal, not fewer logical facts, a RHS takeover or a
speedup. Pending same-Run reads and small source restoration boundaries remain.
The next structural target remains duplicate stable/instance representation.

Rebuild and repeat the preceding memory commands into `out/cell-explicit-barriers`,
then compare with:

```sh
python3 benchmarks/cell-bake-owner-merge/barrier_results.py out/cell-restoration-boundaries out/cell-explicit-barriers benchmarks/cell-bake-owner-merge/barrier-results.json
```
