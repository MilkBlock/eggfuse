# Stable fact access before completed-owner replacement

The latest natural-lifetime experiment removed 100 final parent links without
changing any Run-boundary counted bytes. Its surviving small Cells still own live
FactState maps, and old readers require cells[cell].facts[op]. Merely creating a
larger completion object would retain the original owners.

Point reads, mutation, insertion, removal and liveness now pass through FactStates,
keyed by the existing FactRef. The implementations borrow/mutate the original map:
there is no new index, registry, fact copy, heap allocation or dynamic dispatch.
Worker canonical queries, constructor candidates, visibility, repair/collision,
retirement, Entry dispatch and producer contexts use the boundary. Bulk ownership
initialization and saturation observation use its stable-identity iteration.

Graph.fact resolves stable fields or decoded rows from the fact state before
requesting a recipe frame. Only the recipe fallback retains that requirement.
This removes an eager source-frame lookup on those paths; it is not a demonstrated
speedup. In-flight RHS frame access stays direct, since those operations own and
mutate their execution frame before any completed-state transfer.

## Not yet implemented

FactStates still stores every fact in its original Cell. No small owner has been
retired and no memory compression is claimed. Diagnostic storage enumeration,
serialization and remaining bulk traversals also need the replacement backend
before physical migration can be enabled. Keep them authoritative: an empty old
map must never make migrated facts disappear from memory accounting or exports.

The next representation must preserve logical FactRef identity and table membership,
visibility/birth/epoch/hash updates and independent deletion. Existing composed
Cell wiring should select the shared storage owner; avoid another maintained fact
graph or per-producer reverse lists. Recipe reads, captured results, writer origins,
parent lifetimes and source-Run ordering remain live obligations. Charge any new
address directory and fallback materialization against bytes removed.

## Validation

Actual standalone Cell runtime, access refactor only. 148 runtime tests include
parallel-residuals and a new stable fact lookup/mutation/retirement test through
arena relocation. 33 ownership and 21 ripsat integration tests pass, covering
cross-stage Run snapshots, deletion, union-enabled completion and worker results.
Default non-sparse runtime also passes cargo check. No performance campaign or
new full sum-bits export campaign: this change preserves the existing store and
uses the relevant local semantic tests. Full saved Run audits remain required
when enabling the replacement storage backend.
