# Typed dual-source layouts and relocation-safe public port handles

This follows the matched multi-source observation. It compiles candidates from the
saved trace; it does not install runtime takeover or execute another workload.

| case | typed candidates | observed applications of those candidates | candidates aliasing one / two symbols |
|---|---:|---:|---:|
| fact | 492 | 617 | 476 / 16 |
| loopfact | 409 | 467 | 395 / 14 |
| sum-bits | 1,857 | 2,800 | 1,824 / 33 |
| dot-product | 1,299 | 1,790 | 1,256 / 43 |

The compiler checks the source program identity, complete source Shape/code
coverage, exact query Entry/operator/field positions, constructor immutability,
and the combined source-frame bound. It re-derives shared Eq-slot relations from
the original query. It rejects a profile that invents or changes a substitution;
the trace's current root coincidence is not proof. Scalar guards, mutable queries
and other residual atoms remain authoritative at execution time.

The result is an ordinary existing Cell `Shape`, two symbol maps and two frame
offsets. Every source operation/use is retained. Aliased source symbols share one
slice, with duplicate uses coalesced. No new maintained fact graph or copied query
bindings are introduced. The offline auditor checks all source port maps and all
instruction slices against the saved original Shapes. Most candidates alias only
one symbol, so candidate counts alone do not justify a compression claim.

## Address obligation found before activation

Stable node records currently cache `(component, frame, operation)`. Their field
views resolve component symbols. Moving a source to another component would leave
those records stale unless takeover relocates them. Query-class masks also require
a closure over the newly joined uses; simply keeping the old origin class could
skip a valid constructor. These are live runtime obligations, not reasons to
silently disable query pruning or retain a second full component graph.

Public `PortRef` now names `(source Cell, local port)` and resolves through the
existing source directory. The resolved `ComponentPort` is crate-internal and
short-lived. A takeover can change component/frame/symbol locations without
changing public handles; retired source IDs never rebind. Public serialization
therefore uses `cell` and `local`, replacing `component` and `symbol`. Internal
stable-field/key hot paths still use the resolved component location. No forwarding
table, retained child list, extra source directory or extra per-instance binding
is added. This change alone does not retire a component or reduce its storage.

Borrowed live guards resolve source ports through the same directory. Frozen
completion snapshots still consume their frozen component-local field locations;
they cannot resolve an arbitrary public source handle. The snapshot type is not a
public API, and takeover must remain outside an active read epoch.

## Validation

- Runtime compilation and no-default-features check pass.
- On the merged worker-write baseline, 47 execution, 62 ownership, 14 stable-port,
  2 read-guard and 2 parallel-publication integration tests pass.
- The compiler fixture rejects a wrong program identity, invented symbol alias
  and incorrect operation position; different instance values retain one pattern.
- A runtime unit fixture relocates the source to another component, frame ordinal
  and symbol position, then unions its value and retires the source. The same
  public handle follows relocation/union and rejects retirement while a sibling
  remains readable. All three guard unit tests pass, including scoped-worker
  condition sharing.
- All 4,057 compiled candidate layouts pass the offline source-wiring audit.

These are typed compilation and address prerequisites. No measured runtime
compression, removed query, skipped RHS effect or publication speedup is claimed.
Existing cached stable fields, complete query-class masks, pending completion,
source/fact lifecycle, boundary route replacement and one-time migration costs
must be covered by the actual takeover before enabling it. The user's large
runtime-egraph compression objective remains open.

## Reproduction

Reuse the saved multi-source-observation candidates and witness-checked traces.
Under the shared compute queue, build/run the existing example with
iterative-bake,sparse-cells,storage-metrics:

```sh
batch_cell_learning compile-joins ROOT multi-source-observation
python3 benchmarks/cell-bake-owner-merge/dual_source_results.py ROOT OUTPUT.json
```

The per-case compiled-joins.json files stay in untracked output. The committed
summary includes their hashes, source identities, bounds and alias distributions.
