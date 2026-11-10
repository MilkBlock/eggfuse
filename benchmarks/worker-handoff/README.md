# Compiler preparation for ae123cf9 worker handoff

This is a preparation artifact for the standalone Cell CPU, not a runtime
optimization or native egglog measurement. The target branch's query workers
complete point-query Entries, return Matched values, restore source ordinals and
select winners before making Binding/StagePatch and executing RHS serially.

Opportunity: use actual successful Cell/Run transitions from the last catalog
to select compositions that discharge repeated binding assembly, retained-slot
transfers and internal publication. Execution frequency selects candidates; it
never proves validity. This artifact consumes the existing checked catalog; it
does not train a new catalog or manufacture execution counts.

Generate on this branch:

```
cargo run -p eggfuse-cell-compiler --features iterative-bake --example emit_worker_handoff -- PROGRAM.json HANDOFF.json
```

`worker_handoff::validate(program, handoff)` reconstructs the entire artifact,
rejecting altered program identity, operations, catalog or obligations. The
sidecar is deliberately not installed in Program or used to grant execution
permission. The exact program digest binds rule/operation/slot IDs. It must be
regenerated after recompiling or changing the Bake catalog.

Information supplied:

- Per rule: template ID, frame width, successful-match input slots, input slots
  used by RHS, and existing slot-definition coordinates.
- Per original RHS operation: read slots, destination slot, table, effect kind
  and candidate shared Entry IDs. Literals and instruction semantics remain in
  the authoritative Program, not copied into another instruction language.
- One shared Entry schedule with its existing consumer projections/control.
  Candidate routing means matching the source table only; it is NOT proof that
  a query succeeds, that a mutable read publishes, or that all candidates can
  receive a result. Existing aliases/last-write selection remain authoritative.
- Reconstructed stage contracts: exported source sites, inherited result-slot
  mapping, query/RHS reuse proofs, next states, restart and retained distance.
  These describe existing bounded paths, not arbitrary cross-stage closure.
- Live obligations: source ordinal/winner/delta ownership, residual enumeration,
  actual returned receipt, current Eq, mutable reads, visibility, retirement,
  generation and cross-thread ownership. Every worker_execution_proved flag is
  false: primitive classification alone is not a purity/error-order proof.

Integration points in ae123cf9:

1. query_workers::finish_run: retain successful frame ownership after winner
   selection; use rhs_input_slots rather than inventing another binding layout.
2. runtime's Binding::matched / StagePatch construction: consume that same
   storage, maintaining original rule/ordinal order and ordinary deduplication.
3. RHS and Shared Entry: resolve actual receipts into the export slots, then
   use the existing Entry projections and state transitions. Remove a packet
   or transfer only after proving its visibility, replacement and lifetime
   obligations; cross-Run edges still wait at the original Run boundary.

The sidecar currently depends on this branch's v2 state-contract support
(7d4144b1 and its prerequisite state-plan implementation); it is not advertised
as a standalone cherry-pick onto ae123cf9. Its JSON is available immediately
for downstream design; compiler integration must port the checked contract
producer as well. No change is made to the other worktree.

Against the current branch, runtime execution and program bytes are unchanged:
no runtime loader, dispatch or publication path consumes this sidecar. The
sample records static counts/encoded size, not saved operations or speedup.
The existing semantic exports remain applicable because no executor or input
artifact changed. Tests reconstruct the fixture and reject forged metadata.
