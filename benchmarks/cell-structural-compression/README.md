# Runtime Cell state takeover

The target is at most 30% of the original 3,979,373-byte Graph-exclusive heap
(1,193,811 bytes), with unchanged source semantics. This work does not yet meet
that target. It is an actual standalone Cell runtime experiment, not a native
egglog runtime change or standalone simulated compression model.

**Latest complete retained cost:** the Graph uses 2,781,877 B and retained
Program/shared compiled data adds 1,021,315 B versus the fixed original.
The charged total is **3,803,192 B (95.57% of baseline)**, still far above the
1,193,811-byte target. This is a 4.43% net reduction, not 70% compression.
Before shared query/condition code, the total was 4,698,880 B (118.08%).
The Graph-only fraction remains 69.91% and must not be used as the whole-scheme
acceptance result.

The observer now drops the executor and Graph, then measures the final retained
Program teardown. Original/latest Program ownership is 115,462,476 / 116,483,791 B.
Only the positive increment is charged; the original common Program is excluded.
Shared allocations are released once, avoiding double-counting compiled layouts.
All measurements are taken after the recorded execution peaks. This does not
measure a Graph-exclusive within-Run peak; full process peaks are separate.

Reproduce complete retained accounting from the saved traces:

```sh
python3 benchmarks/cell-structural-compression/analyze.py out/cell-structural-compression/original-baseline.json out/cell-structural-compression/shared-code-trace.json benchmarks/cell-structural-compression/results.json out/cell-structural-compression/original-whole-storage.json out/cell-structural-compression/shared-code-peak.json
```

Both teardown runs use the same observer source; the original build omits only
`ownership_storage_trace`, which its API does not expose. `results.json` records
input hashes and verifies the matching Run count, final hash and Graph teardown.

The source program has 2,174 live ownership components, no baked ownership
transitions, and **zero retained Cell parent links**. Therefore parent chains
are not the dominant storage explanation for this workload. Actual ownership
training observes 646 candidates; the existing checked selector retains 259
transitions. Stage ordering and incomplete-domain fallback remain unchanged.

Implemented changes:

- Shared Cell wiring describes stable equality field locations. A fact keeps
  dynamic scalars and its component identity instead of repeating every PortRef.
  Fields reference the existing PortProgram and shape port map; there is no
  additional compiled field-layout representation.
- Completed instances delegate proven-equal bindings to existing component
  symbols. Typed original recipe aliases/native identities can reconstruct
  additional slots without a second runtime alias table. Required actual
  constructor results that differ from the implicit native identity remain stored.
- A complete parent projection can detach its old reference. Values not covered
  by a bound symbol are retained explicitly and charged. Before retiring a
  component, delegated source slots are restored for any surviving source frames.
  This path matters for lifecycle correctness but adds no savings in this source,
  whose parent-link count is already zero.
- The ownership frame directory stores live records densely with stable logical
  IDs. Retiring a record relocates at most one live record and adjusts its index;
  public Cell/Fact identities are never renamed or recycled.

Binding takeover and capacity reclamation are currently explicitly invoked by
`compact_retained_capacity` under `storage-metrics` at idle source Run boundaries.
They are not yet a default online completion policy. Stable field wiring and the
live frame directory are ordinary runtime representations. Per-boundary sweeps
are a diagnostic implementation, not a claimed fast scheduling strategy.

## Reproduction

