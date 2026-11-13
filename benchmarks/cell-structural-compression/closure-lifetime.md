# Why a proved closure still falls back

The next iteration must learn from actual executions of the existing catalog.
The current seven direct states already cover useful cross-Run routes; adding a
route produced no incremental work saving. This investigation tests whether
expired actual result receipts, rather than missing symbolic closure proofs,
prevent a scheduled block transition from discharging constructor work.

## Evidence

The existing v5 directory has 44 direct-completion witness failures. All 44
are retired receipts; missing slots, wrong tables and hidden receipts are zero.
Failure classification is now retained in runtime statistics. Its extra
live-table lookup on each failed visibility check is charged by measured-work
credit (44 reads here); missing slots need no such lookup. Counters describe
the first failing output per attempted completion, not every invalid slot.

Temporary publication diagnostics found 15 forwarded slots in shared current
frames that the unique-owner sealing path deliberately skipped. Twenty later
failed-output observations refer to one of those old identities. This is a
correlation, not twenty independently recoverable rule applications. The Run
forwarding map expires, while projected histories can retain the old receipt.
Ordinary execution remains correct by falling back.

Two finite alternatives were tested against the saved audit, then removed:

| Work | Current v5 | Eager shared-frame sealing | Query-receipt replacement |
| --- | ---: | ---: | ---: |
| Direct completions | 165 | 174 | 165 |
| Witness fallbacks | 44 | 35 | 44 |
| Constructor requests | 8,023 | 8,014 | 8,023 |
| Key lookups | 12,124 | 12,115 | 12,124 |
| History capture allocations | 320 | 311 | 320 |
| Extra sealing allocations | 0 | 22 | 0 |
| Sealing slot reads | 284 | 497 | 284 |

Eager sealing scanned the current shared view when the Run had forwarding,
materializing only changed frames and retaining only their current outputs.
It copied 33 slots across 11 frames. Its 311 history capture allocations omit
22 separately counted sealing allocations: do not claim a net allocation
reduction. It recovers the nine extra constructor queries introduced by v5,
but adds maintenance to unmodified shared frames. This is not adopted as the
new runtime path or claimed as a speedup. Its saved `history_seal_writes` counts
changed receipt identities; materialized slots are the full copy count.

Query replacement used the checked `Site::Query(atom)` output mapping to read
the consumer's existing matched receipt, only when the donor output was stale.
It validated all outputs before copying a current result frame. There were
zero query replacement attempts: the failing outputs are RHS effects. This
alternative has no demonstrated benefit and is removed too.

All three trials pass all 1,428 saved Run graph and ordered RHS/write/resume
hashes; their final graphs agree exactly. The retained diagnostic lane also
passes the prescribed native-choice semantic acceptance. These are actual
standalone Cell runtime executions, not native runtime timing measurements.
The earlier unrelated borrowed-layout working-tree changes are common to all
lanes. No rule matches were removed; no complete egraph memory claim follows.

## Next structural obligation

A symbolic saturated transition is not sufficient for executable completion:
its required *effect result witnesses* must survive until the consuming Run.
Bake should use its existing result exports and source/consumer mappings to
identify demanded effect slots and their lifetime, then choose where preserving
those witnesses is cheaper than falling back. Do not add a global receipt graph,
scan all historical frames, or infer actual addresses from producer/op identity.
Boundary visibility, queued union order, residual matches, and deletion remain
live obligations. Additional catalog depth alone does not repair this failure.

Acceptance must count additional reads/copies/allocations and genuinely avoided
constructor requests separately. The nine recovered completions are not nine
newly skipped matches. The retained classification is observation, not a
completed takeover.

## Saved-evidence analysis

```sh
python3 benchmarks/cell-structural-compression/analyze_closure_lifetime.py \
  out/cell-structural-compression/closure-diagnosis-work.json \
  out/cell-structural-compression/closure-sealed-work.json \
  out/cell-structural-compression/closure-refreshed-work.json \
  benchmarks/cell-structural-compression/closure-lifetime-results.json
```

The analyzer rejects missing Run acceptance or unequal final graphs and omits
all timings. Raw rejected-trial outputs and temporary patches stay in ignored
`out/`; neither rejected implementation is present in the runtime. The current
failure counters can be reproduced with the `runtime_closure_work` command in
[closure-execution.md](closure-execution.md).
