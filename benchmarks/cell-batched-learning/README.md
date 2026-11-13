# Batched learning over four frozen pass3 inputs

The batch contains `fact`, `loopfact`, `sum-bits`, and `dot-product` from the
checksummed pass3 suite. Each input executes separately. Their traces are pooled
before selecting **one shared catalog**, rather than baking four independent
catalogs or merging their runtime egraphs.

This experiment uses direct typed source compilation without input-specific
marker catalogs. Its per-input unbaked controls therefore differ from the earlier
marked sum-bits configuration. No old memory denominator is silently replaced.

## Identity, selection and proof

The compiler exports existing rule definitions, shared port-program definitions,
and query Entry atom indices. Pooling checks the table contracts and each trace's
source digest. It identifies a rule/port program by its full static definition,
not by its local array index, runtime Cell ID, or eclass representative. Entries
are translated through query atom indices. The input-specific initialization
rules remain distinct.

There are 2,797 different candidate paths, 334 observed on multiple inputs and 99
observed on all four. Each target can map 2,710 candidate paths. The global
selection contains 533 paths, of which 272 were observed on multiple inputs.
All four targets can load that same selection, with remapped local coordinates.
Foreign observations can therefore propose a path the target's training run did
not encounter. Normal typed substitution checks must still prove every hop when
compiling the target; ordinary execution remains available at uncovered edges.

This identity is conservative, exact structural matching. It does not equate
arbitrary alpha-renamed rules or prove that different histories have reached the
same saturated state. Recorded local projections and longer paths overlap;
their credits are not additive savings. All four inputs contribute training, so
this is not a held-out generalization result.

## Remove a duplicate runtime directory

The first batch helped the larger inputs but regressed fact and loopfact. Each
Graph copied the entire compiled transition directory into a HashMap, including
paths never activated on that input. The compiled directory was already sorted
by transition key.

Production now binary-searches that existing immutable directory. Only newly
learned transitions use the runtime overlay. Catalog-first training selection,
shape IDs, actual instance binding, source effects and Run boundaries are
preserved. This deletes 50,184 requested allocation bytes from each candidate
Graph. Retained Program bytes and all other Graph field charges are unchanged;
this is not moving the charge to Program. Lookup speed has not been measured.

| Input | Unbaked Graph bytes | Pooled, copied directory | Pooled, shared directory | Reduction vs unbaked |
|---|---:|---:|---:|---:|
| fact | 803,567 | 828,503 | 778,319 | 3.14% |
| loopfact | 726,057 | 732,449 | 682,265 | 6.03% |
| sum-bits | 2,257,323 | 2,123,571 | 2,073,387 | 8.15% |
| dot-product | 2,199,779 | 2,097,387 | 2,047,203 | 6.94% |

The sum of four separate final Graph heaps falls from 5,986,726 to 5,581,174
bytes (6.77%). This is not a simultaneous combined-graph measurement or a peak.
Program costs are reported separately. Live source-frame counts remain unchanged;
this has not yet implemented replacement of all dominated source instances.

## Validation scope

Forty-two ownership tests and eight Unit specialization tests pass. Five pooling
tests cover reordered program/rule IDs, Entry atom remapping, unseen-path transfer,
incompatible contracts, inconsistent costs and duplicate samples. Runtime checks
compare graph exports, ordered RHS and physical writes at every source Run against
each input's own unbaked control: 418 + 398 + 882 + 954 = 2,652 Runs. The shared
catalog is checked before and after removing the runtime directory copy.

These are standalone Cell runtime regression checks. They do not extend the
reviewed native sum-bits semantic contract to the other workloads, nor establish
native egglog equivalence for this direct-source batch. No timing result or
universal default admission is claimed. The broader egraph compression and
stage-driven RHS objective remains open.

## Reproduction

Use the repository's local Cargo toolchain and target directory:

```
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo build \
  -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics \
  --example batch_cell_learning --example runtime_storage_peak

target/debug/examples/batch_cell_learning prepare workloads/pass3/suite.json \
  out/cell-batched-learning fact loopfact sum-bits dot-product
python3 benchmarks/cell-batched-learning/pool.py out/cell-batched-learning
target/debug/examples/batch_cell_learning apply out/cell-batched-learning
target/debug/examples/batch_cell_learning verify out/cell-batched-learning
python3 -m unittest discover -s benchmarks/cell-batched-learning -p test_pool.py
```

