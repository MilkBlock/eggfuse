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

### Guarded constructor witness execution (explicit experiment)

An optional `ownership_witnesses` catalog now lowers the observed addresses into
operation-indexed routes. Loading checks source identity, shape/code compatibility,
query and RHS operators, and constructor eligibility. It never trusts a trace to
prove key equality. The runtime uses the existing current Entry, checks its source
frame/code and the target frame/code, and passes that actual fact reference to the
existing live prepared-result consumer. It constructs the key once; a valid witness
returns its actual result and eliminates the ordinary constructor lookup. A dead,
hidden or mismatching witness falls back using that same key. A Cell-route witness
never receives the stronger Run certificate used by query-prepared results.

No extra per-instance binding, result history, or reverse consumer list is added.
Rules absent from the catalog have no witness Entry admission; operations without
a plan do not probe routes. Entries are admitted for selected witness rules even
when those rules have no birth-producing composition transition. Without this
admission the first fixture had zero probes: collecting a catalog alone did not
connect it to execution. The regression now requires both an accepted route and
fewer actual key lookups, in addition to equal graphs, snapshots and binding audits.
It also checks hidden/deleted witnesses and rejects invalid operator code.

| pass3 | route probes | accepted / lookups removed | added field checks | Graph bytes delta |
|---|---:|---:|---:|---:|
| fact | 258 | 23 | 72 | 0 |
| loopfact | 204 | 14 | 35 | 0 |
| sum-bits | 1,649 | 115 | 392 | 0 |
| dot-product | 1,988 | 148 | 532 | 0 |

The initial rule-wide route map required 6,895 probes. Compiling per-operation
admission and only the relevant Entry positions reduces that to 4,099, preserving
all 300 acceptances. Measured port constructor index lookups decrease by exactly
300 as well. Failed guards are charged, not counted as skipped work. Retained
Program increases 91–293 KB per case (including artifact/catalog storage), reported
separately. Final Graph remains unchanged. The catalog is **not installed in the
shared seed**, and no speed or large compression result is claimed. Reusing an
already-existing constructor does not by itself eliminate its retained fact state.

48 ownership tests and 17 Python tests pass; the default runtime also compiles.
The final dispatch implementation is checked against all 2,652 saved source Run
checks and terminal effects. This is the same-source standalone Cell contract,
not a new native egglog semantic admission for these unmarked inputs.

```
target/debug/examples/batch_cell_learning apply-witnesses \
  out/cell-batched-learning owned-state witness-direct
target/debug/examples/batch_cell_learning check-passive \
  out/cell-batched-learning witness-direct
# Measure each witness-direct/CASE/candidate.json in inherited-owners
# --port-domains-only mode; heap.json is the first route implementation,
# heap-dispatch.json is the final per-operation dispatch implementation.
python3 benchmarks/cell-batched-learning/direct_witness_results.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/direct-witness-results.json
```

### Residual inherited values instead of a complete parent dependency

The completed-parent plan previously required every remaining inherited slot to
have a local symbolic or stable-scalar provider. A single missing provider kept
the whole parent edge, even when the value was already stored in the child. In
particular an RHS constructor can reuse a foreign fact and provide no local
scalar storage. A compile-time list of possible local providers cannot establish
that a provider actually exists for this instance.

The compiler now emits the complete remaining parent-slot read obligation.
At completion, the runtime uses existing local values first, then equal local
symbolic/stable-scalar providers, and captures only uncovered actual values into
the existing child slots. It computes the residual before changing ownership;
errors preserve the original parent. Only after satisfying every retained read
obligation does it release the parent reference. Original Run-boundary GC remains
unchanged. This introduces no extra binding map or per-producer consumer list.

The same shared catalog now produces:

| pass3 | parent edges | ordinary source records | Graph bytes before → after |
|---|---:|---:|---:|
| fact | 89 → 0 | 461 → 371 | 747,247 → 732,807 |
| loopfact | 76 → 0 | 438 → 366 | 662,041 → 657,009 |
| sum-bits | 216 → 0 | 1,116 → 893 | 1,989,427 → 1,962,163 |
| dot-product | 231 → 0 | 1,211 → 983 | 1,965,147 → 1,935,099 |

These are physical storage gains, **not logical node elimination**: logical frames
remain 753 / 691 / 2,180 / 2,136 and live fact counts remain 948 / 892 / 2,895 / 2,825.
Parent-free children can join existing completed owners. Capturing the residual
adds 135 / 116 / 333 / 373 slot writes over execution; explicit final slots increase
by 113 / 107 / 260 / 315. Cumulative capacity growth from capture is 624 / 864 /
2,088 / 1,656 bytes. The report charges those costs and takeover peaks. Net Graph
savings remain only 0.8–1.9%; zero parent edges is not evidence of the larger
compression goal being reached.

