# Worker result fragments

This experiment runs the actual standalone Cell CPU, not the native egglog
runtime. The frozen control is `67d32b09`; only the query result transport changes.

The preceding Raytrace execution returned 1,554,547 residual answers. The
coordinator reopened each result array, looked up each answer's compiled rule
and appended its Instance to another array before sending it to winner selection.
Range workers already return compiled origin spans. When those spans all name
one rule, that rule can own the entire original allocation. No additional Bake
iteration is needed to prove this transport ownership. Catalog growth alone
would leave the serial transport intact.

The candidate moves the original array and its existing origin spans to the
rule's finishing task. That task gathers rows and performs the existing stable
input/source sort and deduplication. Alternating fragments and mixed-rule rows
retain their arrival order, including exact source ties. The coordinator still
routes mixed-rule arrays and point expansions by row. A rule's accumulated
answers must reach the existing worker grain (64 in these runs), and the Run
must already be pooled. Its finishing task therefore qualifies for a worker.
Once it qualifies, subsequent small arrays also transfer as fragments. Smaller
rule outputs retain the ordinary buffer; worker/inline destinations remain counted.

This removes per-answer coordinator routing within the proven coverage, not
all result compaction. Instances and their actual witnesses retain ownership;
no binding copy, new fact graph, per-producer subscription or extra task barrier
is introduced. Origin codes become source positions once per span. Rule-level
completion still waits for its contributors. Error ordering, source Run
visibility, delta ownership, residual enumeration and winner rules remain live.
The change does not discharge cross-Run reads or allow early RHS visibility.

Metrics distinguish transferred arrays/rows/spans, remaining coordinator rows,
worker versus inline gather rows, fallback rows moved a second time, fragment
header capacity, and ordered-buffer capacity. Original worker answer capacity
remains charged after transferring its allocation. Byte counters are accumulated
capacities, not peak resident memory or allocator call counts.

The initial work-only trial admitted all single-rule arrays. Raytrace transferred
1,139,666 answers, including 40,255 gathered inline; sum-bits transferred only
373 answers, all inline. Those small arrays paid new packaging costs without
moving work off the coordinator. The final eligibility rule excludes them.
The initial exports remain under `candidate-all-fragments` and their work report
under `all-fragments-results.json` in the artifact root. An intermediate check
applied the grain to individual arrays: it transferred 771,430 Raytrace answers
but increased fallback regathering to 355,811 rows. The final criterion uses the
rule-level task size, matching the scheduler. Intermediate exports remain under
`candidate-array-grain` and `array-grain-results.json`. Neither variant was timed.

The final work run preserves exact sum-bits and Raytrace states, all 1,428 and
16,883 source Run summaries, logical effects and iterative Bake evidence.
The unchanged native sum contract validator passes and its CPU export hash
equals the fresh candidate state. Raytrace is a differential runtime check,
not an extension of the native contract. Validation includes 209 runtime unit
tests, 110 compiler integration tests, legacy/all-feature compilation and the
three README commands. Another 20 query/residual integration tests passed with
the concurrent Bake diagnostic changes present at integration. The frozen
timing candidate is `e5dba47b`, and `24510d66` integrates the same runtime files
into that mainline. File hashes and binary hashes are in `provenance.json`.

| Final transport work | sum-bits | Raytrace |
|---|---:|---:|
| Residual answers | 4,082 | 1,554,547 |
| Original arrays transferred | 0 | 17,093 |
| Answers transferred to finishing workers | 0 | 1,035,361 |
| Remaining coordinator row routing | 4,082 | 519,186 |
| Transferred answers gathered inline | 0 | 0 |
| Fallback answers regathered by workers | 0 | 233,351 |
| New fragment header capacity | 0 | 2,804,928 B |
| Fallback buffer capacity before gathering | 0 | 55,385,088 B |

Raytrace's merge buffer plus new fragment/fallback capacities sum to 357,224,928 B
versus 404,538,816 B for the control merge buffer. Original answer capacity remains
363,177,024 B in both. The default output record grows from 88 to 96 bytes;
its plan capacity is charged separately. These figures do not measure peak RSS.
Sum keeps the old merge capacity (1,181,840 B) and no fragment allocations.

Scripts use a fresh artifact directory and isolated checkout:

```sh
# First freeze the 67d32b09 release binary as ARTIFACT/control-runtime.
python3 benchmarks/cell-query-fragments/validate.py CHECKOUT ARTIFACT/checks TARGET
python3 benchmarks/cell-query-fragments/execute.py CONFIG_ROOT ARTIFACT out/cell-entry-owned/semantic
python3 benchmarks/cell-query-fragments/check.py ARTIFACT RESULTS.json
```

`CONFIG_ROOT/manifest.json` supplies the unchanged input programs and four-worker
arguments. Control and candidate use `cell-absorption,view-ports,parallel-publication`
release features. Sequential timings follow with
`benchmarks/raytrace-parallel/quick.py`; all control samples precede every
candidate sample, without interleaving or concurrent compilation.

