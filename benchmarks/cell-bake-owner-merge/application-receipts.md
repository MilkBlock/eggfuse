# Optional diagnostic apply-receipt materialization

The original sum-bits source contains 107 generated `CellSpineApplied*` tables,
130 rule-head references and no rule-body references to these names. The measured
final state retains 264 rows in 18 of these tables, each with a source origin.
These observations motivate eliminating publication, not merely repacking rows.
They are not by themselves a general dead-table proof.

The compiler now accepts `--marker-receipts materialized|omit`, defaulting to
`materialized`. `omit` acts at the marker generator, before typed lowering. It
never emits the diagnostic apply-table declarations or their final RHS writes.
The existing correlated query markers, publication/completion rules and Cell
compiler remain in use. It does not remove a user-defined relation by matching
its name, or alter an existing Program in memory.

## Proof boundary

The original source is checked for the reserved marker namespace before either
mode runs. The generator alone creates each apply receipt. Its keys are selected
from already-bound source variables; producing a receipt performs no nested
constructor or primitive computation. The receipt is a Unit-valued merge-old
function write appended after the original effects and query-marker publications.
The generator emits no query, completion rule or merge expression that reads it.
Therefore omission removes a diagnostic membership write and its storage, not
an input to a later source operation. Query markers are separately generated and
are not subject to this option. Future additions that read apply receipts must
update this proof and the option's tests before enabling omission for them.

The old `marker_ir` continuation report uses materialized receipts to identify
source applications. In omit mode its receipt-derived entries are empty, and its
state description explicitly says apply history is not materialized. Ordinary
Cell templates still describe the actual query and effects. This change does
not claim to preserve that old diagnostic interface or produce a saturation
certificate. Users who need apply-history exports keep the default mode.

Removing a previously observable diagnostic table is an explicit mode choice.
It is not a whole-graph equality claim. The acceptance projection removes only
the exact generated receipt names returned by the materialized generator report,
while retaining every other source/query-marker table and hidden fact. The
reviewed sum-bits acceptance rules are unchanged. No broad table exclusion is
added to `choice_diagnosis.py`.

## Validation scope

The short constructor fixture runs both materialized and omitted programs in
native egglog and the standalone Cell runtime. Native-versus-Cell comparison
within each mode includes all tables. Across modes, each Run and the final graph
are compared modulo exactly the declared diagnostic receipt tables, using the
existing graph equivalence checker. Query-marker definitions must be identical,
materialized execution must actually create receipt rows, and omitted source
must contain no receipt declaration or action. Both legacy and values handoffs
are exercised. A reserved-namespace negative test prevents silently dropping a
user table. A subsequent union-and-rerun fixture checks later activation.

These checks establish the short fixtures' stated contract; they are not a new
full sum-bits native acceptance or a whole-workload memory result. The saved 264
rows are an opportunity count, not a measured count eliminated from the original
workload by this commit. That workload must be regenerated and its supported
core contract checked before claiming the corresponding memory reduction.

No runtime shadow graph, new instance bindings or per-producer subscriber list
is introduced. Large egraph compression and saturated-stage completion remain
unfinished.

Validation job 273: all 18 compiler library tests pass, including both omission
fixtures in legacy/values modes and source schedule/iteration/match-count checks.
