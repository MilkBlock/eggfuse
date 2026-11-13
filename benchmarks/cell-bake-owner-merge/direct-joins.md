# Matched multi-source expansion: a rejected memory tradeoff

The selected direct-source Program already has 256 ordinary continuation paths.
Job 330 observes that exact installed catalog and checks all 882 Run graphs and
ordered audits against the saved direct-source control. Local full RHS coverage
increases from 32 in the singleton catalog to 105, but 4,608 applications still
report a missing local constructor. This is observed local coverage, not a
global saturation proof or saved execution.

The new `bake_observed_joins` helper generalizes the existing four-workload
dual-source experiment to one audited artifact and a batch of budgets. Like the
multithread branch's `bake_observed_witnesses`, it requires the exact installed
catalog identity as well as the source digest and successful Run audit. The
typed loader re-derives query substitutions and checks source layouts; trace
frequency only ranks candidates. Existing patterns, source shapes and suffix
transitions must survive installation. Runtime lifetime, visibility, current
equality, pending-work and frozen-read checks remain unchanged.

The trace yields 1,525 typed two-source candidates, 593 observed at least twice.
From this one trace, job 332 compiles budgets 32, 128 and all 593. Job 333 measures
all three with the same frozen runtime and owner/port/field settings. No extra
training run is performed between these selections.

| Patterns | Actual joins | Bindings retired | Graph bytes | Graph saved | Program added |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 1,405,919 | — | — |
| 32 | 48 | 48 | 1,403,727 | 2,192 | 511,341 |
| 128 | 87 | 87 | 1,403,855 | 2,064 | 2,141,549 |
| 593 | 135 | 135 | 1,399,999 | 5,920 | 9,387,054 |

The expanded catalogs are **not adopted** as the selected configuration. Their
small Graph reductions do not justify retained Program growth. The current
selected Graph remains 1,405,919 bytes; none reaches the 30% goal. A lower
component count is not sufficient evidence of useful compression.

The largest catalog attempts 1,386 route probes, admits 135 joins and records
1,947 early exits at the pending/frozen/repair guard. Every admitted join retires
only one binding. These counts identify two separate limits: reaching a legal
takeover point and eliminating enough state after reaching it. They do not imply
that all early exits would have matched a compiled candidate, nor that clearing
the guard would make them legal.

The aggregate guard previously conflated pending facts, pending component
signals, frozen component reads, queued unions and dirty facts. Five independent
reason counters now distinguish them without changing admission or maintaining
another dependency structure. Reasons may overlap within one skipped apply.
Their measured breakdown is saved in `direct-joins.json`; a reason counter is
diagnostic evidence, not a completed takeover or speedup.

Job 336 isolates the cause: all **1,947** exits have queued unions; pending facts,
pending component signals, frozen reads and dirty facts each count zero. The
instrumented replay has identical Graph fields, logical state, Run sequence and
final export, and all 67 ownership tests pass. The current union queue stores
Eq-value pairs, not component addresses; publication still occurs later through
the original union batch. This identifies a specific proof obligation for the
next change: can a matched takeover, justified entirely by current equality,
relocate boundary wiring before that unchanged queued batch commits? Queue
address stability alone does not prove the downstream repair/retirement path.
The guard is deliberately unchanged in this commit.

## Validation and reproduction

Job 332 passes the selector's catalog/audit rejection test and compiles all
three catalogs. The first build (job 331) caught an incorrect map-style access
to the existing transition vector; that was corrected before generating any
candidate. All three final exports exactly equal the selected control. Expanded
candidates have no fresh full per-Run audit and are not promoted on final-state
equality alone. The source observation does have a full Run audit. No timing
measurement or native contract extension is claimed.

Under the shared compute queue, build the helper with
`iterative-bake,sparse-cells,storage-metrics`, then:

```sh
runtime_catalog_trace SELECTED_PROGRAM SAVED_CHECKS trace.json
bake_observed_joins SELECTED_PROGRAM trace.json OUTPUT 32 128 4096
runtime_storage_peak OUTPUT/budgetBUDGET/program.json MEMORY inherited-owners --port-domains-only --cell-fields --state-output STATE
```

`4096` is the selection ceiling; only 593 repeated candidates exist here.
Detailed outputs and frozen tools remain in `out/cell-direct-joins`. The JSON
summary records source, trace, candidate and measurement identities. Further
work must prove which outstanding obligations actually depend on relocated
component addresses before narrowing a guard; blindly removing it is unsafe.
