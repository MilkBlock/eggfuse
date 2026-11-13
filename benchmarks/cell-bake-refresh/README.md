# Structural Bake refresh on the parallel branch

This merges the complete committed `codex/cell-structural-compression` branch
through `e992797be4ebbef00bb34f6188d3bef3ac0802e3` into parallel control
`7a9e2f41`. The earlier merge already included `8c73ff84`; this refresh adds
`83bcf700`, `c168e0eb`, `44d068ec`, and `e992797b`. The other worktree's
uncommitted changes are not included or modified.

## What is integrated

- Explicit finite selection budgets support larger compiled Cell catalogs.
  Increasing a budget does not bypass typed substitution checks.
- Traces from compatible inputs can propose one shared catalog, with rule,
  port-program and Entry coordinates remapped through static definitions.
  This is exact structural identity, not a proof that arbitrary derivations
  have reached the same saturated state.
- Production reads the existing sorted compiled transition directory.
  Only newly learned transitions occupy the runtime hash overlay. This removes
  a directory copy without creating a second runtime binding representation.
- Completed scalar slots can delegate to actual immutable constructor fields.
  Completion checks the actual provider and value. Retirement restores the
  binding before its last provider disappears; foreign constructor reuse is
  not treated as a synthetic local result address.

The merge conflict was confined to execution-plan storage accounting. Both the
parallel Unit plan and the incoming scalar projection layout remain charged.
Run-owned queues, root continuation, worker registration, collision checks and
completion events are retained.

## Opportunity and remaining obligations

The incoming batch uses actual applications from the last catalog rather than
inventing hot paths from rule text. A scheduled cross-Run continuation can reuse
its compiled transition and completed fields under the existing typed operation
and Entry proofs. The shared directory and scalar provider layout are static
wiring; neither introduces a per-producer consumer list.

Original Run/effect ordering, residual enumeration, visibility, late union,
actual returned witnesses and provider retirement remain authoritative. Scalar
delegation adds provider searches, completion scratch and retirement restoration;
the binary-searched directory changes lookup cost as well as removing storage.
These costs must not be counted as free.

The parallel workload comparison reuses the same frozen programs and catalogs;
it does not retrain or silently switch configurations. Completed-parent/scalar
takeover remains opt-in and requires the storage-metrics build. Composed
ownership still excludes the local constructor-worker path through
`local_jobs_supported()`. This merge does not solve that integration boundary
or establish recovery from the preceding timing regression.

## Work against the current branch

The same frozen parallel inputs give the following counts, control → merged:

| Work | sum-bits | Raytrace |
| --- | ---: | ---: |
| Generic execution instances | 5,195 → 5,195 | 1,024,678 → 1,024,723 |
| Ordinary key lookups | 12,910 → 12,910 | 3,825,444 → 3,825,298 |
| RHS dispatch batches | 135 → 135 | 6,600 → 6,602 |
| Admission/preparation operand reads | 4,132 → 4,132 | 605,646 → 605,964 |
| Worker slot leases / reattachments | 1,101 / 1,101 → same | 215,803 / 215,803 → 215,913 / 215,913 |
| Live reverse directory headers | 2,193 → 2,193 | 524,655 → 524,655 |

Execution instances are not physical Graph Cells. Some dispatch/preparation
counts depend on worker completion order; one execution does not isolate a
latency effect. Neither a few fewer lookups nor the incoming storage results
establish a speedup. Both parallel runs keep scalar delegation disabled, and
its new elision/restoration counters are zero. The separate batch checks below
exercise that opt-in path.

## Validation

This is the actual standalone Cell CPU, not native egglog. The work comparison
uses one execution each of the frozen sum-bits and Raytrace programs with four
workers. The README one-repeat bench is a smoke check; this is not a repeated
timing campaign. See `results.json` for exact commands, work counts, final-state
hashes and ordered Run-summary checks.
The 1,428 sum-bits and 16,883 Raytrace ordered Run summaries, final-state hashes,
logical effects, live reverse occupancy and iterative evidence match the control.

202 runtime unit tests and 146 integration tests pass, plus five pooling tests,
four storage-enabled root checks and forced hash/Bloom-collision reruns.
All-features, sparse-only and legacy runtime builds compile, as do the incoming
batch-learning and Unit-closure examples. README compile/run/bench checks pass.

The separate incoming four-input catalog check compares every source Run's
graph, ordered RHS and physical writes against its own unbaked control, with
completed-parent takeover disabled on the control. Frozen artifacts and their
hashes are retained under the ignored output directory. This check does not
extend the reviewed native semantic contract to those inputs.
All 2,652 source Runs pass: fact 418, loopfact 398, sum-bits 882, dot-product 954.

The initial debug batch verification reached its 240-second harness timeout
after verifying fact, loopfact and sum-bits. Their completed reports are retained;
dot-product is checked separately with the same binary and frozen inputs. This
interrupted attempt is recorded separately in `validation_attempts`.

The native sum-bits gate is the existing choice validator, tied to the freshly
generated CPU export by its hash. Raytrace remains differential validation
against `7a9e2f41`; final-state checks do not replace the targeted Run-boundary,
retirement, deletion and collision tests.

## Reproduction

Run the successful commands listed in `results.json`'s `validation` array.
Builds use `CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1`. Copy the incoming batch's
manifest and four `baseline.json` / `candidate.json` pairs into a fresh local
artifact directory, recording their hashes as `batch/frozen-inputs.json`, then
run the compiled `batch_cell_learning verify` example there.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-bake-refresh/run.py out/cell-root-continuation FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-bake-refresh/check.py out/cell-root-continuation FRESH_OUTPUT RESULTS.json
```

The checker reuses the root-continuation acceptance requirements; its new
control parameter leaves the historical check's default unchanged. Store the
successful validation commands in `validation.json` and `readme-checks.json`.
Build outputs, binaries, generated programs, full exports and caches are not
tracked. Exports may be losslessly gzipped; checks hash decompressed contents.
