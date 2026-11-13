# Integrate original-workload iterative Bake into worker continuation

Merge the complete committed `codex/cell-parallel-admission` lineage through
`d911ff49`, which contains the user-specified `d0d8ee33`, into
`codex/cell-result-routing` after `2fcb9c56`. Seven non-merge commits since the
previous integration bring original-workload observation/selection, optional
diagnostic apply receipts, admitted context-plan storage, and physical pooling
of newly completed short compositions. This is a full branch integration, not
selected cherry-picks; the other worktree's uncommitted files are untouched.

No manual conflict resolution was needed. Worker chunk selection and the
actual-witness prefix layout are preserved. Job 315 passes 152 compiler
integration tests (including 70 ownership tests), two selector tests, 233
runtime tests, the no-default runtime compile, and 48 experiment-script tests.
The pooled-owner test performs union, deletion and regeneration after sharing
storage, rather than checking final size alone.

The incoming original-workload round-one/round-two programs have the same
`source_core` as the ordinary performance input. `multi_stage` metadata differs
and a checked ownership-fragment catalog is added; therefore their own Run and
worker execution checks are still required before crediting those compositions
to the ordinary performance lane. They are distinct from the previously timed
882-Run learned artifact. Incoming memory savings and sequential source audits
do not prove worker speed or saturated-RHS execution.

The next useful takeover is to feed that actual 1,428-Run composition evidence
into worker continuation and identify the retained query/result/publication work
inside admitted combinations. Source order, visibility, delta ownership,
mutable effects and returned-witness lifecycle remain authoritative. Do not add
the incoming component/storage savings to the 558 existing witness hits as if
they measured the same input or eliminated the same operations.

Post-merge frozen workload validation and timing will be recorded below. Prior
chunk results belong to `364d9a91`, not automatically to this merge.

## Post-merge validation and coverage

The merge is `437d1e7c`. Job 317 freezes it and checks ordinary sum-bits,
Raytrace and the existing 882-Run learned artifact against `364d9a91`. Exact
final states, Run summaries and logical effects agree; the native sum-bits
choice validator passes and binds to the fresh ordinary export. All previously
recorded ordinary preparation/ownership work is unchanged.

Job 319 then runs the ordinary original program plus the incoming round-one and
round-two composition artifacts with the same four-worker binary and flags,
adding `--audit-stages`. The harness checks identical `source_core` and rejects
changes outside the declared composition metadata. All **1,428 graph snapshots
and ordered binding sequences** match byte-for-byte for each lane, along with
Run summaries, logical effects and the native-accepted final state. Snapshots
are losslessly gzipped after hashing. This does not claim that physical writes
or performance are identical; no scoped table exclusions or new equivalence
rules are used. `original_worker_audit.py` reproduces these checks.

| Actual four-worker work | Original | Round one | Round two |
| --- | ---: | ---: | ---: |
| baked composition hits | 0 | 709 | 976 |
| signal bindings created | 8,909 | 8,108 | 7,835 |
| result-based composition joins | 0 | 49 | 86 |
| source prefix Entry reads | 0 | 1,263 | 1,336 |
| generic constructor queries | 14,653 | 14,653 | 14,653 |
| cumulative worker result-buffer capacity | 34,288 B | 37,968 B | 38,672 B |

This establishes real original-workload coverage of the prepared-result Entry
path, which was zero on the older ordinary/learned inputs. It also identifies
the remaining gap: these catalogs reduce binding maintenance but do not remove
constructor queries. They contain no active prepared-witness routes. The added
Entry reads and retained result slots are paid work and cannot be counted as
query savings or conflated with 976 avoided rule applications. Source prefix
constructor operations remain 2,478 in all three lanes.

## Merge timing remains a concern

Job 320 completes the entire pre-merge lane before the entire merged lane,
with 84 clear boundary guards. Medians from 5/3/7 measured samples:

| Workload | Pre-merge `364d9a91` | Merge `437d1e7c` | Change |
| --- | ---: | ---: | ---: |
| ordinary sum-bits | 22.619 ms | 21.684 ms | −4.13% |
| Raytrace | 4.744703 s | 5.146749 s | **+8.47%** |
| older learned sum-bits | 21.185 ms | 21.199 ms | +0.07% |

The Raytrace regression is unresolved. Identical recorded work does not prove
identical instruction cost, allocation behavior or scheduling. Candidate samples
range 4.820–5.291 s versus control 4.728–4.752 s; do not dismiss this as noise or
claim a stable speedup. Preserve the pinned `aef89181` performance baseline.
This timing does not measure the incoming round-one/two programs: their evidence
above is correctness and actual work, not speed. Full provenance and samples
are in `original-bake-integration.json`.

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/original_worker_audit.py REPO MERGE_ARTIFACTS ORIGINAL_COMPOSITION OUTPUT
eggfuse-job run --kind timing -- python3 benchmarks/cell-bake-owner-merge/prepared_timing.py MERGE_ARTIFACTS OLD_LEARNED_PROGRAM TIMING_OUTPUT --include-ordinary
```

Use Python 3.11+ for the audit's `hashlib.file_digest`. The next implementation
should consume the actual original-source composition evidence to compile
applicable witness/continuation code, then remove the repeated query or handoff
inside its proven coverage. More combinations alone did not discharge those
queries. The separate Raytrace regression needs attribution before promoting
this experimental branch as a performance configuration.

Reading the saved timing samples locates the increase across several phases,
without another timing run. Raytrace phase medians are search 1.698→1.772 s,
RHS 1.691→1.864 s, repair 0.437→0.491 s and query-index update 0.894→0.991 s.
The last candidate sample is much closer to control in every phase. Thus the
observed increase is not isolated to worker witness routing or one new wait;
these aggregates still do not distinguish instruction/layout costs from machine
scheduling. Phase samples are retained in the integration result for follow-up.
