# Learn constructor witnesses before an uncovered RHS suffix

The constructor-lifetime trace establishes that cross-stage result reuse is
common, but final source/component membership cannot prove the topology at the
moment of reuse. In particular, a receiver's final component is not necessarily
the query anchor's component. Do not generate a proof from that final-state join.

The existing apply observer already evaluates actual bound inputs against live
facts in query-anchored components. Its `covered_rhs` returns both the checked
prefix and the actual constructor positions found before the first unsupported
operation. Previously those positions were discarded unless **all** RHS effects
were covered. A missing later constructor, mutable write, nontrivial union or
visibility operation therefore prevented Bake from using an earlier valid
constructor witness.

The observer now keeps nonempty checked prefixes. A recipe explicitly records
`coverage: checked_prefix` or `full_rhs`. This describes observation extent; it
is not a runtime permission flag. The normal recipe compiler checks source
identity, operator/layout compatibility and shared-wiring key proofs. Runtime
admission checks actual anchors, current keys where needed, visibility, ownership,
forwarding and dirty state. The existing fallback is retained when the local
witness is no longer admissible. No effect is moved across the unsupported suffix.

One apply may produce prefix candidates in multiple query-anchored components.
Recipe observation counts must therefore not be summed as unique rule applies or
saved effects. The existing per-apply outcome rows retain their previous meaning.
The trace still stops scanning after finding full coverage; it does not build a
new runtime fact graph or preserve per-instance history for execution.

## Executable takeover check

The small integration fixture establishes Start(x), then Pair(Start(x),x) in
successive stages. A later rule reconstructs Start(x) before an uncovered suffix.
Three suffix variants exercise a new G(x), a nontrivial union and deletion.
Only checked-prefix recipes are installed in the candidate. Each candidate
accepts a compiled route and performs fewer generic key lookups, while exact
exports, stage snapshots, binding audit and logical fact creation match control.
All 58 ownership integration tests pass. This replaces a real lookup rather
than only adding a catalog entry; it is not a workload speed or memory claim.

## Catalog-only batch comparison

`prefix_catalog.py` compares two catalogs from the same audited observations:
full RHS only, and full RHS plus checked prefixes. Both compile and replay with
one executable against the existing saved Run/terminal checks. The script rejects
any artifact difference outside the witness catalog/digest, compares final states,
and reports generic lookups alongside route probes and candidate checks. The
observer and timing overhead are not used as performance evidence.

Prepare a fresh `prefix-observation` variant with the four seed `candidate.json`
and `selection.json` files used by `pooled-audit`, then run:

```sh
~/.local/bin/eggfuse-job run --kind compute -- env CARGO_INCREMENTAL=0 cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --example batch_cell_learning -- check-passive out/cell-bake-owner-merge/batch prefix-observation witnesses
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/prefix_catalog.py out/cell-prefix-witnesses/batch-frozen out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/prefix-catalog.json
```

`batch-frozen` is an immutable copy of the executable used for the observation;
its SHA-256 is included in the result. These are standalone Cell CPU differential
checks, not a new native egglog semantic acceptance result. The large runtime
compression and complete saturated-stage RHS objectives remain unfulfilled.

## Measured work and remaining cost

Both lanes pass all 2,652 saved Run checks and four terminal checks. The table
compares full-only to including-prefix catalogs, using the same frozen binary.

| case | recipes | generic key lookups | extra route probes | extra candidate field checks |
| --- | ---: | ---: | ---: | ---: |
| fact | 29 → 237 | 2,794 → 2,697 | 214 | 6 |
| loopfact | 24 → 224 | 2,181 → 2,116 | 206 | 14 |
| sum-bits | 90 → 766 | 12,361 → 11,965 | 2,756 | 400 |
| dot-product | 79 → 752 | 9,519 → 9,202 | 1,045 | 339 |

The 875 removed generic lookups are actual executor work, not logical matches or
potential rule skips. However, they do not establish a net speedup: sum-bits pays
nearly seven additional route probes per eliminated lookup, and the candidate
catalog is much larger. Route probes and generic lookups have different costs;
subtracting their counts is not a latency model. Retained compiled-catalog bytes
and actual timing were not measured here. Runtime graph compression is unchanged.

Keep the expanded catalogs experimental. The result changes the next priority:
resolve applicability once at a checked Entry/continuation boundary, instead of
repeating unsuccessful route selection at each constructor. Any cached selection
must preserve target lifetime checks and account for shape extension, union,
retirement and suspended execution. Do not claim all these probes disappear just
because the compiler knows the candidate locations.
