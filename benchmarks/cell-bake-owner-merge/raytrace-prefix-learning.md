# Learn Cell composition from the actual four-worker Raytrace

The ordinary Raytrace artifact has no ownership fragments or witness catalog.
Its current execution creates 2,151,665 signal bindings and attempts 1,840,693
boundary registrations, with 4,332,972 key lookups. The earlier stack sample
also places ordered boundary-set insertion in the coordinator's activation
path. This experiment asks whether observed, typed Cell composition can remove
enough of that work to justify its dispatch and setup costs.

## Bounded learning with explicit proof coverage

`worker_prefix_catalog_trace` keeps the entire input program unchanged. It runs
a complete control prefix, then the complete observed prefix, using the same
four-worker setup order as the ordinary CLI configuration. For each of the 128
Runs it compares the full graph digest, ordered matched bindings and source Run
summary. Large graph exports are released at each boundary; they are not
retained in another runtime history. This is diagnostic execution, not timing.

The result explicitly says `full_execution_claimed: false`. Only genuinely
compared saved Run checks authorize its `all_saved_run_checks_equal` field.
Catalog identity, nonempty exact prefix length and typed source wiring remain
required by the existing selectors. Two tests cover an unchanged source with
an unexecuted, observable suffix; incorrect graph/binding/epoch checks; wrong
catalog identity/length; and premature program completion (job 372).

Job 373 audits the original prefix: 35,903 actual applications, 17,446 proposed
composition paths and 2,119 witness recipes. All four workers execute queries.
Job 374 selects 32 composition paths with the existing ranking, and verifies
typed wiring and preservation of every seed transition. They activate 18 rules,
which account for 28,860 of the prefix's 35,903 applications. Proposals and
alternative anchors overlap; their support is not additive saved work.

Job 376 freezes optimized audit tools. Job 378 checks the selected catalog's
128-Run prefix against its own passive observer and against the original
prefix. It then executes both complete Programs on the **same** frozen
`451058f3` runtime, without the audit build's instrumentation. Both final graph
exports, all 16,883 source Run summaries and logical effect counts agree with
the pre-existing Raytrace reference. No source definitions, queries, effects,
Run ordering or semantic exclusions change.

This is a differential Raytrace contract, not a native correctness claim or an
audit of every full-run intermediate graph. The new checker binds source and
catalog file identities to the saved prefix evidence before full execution.

## Work actually removed and added

| Full Raytrace work | No catalog | 32 paths |
| --- | ---: | ---: |
| Signal bindings created | 2,151,665 | 2,139,542 |
| Boundary registration attempts | 1,840,693 | 1,827,856 |
| Ownership components created | 587,058 | 575,863 |
| Key lookups | 4,332,972 | 4,332,972 |
| Compiled composition hits | 0 | 11,195 |
| Transition probes | 0 | 143,571 |
| Unbaked fallbacks | 0 | 132,376 |
| Ownership Entry reads | 0 | 273,448 |
| Captured actual RHS result writes | 0 | 88,235 |

The existing composition mechanism now actually takes over 11,195 instances
on Raytrace, including 10,841 cross-Run joins. The static wiring removes the
corresponding duplicate binding/registration work; no new per-producer consumer
list is installed. However, the 12,123 fewer bindings and 12,837 fewer boundary
registrations come with many unsuccessful attempts. This does not remove RHS
queries or increase the worker mutation scope. Native Eq addressing, source
lifetimes, actual foreign results, residual enumeration and visibility remain
live obligations.

## Whole-lane timing and decision

Job 379 reserves one timing window: one warmup plus three control samples, then
one warmup plus three candidate samples. All 20 process-boundary guards pass.

| Median | No catalog | 32 paths | Change |
| --- | ---: | ---: | ---: |
| Inference | 4.740614 s | 4.693971 s | -0.98% |
| Program load | 366.808 ms | 488.381 ms | +33.14% |
| Whole process | 7.183696 s | 7.268121 s | +1.18% |

The inference change is small and this grouped short trial does not establish
a stable speedup. Whole-process latency regresses. The catalog remains an
experimental artifact; it is not installed as the default input.

The more useful outcome is the missing selection cost. Ranking each edge's
observed sharing against its static instruction count does not charge the
other entries and result captures activated by selecting its rule. The next
iteration should first cover more of the already active rules, using this
catalog's own new trace (13,002 proposals), and account for any newly activated
rule/result-capture path once at the rule level. A longer Cell or more hits is
insufficient: complete-run binding, registration, Entry, query and load costs
must all be retained in the comparison. Frequency remains a selection hint;
typed checks and runtime lifetime/visibility checks authorize reuse.

## Reproduction

All commands run through the machine-wide queue. Build the three examples with
`iterative-bake,cell-absorption,view-ports,parallel-publication`, then freeze them
before another worktree builds into the shared target. Artifacts are on the
external disk under worktree 3063's
`out/cell-bake-routing-refresh/raytrace-prefix-learning`.

```sh
worker_prefix_catalog_trace ORIGINAL_PROGRAM 128 original-prefix128
extend_observed_owners ORIGINAL_PROGRAM original-prefix128/trace.json 32 round1
worker_prefix_catalog_trace round1/program.json 128 round1-prefix128
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py check ACCEPTED_RUNTIME \
  original-prefix128 round1/program.json round1-prefix128 round1-full
python3 benchmarks/cell-bake-owner-merge/ray_catalog_check.py time \
  round1-full round1-timing --repeats 3
```

The final command requires a timing lease; all preceding build/execute/Bake
commands require compute leases. Exact inputs, binaries, work deltas and raw
timing identities are recorded in `raytrace-prefix-learning.json`.
