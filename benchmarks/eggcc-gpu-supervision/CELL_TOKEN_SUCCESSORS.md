# Toward generated, consumable Cell tokens

The Eq classifiers are insufficient for the intended runtime: all their Cell
instances are still supplied by CPU matches. Even perfect Eq prediction would
not create the next Cell or eliminate the CPU matcher. Further classifier-only
calibration is paused. The uncommitted effect-context experiment is not part of
this change.

The next execution contract is that a GPU-generated Cell carries sufficient
state to enter a subsequent compiled Cell without CPU rematching or encoding.
The first prerequisite implemented here is a compiler-only continuation proof.
It reads the full recipe, never execution traces, labels or recorded consumers.

For each producer it symbolically completes immutable constructor effects:
copy aliases, constructor applications/assignments, union and congruence.
Congruence computation happens in Bake. Its term symbols are not addresses of
physical constructor results. Mutable, potentially failing or visibility-changing
effects stop admission rather than being moved or ignored.

A consumer is admitted only if every query atom is a constructor fact witnessed
inside the completed producer. Repeated slots and literals must agree. An
unproved extra atom, primitive condition or mutable read prevents admission.
The entry records exact consumer slot substitution and query witnesses. Match
budget exhaustion rejects the entire candidate, never a truncated list.

For the directly compiled full sum-bits program:

- 548 rule templates examined; 397 have supported complete effect sequences.
- 781 entry substitutions remain after removing 62 identity self-handoffs; they connect 184 producers to 110 consumers.
- 618 substitutions cross source ruleset names.
- 151 producers retain explicit effect boundaries.

These counts are potential local coverage, **not executed transitions or saved
work**. An RHS fact occurrence can already exist; it does not prove novelty.
Every entry explicitly requires novelty checking. The catalog cannot authorize
advancing a source Run, dropping a visibility check, or declaring saturation.
The subsequent [bounded device dataflow experiment](GENERATED_CELL_FLOW.md) generates speculative Cell states; it does not yet establish novelty or full source execution.

Remaining integration obligations:

1. Use the substitution as the consumer's actual input layout, carrying exact
   boundary identity separately from lossy floating state. Do not rematch on CPU.
2. Produce and consume floating Cell state on device; merely activating a bitmap
   of precomputed answers is not the intended learned computation.
3. Preserve the original Run schedule, including stage transitions. Cross-ruleset
   connectivity is not permission to execute an effect early.
4. Distinguish novel information from alternative proofs, using shared Cell
   structure and actual boundary identity. Bounded capacity is an explicit mark,
   never a successful saturation signal.
5. Expose unsupported external joins and mutable/guarded work for CPU checking
   and eventual correction. Never silently declare the covered catalog complete.

Reproduce the compiler coverage with:

```sh
python3 benchmarks/eggcc-gpu-supervision/cell_token_successors.py PROGRAM CATALOG
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_cell_token_successors.py
```

`cell-token-successors-results.json` records the actual full-program coverage.
Tests cover multi-atom queries, repeated-slot constraints, compiler alias/reuse,
mutable and primitive barriers, incomplete guarded consumers and capacity failure.
No runtime reverse dependency graph, publication path or Cell state has been
introduced or removed by this compiler prerequisite alone.
