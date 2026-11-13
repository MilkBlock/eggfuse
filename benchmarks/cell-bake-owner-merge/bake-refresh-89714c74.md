# Refresh the branch containing d0d8ee33

The requested source is `codex/cell-parallel-admission`, pinned at `89714c74`.
It contains `d0d8ee33` (`bound alias savings against retained runtime state`).
The earlier merge `437d1e7c` already included its history through `d911ff49`;
this refresh merges all five subsequent commits, not selected patches from the
similarly named structural-compression branch. The destination is
`codex/cell-result-routing` in `/private/tmp/eggfuse-cursor-writes`.

## What is adopted

- Derive residual domains and slot assignments from checked Cell coordinates.
  Legacy explicit annotations remain checked; forged annotations still fail.
  Local reads share immutable producer operands rather than copying them per
  consumer. Ordinary query atoms and residual enumeration remain authoritative.
- Pool newly completed suffix storage even when an old prefix shares its owner
  with unrelated sources. Prefix slots stay in place; logical source IDs,
  restoration slices and port routing are unchanged. This optional storage
  path must not be credited as a speedup of the ordinary parallel runtime.
- Install the audited direct-source and matched-source Bake experiment tools,
  their retained-memory evidence, and separate pending-work reason counters.

The incoming queued-union admission experiment is already rejected. Its patch
is retained as research evidence and is **not applied** to the runtime. More
admissions increased retained Graph storage on every tested catalog. The merge
does not remove union, frozen-read, pending-signal or dirty-fact guards.

## Implication for the next Cell optimization

The actual direct-source trace contains thousands of connected immutable matches
despite shallow Cursor history. It is useful input for selecting combinations,
but an observed match does not prove source retirement or future equality.
Simply adding patterns is expensive: the largest matched-source catalog saves
only 5,920 Graph bytes while adding 9,387,054 Program bytes in the incoming study.
Those are the peer's storage measurements, not new timing results here.

The more useful next target is the lifetime of a partially retired composed
Cell. Current retirement decrements a component-wide count; surviving sources
can keep retired-source descriptors and bound signals alive. Bake should derive
the remaining live source layout and its valid suffix transitions. Native Eq
routes, shared symbols, escaped boundary readers, live result witnesses, source
generations and later Run visibility must remain resolvable. Removing a source
descriptor without such a route is not a valid takeover. No new reverse map,
runtime fact graph, or duplicate bindings should be introduced.

This refresh does not implement that retirement specialization. It supplies the
existing shared-layout mechanisms and measured counterexample needed to design
it. Acceptance below checks the actual four-worker Cell runtime separately from
the optional compression experiments.

## Merge checks

Compute job 343 passes the ownership, compiler and witness integration suites,
the runtime library suite, the no-default runtime compile, and all four offline
route-analyzer tests. Frozen workload validation and a whole-control-then-
candidate timing trial follow; no speed improvement is inferred from these tests.
