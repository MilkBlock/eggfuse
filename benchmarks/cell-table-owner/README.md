# One worker region for terminal Unit table ownership

This checkpoint runs the actual standalone Cell CPU, not native egglog. The
control is `b913ab20`; the frozen programs and catalogs are unchanged. It
records work and correctness, with no new comparative timing campaign.

## Opportunity and live obligations

The previous catalog execution sent 106,316 Raytrace Unit candidates through
1,055 table-registration batches. The path classified exact keys on workers,
assigned compact Function IDs on the source thread, adopted the original rows,
then regrouped their IDs and entered a second pool region to install indexes,
membership, versions and change events. The second call was skipped for an
empty insertion set. These aggregate counters do not recover its exact call
count, so this checkpoint does not invent a baseline count of 2,110 calls.

The typed proof already comes from the Cell's terminal Unit tail: an old/new
merge of the Unit value, no intervening mutable read, fallible suffix or union,
and the constructor job reaching the end of the actual Cell. Runtime admission
also requires no earlier pending union/dirty repair, ordinary Unit storage,
at least 32 candidates and at least two tables. Ordinary instructions and Run
visibility remain authoritative. Uncovered Cells use their existing path.

The owner now takes the **actual** key directory, membership and change map of
each affected table. In a single pool region it:

1. Classifies exact existing/new/duplicate keys per table.
2. Computes the compact source-order ID prefix on a worker.
3. Installs keys, membership, versions and change events in those same owners.

The original candidate row carries its assigned ID. Source adoption moves the
worker's actual row allocation into Function storage and preserves origin,
lifecycle, Eq subscriptions and table-activation order. Returning the prepared
owners opens the directories after the rows exist. **The second pool call,
post-adoption table regrouping and success-path index reconstruction are gone.**
There is no second binding array or maintained fact graph. Duplicate candidates
are still exactly validated and discarded; Bloom matches are never proofs.

Compact source IDs still impose a prefix between the parallel classification
and installation loops inside that worker region. Source Function appends and
constructor adoption are still ordered. A single pool call is not evidence
that all synchronization or source work has disappeared.

An adoption error returns every original owner after removing reserved entries
beyond the actually adopted Function prefix. A short-lived shared reference to
each new row's fields supports this cleanup without copying its payload. Held
key directories and membership reject access; they cannot appear as an empty
table or expose reserved but unallocated rows. No later Run sees provisional
effects. Selective completion, retirement/generation and real foreign result
witness obligations remain in their existing paths.

Across Runs this removes table-registration handoff work beneath the same
scheduled Cell switch and Entry projections; it does not learn new dominators
or authorize early next-Run publication. Existing catalog executions identify
the covered work, and existing typed Cell facts prove the takeover.

## Measured work and costs

Release features: `cell-absorption,view-ports,parallel-publication`. Both lanes
use the frozen candidate4 invocations in `out/cell-events/{sum,ray}-manifest.json`:

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Registration batches | 1,055 | 1,038 |
| Candidates through table registration | 106,316 | 103,729 |
| ID-prefix rows assigned on workers | 0 | 103,729 |
| Pool calls in new registration path | not counted | 1,038 |
| Prepared table owners returned | not counted | 2,076 |
| New Function rows installed through this path | 70,259 | 68,517 |
| Prepared entries discarded after adoption error | not counted | 0 |
| Registration payload capacity, cumulative bytes | 9,465,672 | 11,364,240 |
| All Unit candidates / duplicate invalidations | 129,123 / 43,783 | 129,123 / 43,783 |
| Total key lookups | 4,027,756 | 4,027,756 |
| RHS queue payload capacity, cumulative bytes | 95,111,216 | 95,117,616 |
| Completion payload capacity, cumulative bytes | 143,118,464 | 140,602,720 |

Ready-prefix sizes vary with scheduling, so coverage changes are not themselves
an algorithmic improvement or lost work. Remaining Unit candidates use normal
exact adoption. Both executions have 81,223 constructor jobs and 41,789 jobs in
background admission waves. Admission while a producer remains unfinished was
observed 17,191 times in the control and 7,225 in this execution; these counts
depend on relative progress and do not measure utilization or elapsed savings.

The new registration capacity is about 1.90 MB higher cumulatively. It charges
the prefix choices, owner/job/item storage, classification scratch and rollback
field handles. This is not peak live memory or an allocator trace. Actual table
maps move; they are not copied. Owner markers also add checked unavailable
states to existing directory/membership accessors. Whole-runtime timing must
decide the net benefit; the last complete timing campaign's regression remains
unresolved. Earlier diagnostics attributed only about 0.63% of inference to the
two old Unit registration phases, so this change alone cannot establish broad
multi-core saturation.

sum-bits does not reach the multi-table registration threshold. It retains 255
constructor jobs and 14,012 key lookups. All 323 Unit candidates and 124 duplicate
invalidations stay exact. Its completion payload capacity changed from 521,184
to 522,160 bytes with event batching; no speed benefit is claimed.

Feature-gated diagnostics now report the combined `registration` phase. Old
`classify`/`install` fields remain for report compatibility and are zero on this
path; that does not mean their work vanished. The combined pool residence is
not isolated synchronization waiting. The old unused per-task timing wrapper
was removed. `CELL_SYNC_REGISTRY_INLINE=1` still executes the same owner logic
inline for diagnostics, with zero pool calls.

## Validation and reproduction

153 runtime tests and 85 relevant integration tests pass. New tests cover scalar
and tuple keys, existing and empty tables, and interruption after 0, 1, 2, 5, 19
or 64 source rows. They compare exact IDs, original allocations, final graph,
versions, coalesced changes, activation order and later ordinary writes. They
also check that unadopted field references are released and held tables cannot
be queried. Diagnostic inline and pooled variants pass these same tests.
Existing tests cover duplicate writes, union, deletion/recreation, same-Run
invisibility, late errors and actual Run snapshots. Forced hash/Bloom collision
tests and all-feature, sparse-only and legacy builds pass.

The frozen sum-bits and Raytrace exports, all 1,428 / 16,883 ordered Run
summaries and logical effect counters equal the control. Summary equality is
not a full graph snapshot at every Run; the small integration fixtures provide
those checks. Native sum-bits semantic acceptance is `pass`, and its saved CPU
export hash equals this execution. Raytrace is an exact differential check,
not an extension of the native proof contract.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-table-owner/semantic-acceptance.json
python3 benchmarks/cell-table-owner/check.py out/cell-admission-pipeline out/cell-table-owner benchmarks/cell-table-owner/results.json
cargo cell-compile --case sum-bits --output out/cell-table-owner/readme-program
cargo cell-run --program out/cell-table-owner/readme-program/program.json --output out/cell-table-owner/readme-run
cargo cell-bench --program out/cell-table-owner/readme-program/program.json --repeat 1
```

Use fresh output paths for the Cargo smoke commands. The one-repeat bench is a
README workflow smoke check, not a performance comparison. Source root admission,
shared constructor-index adoption and ordered effects remain larger ownership
boundaries; this change does not claim to finish the scheduler refactor.