Use the reviewed sum-bits artifact as `$PROGRAM`. Keep complete raw traces in
ignored output directories; the analysis can be repeated without another run.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- profile-cell-ownership --program "$PROGRAM" --output out/structural-profile
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- bake-cell-ownership --program "$PROGRAM" --profile out/structural-profile/profile.json --output out/structural-baked
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_comparison -- "$PROGRAM" out/structural-final.json out/structural-baked/program.json
python3 benchmarks/cell-structural-compression/analyze.py ORIGINAL_BASELINE_TRACE out/structural-final.json out/structural-summary.json
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,storage-metrics,iterative-bake --lib
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test stable_ports --test cell_ownership
```

The fixed original trace uses f20c0fce's runtime plus the example's per-Run
checksums (no representation changes). Preserve it; do not reset the baseline
as optimizations accumulate. The example compares an unbaked/uncompacted lane
and a baked/takeover lane on all 1,428 source Runs. Original baseline checksums
also guard against a bug shared by both new lanes. No performance measurement
is inferred from this debug allocator/export diagnostic.

Graph heap is measured by actual System allocation bytes released at teardown,
keeping both Programs alive and first dropping Executor caches. Any new shared field
layout storage is separately charged even though Program-retained allocations
are excluded from Graph-exclusive bytes. The final representation adds none;
its two shared handles per fact are included in Graph-owned record storage. The boundary capacity subtotal is not
complete heap and does not bound within-Run peak or temporary takeover storage.
The 30% target cannot be declared reached from that subtotal.

The next structural gap is still the complete source Cell/fact/index owner:
removing duplicate bindings does not yet replace every dominated source frame
with a combined Cell owner. Use `instance_trace` and `function_trace` to derive
future slot demands and explain remaining fact-free frame retention before
adding more Bake shapes or another runtime registry.

## Instance takeover checkpoint (b238d5d3)

This checkpoint adds zero field-layout storage.
Original Graph-exclusive heap: 3,979,373 B. Final: 3,080,829 B
(**77.42% remaining**, 22.58% reduction). The 30% target is **not met**.
The source has 1,863 delegated frames and 10,742 explicit slots (down from
14,755); physical source Cells and the remaining fact/index representation
still exist. There are 211 fact-free frames with 2,097 slots and 387 live
function-origin references. Dropping only these frames cannot reach the target.

Validation: all 1,428 original graph and ordered RHS/write/resume digests match;
135 runtime unit tests, 27 ownership integration tests and 14 stable-port tests
passed, including delegated slots across late unions and materialization before
component retirement. Runtime all-features compilation passed. The semantic
acceptance report uses the optimized final graph and the existing reviewed
native exports. Exact source Run equality is checked separately from legal
native extraction-choice equivalence. No timing or within-Run heap-peak claim.

Raw inputs/outputs are retained locally under `out/cell-structural-compression/`:
`original-baseline.json`, `profile.json`, `baked-program.json`, `final-trace.json`.
The original baseline is preserved across subsequent iterations. The sources,
summary and semantic proof are versioned; generated programs/raw traces are not.

## Program materialization and iteration peaks

The optional `bake-cell-ownership --materialize-markers false` flag omits the
redundant JSON copy of the typed ownership plan. Source Cell definitions and
checked ownership fragments still derive that plan. The default remains true
for existing artifact consumers. This does not remove logical `.egg` marker
facts, change the chosen fragments, or count as runtime instance compression.

`peak-results.json` compares single-lane allocator traces. These include Program,
Graph, Executor and a fixed 196,608-byte diagnostic buffer. They exclude parsing
high water and allocator padding; they are not RSS or Graph-exclusive peaks.

| Lane | Loaded program + process bytes | Execution/takeover peak bytes |
| --- | ---: | ---: |
| Fixed original f20c0fce | 113,734,400 | 124,720,514 |
| Current, materialized plan | 123,705,635 | 133,667,563 |
| Current, derived plan | 116,099,089 | 126,061,017 |

The current two lanes use the same runtime source and differ by optional JSON
materialization. Their initialization-relative peak growth is identical:
6,147,585 bytes. The materialization costs 7,606,546 bytes; even after removing
it the process peak remains 1,340,503 bytes above original. All 1,428 Runs are
sampled, including allocations between boundaries. Final graph digests match.
Cross-worktree shared Cargo caches reused an older runtime in an intermediate
comparison (detected by missing new census fields). Those results are discarded.
All three published lanes use independent worktree-local target directories.
The observer rejects takeover runs without the delegated-frame census.
No Graph-exclusive within-Run peak or 30% completion claim follows from these
numbers. The CLI plan equivalence and execution audit test passes as part of
all 28 ownership tests.

The isolated lean-program validation also reproduces the 3,080,829-byte
Graph-exclusive result, 1,863 delegated frames and 10,742 stored source slots.
All 1,428 graph and ordered RHS/write/resume hashes match the fixed original
trace. `choice_diagnosis.py` returns `pass` / exit 0 on that exported state.
The checkpoint used `lean-isolated-trace.json`; raw traces remain
under the ignored experiment output directory.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- bake-cell-ownership --program out/structural-baked/program.json --materialize-markers false --output out/structural-lean
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_peak -- out/structural-lean/program.json out/peak-lean.json takeover
python3 benchmarks/cell-structural-compression/compare_peaks.py ORIGINAL_PEAK MATERIALIZED_PEAK out/peak-lean.json out/peak-results.json
```

