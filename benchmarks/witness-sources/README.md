# Published witness sources

This is the standalone Cell CPU, not the native egglog runtime. Baseline:
`595a079f` (runtime source unchanged from the frozen `f5bc98ca` build).
This iteration uses short correctness/counter executions, not a new timing campaign.

## Short workload outcome

The final sum-bits comparison removes failed dispatch work; it does **not** yet
reduce this workload's real queries or demonstrate an overall speedup.

| Observed work | Baseline | Candidate |
|---|---:|---:|
| Spine producer context / route probes | 90 / 90 | 12 / 12 |
| Spine failed donor attempts | 25 | 0 |
| Prefix context reads / plan comparisons / donor attempts | 6 / 26 / 6 | 0 / 0 / 0 |
| Actual key lookups | 19,222 | 19,222 |
| History capture reads / slots / allocations | 1,987 / 1,987 / 1,137 | unchanged |
| Execute allocation calls / reallocations | 203,945 / 20,743 | unchanged |
| Execute requested bytes | 35,645,834 | unchanged |
| Setup allocation calls / requested bytes | 69,004 / 7,974,066 | unchanged |

Both witness mechanisms still have zero hits on this frozen workload. The new
positive regression fixtures exercise actual receipt hits and fewer queries;
they do not establish production-workload speedup. No Raytrace run was added.
All 1,428 ordered Runs agree in state, RHS, writes, resumes, schedule and Spine
shape. Workspace all-features: 363 passed, 4 ignored; non-sparse focused checks:
23 passed; minimal no-default-features build passed. See [comparison.json](comparison.json)
and [validation.json](validation.json).

## Opportunity and typed proof

The preceding sum-bits execution attempted 25 complete Spine donors and 6
register-prefix donors, all unsuccessfully. Its 19,222 actual key lookups did
not decrease. RHS aliases and constructor reuse mean `(producer Cell, RHS op)`
is not necessarily the storage location of a result. The logical publisher may
also differ from the physical producer of an already existing anchor.

A further obstacle was the consumer switch: entering an uncatalogued consumer
resets its iterative state, dropping the producer's retained history before
local matching reads it. Preserve a temporary shared history handle across that
dispatch; do not carry it into a new history or extend its lifetime after matching.

The shared read plan now distinguishes query receipts, executed RHS receipts,
and physical effect fallbacks. Derive it after validating the iterative catalog.
A query donor is eligible only when the existing catalog already retains that
source. An effect tries an existing retained receipt when available and otherwise
uses its physical position. Dispatch uses the logical publication's rule/output;
physical context remains a conservative fallback when there is no publication.

Newly compiled routes omit statically elided RHS aliases from donor alternatives:
they are the same source as an earlier query/effect, not a second distinct row.
They remain valid publication anchors. Existing artifacts remain loadable.

Zero-argument constructor reads already use the singleton directory fast path.
Exclude them from witness/prefix plans: reducing their `key_lookup_calls` by
adding receipt dispatch would not demonstrate removed hashing or key checking.

## Live obligations and cost limits

Every returned receipt is read now and checked for visibility, table, arity and
all current equality/scalar key fields. Prefixes preserve result constraints,
primitive order, delta ownership and the complete residual expansion. Missing,
retired or mismatched receipts use the ordinary lookup; absence is never negative
proof. Stable FactRef IDs address rows, not equivalence. Equality representatives
are not reinterpreted as row addresses, including imported values.

No new capture demand, per-Cell receipt array, subscription or reverse list is
introduced. Reuse the existing published Entry/history packets. Earlier probes
that enlarged capture sets were rejected because they added storage work to buy
very few lookups. Uncaptured relations still fall back.

Failures distinguish missing Cell, missing fact, missing receipt, hidden row,
shape mismatch and key mismatch. Charge publication probes, receipt search steps,
shared-history handles, actual row reads and full-key checks. `receipt_hits` means
an address was found; only validated hits can avoid a lookup. Actual row reads
exclude attempts that fail before obtaining an address. Spine row reads are
already in `decoded_rows`, so the work ledger does not charge them twice.

The report also includes `/multi_stage/witness_plan`: static retained-read and
physical-fallback counts, excluded reads, and zero new capture slots. These are
shared plan entries, not executed events. Parse-time metadata size/load cost and
Raytrace timing are not measured by this short check.

## Verification

The regression fixtures compare ordered bindings, Run fields and complete state.
They cover reused constructors, query aliases, all-reused RHS publication,
uncatalogued full Spine consumers, retired second donors, residual expansions,
and the excluded singleton case. Existing tests retain union, ownership,
mutable-function, guard and repeated-variable checks.

The short diagnostic comparison uses the unchanged sum-bits artifact and exact
state/RHS/write/resume/schedule/Spine-shape hashes. Allocation counters measure
allocator requests, not RSS; setup excludes program parsing. Missing baseline
counters remain missing, not zero. Final observations are in `comparison.json`.

```sh
CARGO_TARGET_DIR=/private/tmp/eggfuse-union-digest/target CARGO_INCREMENTAL=0 \
  cargo build --release --locked -j 2 -p eggfuse-cell-runtime \
  --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics
cp /private/tmp/eggfuse-union-digest/target/release/eggfuse-cell-runtime out/witness-address/runtime-final
python3 benchmarks/witness-sources/compare.py \
  out/witness-prefix/runtime-diagnostic out/witness-address/runtime-final \
  out/condition-bake/query-classes-sum/program.json out/witness-address/final-audit
```