Run `runtime_storage_peak` on each input's `baseline.json` and `candidate.json`,
using `inherited-owners --port-domains-only`, to reproduce the current heap
columns. The copied-directory column requires the pre-change runtime; its saved
reports are preserved as `candidate-copied-directory-heap.json`. Generate the
tracked small report with `summarize.py ARTIFACT_ROOT OUTPUT.json`. Generated
programs, full traces, binaries and Python caches are not tracked.

## Completed scalar bindings (follow-up)

The frozen shared catalog exposes duplicate retained state: Eq slots already
read composed symbols, but scalar operands were still held both in source slots
and stable constructor fields. Completion now derives `(slot, operation, column)`
projections from the original typed constructor instructions and Copy aliases.
Only immutable primitive scalars are admitted; container values and mutable
function reads are not recomputed. The existing execution plan holds this static
layout, without changing port-program identity or keeping another binding map.

A completed instance removes an explicit slot only after finding an actual local
stable constructor field with the same value. A reused foreign constructor does
not supply a synthetic local address. Parent handoff can use the same projections.
Before retiring the final provider of a delegated slot, the runtime restores its
value; completed shared storage is unsealed when necessary. Other live providers
avoid that restoration. This uses static template wiring, not consumer lists.

The same four candidate artifacts, without retraining, give:

| Input | Prior Graph bytes | Scalar delegation | Explicit slots before → after |
|---|---:|---:|---:|
| fact | 778,319 | 775,343 | 1,190 → 1,066 |
| loopfact | 682,265 | 679,001 | 1,158 → 1,022 |
| sum-bits | 2,073,387 | 2,057,283 | 3,989 → 3,276 |
| dot-product | 2,047,203 | 2,035,803 | 3,954 → 3,479 |

The final parent-link counts remain 89, 76, 216 and 231: this does **not** retire
the dominated source instances. Sum-bits elides 731 scalar slots over execution
and restores 18 on retirement; the other inputs restore none. The added compiled
layout costs 12,608 retained Program bytes per input, separately from Graph.
Runtime costs include provider lookups, a temporary list at completion, and
restoration/unsealing at retirement. No latency benefit is claimed.

The batched verifier now disables completed-parent takeover on the control lane,
so both sides cannot mask the same delegation error. All 2,652 source Run graph,
ordered-RHS and physical-write comparisons pass. The 44 ownership and 8 Unit tests
include retirement after shared-owner transfer, surviving child reads, worker
execution, and retaining an alternative scalar provider until the last retires.

The previously accepted **marked** sum-bits artifact separately falls from
2,477,174 to 2,460,662 Graph bytes, with the same final-state digest as its reviewed
saved export. The saved-export `choice_diagnosis.py` gate passes. This is a
final-state check, not a new native Run-boundary proof for the unmarked batch.

Reproduce by rebuilding the two examples above, running `verify`, and measuring
the unchanged candidate artifacts with `runtime_storage_peak ... inherited-owners
--port-domains-only`. Results are in `scalar-results.json`; the earlier directory
and batch measurements are intentionally retained as their own controls.

## Physical owner completion across Runs

The previous physical transfer collected only ordinary Cells, requiring two or
more eligible sources. Once two earlier frames had transferred, a single later
stage could not join their backing owner. The composed port shape grew, while
storage completion stopped at the earlier stage.

Transfer now includes the component's existing completed frames. A later Run
can absorb one new frame into the existing owner, preserving each original
logical ID, metadata, scalar binding, and live fact state. The old owner is not
unsealed into ordinary Cells just to assemble the new one. Complete coverage of
all participating owner slices is checked before mutation. Dead fact holes are
omitted when moving the backing arrays; missing facts stay missing. External
readers no longer disqualify an otherwise complete, parent-free source: their
stable logical references already support completed storage and retirement
fallback. Sources that themselves still require a parent remain ineligible.

The new work is charged explicitly: extension events, newly absorbed frames,
referenced frames, merged owners, and old slot/fact entries moved. This is a
storage takeover at a settled source Run boundary, not an earlier publication or
permission to skip a rule. Repeated transfer of an unchanged owner is a no-op.

Testing caught allocation cliffs in **both** completed-frame and owner-header
Vecs. Enlarging the eligible population could double either directory and lose
the memory benefit. Both now grow normally at small sizes and in increments of
128 records thereafter; IDs and record formats are unchanged. Temporary arrays
still exist during extension and are included in the heap high-water sampling.