Use `CARGO_TARGET_DIR="$PWD/target"` in each worktree; do not share compiled
workspace crates between baseline and current lanes. The original lane uses
the same allocation observer built against f20c0fce,
with the original source artifact and `baseline` mode. The observer is not a
performance benchmark and serialization happens after peak observation.

Two rejected approaches guide the next structural change. Pruning slots from
future consumer `LocalRead` demands alone fails the surviving-source-frame
contract: component retirement can expose a still-observable source slot.
`retiring_shared_owner_restores_delegated_source_slots_before_gc` caught the
failure; that edit was reverted without weakening the test. Exact identical
binding-array sharing has only a 5,464-byte positive-group upper bound in the
saved final trace, before grouping overhead. Neither approach can replace
proper composed ownership of source instances, facts and indexes.

The saved allocator teardown also gives a useful impossibility bound for a
frame-only solution: `cells` releases 782,416 bytes and `ownership` releases
806,728 bytes. Even deleting both in their entirety, with zero replacement
cost, leaves 1,491,685 bytes, above the 1,193,811-byte goal. Real takeover must
therefore cover fact/field and index representation too. Next implementation
must preserve stable fact identity, source reads after component retirement,
visibility and worker read epochs while consolidating these owners. Merely
moving source bindings into an additional composition object cannot meet the
target. Field teardown charges shared allocations to their last owner; these
numbers are an optimistic bound, not achievable independent savings.

## One owner for functional rows and keys

Actual prior execution retained 416,448 bytes across `functions` and
`function_decoded`, plus 140,236 bytes in `function_keys`. Each ordinary
function owned key/value fields, another complete decoded row, and (for
multi-field keys) another key vector in its index. These are repeated runtime
values, not facts a larger Bake catalog can independently prove away. Removing
them also removes repeated field installation at source writes and repair.

Function now owns one immutable shared row. Queries borrow or share that row;
updates replace it so already returned rows retain their old version. Existing
union notifications invalidate canonicality; existing repair restores it.
Projected Unit rows retain their own owner and ordinary fallback. The separate
`function_decoded` directory is gone. Scalar-key indexes keep direct word
lookup; other indexes contain hashes and candidate IDs, then compare the exact
key against the authoritative row. They never own another key vector. Hashes
are candidate filters, not equivalence evidence. Removal identifies the exact
candidate, preserving other colliding keys.

Measured against 1ab0270b on the same baked sum-bits program:

| Allocation owner | Before | After |
| --- | ---: | ---: |
| Function records, rows and writers | 293,264 B | 303,664 B |
| Separate decoded function rows/directory | 123,184 B | 0 B |
| Function key indexes | 140,236 B | 70,716 B |
| **Complete Graph-exclusive heap** | **3,080,829 B** | **2,898,525 B** |

