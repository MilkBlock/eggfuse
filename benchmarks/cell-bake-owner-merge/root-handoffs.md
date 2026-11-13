# Seed result handoffs directly from completed typed producers

The four audited `prefix-all` artifacts each install 533 ownership fragments,
with 237/224/766/752 witness recipes. None installs `iterative_bake`, a result
switch, or spine-block entries. The inventory records each input digest. Ordinary
Shared Entry and ownership composition still run; their presence is not evidence
that catalog-driven result history or a closed-stage RHS program is installed.

The result-handoff compiler previously required a nonempty spine-block seed even
when `emit_matched_routes` had enough typed producer/output/consumer/pivot data.
A completed producer root is now sufficient. It does not need an unrelated query
expansion block. Existing block seeds remain validated and hashed into the source
contract. An absent block seed hashes as null; the typed recipe and sorted,
bounded producer roots remain mandatory. Empty catalogs without roots are still
rejected. If a null catalog's proposed routes offer no typed reuse, it remains
null rather than creating captures and dispatch metadata.

The existing lowering checks source operations, consumer pivots and result
reuse. The ordinary matcher still establishes all consumer conditions before
resumption, and actual retained receipts keep their current lifetime checks.
No alternate runtime representation, copied binding map or source marker is
introduced. `bake_matched_handoffs` also rebinds both existing ownership fragments
and witness recipes to the changed artifact, then revalidates their typed plans;
previously it updated only the fragment source identity.

## Validation and limits

A new fixture starts from the ordinary compiler output, with neither spine blocks
nor an iterative catalog. The typed matched route installs actual result reuse.
Serial, Shared Entry and two-worker executions match baseline snapshots and
binding audits, increase actual `handoff_lets`, and reduce `key_lookup_calls`.
The empty-route case leaves no catalog. This is an executable fixture, not a
pass3 performance or memory result.

The compiler integration suite passed 19 tests, Entry publication passed 14,
and matched handoffs passed five (including the no-useful-RHS negative case).
Six runtime iterative library tests and the handoff example compile check also pass.
After the work-credit compatibility repair, query receipts pass 7/7 and ripsat
completion passes 23/23 on the merged parallel-publication runtime. Matched
handoffs pass 5/5 and parallel publication passes 2/2. These are standalone Cell
CPU checks, not a new native egglog acceptance or performance measurement.

The scoring repair accepts the exact current constructor preparation v7, local
births v4, completion-events v4 and query worker cell-run-events/v6 schemas.
It charges Unit preparation, actual admission and witness checks, registry work,
root preparation, scheduler admission/event work and final winner comparisons.
Successful/failed admission outcomes enumerate actual checks; they earn no
negative credit. Prefix subsets, final output rows, timing and bytes do not add
another operation charge. Five work-credit tests pass, including counter
perturbations that require each new operation to reduce savings, missing-field
rejection, and checks that subsets do not count twice. The score remains an
unweighted operation comparison, not a latency estimate or full heap account.

No four-workload catalog has been modified by these changes, and no large Graph
compression or stage-switch speedup is claimed. The next task is to install
routes backed by the saved actual producer/result history and measure the
removed runtime work and retained storage, rather than infer coverage from the
number of compiled routes.

## Trace-to-plan boundary

Use actual producer rule and returned publication operation from the execution
trace when generating matched routes. Ownership frame codes share operator/port
layouts across source templates, so a frame code is not a unique producer rule.
Likewise, a final component is not necessarily the query-anchor topology that
held at the earlier match. Do not invent cursor ancestry by casting those IDs.
Existing successful-match evidence, ordinary residual enumeration and current
actual-result checks remain the authority.

```sh
python3 benchmarks/cell-bake-owner-merge/catalog_inventory.py out/cell-bake-owner-merge/batch/prefix-all benchmarks/cell-bake-owner-merge/catalog-inventory.json
~/.local/bin/eggfuse-job run --kind compute -- env CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --test matched_handoffs
```