49 ownership tests (including serial and two-worker reuse of foreign constructor
results) and eight Unit tests pass. The batch is checked against all saved source
Runs and terminal effects. The separate reviewed marked sum-bits retains digest
`1ccf8502afaebbfcb0f8e4820c9a9e8bff699f7008fa1b431dbf1f16da270b82`;
Graph is 2,392,254 → 2,362,006 bytes and saved-export `choice_diagnosis.py` returns
pass. This does not create a new native semantic contract for the unmarked batch.

Measure each unchanged seed candidate into `candidate-residual-parent-heap.json`
in `inherited-owners --port-domains-only` mode, then summarize:

```
python3 benchmarks/cell-batched-learning/residual_parent_results.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/residual-parent-results.json
target/debug/examples/batch_cell_learning check-passive out/cell-batched-learning owned-state
```

### Reusing completed child storage inside a larger Cell

A composed Cell can contain several smaller completed Cells. The prior extension
path flattens all their slots and facts into one replacement array on each later
stage. The optional `nested-owners` experiment retains existing storage segments
and transfers only newly completed source frames. The existing component frame
list and source-to-owner directory remain authoritative: no second runtime child
registry or reverse dependency list is introduced. It can reuse a partial old
segment without consuming its siblings because it never relocates that segment.

A lifecycle test checks unchanged old array addresses, atomic rejection of duplicate
sources, a one-frame suffix, partial unsealing, deletion and surviving siblings.
Six fact-state tests pass. `check-nested` passes all 2,652 source-bound cached Run
and terminal checks, using segment reuse only at the original transfer boundaries.
This remains a standalone Cell runtime check, not new native semantic admission.

The four workloads avoid 4,355 old-slot moves and 3,710 old-fact moves. This is
real removal of repeated transfer work, **not final egraph compression**:

| pass3 | Graph before | nested storage | added bytes |
|---|---:|---:|---:|
| fact | 732,807 | 733,431 | 624 |
| loopfact | 657,009 | 662,273 | 5,264 |
| sum-bits | 1,962,163 | 1,975,179 | 13,016 |
| dot-product | 1,935,099 | 1,949,387 | 14,288 |

Old slots/facts no longer move during extension, but independently allocated
segments add headers and retain some retired entries until their own segment
retires. The original per-source frame descriptors also remain. **The experiment
is not selected as the default**; there is no speed measurement or large-compression
claim. Smaller transient allocations are not guaranteed either; the recorded
peak is reported separately.

This identifies the required next representation change. Template reuse and
instance reuse must be distinct. A parent template can reference child templates
with static port projections and stage obligations. A parent instance should
carry only actual child identity/parameters and new state. A repeated small
pattern with different bindings is a different instance; sharing one actual child
requires a lifetime proof. Runtime source IDs and fact visibility cannot disappear
until their addresses and outstanding readers have a proved replacement. Merely
adding child blocks while preserving every flattened descriptor is insufficient.

```
# runtime_storage_peak PROGRAM OUTPUT nested-owners --port-domains-only
# Write candidate-nested-owner-heap.json for each unchanged shared seed.
target/debug/examples/batch_cell_learning check-nested out/cell-batched-learning owned-state
python3 benchmarks/cell-batched-learning/nested_owner_results.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/nested-owner-results.json
```

### Nested Cell granularity: a rule body is not an indivisible child

The next storage change must address actual cross-component wiring rather than
only shrinking source headers. `subcell_links.py` reads the existing batch
snapshots, decodes possible native result addresses, and verifies the producer's
current symbol binding before classifying a link. It keeps distinct instances and
operator codes distinct even when they share one port layout. It separately tests
whether an owned, visible provider fact remains. These are snapshot candidates,
not a replacement for match evidence or a count of removable boundary records.
A visible provider site alone is also not proof of immutable constructor semantics;
mutable reads still require their original freshness obligations.

| pass3 | cross-component symbol references | with visible provider | largest producer references | distinct producer ports |
|---|---:|---:|---:|---:|
| fact | 964 | 957 | 768 | 62 |
| loopfact | 915 | 910 | 614 | 47 |
| sum-bits | 4,052 | 2,962 | 1,576 | 78 |
| dot-product | 3,488 | 3,406 | 2,315 | 161 |

In these frozen inputs the largest producer is component 128 / source frame 129 /
template 341: the typed `initialization` rule. It contains 48–171 live facts in
one source frame. Its 5,273 references account for 56.0% of all 9,419 cross-component
symbol references, but are spread across many different ports. A whole-component
merge would pull unrelated initialized expressions into the same owner. Conversely,
selecting only existing source-frame boundaries cannot expose their repeated small
substructures. On sum-bits, 1,090 cross-component references have no currently
owned visible provider in the mapped producer; an address alone cannot authorize
importing a fact or skipping its construction.

The architectural requirement is therefore both **composition and slicing**:

