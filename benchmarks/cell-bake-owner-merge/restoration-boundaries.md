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
