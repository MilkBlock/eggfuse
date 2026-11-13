# Cross-stage owner and iterative Bake merge

This integrates the complete committed `codex/cell-structural-compression`
branch through `b563e90cda050d71f658deae634e94a2ce905261` into parallel control
`26b1650b`. Four commits follow the previously merged `e992797b`:
`7878a14f`, `eae8acf6`, `dc5eb712`, and `b563e90c`. The source worktree's
uncommitted work is not part of the merge. Git merged the runtime changes
without textual conflicts; the parallel scheduler and prepared continuation
remain in place.

## Integrated behavior

- A later completed stage can extend an existing shared storage owner. Logical
  Cell identities, metadata, retained parent readers and retirement fallback
  survive the transfer. Moving previous slots and facts is explicitly charged.
- Shared catalogs can be extended from audited executions of the installed
  catalog. Typed source and Entry mappings and the seed transition language
  are rechecked. The expanded experimental catalogs remain optional: the
  incoming 64/256-proposal selections did not improve storage on every input.
- Completed owned facts store only mutable lifecycle fields. The owner proves
  the omitted representation fields; exceptional writes restore ordinary
  storage. Ordinary and compact facts use the same access boundary.
- Saturation observation reads age through common Cell metadata, so a
  transferred predecessor is still recognized as belonging to an earlier Run.

## Opportunity and live obligations

The incoming audit uses actual applies from the last installed catalog. It
finds 821 fully witnessed RHS applications out of 15,231 observed applies,
including 524 remaining constructor operations and 390 already-equal unions.
These are opportunities, not effects removed by this merge. The proposed next
takeover is a compiled actual-witness projection for repeated relation closure.
Static aliases and copies receive no second effect credit.

A scheduled switch can reuse completed bindings and facts at a settled Run
boundary under the existing typed composition and Entry proof. Original Run
visibility, mutable reads, delta ownership, residual matching, actual returned
constructor identities and lifecycle checks remain authoritative. This merge
does not add a second runtime fact graph or internal consumer lists.

Compact ownership still requires the opt-in storage path. The ordinary
four-worker lane below does not enable it; composed ownership still excludes
local constructor worker jobs. Neither the storage reduction nor the catalog
audit removes that integration boundary or establishes a parallel speedup.

## Work against the parallel control

One execution each with the same four-worker configuration gives:

| Work | sum-bits control → merge | Raytrace control → merge |
| --- | ---: | ---: |
| Generic execution instances | 5,195 → 5,195 | 1,025,396 → 1,025,397 |
| Ordinary key lookups | 12,910 → 12,910 | 3,824,859 → 3,824,824 |
| RHS dispatch batches | 135 → 135 | 6,550 → 6,552 |
| Prepared witness resumptions | 711 → 711 | 71,777 → 71,778 |
| Completed instances released beside the queue | 18 → 18 | 4,863 → 4,865 |

Batch and admission counts can vary with worker completion order. These small
changes do not establish a latency effect or explain the previous regression.
The new owner-extension counters remain zero in this ordinary parallel lane;
the separate opt-in replay below exercises the new storage representation.

## Validation and reproduction

The comparisons exercise the actual standalone Cell CPU, not native egglog.
They use unchanged frozen programs and flags, without retraining the parallel
inputs or changing their catalog. `results.json` records the checks and work
against `26b1650b` (runtime code identical to `c7874855`).
Both final exports, all 1,428 sum-bits and 16,883 Raytrace ordered Run summaries,
logical effects, live reverse occupancy and existing iterative evidence match.
Suspended lifecycle holds are all released.

203 runtime tests and 139 integration tests pass, alongside the storage-enabled
fact lifecycle / prepared continuation checks and forced hash/Bloom collision
reruns. All-features, sparse-only and legacy configurations compile; the incoming
batch example compiles and all 13 Python pooling/selection/audit tests pass.
README compile, run and one-repeat bench smoke checks pass.

The separate four-input replay uses frozen incoming seed candidates, cached
per-Run graph/ordered-RHS/physical-write checks and terminal effect checks.
Input file hashes are recorded. It validates the opt-in owner path separately
and does not extend the reviewed native contract to those inputs.
All 2,652 Runs pass: fact 418, loopfact 398, sum-bits 882 and dot-product 954,
including the terminal non-Run checks. Each case actually transfers completed
frames into owners and uses the 32-byte compact fact representation.

Native sum-bits acceptance uses the existing choice validator on saved exports,
tied to the freshly generated parallel CPU export by its exact hash. Raytrace
uses differential validation against the current branch. No repeated timing
campaign is part of this merge; README bench is a one-repeat smoke check.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-bake-owner-merge/run.py out/cell-prepared-continuation FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --locked -p eggfuse-cell-compiler --features iterative-bake,cell-absorption,view-ports,parallel-publication,storage-metrics --example batch_cell_learning
target/debug/examples/batch_cell_learning check-passive FRESH_OUTPUT/batch owned-state
python3 benchmarks/cell-bake-owner-merge/check.py out/cell-prepared-continuation FRESH_OUTPUT RESULTS.json
```

Before replay, copy the incoming batch manifest and each case's `candidate.json`,
`catalog-observation.json`, `terminal-check.json`, and `owned-state` candidate /
selection into `FRESH_OUTPUT/batch`; record their SHA-256 in `frozen-inputs.json`.
Run the validation commands recorded in `results.json` and store their successful
exit codes in `validation.json` and `readme-checks.json`. Build outputs, generated
programs and full exports remain untracked. Exports may be losslessly gzipped;
the check hashes decompressed contents.
