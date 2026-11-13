# Completed RHS results participate in the same Cell Entry composition

The actual reuse trace found thousands of earlier-Run constructor results, but
composition admission only received LHS query receipts. A consumer that matched
Tick(a), reused an existing F(a), and then created G(F(a)) could not use that
completed F relation to share the new source's wiring. This change adds that
proof source to the existing finite Entry substitution mechanism.

The compiler derives Eq-column substitutions directly from each constructor
operation's existing port program. Its Entry position is the number of ordinary
query Entries plus the source operation index. Existing query positions retain
their meaning; no source marker, alternate fact graph or copied bindings is
introduced. Fragment validation, shape interning, bounded extent, selection and
production dispatch remain the existing mechanisms.

While a source executes, its existing Entry can hold one actual reused FactRef
and its operation position. It is not a retained history owner or a producer's
consumer list. Only a visible result from another composed source is eligible,
and only before the current source has its own composition frame. Selection
rechecks ownership, visibility, source ordering and the existing component limit.
If the fact was hidden, retired, or no compatible baked transition exists, the
ordinary query Entry/boundary path remains. Stored source IDs are not reassigned;
existing component retirement and source-sized restoration continue unchanged.
The candidate moves with the existing suspended Entry and ends with that source.

An installed catalog enables result capture only for rules with such transitions;
training and explicit observation can discover them. Training still prefers an
installed transition before inventing an uncovered shape. Among available Entry
alternatives it tries the latest eligible actual result first. This is bounded
selection, not exhaustive closure search; an earlier useful result may be missed.
Worker-prepared prefixes that bypass ordinary constructor execution are not yet
an additional source of these candidates. Those limitations remain live work.

## Removed work and added costs

An admitted result Entry substitutes its input/result ports into the shared
static shape, removing their otherwise independent runtime signal bindings and
boundary registration. It does not skip the constructor that supplied evidence,
its query, or subsequent effects. All RHS and merge source order is preserved.
The new path is not the rejected constant-prefix/single-write trial.

Costs are charged through existing composition_entry_reads and the new
composition_result_writes counter. composition_result_joins is coverage, not an
extra saved-operation credit. Work-credit recognizes the explicit completed-rhs/v1
report and requires the write count; a missing counter fails scoring. Static
source mappings and result-rule flags occupy Program storage; each outstanding
Entry adds one optional candidate. Full memory/latency accounting is still
required before claiming net workload improvement.

## Validation

61 ownership integration tests pass, including cross-Run result composition and
rejection after subsume/delete. Five work-credit tests pass, including charging
and missing-counter rejection. A no-default-features runtime compile check passes.
After simplifying the candidate field, both focused RHS-result tests pass again.

The positive test trains from actual execution, selects and reloads the catalog,
and compares source Run snapshots and binding audits, including a subsequent
nontrivial union. A second control retains the selected ordinary query-prefix
fragments but removes RHS-result transitions. Against that control, serial and
two-worker executions both create **12 -> 10 signal bindings**, with two actual
result joins, two candidate writes and zero runtime shape builds. Thus the
additional sharing is attributable to the new result Entry, not ordinary LHS
composition learned in the same training run.

This is actual standalone Cell runtime fixture evidence. It is not a four-workload
Graph memory result, native egglog acceptance, fewer logical facts, or an RHS
speedup. The large compression goal remains open. The next batch should learn
result transitions from the current installed catalogs and charge their whole
Graph/Program storage and maintenance, before expanding their scope.

```sh
~/.local/bin/eggfuse-job run --kind compute -- cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --test cell_ownership
~/.local/bin/eggfuse-job run --kind compute -- cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --lib work_credit
```
