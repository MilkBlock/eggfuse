# Share source validation across installed Cell catalogs

The actual original-source witness experiment removes 280 constructor lookups
but does not improve inference. It also increases Program load from 98.712 to
122.797 ms. Inspection finds a concrete duplicate cost: composition fragments,
dual-source patterns and constructor witnesses independently hash the entire
same source artifact during one ownership Plan construction. The last audited
408-recipe catalog contains both fragments and witnesses; another observation
cannot eliminate this repeated compiler work.

The ownership Plan now validates every installed header against a single lazy
source digest. The artifact is immutably borrowed throughout this construction.
No digest is stored in Program, no global cache is added, and catalog-free Plans
do not compute it. Private subcompilers retain schema, budget, typed port/code,
query substitution and actual-result-source checks. Agreement between catalog
headers is not enough: each must match the current source independently.

This removes redundant source serialization/hash work during loading, not rule
matches or committed effects. It adds no runtime instance state, producer lists,
fact graph or cross-Run assumptions. Scheduled visibility, source retirement,
union generations, exact unproved keys and residual matching are untouched.
No new Cell completion is credited. Load, inference and full-process time must
be reported separately; a smaller load time is not a parallel speedup.

The regression test loads all three header kinds together and separately,
rejects each stale/missing/non-string source, and then loads a different valid
source carrying the old headers. Existing fragment/witness/join tests still
exercise the typed subcompilers after common source validation. Actual-workload
validation and sequential timing compare with the frozen pre-change runtime.

Compute job 355 passes 71 ownership, 19 compiler and 13 witness integration
tests, plus the no-default runtime compile. The ownership suite includes
storage, composed sources, deletion/union and worker continuation fixtures;
the new header test also exercises lazy ownership preparation without fragments.

## Actual workload result

Implementation: `cf439fae`. Compute job 358 freezes the actual pre-change
`2ef47a82` and candidate runtimes, then validates ordinary sum-bits, Raytrace
and the unchanged original-source 408-recipe witness catalog. Final exports,
Run summaries and logical effects agree. The catalog has 1,428 Runs and the
reviewed native-accepted final hash; the native ordinary sum-bits validator
returns `pass`. All recorded preparation/ownership/scheduler work is unchanged.
This loader-only change does not widen source visibility or any runtime proof.

Timing job 359 completes all control workloads before any candidate workload:
five sum-bits samples, three Raytrace samples and nine witness-catalog samples,
plus one warmup per group. All 92 process-boundary guards are clear.

| Workload / metric | Before | After | Change |
| --- | ---: | ---: | ---: |
| Witness catalog load | 122.718 ms | 98.195 ms | -19.98% |
| Witness catalog inference | 22.924 ms | 21.956 ms | -4.22% |
| Witness catalog process wall | 205.858 ms | 173.164 ms | -15.88% |
| Ordinary sum-bits inference | 21.137 ms | 21.114 ms | -0.11% |
| Raytrace inference | 4.724922 s | 4.808894 s | +1.78% |

The removed duplicate digest corresponds to a 24.523 ms load reduction, close to
the earlier measured load increase from installing this catalog. Catalog-free
load is essentially unchanged (sum 67.248→67.101 ms; Raytrace
364.245→362.996 ms). No digest is computed for a catalog-free ownership Plan;
the witness input computes one instead of two, and all three installed catalog
kinds would compute one instead of three.

Keep this as a demonstrated catalog-load work reduction, not a parallel
inference improvement. Inference has no removed operations, and these short
grouped samples do not establish that the faster learned inference or slower
Raytrace is caused by the loader change. The two-workload inference speed gate
is **not passed**. The pinned broader performance baseline is unchanged, and
no wait time or worker-utilization benefit is claimed. No repeat trial was
selected to replace this unfavorable Raytrace result.

Full sample medians, ranges, source/binary identities, exact work agreement and
validation hashes are retained in `catalog-source-validation.json`; the large
artifacts live under the external `out/cell-bake-routing-refresh` target.
Reproduce using the existing queued `owner_workers.py` with the unchanged
`out/cell-original-witnesses-round1/program.json` as `--learned-program`, then
submit the entire `prepared_timing.py ... --repeats 9 --include-ordinary`
invocation as one timing job. The harness's `learned` label denotes that exact
original-source witness input here, not the older 882-Run workload.
