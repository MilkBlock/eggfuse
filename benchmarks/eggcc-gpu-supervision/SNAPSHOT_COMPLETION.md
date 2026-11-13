# Real snapshot RHS completion followed by owner takeover

This extends SNAPSHOT_QUERY_ADMISSION.md past pending matches. It imports all
visible constructor tables used by a supported original rule's query and RHS,
runs the trained ridge admission path, executes copy/constructor effects and
refreshes the completed token, then attempts matched-source physical takeover.
The compiled Metal flow has no intermediate host state readback. CPU verification
runs afterwards. No backpropagation is used.

## Coverage and observable semantics

Supported RHS operations are copies from slots and immutable constructors
whose arguments are slots. Other effects remain rejected boundaries. A snapshot
containing subsumed facts in a relevant table is also rejected: visible-query
coverage alone does not prove constructor reuse semantics for hidden facts.

This is a frozen canonical snapshot, with no union or mutable updates. Therefore
the imported tables suffice for the tested constructor lookups; they do not
establish global repair coverage. Each rule runs independently with its original
effect order. An incomplete query cannot commit partial-Run effects: speculative
effect outputs are discarded on the device, while admitted tokens remain pending.
This gating still performs numerical work; it is not a compute-saving claim.

The CPU independently joins raw exported values and interprets the original
copy/constructor operations using raw table facts. It checks actual returned
slot identities and validity, rather than prediction scores. Results missing
from the frozen reference are explicitly unknown and fail this audit. All source
fields, roots and scalar metadata remain readable after physical relocation.

The input is the audited dot-product **final** export, not the program's initial
graph. Seed templates differ from training producer templates. Completion is
established by exact GPU effects, not by treating a ridge prediction as proof.
The test does not measure learned-state accuracy, new-fact generation, original
cross-stage scheduling, native proof replay or full Eggcc execution.

## Results and explicit unresolved work

The static selection examines all 548 original rules. It excludes 168 unsupported
queries, 196 unsupported effects, 149 over the 32-source-row budget, and 26 empty
input cases. Nine original rules remain: 50, 54, 244, 245, 246, 534, 535, 536, 537.

| Measure | 8 candidate slots | 32 candidate slots |
|---|---:|---:|
| CPU reference matches | 26 | 26 |
| GPU generated Cells | 19 | 26 |
| Completed Cells | 14 | 26 |
| Generated Cells still pending | 5 | 0 |
| CPU-checked completed results | 14 | 26 |
| Incorrect / unknown completed results | 0 / 0 | 0 / 0 |
| Executed copy/constructor operations | 32 | 56 |
| New constructor identities | 0 | 0 |
| Released physical rows | 10 | 22 |
| Blocked takeover attempts | 4 | 4 |

With eight lanes, three queries overflow during intermediate joins: seven final
matches are missing and five admitted instances remain pending. Those explicit
query boundaries prevent partial effects from being committed. The 32-lane run
has zero missing or extra matches. This is a capacity correction, not increased
model accuracy; it adds work and storage. The narrow result's audit pass means
the reported partial/boundary behavior is consistent, not that execution finished.

All four takeover rejections occur in rule 245 and report uncovered aliases.
The first consumer takes over the shared source; its physical row then carries
the completed consumer and source views. A subsequent single-source plan does
not cover that whole composition. Weakening this check would risk losing live
fields. There are no value-mismatch, stale-generation, occupied-tail or epoch
failures in these attempts. Diagnostic reasons can overlap in general.

The exact RHS operations all reuse existing constructor results in this final
snapshot. They are not 56 committed graph mutations. Released rows are reusable
arena capacity, not OS memory returned or logical facts removed. This evidence
does not show whether the same rules allocate new facts correctly in a complete
initial-program run.

## Bounded takeover work

The previous implementation executed a transfer-shaped operation for every
logical row and atom, including unrelated snapshot seeds. It now compacts rows
with pending eligible evidence using a fixed tensor sort, then processes a
static target budget. There is no data-dependent GPU branch. Unprocessed hints
and target generations remain live for later boundaries; frozen readers still
defer the operation. Stale candidates consume their attempt without affecting
semantic state. Runtime callers can set takeover_budget explicitly.

This reduces the number of transfer-shaped operations from N*A to B*A when
B<N, at the cost of the compaction and a target-index array. Each transfer still
scans aliases and uses functional updates; no speedup is claimed. The runtime
default remains N for compatibility. Optional diagnostics count rejection
reasons only when requested. New regression coverage ensures a one-target
budget does not discard the next valid candidate behind a stale one.

The tracked Bake branch has reached `a93e1271`. Its observed-prefix extension
can replace shorter paths at catalog capacity, but preserves the complete seed
transition language and charges retained plan storage. Here, repeated ownership
attempts identify a related opportunity: compile the current composite owner
shape, not only the original single-source projection. That requires preserving
all aliases and later query routes; this experiment does not yet implement it.

## Validation and reproduction

164 related tests pass, including supported-effect table import, hidden reuse
rejection, bounded evidence retention and the existing nested GPU Run tests.
Run audit_snapshot_completion.py with rhs-dot-product.json, the frozen
class-history-neighborhood-input.npz and an output JSON. Defaults are
--max-source-rows 32 --capacity 32; use --capacity 8 for the bounded control.
Inputs and detailed logs remain under /Volumes/Extreme SSD/eggfuse-artifacts/21ee.
Two text reports preserve hashes, boundary counts, exact-result checks and
rejection reasons. Timing fields include compilation/upload and CPU readback;
they are not a controlled throughput comparison or native runtime benchmark.