This removes 182,304 bytes (5.92% of the prior Graph heap). The fixed original
baseline is still 3,979,373 bytes: **72.84% remains**, so the 30% goal is not met.
No new compiled layouts are introduced. `function-row-results.json` records
this prior/current comparison; `results.json` follows the latest iteration. The independent
process observer's initialization-relative peak growth falls from 6,147,585 to
5,967,009 bytes; takeover extra peak stays 16,548 bytes. This net growth remains
a process metric, not a Graph-only peak. No speedup is claimed.

Validation: all 1,428 graph and ordered RHS/write/resume hashes match both the
fixed original and prior iteration. Native `choice_diagnosis.py` returns pass
/ exit 0. Runtime tests pass: 137 sparse and 84 default; all-feature compilation
passes. All 28 ownership and 14 stable-port integration tests pass. Four parallel
residual tests and the projected producer/consumer schedule test pass. New tests
force index hash collisions and retain old rows through mutation/checkpoint
round-trips.

The extended `view-ports,parallel-residuals` union-digest suite has two existing
failures: `staged_congruence_matches_native_at_each_source_boundary` and
`bake_markers_and_compact_unit_ports_survive_union_digests`. An independent
worktree at 1ab0270b reproduces the same 9 passes / 2 failures and byte-identical
left/right assertion bodies. They are binding-audit discrepancies after unions;
the preceding graph comparisons pass. Tests were not weakened. This documents
the unresolved mode-specific diagnostic, not a blanket semantic waiver.

Raw audited trace: `out/cell-structural-compression/function-row-trace.json`;
raw peak: `out/cell-structural-compression/peak-function-row.json`.
Use the earlier reproduction commands with those output paths, then:

```sh
python3 benchmarks/cell-structural-compression/compare_iterations.py PRIOR_AUDITED_TRACE CURRENT_AUDITED_TRACE PRIOR_PEAK CURRENT_PEAK out/iteration-results.json
```

The remaining source instance/fact and composed-owner allocations are unchanged.
Their consolidation still requires preserving stable identities, old source
reads, visibility, retained query versions and worker epochs. This iteration
removes an independently duplicated row/index owner; it does not claim complete
dominated-instance retirement.

## Rejected independent input-projection layout

The next experiment compiled Eq inputs proven by the matched Entry even when
the receiver's RHS does not use them. It introduced no runtime binding or
reverse edge. It computed projections after shape normalization, intersecting
all incoming routes by increasing frame depth so a normalized shape did not
inherit a fact true only on one history. Source slots assigned by an operation
were excluded. This was an opportunity census, not an enabled takeover.

On the actual same final state there are 956 candidate slots. Each current
`(usize, Value::Eq)` record occupies 24 bytes: even deleting all candidates
saves only 22,944 bytes of final slot payload. The shared layout costs 29,816
bytes, including its added Shape handles, unique vectors and Arc headers.
Thus this isolated design adds at least 6,872 bytes before any runtime handoff
cost. It is **rejected**, and the production representation is unchanged.
`input-slot-opportunity.json` records the bound. The reproducible experimental
source diff is `input-slot-experiment.patch`, applied only to a disposable
worktree at 5290c39c. Run the peak example with the same baked lean program to
regenerate `ownership_inventory`; the experiment does not claim that slots were
deleted. Do not apply this patch as an optimization to the current branch.

## Whole-owner trace for the next structural change

`runtime_storage_peak` now exports existing composition owners **after** peak
observation, together with canonical source Eq bindings. It adds no maintained
runtime history, indexes or cached fields. Its execution final hash matches the
audited 1,428-Run result; initialization-relative peak growth remains 5,967,009
bytes. The complete raw file is ignored at
`out/cell-structural-compression/ownership-storage-trace.json`.

`ownership-opportunity.json` records offline analysis:

- 1,392 live components: 892 single-frame, 199 two-frame, 126 three-frame,
  and 175 four-frame.
- 2,368 composition frame addresses include 191 whose physical source Cell
  is already gone. Do not count those frames as another full retained Cell.
- 6,785 bound symbols represent 6,053 distinct roots summed per component.
  Observed equality alone is not permission to merge static template symbols.
