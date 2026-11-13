# Compile Entry results into ordinary Cell copies

The matched-handoff experiment saved 102 lookups but allocated 342 additional
history objects. This implementation instead uses the existing all-writer Entry
invariant proof to replace a redundant constructor Let with an ordinary Copy of
an already matched slot. It regenerates the typed recipe and its physical,
receipt and publication plans through the normal compiler. There is no new
runtime cache, history format, fact graph, producer list or speculative lookup.

The optimized typed source core is explicit and carries the input program hash
and projection proofs. Source/recipe validation remains enabled. The compiler
function is opt-in and is scoped to closed source execution: external Graph API
insertion is not certified. Mutable reads, guards, original query enumeration,
Run ordering and non-constructor effects remain in the source. A constructor
hidden/deleted anywhere in the scheduled source is ineligible. Every writer of
the projected Unit/merge-old function must establish the relation, including
recursive forwarding; initial View rows are rejected by the proof checker.

For example, when all View writers establish `A(x)=a`, the consumer

```
View(x,a), guard(x) => Out(A(x))
```

becomes the same query and guard followed by `Copy(result,a); Out(result)`.
The View row is not mislabeled as a constructor receipt. Recompilation removes
the eliminated instruction's constructor publication interface; consumers that
still require actual constructor witnesses retain their ordinary query paths.

## Evidence and limits

The focused actual standalone-runtime test exercises a recursive View writer,
a mutable scalar read/guard, and a late input in a subsequent Run. All five Run
snapshots agree; constructor requests fall from 7 to 5, and history allocations
do not increase. Negative tests reject an invalid writer and a scheduled
constructor subsumption. The existing matched-handoff and query-receipt suites
also pass: 12 integration tests in total. This is not a native egglog performance
measurement, whole-egraph compression result or the sum-bits semantic gate.

On the current sum-bits artifact, normal compilation and Program validation
succeed for all four previously proven positions: rule/operation 250/1, 449/7,
452/1 and 507/2. The source input artifact is
`fa9dc6539260f7f5440cdcff0266b6fca1ff527c5c0a204ddf80b0e97dd2df6a`.
No full-runtime savings are attributed to those four positions yet.

The compiler deliberately does not transplant the old learned catalog into a
changed typed recipe. The next integration step must re-lower the selected Cell
paths against the specialized definitions, reject paths requiring the removed
receipt, and revalidate ownership transfers. Until then this is an opt-in compiler
transformation, not a replacement for the accepted compression artifact. A fair
runtime comparison must preserve or explicitly account for those selections;
a freshly compiled catalog is not an equivalent performance baseline. Source
specialization also requires Run-boundary validation and an explicitly supported
semantic comparison before admitting the transformed sum-bits artifact.

## Reproduce

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test entry_value_specialization --test matched_handoffs --test query_receipts
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example specialize_entry_values -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/entry-values-program.json
```

Generated programs stay untracked. The output includes source provenance and the
all-writer proofs, making the transformation inspectable without retaining an
extra runtime representation.