`owner-takeover-results.json` compares the fixed catalog against scalar delegation
alone, including independent source-record counts, actual Graph bytes, temporary
takeover peaks and work. Program storage is unchanged. The earlier native scope
limitations still apply. All 2,652 source Run graph/RHS/write checks pass for the
new takeover and live-reader eligibility, alongside 46 ownership tests, 8 Unit
tests and the low-level owner-extension lifecycle test. Directory growth is an
allocation-only change; the final measured exports match the saved controls.

Reproduce the report after the saved before/after heap runs:

```
python3 benchmarks/cell-batched-learning/takeover_audit.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/owner-takeover-results.json
```

This still retains logical source metadata and fact records inside the shared
owner. It has not contracted internal parent lifetimes or achieved the 30% runtime
egraph target. The saved final trace now includes parent references, retainer
counts and physical-storage kind. Most remaining parent-free sources are in
single-frame components (195, 186, 589, 669); improving their composition coverage
is a larger opportunity than further header packing. There are also 37, 29, 80,
104 observed within-component cross-stage parent links. Those observations alone
do not prove that the parent states can be retired: typed Entry projections,
actual result ownership, external readers and lifecycle preservation remain live
obligations for a future internal-parent contraction.

Final Graph bytes for the four fixed candidates are respectively 759,727;
674,105; 2,043,955; 2,009,467: 60,176 fewer bytes in the sum of separate final
heaps. Ordinary source records fall 495→461, 469→438, 1,251→1,116 and 1,338→1,211
(327 fewer), while logical source and fact counts remain unchanged. The marked
accepted sum-bits artifact separately falls 2,460,662→2,447,294 bytes and
1,580→1,397 ordinary records. Its final digest still equals the reviewed saved
export, and the saved-export semantic gate passes. These are incremental gains,
not a claim of large egraph compression or faster RHS execution.

## Iterating the shared catalog from installed executions

`observe` now records the four inputs **with the installed shared catalog**,
checking every source Run against the unbaked control and saving the graph,
ordered RHS and physical-write checks. Passive unmatched-birth proposals retain
actual source history. They are pooled with the same typed definition and Entry
mapping as the first batch, but keep `matched_births` and
`available_shared_inputs` distinct from actual saved bindings.

The batch contains 3,017 proposal paths. Of these, 1,368 map to all four inputs;
289 were observed on more than one input. The seed catalog is common to all four
and must agree exactly before shared extension. Per-input unmatched proposal
counts are 433, 433, 1,378, 1,177. Respectively 110, 165, 576, 322 already have an
installed local producer/consumer path, but lack the corresponding full source
history transition. These are candidate counts, not disjoint rule applications.

Two selections add 64 or 256 proposals from this **one captured batch**. Both
retain every seed path through maximal-prefix coverage. Alternative Entries for
the same source history and receiver compete rather than accumulating credit.
The compiler rechecks each target and compares the complete seed transition
language before writing a candidate artifact. No foreign instance bindings or
runtime fact graph are introduced.

| Input | Installed seed Graph | +64 proposals | +256 proposals |
|---|---:|---:|---:|
| fact | 759,727 | 757,303 | 757,743 |
| loopfact | 674,105 | 681,329 | 680,689 |
| sum-bits | 2,043,955 | 2,042,715 | 2,033,691 |
| dot-product | 2,009,467 | 1,998,507 | 1,996,955 |

**Neither selection replaces the shared seed.** Both regress loopfact, and the
other gains are small. With 256 proposals, sum-bits ordinary source records fall
1,116→971, yet only 10,264 Graph bytes disappear. For loopfact, crossing a completed
frame-directory capacity boundary adds 10,240 bytes, more than the removed source
storage. More combined shapes also add component/signal storage. Counting newly
covered paths or physical transfers is therefore not a sufficient credit metric.
The next structural step must eliminate redundant retained source state, not only
collect more source frames under the same physical owner.

All eight candidate final exports equal their saved seed controls. The 256-path
candidate additionally passes all 2,652 saved source Run graph/RHS/write checks
and terminal non-Run effect checks. The 64-path candidate is **not** admitted by
that full gate. Program memory is reported separately; no speed or held-out
result is claimed. The larger egraph compression target remains unmet.

The saved checks avoid re-executing and exporting the entire baseline for every
candidate. A source-bound terminal check is cached separately; older captures
reconstruct that check from the admitted seed once, without repeating every
baseline graph export. Source and artifact hashes must match before replay.