1. Keep source rule/effect execution identity separate from reusable Cell regions.
   A typed child view selects existing fact operations and exports their ports;
   it must not allocate duplicate facts just to express a subcell.
2. A parent template references typed child templates, port projections and stage
   obligations. A parent instance references actual child occurrences and only its
   new state. Repeated layouts with different bindings remain distinct occurrences.
3. Use actual successful Entry/apply evidence to select multi-child joins. The
   current append-only transition chooses one component and a new source frame;
   shared roots alone do not establish a safe multi-child join.
4. Remove flattened descriptors and redundant boundary maintenance only inside the
   proven coverage. Shared actual children retain their lifecycle obligations;
   static wiring must not become per-child lists of consumer instances.

No new runtime compression or stage skip is implemented by this audit. It changes
the next target from generic completed-metadata packing to typed views within large
source Cells and composition of those views. Existing local index/visibility/Run
checks remain authoritative. Twenty-one Python tests pass, including invalid
native bindings, hidden providers, foreign slots, and same-layout/different-operator
counterexamples. This uses saved traces; it does not rerun workloads or timings.

```
python3 benchmarks/cell-batched-learning/subcell_links.py out/cell-batched-learning \
  benchmarks/cell-batched-learning/subcell-link-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p 'test_*.py'
```

### Repeated static child views in the saved batch

`subcell_patterns.py` now mines two- and three-operation output-to-input paths
inside existing components. It alpha-renames static template ports, retains typed
operator IDs within each source program, and never uses current union roots to
invent wiring. Hidden or non-owned providers are excluded. Scalar columns remain
parameters requiring validation; this is not a saturation certificate.

| pass3 | repeated patterns | greedily disjoint children | covered existing facts | children crossing birth epochs |
|---|---:|---:|---:|---:|
| fact | 83 | 65 | 181 | 14 |
| loopfact | 86 | 71 | 199 | 12 |
| sum-bits | 156 | 260 | 720 | 48 |
| dot-product | 215 | 263 | 753 | 43 |

These are actual standalone Cell runtime snapshots, not native egglog measurements.
The deterministic greedy packing counts each fact once across all selected views;
it is neither an optimal packing nor a prediction of saved bytes. Facts retain
identity, and no runtime path has been removed. Birth epochs do not establish
source Run order. Different scalar bindings remain different child occurrences.

This narrows the next takeover experiment to concrete multi-operation views,
including views spanning source frames, rather than retaining only whole-rule
frames. A typed compiler admission must still check immutable constructor versus
mutable function semantics, scalar bindings, actual Entry evidence and original
Run boundaries. Storage takeover must remove the corresponding independent
records and charge view addressing; a catalog alone cannot discharge this work.
The observed cross-epoch candidates motivate stage-aware child completion, but do
not authorize skipping an apply or publishing a future effect early.

```
python3 benchmarks/cell-batched-learning/subcell_patterns.py out/cell-batched-learning \
  benchmarks/cell-batched-learning/subcell-pattern-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p 'test_*.py'
```

All 24 analysis tests pass, including alpha-renaming, operator and alias distinction,
scalar-column distinction, hidden providers, and union roots that must not create
static edges. No workloads, timing campaign or runtime semantics were changed.

### Typed child-view lowering and batched layout sharing

`subcell_views.py` lowers the saved paths into constructor-only child-view
candidates. Each column is checked against the source table schema; an aliased Eq
port must have one consistent sort. Cross-program layout identity includes table
names, full schemas and alpha-renamed wiring, rather than program-local table IDs.
The four samples share 86 layouts for 659 selected occurrences covering 1,853
existing facts. Per-case selection remains 65/71/260/263 children. These are
compiler candidates only, not a new runtime fact registry or completed takeover.

Scalar columns are parameters projected from the original `(FactRef, column)`.
They are not captured trace values, copied bindings, or assumed equal merely
because their columns have the same sort. Eq parameters refer to existing
component symbols. This distinction matters: an all-Eq-only admission would retain
just 263 children covering 620 facts; it would reject valid reusable constructor
layouts simply because their instances carry different scalar parameters.
All selected operators in this batch pass constructor and schema validation.

The generated artifact explicitly has `executable: false`: it still lacks Entry
admission, visibility/generation validation and source Run scheduling proofs.
All ports are exported conservatively, so no external-use information is lost.
Before runtime integration, these occurrence addresses must be replaced by shared
shape/frame-relative addressing where proved, without retaining this offline
catalog as a second instance directory. No runtime memory or RHS saving is claimed.

```
python3 benchmarks/cell-batched-learning/subcell_views.py out/cell-batched-learning \
  out/cell-batched-learning/typed-child-views.json \
  benchmarks/cell-batched-learning/subcell-view-results.json
```

The existing Python discovery command passes 29 tests. New checks cover equivalent
layouts under different table numbering, mutable-table rejection, column schema
mismatch, conflicting Eq sorts, and projections onto the original scalar fields.
