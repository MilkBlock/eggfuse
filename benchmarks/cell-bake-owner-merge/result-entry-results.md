# Installed-catalog RHS result learning: no structural compression win

Scope: standalone Cell CPU runtime at `23d55e65`, not native egglog or a speed
measurement. Learn from actual executions of the installed prefix-all catalog,
retain all 533 seed fragments and their exact transition targets, select only
additional fragments containing a completed RHS result Entry, then turn training
off. All 2,652 saved Run snapshots, ordered RHS/write audits, and four terminal
checks pass in learning and production. The control runs the unchanged seed on
the same runtime. Memory lanes use one frozen executable and agree with the
audited program identities, Run counts and final snapshots.

| Case | Added fragments | Result joins | Binding creations, control → new | Graph bytes, control → new |
|---|---:|---:|---:|---:|
| fact | 7 | 6 | 2,007 → 2,001 | 645,935 → 645,715 |
| loopfact | 7 | 7 | 1,873 → 1,866 | 572,285 → 572,241 |
| sum-bits | 45 | 76 | 7,680 → 7,665 | 1,702,627 → 1,703,795 |
| dot-product | 27 | 54 | 6,504 → 6,522 | 1,648,851 → 1,637,011 |

Result candidate writes are 262 / 175 / 2,037 / 980. Transition probes increase
by 49 / 32 / 351 / 165. No runtime shapes are built in either production lane.
Live owned facts and completed source-frame counts are identical between lanes.
Fact-record live bytes and writer bytes are also unchanged. This does not meet
the large runtime-egraph compression objective.

Dot-product's 0.718% Graph reduction largely comes from different completed-owner
packing (8,984 fewer bytes), despite more live signal bindings. Its process peak
increases by 159,639 bytes because retained Program storage grows. Program bytes,
complete Graph teardown bytes, and process execution/takeover peaks are reported
separately in result-entry-results.json; source record subtotals are not a full
memory measurement. The four process peaks increase, by 25,951 / 26,719 / 239,829 /
159,639 bytes. No speed claim is supported.

## What this changes about the next iteration

The trace proves actual cross-Run result reuse but does not prove elimination of
its producer or the consumer's remaining RHS. Current result-first admission can
also displace a different query-Entry composition, so summing successful local
substitutions overestimates whole-execution savings. More selected fragments is
not the next acceptance criterion. Do not promote this learned catalog as a
compression winner.

A useful successor must identify a covered source instance whose independently
stored state and maintenance actually disappear. It must preserve externally
observable fact identities and mutable reads, source Run/effect order, deletion
and visibility, and source-sized restoration after unexpected union. Internal
wiring alone is not that proof. Record source-frame, field and fact/index bytes
alongside binding maintenance, and charge replacement storage and dispatch.
The existing worker-prepared result path remains an uncovered interface; it
should consume the same completion evidence instead of adding another history.

## Reproduction

Requires the saved four-case batch inputs and prefix-all candidates described in
the surrounding benchmark documents. Run build and each experiment under the
machine-wide compute queue. Freeze both binaries after building so another
worktree cannot silently replace the executable during a lane.

```sh
cargo build --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example batch_cell_learning --example runtime_storage_peak
batch_cell_learning learn-results ROOT prefix-all rhs-result-learning
batch_cell_learning check-passive ROOT rhs-result-learning
# Copy prefix-all's per-case candidate.json and selection.json to rhs-result-control.
batch_cell_learning check-passive ROOT rhs-result-control
# For each variant and case:
runtime_storage_peak ROOT/VARIANT/CASE/candidate.json ROOT/VARIANT/CASE/full-memory.json inherited-owners --port-domains-only
python3 benchmarks/cell-bake-owner-merge/result_entry_results.py ROOT OUTPUT.json
```

The learning helper verifies unchanged typed source definitions and retained seed
transitions. Its training counters are explicitly not production savings. The
comparison rejects unaudited/mismatched program identities and final snapshots.