- Completed source frames retain 2,930 unmapped Eq slots whose roots are outside
  their component, and 1,463 unmapped slots whose roots occur inside it.
- 1,062 mapped slots have roots outside the component; another 186 have a root
  somewhere in the component, but not necessarily at their mapped symbol.
  Actual returned values cannot be replaced by an assumed native result.
- 451 mapped slots are in initial, non-completed source frames. Another 1,244
  stored Eq slots lie outside live composition frames altogether.

This rules out treating remaining storage as one long retained parent chain.
The next takeover must account for the other matched inputs and externally
retained source/writer state, not just append more receivers to the chosen
producer. It must preserve actual results, branch users, visibility, generations
and source reads after component retirement. These counts are planning evidence,
not saved bytes or new semantic proofs.

```sh
python3 benchmarks/cell-structural-compression/analyze_ownership.py out/cell-structural-compression/ownership-storage-trace.json out/cell-structural-compression/function-row-trace.json out/ownership-opportunity.json
```

## Delete the duplicate forward dependency owner

The actual prior run retained 1,150 forward dependency records, using 116,648
allocator bytes. These duplicated Eq operands already held by the authoritative
rows. In sparse runtime the `dependencies` directory is now removed entirely;
the non-sparse reference keeps its original implementation.

Registration and removal receive the existing old/new row versions at explicit
lifecycle boundaries. Mutable function updates compare their canonical Eq
footprints, including nested Sets. Old published rows remain immutable. Ordinary
fact operands can change only through union canonicalization: `union()` already
moves and coalesces their reverse incidences. Canonical repair therefore needs
no repeated forward-set replacement or reverse-edge update. Local ownership
handoff explicitly installs edges from an empty footprint; retirement and Cell
adoption remove edges from the actual old row. Query-version changes, source
Run order and the necessary reverse wake index remain intact.

This does not remove the 663 reverse buckets or their 2,885 live incidences;
both counts match the prior run. It removes the redundant forward owner and its
maintenance. No new persistent layout or binding table replaces it.

| Measure | Prior dc63f8f0 | Current |
| --- | ---: | ---: |
| Complete Graph-exclusive heap | 2,898,525 B | 2,781,877 B |
| Forward dependency records | 1,150 | 0 |
| Forward directory teardown bytes | 116,648 B | 0 B |
| In-place forward-set replacements | 436 | 0 |
| Subscription value visits | 8,408 | 7,829 |
| Reverse removal attempts | 859 | 751 |
| Repairs reusing the same row footprint | 0 | 449 |

The saved operation counters do not establish a speedup: the old typed shortcut
omitted 245 root reads and skipped 28 scalar fields, while the new transient
footprint path scans the old/new row operands directly. No timing claim is made.
The independent process observer's initialization-relative peak growth falls
from 5,967,009 to 5,862,977 bytes; takeover extra peak stays 16,548 bytes. Its
maintenance report and complete owner trace are emitted after observation.

The Graph-only comparison to 3,979,373 bytes has **69.91% remaining** (30.09% removed),
not 30% remaining. The target is still **not met**. The full heap falls by
116,648 bytes while the partial boundary array subtotal is unchanged, another
reason that subtotal cannot be used for acceptance. Instance and fact storage
are unchanged by this iteration.

All 1,428 original Run graph and ordered RHS/write/resume digests match, and
the specified native semantic acceptance returns pass / exit 0. Runtime tests:
138 sparse and 84 default pass; all-feature compilation passes. Integration:
28 ownership, 14 stable-port, 5 local-union and 4 parallel-residual tests pass.
The two previously documented view-ports union-digest failures remain the same,
with identical assertion bodies. The new exact reverse-index test covers Eq
result replacement, scalar updates, nested Set references, key/result unions,
merge retirement and deletion without a forward directory.

