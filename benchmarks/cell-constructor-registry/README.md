# Terminal constructor registration shares the existing worker region

This is the actual standalone Cell CPU, not native egglog. The control runtime
is `7b13f259`; programs, catalogs, release features and flags are unchanged.
This is implementation one after the five-change timing checkpoint `2166a3fb`.
Work counts below do not establish a speedup or satisfy the two-workload timing
gate, which still fails at that checkpoint.

## Opportunity and proof

The preceding Raytrace execution built 153,385 local constructor rows. Workers
already resolved their actual values and aliases, but source acceptance still
called `activate_fields` for every row: Cell fact installation, constructor hash
index, table membership, subscriptions and change notifications. The existing
Unit tail registration entered a worker region 1,070 times. Those actual
executions expose a place to transfer constructor ownership without adding a
second pool invocation.

Admission reuses the compiled terminal Cell boundary: a complete ready prefix,
no intervening mutable read, union, fallible suffix or Function producer outside
the compiled Unit tail. The ordinary pending-union/dirty fence remains. Each constructor has
a public original Cell and the existing typed Eq-column footprint; its canonical
fields and actual result were proved by local/peer construction. No stable-port,
digest, ownership or local-union backend is silently taken over. Unknown fields
or unsupported regions retain `activate_fields`.

Across Runs, the same compiled Cell/Entry definitions consume these actual
results at the original publication boundary. This change does not create new
Bake candidates or a second fact/binding graph. Duplicate computation and exact
peer-result selection still happen before registration; hashes/Bloom filters
do not establish equality.

## Connected ownership

The existing Unit owner invocation now also borrows disjoint constructor state:

- One worker owns actual Cell facts, the constructor hash directory, membership
  and prepared change entries.
- Another owns the existing reverse incidences and dependency map. Source and
  worker use the same typed subscription kernel.
- Unit classification and index installation continue on their existing table
  owners in the same pool region.

These paths share the original row allocations. They introduce neither a new
global lock nor a per-producer consumer list. The source's covered per-row
activation loop is gone. It reattaches the original slots, then opens one small
publication fragment per table used by that Cell, advances logical counts and
continues the existing Unit effects and Cell completion.

Prepared changes do not activate a table or increment source mutation counts.
The source activates constructor and Function tables in their original order,
so the next Run cannot observe a later Cell early. On an error, the original
completed-prefix positions identify the unadopted suffix. Its facts, hash
entries, memberships, subscriptions and unannounced changes are removed; earlier
accepted effects remain. This is not a general rollback guarantee for panics.

Publication fragments stay in the existing registration owner. They are not
carried in every worker completion, and the `Piece`/completion layout is unchanged.
Small or single-Unit-table regions are rejected before this metadata is built.
The admission threshold and existing registration join remain; this does not
claim end-to-end asynchronous graph mutation or saturated workers.

## Work and costs

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Local constructor rows | 153,385 | 153,385 |
| Source row installations | 153,385 | 88,593 |
| Worker row installations and subscriptions | 0 | 64,792 |
| Source constructor table-fragment visits | 0 | 64,792 |
| Constructor owner regions | 0 | 974 |
| Existing Unit registration pool calls | 1,070 | 1,044 |
| New registration metadata, cumulative bytes | 0 | 3,966,400 |
| RHS event/task capacity, cumulative bytes | 139,843,984 | 140,147,904 |
| Global key lookups | 4,027,756 | 4,027,756 |

The worker owns 42.24% of this local constructor path's registrations. This is
not 42.24% of all RHS work. In this execution each covered row still contributes
one source table fragment: fragment grouping itself saves no visit here. What
leaves the source is the actual fact/index/subscription installation. The new
source eligibility checks and table-fragment bookkeeping remain work.

See [results.json](results.json) for the final frozen observations, state hashes,
Run hashes, logical effects and new costs. Counts of migrated registrations are
not elapsed-time savings. Ready-prefix sizes and therefore owner pool-call
counts can change with completion arrival; each eligible prefix still has only
its original single registration invocation. Cumulative capacities are neither
peak memory nor complete allocator traffic. Event capacity varies with ready
prefixes even though the completion record layout is unchanged.

The broader constructor and repair paths remain. Sum-bits has no eligible Unit
registration region, so this takeover does not establish a remedy for its
four-worker regression. Registration metadata, source table-fragment acceptance,
the shared-map work on each owner, and the existing join are all still costs.

## Validation and reproduction

165 runtime tests and 87 integration tests pass, including deletion, later
union, foreign result aliases, source errors, Unit winner selection and full
small-fixture Run snapshots. Two new unit tests cover partial adoption followed
by invalidation/repair, original row-allocation identity, interleaved table
activation and selective-publication counts. The 37 execution/owner integration
tests and those two unit tests also pass with forced hash/Bloom collisions.
All-feature, sparse-only and legacy checks pass.

Both frozen final exports, all 1,428 / 16,883 ordered Run summaries, logical
effects, subscription work, global query counts, Sieve work and iterative Bake
evidence match the control. Run summaries are not full intermediate snapshots;
the integration fixtures cover those boundaries. Native sum-bits acceptance is
`pass`, with its saved CPU export hash linked to this execution. Raytrace is
exact differential validation, not an extended native semantic proof.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

The binary/program paths and hashes are in
`out/cell-constructor-registry/manifest.json`. The first work-only observation
and source patch remain in its `initial/` directory; the final layout removes
the extra completion payload found there. No timing campaign was run or replaced.
Use fresh directories for the README smoke commands:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-constructor-registry/semantic-acceptance.json
python3 benchmarks/cell-constructor-registry/check.py out/cell-event-payload out/cell-constructor-registry benchmarks/cell-constructor-registry/results.json
cargo cell-compile --case sum-bits --output out/cell-constructor-registry/readme-program
cargo cell-run --program out/cell-constructor-registry/readme-program/program.json --output out/cell-constructor-registry/readme-run
cargo cell-bench --program out/cell-constructor-registry/readme-program/program.json --repeat 1
```