The first five timing attempts were interrupted by concurrent compilers or Bake
experiments; two stopped before any sample. Those samples are retained separately
and never pooled. See
`timing-attempts.json`. The guard now also recognizes Cargo test executables
under debug/release `deps` directories, not only compilers and named benchmarks.

## Completed timing through the local queue

The sixth attempt acquired shared scheduler timing job 6 and completed all four
groups. All 48 sample/group boundary checks found no known compiler or workload
conflict. Every measured state, source Run summary and logical effect matches
the frozen references, including the reviewed native sum contract. Sum has five
measured runs and Raytrace three, each following one warmup per lane. No samples
from the interrupted attempts are reused.

| Inference median | Control `67d32b09` | Candidate `e5dba47b` | Change |
|---|---:|---:|---:|
| sum-bits | 26.235 ms | 26.116 ms | -0.45% |
| Raytrace | 5.312 s | 5.314 s | +0.04% |

**The pipeline is effectively unchanged in this checkpoint; speed acceptance is
not established.** Removing 66.6% of coordinator answer routing is a transport
metric, not evidence of whole-pipeline acceleration. Final winner sorting and
233,351 fallback row moves remain. The scheduler prevents overlap between its
managed jobs, but background OS services and grouped-order drift still exist.
This experimental path remains a candidate for reducing actual result moves;
it must not be credited as an observed runtime speedup.

`timing-results.json` stores the compact result and the checksum of full retained
observations in `out/cell-query-fragments`. Scheduler validation is recorded in
`tools/local-jobs-validation.json`.

## Remaining result routing on the unified Cell branch

The `d0d8ee33` frontier audit and `b9fda4c1` source-slot projection reinforce the
need to replace a runtime representation and its maintenance, not merely share
more bindings. The current parallel path already transfers 1,035,111 Raytrace
rows as owned fragments, while 519,436 rows still enter coordinator routing.
Those counts alone cannot distinguish mixed-rule arrays from small batches or
point expansions. Increasing fragment coverage without that distinction previously
added inline packaging cost, as the experiment above records.

The routing audit splits the existing fallback by point expansion, non-pooled
inline range, pooled mixed-rule range, and pooled single-rule range below the
finishing grain. These categories are exhaustive and disjoint. Admission, error
and source ordering, delta ownership, binding allocations and Run visibility are
unchanged; the counters do not claim a completed takeover or a speedup.

`routing.py ACCEPTED TARGET OUTPUT --accepted-commit COMMIT` freezes this committed runtime under a compute
lease, runs unchanged accepted sum-bits/Raytrace programs, compares exact states,
source Runs and effects, and checks the reviewed sum-bits contract. It validates
that the four categories add to coordinator rows. The changed-root publication
experiment remains disabled. `ACCEPTED` can be the frozen borrowed-instance
candidate. This is a work audit, not another timing campaign.

### Correct Bake branch integration and observed routing

The requested `d0d8ee33` belongs to `codex/cell-parallel-admission`, not the old
`codex/cell-structural-compression` tip. The integrated source is `28735c67`,
including source-slot fields (`b9fda4c1`), their ordinary-feature compilation fix
(`a304eb6d`) and removal of reverse scalar providers (`28735c67`). Integration
initially exposed the missing `storage-metrics` guard; after incorporating the
source branch's fix, all 14 ordinary query-worker integration tests pass (job 197).
Source-slot fields remain opt-in; this diagnostic uses the ordinary parallel lane.

Audit commit `905350d8`, frozen and executed in compute job 200, gives:

| Remaining coordinator routing | sum-bits | Raytrace |
| --- | ---: | ---: |
| Point expansion | 3,267 | 41,331 |
| Pooled mixed-rule range | 224 | 366,386 |
| Pooled small single-rule range | 308 | 103,812 |
| Inline range | 283 | 8,460 |
| Total | 4,082 | 519,989 |

Raytrace transfers a further 1,034,558 answers as 17,080 existing owned fragments.
Mixed-rule ranges account for 70.5% of the remaining coordinator routing, or
23.6% of all 1,554,547 residual answers. These are operation counts, not elapsed
time shares. Fragment qualification depends on arrival order, so its exact count
can vary between otherwise equivalent executions.

The next transport opportunity is to let a range worker append directly into
rule-owned result fragments, using the rule identity already in each compiled
origin. This could remove the coordinator's per-row origin resolution and
append for mixed results. It must retain the current Cell-local query order,
per-rule dependency completion, stable source ties and error order. Worker-owned
buffers need allocation/capacity accounting; creating many small buffers or
merely moving the same repeated flattening elsewhere is not an established win.
This is a within-Run transport opportunity, not an additional cross-Run proof or
new saturation coverage. No takeover is implemented or credited by this audit.

Both fresh exports exactly match the accepted states, all 1,428 / 16,883 source
Run summaries and logical effect counts. The reviewed native sum-bits validator
returns `pass`, and its CPU export hash matches the fresh sum state. Raytrace
retains differential coverage only. `routing-results.json` records these checks,
the runtime hash, features, queue job and the complete count breakdown. No speed
comparison was performed for this merge; the source-field memory result is not
treated as parallel acceleration.
