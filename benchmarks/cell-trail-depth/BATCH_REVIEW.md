# Batch review before structural changes

Use `python3 benchmarks/cell-trail-depth/review.py HISTORY CATALOG PROGRAM OUTPUT_DIR`.
It writes every retained event, its full retained parent chain and witness, a
rule dictionary, and ALL path patterns of lengths 2–6. No new runtime execution
is needed. Coverage counts overlap and are not saved operations.

The saved sum-bits round-0 trace yields 141 patterns across 18 rules:
39 length-2, 44 length-3, 37 length-4, 20 length-5, and one length-6 pattern.
174 parent events fork; maximum fanout is nine. The frequent 143->137 suffix
occurs 196 times across 120 retained roots, covering 355 distinct events.
143->55->143->137 occurs 33 times across 33 retained roots. Different events
can share prefixes; frequency, independent roots and covered events differ.

Of 723 known parent edges, 457 span four Runs and 131 span three Runs. Some
span hundreds (maximum 776). Same ruleset must not be confused with adjacent
Runs. Retained ancestry is incomplete, the catalog has no composed joins, and
neither candidate losses nor actual Cursor depths are recorded.

## One coordinated optimization batch

1. Shared suffixes and forks: build reusable continuation states around actual
   high-coverage suffixes, retaining branch-specific output incidence. Compare
   final-state behavior, not just rule sequences. Avoid allocating copied
   prefix bindings for each fork.
2. Recurrent fragments: analyze 143/55/137/145 together, including staged
   LazyUnion effects. Derive the minimum result interface required by exits.
   Repeated rule IDs do not prove equal input ports; do not merge instances on
   that basis or erase source effects.
3. Lifetime compression: separate continuation identity from retained Results.
   Keep only demanded result slots across long Run gaps, with existing
   visibility/generation/deletion checks. Cursor depth is not retention cost.
4. Joint admission: compile this batch from the same trace, count overlapping
   avoided work once, and compare total storage, queries and publication work.
   One final performance comparison follows the batch's semantic checks.

Before that implementation, collect a trained-catalog trace ONCE with candidate
min/max/selected Cursor depth per equal-input group, before/after switch pc,
transition/reset reason, live retained-slot layout, completion validation result,
and completed rule/Run/output ancestry. This is the missing evidence for winner
bias and actual misses; the current round-0 archive cannot answer those questions.
Keep diagnostics opt-in and avoid duplicating runtime bindings.

The unfinished staged-route index change and its not-yet-compiling regression
remain uncommitted pending this analysis. They are not accepted results. No
speedup or runtime takeover is claimed by this review.

## Implemented batch: constructor Set and staged route transfer

The trace-wide review found that 117/141 paths contain Set (38 also read mutable
functions). The hot 143->137 rewrite lowers to constructor Set; the earlier
normalizer rejected it outright. Constructor Set now keeps the actual constructor
result distinct from its requested value until commit. If the local proof has
no existing result, it introduces an opaque actual result rather than assuming
runtime table absence. An ordered `constructor_unions` obligation records the
required equality separately from explicit source unions. Neither kind feeds
same-RHS constructor closure. Mutable table reads/updates remain unsupported.

The equivalent-route index now accepts stage-preserving keys and final-stage
canonical output ports as well as flat structures. Exact full keys, not hashes,
select candidates; the existing terminal result proof still authorizes the
specific execution route. It does not skip source union effects or Run boundaries.

One offline pass over all 141 saved path shapes gives:

| Representation | Previous Set rejection | Batch |
|---|---:|---:|
| Flat | 10 | 11 |
| Staged | 12 | 87 |
| Opaque | 119 | 43 |

This is 22 -> 98 supported paths, not an execution-hit rate. The prior column
applies the exact old unconditional Set rejection to the same typed paths; no
workload replay is used. All 98 supported full structures are distinct, so this
is expanded recognition, NOT measured final eclass compression. The corpus and
round-0 limitations above still apply. `batch-coverage.json` records the summary.

Reproduce using `cargo run --locked -p eggfuse-cell-compiler --features
iterative-bake,sparse-cells --example review_completion_paths -- PROGRAM
REVIEW_JSON OUTPUT`. The tool explicitly removes the archived derived completion
certificate, reseals and validates the source, then reruns current structural
analysis; it does not accept that old certificate as a current executable proof.
Older compiled completion certificates whose structures change need regeneration.

The actual runtime staged-route fixture transfers an admitted completion across
an intermediate nontrivial union: completed RHS 0 -> 1, constructor requests
10 -> 8, unions 2 -> 2, plan probes 4 -> 4. History allocations increase 1 -> 2
and history slots written 2 -> 4. Run graphs, ordered bindings/writes/resumes
remain identical. This establishes a real takeover, but not net acceleration.
It also points to the next compression target: shared stage/suffix structure and
retained result interfaces, without counting recognition coverage as speed.

The previously uncompiled route regression is now fixed and validated. Focused
negative coverage ensures pending constructor Set cannot make the requested
value the key of a later constructor, even when no existing result is known
locally. Full ripsat completion and query-receipt integration tests pass.

## Proven representation compression: shared stage definitions

The same 141-pattern batch contains 302 stage occurrences but only eight unique
canonical stage definitions. Actual completion contracts now store those eight
definitions once in `stage_structures`. Each staged structure keeps ordered
`stage_refs`, links, and boundary effects. This is ordinary indexed sharing,
not bit packing. The native registry retains the compact keys instead of
expanding each stage into every descriptor. References are scoped to that
registry's immutable contract table; reports refer to the authoritative table
rather than duplicating it. Exact canonical strings establish stage equality.

Measured by the production serializer and native registry, including all 43
opaque paths and all implementation maps:

| Payload | Before | After |
|---|---:|---:|
| Complete contracts | 203,547 B | 47,698 B |
| Structure table, including shared stage pool | 191,906 B | 36,072 B |
| Native registry descriptor key strings | 210,541 B | 50,590 B |
| Shared stage pool alone (already included in contracts) | — | 4,082 B |

Complete contracts shrink 76.6%, or 4.27x. Counting descriptor keys plus a
separate stage pool still saves 74.0%. These are serialized bytes and key-string
payload lengths, not allocator/RSS measurements. Stage payloads shrink from 302
copies to eight definitions; semantic eclasses stay at 141. All expanded
structures compare exactly, and all native unit-to-eclass assignments agree.
This is large compile-time representation compression, not an inference speedup
or a reduction in semantically distinct states. No runtime slot/union behavior
is changed by this factoring.

The analysis example now performs the exact round-trip and native partition
checks, with the measured summary saved in `shared-stage-compression.json`.
The batch analysis was validated against an isolated checkout of 2f4425b3 plus
these changes while another worker modified the runtime. Integration tests also
passed in the main worktree once its missing source file appeared. Corrupted
stage references and corrupted stage definitions are rejected. Old expanded
contracts are compared against exact expansion of the newly computed proofs;
this compatibility does not waive any structural check.
