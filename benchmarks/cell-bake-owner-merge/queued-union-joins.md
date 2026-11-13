# Queued unions are not the compression bottleneck by themselves

This is a rejected runtime trial, retained as a reproducible patch. Production
admission is restored to `6dcbd782`; the patch is **not applied**. The selected
configuration remains the 1,405,919-byte Graph from pooled suffix storage.

## Trial and proof coverage

The union queue stores stable `(u64, u64)` Eq pairs. Its later commit resolves
current native-port and boundary wiring. The trial allowed matched-source
takeover before that batch commits, while retaining pending-fact, pending-signal,
frozen-reader and dirty-fact guards. It neither consumed the queue nor used its
future equalities as present evidence. Actual matched alias checks and original
union publication order remained in place.

The short integration fixture adds a nontrivial F/G union to the first H
application so later applications actually join while it is queued. A dedicated
admission counter makes this test nonvacuous. Stable ports, later union, deletion,
snapshots and binding audits agree with control across existing field/worker
configurations. Job 337 passes this test; job 338 passes all 67 ownership tests.

One frozen candidate then measures all three saved join catalogs. All final
exports and Run work sequences agree with their controls. Full-workload per-Run
graph/effect audits were **not** rerun: the trial failed its compression gate and
is not adopted on these narrower checks. No timing improvement is claimed.

| Patterns | Joins before → after | Joins with queued unions | Graph before → after |
| --- | ---: | ---: | ---: |
| 32 | 48 → 100 | 74 | 1,403,727 → 1,408,159 |
| 128 | 87 → 163 | 118 | 1,403,855 → 1,406,319 |
| 593 | 135 → 222 | 144 | 1,399,999 → 1,403,671 |

Admission increases and the early-exit count becomes zero, but **every catalog
uses more Graph memory**. Resident Program is unchanged by the runtime patch.
More successful joins are not a useful compression metric on their own.

## The retained-state problem

For the largest catalog, final components fall from 1,459 to 1,409, while their
source-frame descriptors grow from 2,296 to 2,359, signal slots from 8,179 to
8,300, and bound signals from 6,783 to 6,878. Live boundary entries increase from
4,721 to 4,816. This is not merely a spare-capacity regression.

The saved source-storage census identifies 119 component source IDs absent from
the retained Cell source records before the change, and 182 afterward. Static
signal instruction lists referring only to such absent sources cover 303 slots
(243 bound) before, and 471 (385 bound) afterward. The already selected no-dual
catalog also has 107 absent-source frame descriptors, so this is not unique to
the rejected expansion.

`composition_retire_fact` currently decrements one component-wide live-fact
count. It removes the frame directory and signal bindings only when the entire
component dies. Larger components therefore extend the lifetime of descriptors
and bindings associated with former sources. This explains why extra joins can
increase retained state despite sharing one more input at each admission.

Those descriptors are not automatically garbage: an Eq value encodes its source
ID, and `native_port` resolves it through that directory. A surviving component
may also use the source's shared symbol. Dropping a frame without replacing its
native route can lose future union propagation. Even signals with no retained
source instructions require checking external readers and retained query/
continuation obligations. The census is an opportunity bound, not a deletion
certificate or an additional memory-saving claim.

The structural follow-up is to specialize a composed Cell's remaining live
sources at retirement, preserving the bindings and native/boundary routes that
still serve them. Bake must also carry forward valid suffix transitions; shrinking
a shape must not silently discard future completion. Merely removing a global
guard, or growing the composition directory, does not solve that obligation.

## Reproduce

Apply `queued-union-join-trial.patch` to `6dcbd782` in an isolated checkout.
Under the shared compute queue, build the compiler test and memory example with
`iterative-bake,sparse-cells,storage-metrics`, then use each unchanged
`out/cell-direct-joins/budget{32,128,4096}/program.json` with:

```sh
runtime_storage_peak PROGRAM MEMORY inherited-owners --port-domains-only --cell-fields --state-output STATE
```

Frozen binaries and reports remain under `out/cell-queued-union-joins`.
`queued-union-joins.json` records identities, full admission counters, both source
censuses and the proof limits. The 30% Graph target and saturated RHS completion
goal remain unfinished.
