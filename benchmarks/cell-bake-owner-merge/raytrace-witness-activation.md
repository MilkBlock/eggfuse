# Reuse existing Entry activation for observed Raytrace witnesses

The previous executed Raytrace catalog had 64 transitions but still performed
4,332,972 key queries. Its audited prefix supplied 2,127 witness recipes. This
iteration installs routes only for rules already capturing ownership Entries,
so route reuse does not silently activate another population of source records.

Implementation `230b221a` adds `bake_observed_witnesses --reuse-activation`.
The mask comes from the typed composition and compiled witness routes, together
with the existing marker program's eligibility. Raw recipe presence is not a
proof that a usable route exists. Installed recipes are retained; malformed
new rule IDs fail even when filtering would otherwise exclude them. The default
unrestricted selector remains available. After recompilation, Entry activation
must be exactly unchanged, as must result capture and composition wiring.
The existing `has_witness_routes` accessor is made public for compiler clients;
no runtime record or new capture mechanism is introduced.

Two selector/audit tests pass in job 406. Job 409 builds and freezes both
examples, reruns the old catalog's 128-Run audit on the merged runtime, selects
from that fresh trace, audits the new catalog, and executes both complete
Programs on the same frozen `4b7a9a4d` runtime. The old catalog is the previous
44-path/64-transition Raytrace artifact, not a catalog from a different workload.

## Coverage and validation

Exactly **1,041 recipes** are selected and 1,086 excluded. Eighteen rule Entry
classes and six result-capture classes stay enabled. Both prefix executions
have identical graphs, ordered bindings and source Run summaries at all 128
checked boundaries. Complete executions preserve the accepted Raytrace final
state, all 16,883 Run summaries and logical effect counts, including merge
calls. This is a differential Raytrace contract, not native Raytrace proof or
full-program per-Run graph coverage. The ordinary runtime binary is unchanged
from the preceding merge validation; this is a catalog comparison.

Observed matches remain hints until typed compilation and runtime admission.
Actual foreign result addresses, exact unproved keys, source/target liveness,
visibility, residual matching, ordered effects and Run boundaries remain live.

## Actual work, including the extra work

| Quantity | Control | Witness catalog |
| --- | ---: | ---: |
| Total key queries | 4,332,972 | 4,329,998 |
| Prepared worker key queries | 1,265,890 | 1,262,916 |
| Prepared worker key fields | 2,551,324 | 2,551,324 |
| Ownership Entries | 109,985 | 109,985 |
| Actual-result writes | 88,235 | 88,235 |
| Worker witness attempts | 0 | 38,170 |
| Worker anchor reads | 0 | 31,160 |
| Worker route probes | 0 | 5,696 |
| Worker reused route selections | 0 | 25,464 |
| Worker lifecycle checks | 0 | 5,267 |
| Worker witness hits | 0 | 2,974 |
| Worker proved-key hits | 0 | 1,037 |

All 2,974 omitted key queries are accounted for by worker witness hits. This
is only **0.0686%** of total key queries. Coordinator routing adds 3,461 address
checks and 1,224 route probes but accepts no witness. All ownership work counts
are unchanged. Prepared prefix storage, writes and buffer growth are also
unchanged, but that does not imply zero catalog memory: the serialized Program
grows by 484,411 bytes. Runtime catalog heap was not measured in this trial.

The coverage is concentrated: 1,035 recipes belong to rule 539, the
`Single`/`HasType` rule building `TNil`, `TCons` and `TupleT`. The selected sites
include 1,035 nullary `TNil` positions. These are template-site counts, not
runtime hit counts. Canonical nullary queries already have a direct member
lookup in `query_reads.rs`; counting every omitted point query as an omitted
hash lookup would overstate the saving. Key-field preparation did not fall.

The current witness key prover carries matched anchor inputs through Copy
operations, but clears a destination on Let. Thus earlier constructor results
in a prefix do not by themselves become a proof for later keys. Any extension
must use their actual returned results and validity, not infer liveness or
equality from an observed operation sequence. More recipe IDs alone do not
solve this proof or coverage limitation.

## Sequential timing and decision

Job 412 uses one timing lease, finishes all control samples before candidate
samples, and passes all 20 process-boundary guards. Each lane has one warmup
and three measured runs. The frozen binary is identical in both lanes.

| Median | Control | Witness catalog |
| --- | ---: | ---: |
| Inference | 4.760493 s | 4.785999 s |
| Load | 474.451 ms | 479.199 ms |
| Whole process | 7.338930 s | 7.340553 s |

Inference is **0.54% slower** in this short grouped trial; no speedup is
established. All samples are retained. The catalog remains experimental and
is not adopted as the default. The selector provides a checked activation
budget, not a calibrated cost model. Further selection must charge actual
route attempts and distinguish cheap member access from hash/key preparation
and whole-prefix work that can really be discharged.

This does not expand worker mutation scope. In particular, the canonical-owner
lane still encounters the ownership backend rejection in
`cell_births.rs::take_local_job` and `local_jobs_supported`. Removing that
global rejection needs a proof and implementation for birth-time ownership
effects; a larger witness catalog cannot substitute for it.

## Reproduce

Under the shared compute queue, build the two examples with
`iterative-bake,cell-absorption,view-ports,parallel-publication`, then run:

```sh
worker_prefix_catalog_trace round2/program.json 128 control-prefix128
bake_observed_witnesses round2/program.json control-prefix128/trace.json selected --reuse-activation
worker_prefix_catalog_trace selected/program.json 128 candidate-prefix128
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py check ACCEPTED_RUNTIME \
  control-prefix128 selected/program.json candidate-prefix128 full \
  --control-program round2/program.json
```

Submit the entire timing command once with `--kind timing`:

```sh
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py time full timing --repeats 3
```

Large artifacts are in worktree 3063's external
`out/cell-bake-routing-refresh/raytrace-witness-activation`. Exact commands,
binary/input identities, work, validation and retained samples are indexed in
`raytrace-witness-activation.json`.