`row-footprints-results.json` includes the prior/current allocator and operation
comparison. Raw inputs are `row-footprints-trace.json`, `peak-row-footprints.json`,
`footprints-control-metrics.json` and `footprints-current-metrics.json` in the
ignored experiment output directory. The control is dc63f8f0 with only the same
post-observation maintenance export added to the example. Both lanes use their
own worktree-local Cargo target directories.

## Retained compiled-state attribution before shared code

The complete post-Graph Program release now attributes its fields in destruction
order, including ownership composition. The observer preallocates its result
buffer and checks that all attributed bytes sum to the complete teardown.
Shared allocations belong to their last owner; these are not independent
inclusive field sizes. No execution storage or decisions change.

| Added retained owner | Delta from fixed original |
| --- | ---: |
| Composition shapes | 413,256 B |
| Congruence conditions | 476,256 B |
| Query column positions | 423,672 B |
| Representative fragments | 44,128 B |
| Transition keys | 12,432 B |
| Source artifact | 547,259 B |
| Total | 1,917,003 B |

Effects have no measured increment in this configuration. The runtime still
retains the artifact, so its added fragment JSON is charged as well as compiled
code. Removing only small runtime arrays cannot compensate for these costs.
The next structural opportunity is shared query/condition prefixes: current
`prepare_queries` and `prepare_conditions` derive a complete plan per composed
shape, while shape signal slices already share unchanged prefixes. Sharing
must use identical compiled meaning, including frame, operator and scalar/input
checks; observed equality alone cannot justify deleting conditions. This is an
opportunity identified by measurement, not an implemented takeover or saving.

```sh
python3 benchmarks/cell-structural-compression/analyze_program.py out/cell-structural-compression/program-fields-original.json out/cell-structural-compression/shared-code-peak.json benchmarks/cell-structural-compression/program-storage-results.json
```

Both lanes use the same destructive observer on their respective actual runtime;
the original worktree carries only diagnostic instrumentation. Both completed
1,428 Runs with the same final hash and unchanged complete teardown totals.
`program-storage-results.json` records all owner contributions and input hashes.

## Share repeated query and congruence code

Actual executions selected the same 259 transitions; no retraining or change
of coverage is involved. Composed shapes previously reallocated identical query
column positions and condition/site records. Query column slices now share exact
position/input-bit contents. Condition and site records share exact structural
contents, including frame/op positions, all field bindings, equality inputs,
scalar columns, output symbols, and check ordering. Caller-local shape identity,
operator guards, liveness checks and source Run order remain authoritative.

The content interners are temporary compile-time sets and are discarded before
execution. Runtime reads immutable shared code through Arc handles; it performs
no new content lookup and maintains no producer/consumer list. No condition is
removed based on training observations. Full Eq comparison resolves hash matches.

| Retained owner | Before | After |
| --- | ---: | ---: |
| Queries | 728,376 B | 124,640 B |
| Conditions | 696,872 B | 404,920 B |
| Complete Program | 117,379,479 B | 116,483,791 B |
| Graph | 2,781,877 B | 2,781,877 B |
| Graph + positive Program increment vs original | 4,698,880 B | 3,803,192 B |

The 895,688 B saving is shared compiled storage, **not** fewer runtime instances,
facts or fields. Process execution/takeover peak falls from 125,763,669 to
124,867,975 B (small path-length differences also affect the process observer).
Initialization-relative growth stays 5,862,977 B and takeover extra peak stays
16,548 B. Setup peak is 119,007,614 B; temporary interning is included in observed
setup allocations. No speed claim is made.

All 1,428 Run graph and ordered effect digests match the fixed original and the
previous iteration. Native choice acceptance passes / exit 0. Checks: 138 sparse
runtime tests, 84 default runtime tests, 28 ownership, 14 stable-port and 5
local-union integrations pass; all-feature runtime compilation passes. Historical
union-digest diagnostic failures documented above were not reinterpreted as
passing by this change. `shared-code-results.json` records peak comparison;
`program-storage-results.json` records the latest complete ownership accounting.

