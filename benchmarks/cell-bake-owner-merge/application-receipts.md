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

## Original workload measurement

Jobs 277 and 279 reconstructed the full original sum-bits source and training
input from `workloads/pass3/suite.json`, following the marker-handoff reproduction
instructions (no frozen suite catalog). The materialized regeneration has an
exactly identical `source_core` and `recipe` to the original artifact. The
receipt-only audit proves omission removes 107 declarations and 130 set sites;
all other typed source fields, schedule, and marker-selection fields agree.
It rejects residual references anywhere in the remaining core and computed or
non-Unit receipt writes. This is an audit of generated artifacts, not a generic
name-based dead-table optimizer. Three audit regression tests pass (job 280).

Actual standalone Cell runtime measurements use completed owners, port domains,
and Cell fields in all lanes. Job 280 runs original and omitted artifacts; job
282 adds the regenerated materialized control using the same frozen binary.

| Artifact | Runs | Graph bytes | Retained Program bytes | Receipt rows |
| --- | ---: | ---: | ---: | ---: |
| Original frozen | 1,428 | 2,038,485 | 115,168,530 | 264 |
| Regenerated, materialized | 1,428 | 2,040,453 | 123,895,013 | 264 |
| Regenerated, omitted | 1,428 | 1,925,591 | 120,103,556 | 0 |

The isolated omission saves **114,862 Graph bytes (5.63%)** and **3,791,457
retained Program bytes** against current compilation with receipts. It removes
264 actual receipt rows. Against the original artifact, Graph saves 112,894
bytes, but retained Program grows 4,935,026 bytes: this is not a total process
memory improvement over the old artifact. Regeneration alone adds about 8.7 MB
of Program data, mostly `context_cuts` and its JSON `artifact` copy. Those are
resident compiler plans, not disposable offline Bake data. This duplication is
a separate opportunity to investigate, not a saving credited to this change.

The omitted Graph is **48.39%** of the original 3,979,373-byte historical
denominator, still above the 30% target by **731,780 bytes**. The historical
baseline qualification in `original-target.md` remains applicable. These are
retained Graph bytes; process high-water includes Program and is not Graph peak.

`runtime_storage_peak --state-output PATH` now saves the same measured
execution's already-built final export after measurements, avoiding a second
execution for semantic acceptance. Job 281 runs the unchanged
`choice_diagnosis.py` and all four comparisons pass. Its existing `cpu_legacy`
input is the original artifact's new execution; `cpu_values` is the new omitted
legacy-handoff execution. Native references are the saved reviewed exports.
These labels are validator input slots, not a claim to have run a new native
omitted or values-handoff lane. No exclusions or proof rules were broadened.
The regenerated materialized final-state digest exactly matches the original.
Full-workload Run-by-Run graph comparison has not been repeated for omission;
the unchanged 1,428 Run count is not such a proof. The earlier short fixtures
cover individual Run boundaries and later union activation.

Reproduce the generated artifacts using the earlier marker-handoff commands,
adding `--marker-receipts materialized` or `--marker-receipts omit`. Then run:

```sh
python3 benchmarks/cell-bake-owner-merge/receipt_omission.py MATERIALIZED OMIT ORIGINAL_PROGRAM SOURCE_DELTA.json
runtime_storage_peak PROGRAM MEMORY.json inherited-owners --port-domains-only --cell-fields --state-output STATE.json
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_BUNDLE SEMANTIC.json
```

Build and run through the shared compute queue. Detailed hashes, field charges,
source audit, semantic result and lane mapping are in `receipt-omission.json`.
Default receipt materialization remains unchanged. No timing claim is made.

Follow-up: `admitted-cuts.md` identifies the major plan-growth cause. The
regenerated artifact lacks the historical admission policy, so it formerly
retained executable cut candidates that its runtime could never dispatch.
The follow-up removes those unused instructions without changing this artifact
or the accepted final state; it does not credit Program bytes to Graph savings.
