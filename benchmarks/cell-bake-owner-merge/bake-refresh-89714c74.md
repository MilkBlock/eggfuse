# Refresh the branch containing d0d8ee33

The requested source is `codex/cell-parallel-admission`, pinned at `89714c74`.
It contains `d0d8ee33` (`bound alias savings against retained runtime state`).
The earlier merge `437d1e7c` already included its history through `d911ff49`;
this refresh merges all five subsequent commits, not selected patches from the
similarly named structural-compression branch. The destination is
`codex/cell-result-routing` in `/private/tmp/eggfuse-cursor-writes`.

## What is adopted

- Derive residual domains and slot assignments from checked Cell coordinates.
  Legacy explicit annotations remain checked; forged annotations still fail.
  Local reads share immutable producer operands rather than copying them per
  consumer. Ordinary query atoms and residual enumeration remain authoritative.
- Pool newly completed suffix storage even when an old prefix shares its owner
  with unrelated sources. Prefix slots stay in place; logical source IDs,
  restoration slices and port routing are unchanged. This optional storage
  path must not be credited as a speedup of the ordinary parallel runtime.
- Install the audited direct-source and matched-source Bake experiment tools,
  their retained-memory evidence, and separate pending-work reason counters.

The incoming queued-union admission experiment is already rejected. Its patch
is retained as research evidence and is **not applied** to the runtime. More
admissions increased retained Graph storage on every tested catalog. The merge
does not remove union, frozen-read, pending-signal or dirty-fact guards.

## Implication for the next Cell optimization

The actual direct-source trace contains thousands of connected immutable matches
despite shallow Cursor history. It is useful input for selecting combinations,
but an observed match does not prove source retirement or future equality.
Simply adding patterns is expensive: the largest matched-source catalog saves
only 5,920 Graph bytes while adding 9,387,054 Program bytes in the incoming study.
Those are the peer's storage measurements, not new timing results here.

The more useful next target is the lifetime of a partially retired composed
Cell. Current retirement decrements a component-wide count; surviving sources
can keep retired-source descriptors and bound signals alive. Bake should derive
the remaining live source layout and its valid suffix transitions. Native Eq
routes, shared symbols, escaped boundary readers, live result witnesses, source
generations and later Run visibility must remain resolvable. Removing a source
descriptor without such a route is not a valid takeover. No new reverse map,
runtime fact graph, or duplicate bindings should be introduced.

This refresh does not implement that retirement specialization. It supplies the
existing shared-layout mechanisms and measured counterexample needed to design
it. Acceptance below checks the actual four-worker Cell runtime separately from
the optional compression experiments.

## Merge checks

Compute jobs 343/344 pass 70 ownership, 19 compiler and 13 witness integration
tests, 215 runtime library tests, the no-default runtime compile, and all four
offline route-analyzer tests. The ownership suite includes the storage-metrics
configuration needed to exercise shared prefix/suffix storage.
Job 350 also passes both Bake tools' audited-run/exact-catalog rejection tests.

Job 346 freezes merge `2ef47a82` and reuses the hash-checked `437d1e7c` control.
Sum-bits and Raytrace final states, Run summaries and logical effects agree;
the reviewed native sum-bits entrypoint returns `pass`. The unchanged older
learned catalog also agrees at its differential final-state/Run/effect contract.
Recorded work dictionaries are identical for all three inputs.

Job 348 runs both the original source and its 408-recipe witness catalog on the
fresh four-worker binary. All 1,428 Run snapshots and ordered binding sequences
agree. Their hashes also equal the saved pre-refresh binary's corresponding
audits, not merely each other. No semantic exclusions are changed.

## Sequential timing

Job 347 uses five measured samples and one warmup per workload/lane, completing
all control workloads before any candidate. All 56 boundary guards are clear.

| Workload | `437d1e7c` | `2ef47a82` | Change |
| --- | ---: | ---: | ---: |
| sum-bits inference | 21.225 ms | 21.382 ms | +0.74% |
| Raytrace inference | 4.736604 s | 4.724004 s | -0.27% |
| sum-bits load | 65.565 ms | 66.058 ms | +0.75% |
| Raytrace load | 348.177 ms | 347.970 ms | -0.06% |

There is no large regression in this short trial and no demonstrated speedup.
This does not resolve the earlier `364d9a91`→`437d1e7c` slowdown. Inputs remain
the same frozen artifacts, including their legacy route annotations; the new
wire-emission compaction is covered by compiler tests and incoming memory
experiments, not by an invented reduction in these timing inputs. The optional
owner transfer API is not enabled by this ordinary runtime configuration.

The complete timing summary, binary/input evidence, work agreement and audit
hashes are recorded in `bake-refresh-89714c74.json`. Large artifacts are stored
on the external disk, reached through `out/cell-bake-routing-refresh` in worktree
3063; the shared build cache remains in its existing external target directory.