Observation review also found a lifecycle bug: the saturation observer read
cross-stage age only from ordinary Cells. After shared-storage transfer it could
mislabel an old component as same-stage. It now reads the common metadata access
path; a regression test first failed with `rhs_covered / cross_epoch=false` and
then passes with the transferred predecessor correctly recognized. The saved
batch's saturation totals are aggregated **across** age buckets. Its old raw age
flags must not be used to infer cross-stage coverage; future captures use the
corrected observer. The selection above does not use these age flags.

```
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo build \
  -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics \
  --example batch_cell_learning --example runtime_storage_peak
target/debug/examples/batch_cell_learning observe out/cell-batched-learning
python3 benchmarks/cell-batched-learning/passive.py out/cell-batched-learning
# Apply each of passive/budget64 and passive/budget256:
target/debug/examples/batch_cell_learning apply-passive out/cell-batched-learning passive/budget256
# Measure candidate.json in each variant/case directory with runtime_storage_peak,
# storing heap.json, in inherited-owners --port-domains-only mode.
target/debug/examples/batch_cell_learning check-passive out/cell-batched-learning passive/budget256
python3 benchmarks/cell-batched-learning/analyze_passive.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/passive-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p 'test_*.py'
```

The report preserves saturation outcomes and storage-field deltas as well as
net Graph bytes. Nine Python tests cover pooling and passive selection; 47
ownership tests pass, including transferred-frame saturation observation.

### Completed-owner fact representation

The pooled traces expose a repeated invariant: completed-owner facts are owned,
not local-union owned, have no decoded copy or Entry alias, and no receipt slot.
Transfer now checks this contract atomically. The owner supplies those invariant
fields; each fact retains only its mutable epoch, birth epoch, hash and visibility.
This removes redundant representation state without bit packing or another index.
Ordinary facts remain unchanged. Reads use a borrowed/value view; mutation uses a
stack guard, keeping ordinary lifecycle changes compact. An exceptional alias or
representation change restores the original source Cell before committing it.
This does not remove logical fact identities, source frames, or their lifecycle
obligations. It does not skip additional rule applications or RHS operations.

Same seed artifacts, before/after requested Graph bytes:

| pass3 | before | after | saved |
|---|---:|---:|---:|
| fact | 759,727 | 747,247 | 12,480 |
| loopfact | 674,105 | 662,041 | 12,064 |
| sum-bits | 2,043,955 | 1,989,427 | 54,528 |
| dot-product | 2,009,467 | 1,965,147 | 44,320 |

Owned fact state falls 64→32 bytes; all four runs have zero representation
fallbacks. Allocated fact slices include retired entries, so savings are not
simply 32 times the live fact count. `owned-state-results.json` also records
execution peaks and takeover temporary bytes; these peaks include Program and
executor allocations, unlike the separately measured final Graph. No speed or
major compression claim follows from these modest reductions.

Validation: 2,652 cached Run graph/RHS/write checks plus terminal non-Run effects
pass, with identical final exports. The separate reviewed marked sum-bits artifact
has Graph 2,447,294→2,392,254 bytes and unchanged final digest
`1ccf8502afaebbfcb0f8e4820c9a9e8bff699f7008fa1b431dbf1f16da270b82`;
`choice_diagnosis.py` on its saved exports returns pass. This does not extend the
native semantic contract to the four unmarked inputs.

47 ownership, eight Unit, five fact-state lifecycle, five local-union, eight
port-completion, five repair-cell and 14 stable-port tests pass. Default and
receipt-slot configurations compile. Three maintenance assertions fail both here
and at unchanged `eae8acf6`: repair-ports subscription count, and two union-digest
binding-audit comparisons (their left/right payload hashes are identical between
control and candidate). These remain known baseline failures, not passing tests.

Reproduce by measuring each seed candidate with `runtime_storage_peak` into
`candidate-owned-fact-heap.json` using `inherited-owners --port-domains-only`.
For the cached gate, copy each unchanged candidate into `owned-state/CASE` with
its source-bound selection, then run `check-passive` as above. Summarize with:

```
python3 benchmarks/cell-batched-learning/owned_state.py out/cell-batched-learning \
  benchmarks/cell-batched-learning/owned-state-results.json
```

### Batch saturation credit audit

`saturation_credit.py` joins the saved catalog observations to the exact source
artifact and the current heap census. It pools rules by their complete static
definition (including stage metadata), never their sample-local rule number.
Full RHS coverage is counted separately from partial prefixes. Copies and already
compiled static aliases receive no additional effect credit. Counts are checked
against the observation's instruction totals before use.

