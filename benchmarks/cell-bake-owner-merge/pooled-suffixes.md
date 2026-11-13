# Pool completed suffixes without moving shared prefixes

The direct-source Bake experiment reduced logical component state, but increased
physical owners from 306 to 768 (128 paths) or 825 (256 paths). An old prefix can
share a physical slab with unrelated source frames. Flattening that prefix is
correctly rejected; the fallback previously allocated one new owner per suffix.

Before batching completed sources, the runtime now checks the existing owner
directory for external siblings. Such prefixes stay in place. Only their new
suffix frames enter the existing bounded pool (16 frames / estimated 4 KiB,
with an oversized individual group kept separate). Whole unshared prefixes still
use the existing extension path. No persistent map, child graph, binding copy or
new storage format is introduced. The directory check allocates nothing and
compares owner membership within the candidate frame list.

The authoritative logical components, source identities, facts and ports are
unchanged. Source-local retirement/restoration remains independent even when
different suffixes share a physical slab. This removes duplicate physical owner
containers; it does not claim additional logical source or fact retirement.

## Actual runtime measurements

Job 325 uses one frozen candidate binary on the unchanged direct-source seed and
both selected catalogs. Controls are the saved preceding measurements, with the
same Program hashes and completed-owner/port-domain/Cell-field flags.

| Catalog | Owners before → after | Graph bytes before → after | Saved |
| --- | ---: | ---: | ---: |
| Seed | 306 → 306 | 1,545,531 → 1,545,531 | 0 |
| 128 paths | 768 → 305 | 1,448,995 → 1,408,207 | 40,788 |
| 256 paths | 825 → 305 | 1,457,431 → 1,405,919 | 51,512 |

All savings occur in the Cells field. Program allocations, logical component
inventory, ownership query work, Run sequence and final exports are unchanged.
Maximum extra allocation during takeover falls from 16,244 to 11,376 bytes for
128 paths and stays at 11,376 for the seed and 256 paths. These are requested-heap
observations of the actual standalone Cell runtime, not RSS or timing results.

The 256-path candidate now edges out 128 paths on Graph memory, but retains more
Program memory. Its 1,405,919-byte Graph is about 35.33% of the historical
3,979,373-byte denominator, still 212,108 bytes above the 30% target. The Graph
target is not achieved, nor has saturated-stage RHS skipping been implemented
by this storage change. Extra catalog Program storage remains charged.

## Validation

The short regression fixture transfers prefixes either immediately or after
their suffixes are present. It checks actual slab sharing and zero moved prefix
slot/fact entries, then executes union, deletion and reconstruction while
comparing exports, snapshots and binding audits. Job 324 passes this fixture;
job 325 passes all 67 ownership integration tests, including full-owner extension
and restoration cases. These checks exercise the new storage path.

Job 326 checks the selected 256-path candidate against the direct-source control
with completed-owner takeover: all 882 Run graphs and ordered audits pass.
Job 328 applies the existing native
sum-bits semantic entrypoint to the candidate's saved final export, reusing the
reviewed native exports; all four comparisons and the overall status pass.
Final statuses and output hashes are recorded in
`pooled-suffixes.json`. The final-state contract does not replace Run checks.

Rebuild `runtime_storage_peak` and `runtime_storage_comparison` with
`iterative-bake,sparse-cells,storage-metrics` under the shared compute queue.
Frozen binaries and detailed results stay in `out/cell-pooled-suffixes`.

```sh
runtime_storage_peak PROGRAM MEMORY inherited-owners --port-domains-only --cell-fields --state-output STATE
runtime_storage_comparison SEED budget256-checked.json BUDGET256 --completed-owners
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_BUNDLE semantic.json
```

The comparison tool's old report records the seed digest; the frozen job command
binds its candidate to `out/cell-direct-composition/budget256/program.json`.
The semantic bundle retains the original reviewed `sum-legacy/program.json` and
uses the new candidate export in `run-values/state.json`; those lane names are
validator input labels, not an assertion that markers were reintroduced.
