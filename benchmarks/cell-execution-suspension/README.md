# Suspending the graph context of a Cell execution

Scope: standalone Cell CPU; control source `b2fb26f9`, frozen runtime `9345194d`.
This is part of [the complete refactor](../../docs/CELL_EXECUTION_REFACTOR.md),
not an independently scheduled multi-frame executor or a throughput claim.

The preceding complete sum-bits/Raytrace executions have zero remaining scalar
suffix dispatches. Adding another queue cannot make those operations parallel
again. Extending worker scope requires an owner that can release the current
graph context without losing its completed effects or treating old captured
inputs as newly canonical. `active_rhs`, writer origin, input certificate and
composition Entry previously remained attached to the graph across a worker
suffix. This change detaches those together on the existing dispatch path.

The authoritative Cell still owns the slots and `completed_prefix`. Bake's
typed scalar segment decides which instructions can run without graph reads;
the next shared instruction remains at its original source position. Suspended
state contains the private frame or a retained public identity, writer hint,
source Run epoch, captured-input union generation and the original Entry.
No bindings, effect log, per-consumer dependency list or result array are copied.
The ordinary RHS continuation header does not grow.

* A still-private frame moves with its original slot allocation. A projected
  parent is retained using existing lifecycle accounting until resumption.
* A frame referenced by a function origin or another Cell must stay addressable.
  Suspension promotes it into the ordinary Cell arena when needed, and retains
  it against deletion/garbage collection. This promotion is a real added cost;
  the former inline-writer optimization may no longer apply to that frame.
* A previously public frame stays in the graph. Workers borrow it exclusively;
  this does not authorize concurrent graph mutation.
* Resumption restores only the execution's own input certificate. A union while
  parked invalidates that certificate even if another batch was freshly sealed.
  Source RHS suspension cannot cross the original Run epoch.
* Ownership Entry anchors now move from the existing collected array rather
  than being copied into another persistent composition array. Entry switching
  does not supply new matching evidence or change composition selection.

Existing source-effect ordering, failure/Hide stopping positions, actual foreign
results, residual enumeration, completion and Entry publication remain in force.
The current driver still waits for each dispatched suffix. The private frame
can now survive an intervening execution in isolation tests; a scheduler still
needs to choose useful independent work and preserve the source commit frontier.
Ordinary history unification and useful worker coverage also remain unfinished.

## Validation and costs

The native-checked `boundary_scalar_result_resumes_with_private_constructor_and_writer_owners`
integration test exercises three actual dispatch paths: no published prefix,
a constructor prefix and a functional-write prefix. Every source Run state,
binding audit and final export matches the disabled executor with two and four
workers, with the ownership backend both disabled and enabled. `bool-<` is
currently a primitive boundary; its actual result enables the following `and`
worker segment. This is a conservative compiler cut, not an inherently shared
read. The
reported work distinguishes private/public suspensions, promotions and balanced
lifecycle holds/releases. This small fixture is not a performance workload or
an extension of the sum-bits extraction-choice contract.

Unit checks additionally keep two private owners alive, switch their different
Entries, invalidate their old Eq certificates, replace a published writer while
parked, and delete a private frame's projected parent before garbage collection.
They check the original slot allocation and exact completed position. A separate
runtime unit test covers a real mutable RHS read and the source-current value;
the native frontend prohibits ordinary function lookups in rule RHS, so the
first proposed native fixture was rejected and replaced with the legal primitive
boundary above. This restriction also limits useful suffix opportunities in
ordinary source workloads. The
existing worker-failure tests check that earlier effects survive and are not
replayed. An initial test-fixture failure lacked the repair-port compiler plan;
the fixture was completed without changing runtime assertions.

`owned-rhs-context/v1` reports suspension header bytes. Graph stats count actual
suspend/resume, promotion, lifecycle hold/release and invalidated certificates.
Iterative Bake charges suspend/resume and both lifetime operations. Promotion is
already charged in `cells_created`; private/public splits and invalidation
outcomes do not get extra work credit. Missing current cost fields fail parsing.

[check.py](check.py) compares full saved executions with the immediate control:
exact final exports and all ordered Run summaries, original graph/query/RHS/
publication work, and every new suspension counter. The sum-bits native choice
contract is checked separately from saved native inputs. No timing campaign is
added in this change; the five-change timing cadence remains in effect.

[results.json](results.json) records exact final states and all 1,428 / 16,883
ordered sum-bits / Raytrace Run summaries, with unchanged checked logical work.
Native sum-bits acceptance is `pass`, exit 0. Both workloads retain zero suffix
dispatches and therefore incur zero new suspensions or lifetime operations.
This is regression evidence, not demonstrated suspension coverage or a speedup
on those workloads. Their ownership backend is disabled in this control;
the targeted fixture separately covers that backend enabled.

The 12 targeted configurations each perform 64 successful worker operations and
64 balanced suspend/resume pairs. Costs per configuration are:

| Existing prefix | Private / public owners | New public promotions | Lifetime holds / releases |
|---|---:|---:|---:|
| No published result | 64 / 0 | 0 | 0 / 0 |
| Constructor | 0 / 64 | 0 | 64 / 64 |
| Functional write | 0 / 64 | 64 | 64 / 64 |

The suspension header is 264 bytes on this build, held only during actual
dispatch; the ordinary execution header remains 440 bytes. No separate heap
allocation is added for that header. These sizes and operation counts exclude
allocator overhead and do not constitute a complete allocation/peak-memory
profile; lifecycle-map and public-arena growth remain possible added costs.

124 runtime unit tests, 15 compiler unit tests and 117 selected integration tests
pass. Compiler/integration tests force hash and Sieve collisions. All-feature
and no-default-feature checks pass. The README Cargo compile/run/bench commands
also pass, with bench repeat 1 strictly as a minimal-branch smoke check.
Logs and frozen executables are retained
under ignored `out/cell-execution-suspension`, including the rejected fixtures.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals --test joint_results --test entry_publications --test scoped_completion -- --show-output
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-suspension/check.py ROOT out/cell-execution-outputs RESULTS.json
```
