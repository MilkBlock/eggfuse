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


## Completed merge checkpoint

`db61fbe4` is the full two-parent merge of structural compression. `d4b9fa2d`
reconciles the current branch's additional witness tooling through `4d3055b5`.
The main worktree was advanced to that commit. Another session's in-progress
edits were temporarily saved and restored with identical added/removed lines;
they were not included in the frozen measurement candidate. Subsequent main
branch commits remain separate from this checkpoint.

The final release snapshot passes exact final-state, all 1,428 sum-bits /
16,883 Raytrace source Run summaries, effect counters and iterative Bake evidence
against `7936e334`. The unchanged reviewed native sum final-state validator
returns `pass`, and its CPU-export checksum matches the newly generated sum
state. README compile/run/bench, both research examples, the legacy feature
check, all-feature compilation and the listed tests pass. Query-anchor report
compatibility was rechecked after incorporating the additional mainline commits.

Both frozen performance inputs make zero compiled constructor-route probes:
this ordinary configuration is a regression baseline, not evidence of direct
route speedup. The new routes and completed storage are exercised by the
ownership and completion tests. Do not credit the existing worker absorption
again as a saving from this merge.

The first grouped timing trial completed the control lanes and candidate sum,
then stopped after candidate Raytrace sample 1 when another `batch_cell_learning`
process was detected. The trial is preserved in `timing-attempts.json`; it does
not supply a complete, uncontaminated performance comparison. No latency gain
or absence of regression is claimed from these samples.

Two earlier work/export attempts also ran out of disk space; their partial
exports and failure records remain under the artifact root. These were not
performance samples. Following the user's request, Cargo caches in two other
worktrees and two temporary target directories were cleaned, releasing about
6.6 GiB (7.7 GiB available immediately afterward). Sources, uncommitted edits,
frozen binaries, input programs and experiment results were preserved. Cleanup
and the initial completion-batch compatibility failure are recorded in
`integration-notes.json`.

To recheck saved results without rerunning workloads:

```sh
python3 benchmarks/cell-bake-full-merge/check.py \
  out/cell-bake-full-merge/control-verified \
  out/cell-bake-full-merge/candidate \
  out/cell-bake-full-merge /tmp/cell-bake-full-merge-rechecked.json
```