Across the four cases there are 15,231 observed applies, of which 821 (5.39%) have
fully witnessed RHS effects: 524 remaining constructor operations and 390
already-equal union operations, alongside 969 copies and 14 static aliases.
These are potential redundant operations, not saved mutations. The largest
constructor group is `BodyContainsExpr(body, Get(tup, i)) ->
BodyContainsExpr(body, tup)`: 141 observed repeats across all four inputs.
The largest union group is `SubTuple(expr, 0, len) -> expr` under a mutable
`tuple-length` read: 180 already-equal unions. Its history cannot justify dropping
that mutable read or future union-enabled matches.

Only 20 of 5,760 retained logical frames have no facts, and all 20 have retainers.
There are 7,560 live facts, 250 parent edges internal to a component and 362
boundary parent edges. Empty-frame cleanup therefore cannot explain a large
compression opportunity. Internal edges are observed co-location, not proof of
safe inheritance contraction. All old cross-epoch trace buckets are aggregated;
the known observer age issue must not inflate a cross-stage claim.

This changes the next experiment: prioritize a compiled constructor witness
projection for recurring relation closure, with shape-relative frame/op positions,
then use that same proof to remove intermediate state. A generic runtime scan of
all facts would duplicate the expensive passive observer. The proof must retain
actual returned references, visibility, mutable-read freshness and delta ownership;
final live fact identities cannot be erased merely because an apply was redundant.
No new runtime takeover or speedup is claimed by this analysis.

```
python3 benchmarks/cell-batched-learning/saturation_credit.py out/cell-batched-learning \
  benchmarks/cell-batched-learning/saturation-credit-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p 'test_*.py'
```

### Shape-relative constructor witness candidates

The passive observer now exports `witness_recipes` for fully covered RHSs that
have actual constructor witnesses. Each site is `[atom/effect, frame, operation]`;
no runtime Cell ID, eclass ID or captured value enters its identity. Query sites
list only retained receipts inside the selected component, not a replacement for
the full query. Input-only unions and partial coverage emit no constructor recipe.
These records exist only when catalog tracing is enabled.

A critical distinction is preserved: port `shape.programs` identify shared wiring,
while `frame_codes` identify typed operator programs. Two constructors may share
one wiring layout. A witness recipe must include both; using the shape's program
ID to address the operator directory is invalid. The new regression fixture uses
identical F/G layouts and rejects an F code substituted at a G witness site.

`witness_plans.py` checks operator names, arity, query-to-symbol projections, copies,
RHS input symbols and union operands against the source definition. It separates
external Eq checks, scalar checks and unproved Eq relations. It does not use trace
values to discharge any obligation. Even exact wiring still requires live facts,
visibility, correct instance generation, the original match/delta contract and
Run/publication order. The emitted analysis is not executable authorization.

The first usable path is a guarded direct witness, not an unconditional saturated
jump: address the fact by checked frame/op, compare remaining inputs, and return
its actual result reference. The runtime must then remove the corresponding
constructor lookup; adding a speculative probe in front of unchanged work would
not establish takeover. This runtime replacement remains to be implemented.

To capture without rerunning the baseline, use the source-bound cached checker:

```
target/debug/examples/batch_cell_learning check-passive \
  out/cell-batched-learning owned-state witnesses
python3 benchmarks/cell-batched-learning/witness_plans.py \
  out/cell-batched-learning/owned-state \
  benchmarks/cell-batched-learning/witness-plan-results.json
```

The `owned-state` directory contains unchanged seed candidates and source-bound
selections, as in the completed-owner checks. Capture writes a separate
`witness-observation.json` only after all saved Run and terminal checks pass.
Tests cover two distinct instances sharing one recipe, partial/input-only
exclusion, and witnesses surviving completed-owner transfer. No new runtime
compression or speed improvement is claimed from exporting these candidates.

The audited batch yields 222 per-input witness recipes covering 431 actual applies:

| pass3 | recipes | observed applies | exact-wiring applies |
|---|---:|---:|---:|
| fact | 29 | 57 | 0 |
| loopfact | 24 | 30 | 0 |
| sum-bits | 90 | 179 | 8 |
| dot-product | 79 | 165 | 44 |

All 2,652 saved Run checks and terminal checks pass. All 47 ownership tests and
17 Python analysis tests pass. These per-input recipe counts are not deduplicated
across workloads. Only 52 observed applies discharge all static key obligations;
the other candidates require guards. Thus treating all 431 as unconditional
saturated transitions would overstate the evidence. The large compression goal
remains unmet; the next runtime change must consume these witnesses while removing
an existing lookup and, where proven, its intermediate retained state.