The next physical takeover still needs to eliminate source Cell records and
storage, while keeping published FactRef identity and restoring delegated slots
when a surviving source outlives its component. This shared-code change does not
satisfy that remaining obligation.

## Continue training from the installed Cell catalog

Saved source-state analysis finds 2,385 retained source Cells, only two without
explicit values. Most composed sources still own facts and bindings. Deleting
those records just because a continuation succeeded would invalidate current
reads. The current four-frame catalog also recorded 771 capacity cuts.
`analyze_source_takeover.py` inventories this evidence without claiming that raw
value equality authorizes static sharing or retirement.

Training now accepts an explicit bounded `--max-frames 2..32` policy and writes
it into the profile and selected catalog. Missing metadata retains the original
four-frame policy. The loader rechecks each path against the declared limit;
operator/condition coverage budgets remain unchanged and uncovered cases still
fall back completely. No new proof is inferred from a larger limit.

A first unseeded 16-frame training run found 1,592 candidates, compared with 646
in the prior four-frame run. Repeated-use selection kept 256 fragments (267
transitions), with at most nine frames. It was **rejected as a compression
configuration** after actual execution:

| Measure | Accepted four-frame catalog | New unseeded catalog |
| --- | ---: | ---: |
| Successful compositions | 1,066 | 1,008 |
| Capacity cuts | 771 | 0 |
| Live components | 1,392 | 1,425 |
| Explicit source slots | 10,742 | 10,780 |
| Graph bytes | 2,781,877 | 2,790,213 |
| Charged Graph + added Program bytes | 3,803,192 | 3,826,784 |

All 1,428 graph and ordered execution digests match the original; native semantic
acceptance passes. Execution/takeover process peak increases from 124,867,975 to
124,891,565 B; initialization-relative growth rises from 5,862,977 to 5,871,257 B.
Removing capacity cuts alone is therefore a bad optimization objective. Results
are in `longer-catalog-results.json` and `longer-catalog-comparison.json`; accepted
`results.json` is deliberately unchanged. No timing claim is made.

The prior training API rejected every already-baked catalog. The new explicit
`--extend-catalog true` mode retains its checked shapes and transitions, executes
known transitions first, and discovers uncovered continuations. Before exploring
any unknown anchor, it searches the installed catalog across the eligible
anchors, preserving production's preference for an existing implementation.
Candidate fragments and checked source identities remain in the existing format;
there is no second runtime fact graph. Existing fresh-training calls still reject
a baked input, and training cannot lower the limit below an existing shape.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics -- profile-cell-ownership --program out/cell-structural-compression/baked-lean/program.json --extend-catalog true --max-frames 16 --output out/cell-structural-compression/profile-seeded-priority-16
python3 benchmarks/cell-structural-compression/analyze_source_takeover.py out/cell-structural-compression/shared-code-trace.json out/cell-structural-compression/shared-code-peak.json out/cell-structural-compression/profile.json out/cell-structural-compression/profile-16/profile.json benchmarks/cell-structural-compression/source-takeover-results.json out/cell-structural-compression/profile-seeded-priority-16/profile.json
```

The seeded run starts with 617 shapes / 259 transitions, records 530 installed
catalog hits, discovers 1,160 dynamic shapes and exports 1,559 candidate records.
These are **training observations, not committed mutation counts or proven
memory savings**. Exploratory composition changes later ownership contexts, so
this mode does not reproduce every production catalog hit: a candidate catalog
still needs separate execution admission. No seeded successor has been admitted
as a new compressed configuration. A subsequent selector must charge retained
state and shared code and justify intermediate-source retirement; maximizing
history length or the number of candidate paths cannot replace that obligation.

Validation: 29 ownership integration tests pass, including a six-Run chain
that exceeds four frames, rejection of invalid limits, rejection of a catalog
whose paths exceed its limit, and seeded discovery from a shorter installed
catalog. All-feature runtime compilation passes. The new test verifies that
seeded training both hits existing code and discovers longer checked paths.
