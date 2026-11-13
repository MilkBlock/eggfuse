# Consume root admission inside the same Cell

Control: merged parallel branch `552db678`. This uses the actual standalone
Cell CPU, not native egglog. Frozen inputs, catalogs, flags and four workers
remain unchanged. This is a work/semantic checkpoint between the agreed
five-implementation timing checkpoints, not a throughput claim.

## Evidence and compiler coverage

The merged Raytrace control falls back from 84,904 occupied root hash buckets.
Admission already read the constructor parameters and computed the hash. The
ordinary RHS boundary then reads those same parameters and hashes them again.
Execution of the previous catalog exposes this aggregate work; it does not
prove a particular new cross-stage route. Retraining is unnecessary to remove
the duplicate preparation. A future iteration can select wider witnessed
completion chains only after establishing their own entry and lifetime proofs.

The existing typed Cell birth plan proves the source operation, input slots,
result destination, downstream constructor region and terminal boundary. Its
root sites contain no intervening mutable read, union or fallible suffix. Runtime
admission still requires a repaired parent epoch, available inputs, no unresolved
in-flight root and the existing bounded-work budget. Entry, completed history
and source Run boundaries remain authoritative; no new cross-Run switch is
inferred from an occupied hash bucket.

The earlier "source execution frames" metric counts entry into the generic
`Execution` continuation. It is not a count of physical graph Cells. This change
targets the repeated admission/boundary work; it does not claim to eliminate
those continuations or all temporary frames.

## Actual takeover

Root admission now consumes its already canonical key and hash in the ordinary
exact lookup. The same candidate order, hidden-row behavior and lookup observers
remain in use. On a hit it fills the current Cell's result slot and demanded
actual witness, advances that Cell's operation position and continues admission.
There is no second boundary invocation, parameter reconstruction or rehash.

On an exact miss, the existing compiled worker cone may run even when the hash
bucket contained unrelated candidates. Workers still choose exact peer results
before using them in descendants. Hash equality does not prove a hit. The
pending-input and in-flight-root guards still apply; this does not waive a value
dependency or permit a later source effect to become visible early.

A previously prepared constructor witness retains its existing stronger path.
It bypasses root probing and is validated at the original source operation.
History transfers, static aliases and shared effects also keep their existing
paths. No new instance field, key cache, binding copy or consumer list is added.
The existing instance frontier, rather than a diagnostic counter, decides
whether execution has advanced. The optional RHS projection observer records
the actual returned witness, including when no later consumer demands it;
this is a diagnostic archive, not additional runtime history ownership.

## Costs and metric interpretation

`root_existing_reuses` counts completed constructor operations, not newly
committed rows. `root_existing_key_fields` counts the admission fields consumed
by those hits; these replace a second read of the same source arguments.
`root_collision_misses` counts occupied buckets whose exact lookup proved
absence. They are included in `root_bucket_fallbacks`, which now means fallback
from the bucket filter to exact comparison, not necessarily to ordinary RHS.
All actual root exact lookups still enter `key_lookup_calls`.

The result is still computed on the admission owner. Removing its repeated
boundary does not make that exact lookup parallel or remove its cost. Worker
operations, queue/event capacities, field reads and source boundaries are
recorded alongside the new counters. Each aggregate birth counter structure
adds three `u64` counters (24 bytes); Cell instances gain no storage.

The same logical constructor still executes once. Do not count both the new
reuse counter and the removed ordinary boundary as two saved constructors.

## Frozen workload result

| Actual work, control → candidate | sum-bits | Raytrace |
| --- | ---: | ---: |
| Counted admission/preparation parameter fields | 5,029 → 4,132 | 689,295 → 605,646 |
| Root hash-bucket probes | 2,029 → 1,356 | 288,073 → 217,070 |
| Separate root conflict probes | 198 → 451 | 33,572 → 61,239 |
| Ordinary constructor boundaries | 5,617 → 5,362 | 1,058,888 → 1,045,028 |
| Direct existing-root completions | 0 → 255 | 0 → 13,936 |
| Admission fields reused by those completions | 0 → 602 | 0 → 26,606 |
| Ordinary key lookups | 12,910 → 12,910 | 3,825,417 → 3,825,444 |
| RHS dispatch regions | 135 → 135 | 6,604 → 6,600 |
| Source `Execution` entries | 5,195 → 5,195 | 1,024,593 → 1,024,678 |
| Cumulative completion-event capacity bytes | 1,014,288 → 1,034,328 | 191,072,424 → 192,716,648 |

Counted admission/preparation reads fall 17.8% / 12.1%; this counter does not
cover every Graph argument read. Reused fields are the key already in hand,
not an additional reduction to add blindly to that subtotal. The ordinary
lookup count does not materially improve. Separate conflict probes increase
because prepared witnesses no longer visit the root admission filter. Event
capacity increases about 2.0% / 0.9%; these are cumulative capacities, not peaks.
Both frozen runs have zero `root_collision_misses` (the adversarial unit test
exercises that case). Completion-order-dependent grouping remains present.

This result removes duplicate preparation and thousands of generic boundary
calls. It does not demonstrate recovery from the previous throughput regression,
lower total allocation, or more CPU utilization. In particular, it did not
remove the extra `Execution` entries that motivated the investigation. Remaining
prepared-witness conflict work and generic instance setup are separate costs.

## Validation and reproduction

202 runtime tests and 91 integration tests pass, plus forced-collision checks
and four root tests with the optional storage/projection observer enabled.
All-features, sparse-only and legacy compile; README compile/run/one-repeat
bench smoke checks pass. The fresh sum-bits / Raytrace exports, all 1,428 /
16,883 ordered Run summaries, logical effects, live reverse occupancy and
existing iterative evidence match `552db678`. Native sum acceptance is `pass`
with the same fresh CPU export hash.

The unit fixture checks actual foreign witnesses, one exact lookup, hidden
results without reactivation, unresolved in-flight roots and pending union.
An adversarial unrelated hash candidate must yield a fresh worker result,
never a false reuse. Integration tests retain exact per-Run graph snapshots,
binding order, duplicate roots, late unions, deletion/recreation, cross-rule
queues and source-error prefixes.

Full frozen-workload checks compare final exports, every ordered Run summary,
logical effects, live reverse edges and prior iterative evidence. Native
sum-bits acceptance uses the reviewed choice validator, with its CPU export
hash required to match the fresh run. Raytrace remains differential validation,
not an extension of the native semantic contract.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-root-continuation/run.py out/cell-bake-merge FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-root-continuation/check.py out/cell-bake-merge FRESH_OUTPUT RESULTS.json
```

`results.json` retains successful validation and README smoke commands.
Generated binaries, raw exports and logs stay under ignored local output.
Saved exports may be losslessly compressed; the checker hashes decompressed
content. Neither the smoke bench nor the single work run establishes a speedup.
