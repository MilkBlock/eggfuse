# Full structural Bake refresh on the parallel branch

This integrates all committed history through `8ca2cc62` from
`codex/cell-structural-compression`, based on parallel runtime `7936e334`.
The source branch's uncommitted experiments are not merge inputs. The pristine
`egglog-baseline` tag is unchanged. Results here describe the actual standalone
Cell CPU, not a prototype or a new native egglog performance result.

The previous catalog's actual applies identify already established constructors
inside a completed component. Bake now compiles observed query/RHS positions
into witness routes, with typed wiring proofs for eligible constructor keys.
Only successful immutable query anchors and still-live actual results authorize
reuse. Unproved routes retain exact key checks and ordinary execution. Cross-Run
visibility, residual matching, union, retirement and effect order remain live
obligations; observation alone does not prove that an entire rule can be skipped.

The other incoming changes include nested completed-owner storage, inherited
fact lifecycle records, scalar restoration accounting and template-derived
scalar-free stable fields. These delete covered storage or lookup work; they do
not make all RHS effects independent or enable compression by default.

## Reconciliation

- Keep the parallel branch's producer registration, actual `ConstructorWitness`
  handling and worker absorption. Adapt incoming direct routes to that witness
  representation rather than restoring the older constructor call path.
- Keep frozen projected candidate membership for overlapped completion. The
  incoming blanket rejection of template fields with completion batches is
  obsolete on this branch. Existing union/retirement/panic tests cover this
  combination; a first integration run caught the accidentally restored reject.
- Retain one witness recipe trace. Derive the older `witness_paths` report from
  it instead of maintaining two runtime histories.
- Retain the richer per-cause restoration counters. Derive the older aggregate
  report fields from these same counters instead of counting restoration twice.
- Keep the existing source observation-only barrier history policy. Both
  branches had independently addressed this cost.

## Validation and measurement contract

The merged runtime passes 217 unit tests and the ownership, parallel guard,
completion batch, Cell execution, query worker, residual, Entry publication,
scoped completion, parallel publication, absorption and owner-pipeline suites.
The ownership suite includes actual constructor witness routes, typed key
proofs, atomic completion, scalar provider retirement and nested storage. The
40 Python catalog-analysis tests pass. Required build/example/README checks
and the full frozen workload comparison are retained in `results.json` when
completed; failed attempts remain recorded separately.

The frozen performance input configuration keeps four workers, repair ports,
Entry publications, Cell absorption, parallel residuals/publication and grain 1.
Its unchanged catalog does not automatically acquire every opt-in storage or
new witness route. A performance comparison of these inputs is a merge-regression
checkpoint, not a measurement of all incoming Bake features.

The acceptance script requires exact final states, all source Run summaries,
actual effects and iterative Bake evidence on sum-bits/Raytrace. Native sum
acceptance additionally uses the unchanged reviewed `choice_diagnosis.py` and
checks its export hash against the fresh candidate. Raytrace remains a runtime
differential check, not an extension of that native proof contract.

Quick timing must finish every control workload before starting any candidate
workload. Use `benchmarks/raytrace-parallel/quick.py` with frozen binaries and
fresh output; its compiler/runtime guards retain interrupted attempts. No
compilation or other task-owned workload runs alongside the timing samples.
