# Real visible snapshot to GPU Cell admission

The prior automatic-takeover test used a hand-built closed family. This experiment
imports actual visible constructor facts from the audited Eggcc dot-product final
export, then lets GPU queries find bindings and generate Cell tokens. It supplies
no future successful-match list, source-to-consumer wiring or consumer outputs.
It is **not** an initial-program or full multi-stage execution benchmark.

## Initialization and identity

RHS captures include after-Run Eq labels but lack per-Run visibility snapshots in
this corpus. Treating every old completed RHS as a live source would be unsound.
The final export instead carries an explicit subsumed bit for each fact. Import
requires that bit, drops subsumed rows, checks table schemas and deduplicates
identical facts. It does not infer visibility from a successful historical apply.

Each input table has one ordinary seed Cell template. Instances store their exact
fields in the existing owner representation. One original consumer rule is kept
unchanged in a local recipe, with its original RHS still pending after a match.
This isolates per-query coverage; it does not rewrite the program's schedule.

Typed canonical values are mapped bijectively to local integer labels. Equal
printed IDs of different sorts do not share identity. Labels never become
floating token coordinates. Scalars remain exact integer-key identities as well
as dynamic features; numbers not exactly representable in f32 use the existing
fixed scalar code instead of rounding their equality identity. These local IDs
are snapshot identities, not recovered historical stable addresses.

All visible rows of each queried constructor table are imported. Tables omitted
because they are not queried are **not** declared complete for RHS or global Eq
repair. The current probe stops after query/ridge/admission and marks every
unfinished RHS. Seed tokens use the same class-balanced encoder, but synthetic
seed template roles differ from the training producers, so this experiment does
not establish token prediction accuracy.

## Real workload results and boundaries

The trace and frozen model hashes are in snapshot-query-admission-results.json.
With 32 source rows and 32 candidate lanes allowed per local query:

| Category | Count |
|---|---:|
| Original rules | 548 |
| Unsupported query forms | 168 |
| Over source-row budget | 114 |
| Empty required input table | 232 |
| Tested rules | 34 |
| Queries completing enumeration without overflow | 34 |
| CPU raw-value reference bindings | 229 |
| GPU-generated Cell instances | 229 |
| Extra / missing bindings found by CPU | 0 / 0 |
| Pending RHS instances | 229 |
| Stored takeover hints | 229 |
| Committed RHS mutations / physical takeovers | 0 / 0 |

The CPU reference independently joins raw exported values and checks repeated
variables after GPU execution. It does not reuse the tensor matcher or provide
bindings to inference. All 229 generated bindings are checked. Pending effects
are 100% of generated instances; correct query completion cannot authorize their
effects, settlement or takeover. Empty-table and unsupported/budget categories
are reported separately rather than counted as tested successes.

Across the 34 separate compilations, input preparation takes about .161 seconds,
GPU compilation/upload/matching/ridge/admission 47.70 seconds, and CPU raw join,
output readback and comparison .008 seconds. These are deliberately different
scopes, not a speedup comparison. Cold per-query compilation is included and its
share has not been isolated; GPU execution is not assumed fast merely because it
uses Metal. No timings from this run should be reported as native egglog or
end-to-end Eggfuse performance.

## Next integration requirements

Import RHS constructor-table coverage, then execute supported effects before
attempting the stored takeover plans. Mutable and unsupported scalar effects
need explicit CPU repair boundaries. Preserve original source Run scheduling
when moving from final snapshots to initial-program execution. Training must
cover actual imported/continued source roles rather than assuming this seeded
state has the captured-producer distribution.

The Bake branch is now `6a9c1434`, which drives prefix compaction from actual
retirement events instead of repeated component scans. The GPU takeover path
already retains actual admitted-source evidence, but its fixed whole-instance
sweep remains expensive; it still needs bounded compaction of eligible events
with leftover obligations preserved. Neither logical matches nor plan counts
are storage savings.

## Reproduction

Run audit_snapshot_queries.py with rhs-dot-product.json, the frozen
class-history-neighborhood-input.npz and an output JSON, using defaults
--max-source-rows 32 --capacity 32. Files live under
/Volumes/Extreme SSD/eggfuse-artifacts/21ee. The reproducible script and text
report are committed; no model binaries are tracked. Sixteen relevant tests
pass, including missing-visibility rejection, schema validation, scalar precision,
duplicate rows, repeated-variable joins and existing GPU owner integration.
