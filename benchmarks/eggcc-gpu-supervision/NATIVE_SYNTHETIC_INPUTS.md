# Native execution of synthetic Cell inputs

Training inputs remain randomized, rule-derived structures. Real Eggcc Run
values are not used by this adapter. `synthetic_native_source.py INPUT OUTPUT`
replays the synthetic generator's validation and emits a native `.egg` program.
Pass `--schedule FILE` for multi-stage inputs; original stage order is explicit.

Compile the emitted source using `cargo cell-compile --source OUTPUT --output DIR`
(README workflow), then execute the existing `capture_rhs_results` example with
`DIR/program.json DIR/trace.json --snapshot-runs=0`. The observer exports actual
matched inputs and RHS results. It does not turn logical matches into committed
mutations. No native runtime or GPU inference code is changed here.

`audit_native_synthetic.py INPUT TRACE SOURCE REPORT [--schedule FILE]` checks
source replay, native audit flags and exact projected final facts against the
independent local reference. Private `SyntheticSeed_SORT(i64)` constructors name
open input ports; those anchors alone are excluded, and every anchor is checked.
Top-level `let` names are deliberately avoided because they create extra tables.
This migration check is not the sum-bits acceptance contract. It does not
cryptographically link the provided source to the captured executable: retain
the compiler artifacts and trace program hash when reproducing results.

Scope: immutable constructors, Eq, copy, constructor set, exact i64 literals;
unsupported operations fail explicitly. This is not broad primitive support,
a bounded batched exporter, or a GPU token-generation implementation.

## First check

Synthetic Get/SubTuple input seed 20261500 (rules 145 and 139): 12 projected
facts equal, six input anchors, two Runs on both paths. Native per-Run graph,
binding audit and Run-control checks all pass. Three unit tests also exercise
schedule rendering, absence of global alias tables, missing facts, failed native
audits and corrupt anchors. No performance claim.

Artifacts on this machine:
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/native-synthetic-subtuple-v2/`.
Used pre-existing compiler/capture binaries under the same root's `cargo-target`;
these were not rebuilt from the currently dirty Rust workspace. Large traces
and binaries are not committed.

The intended data flow is synthetic input -> Eggfuse actual execution/context
capture -> training examples -> ridge fitting -> GPU inference. The local Python
reference is a migration cross-check, not a second production execution engine.

## Multi-stage capture and feature separation

The synthetic context/canon input also passes final projected-graph comparison:
15 facts, 13 input anchors. Native execution has three Runs and nine captured
bindings; the independent Python interpreter has four Runs. This is final-state
agreement, **not identical trajectories**. Use native executed boundaries for
native labels. See `native-synthetic-context-report.json` for artifact and binary
hashes. The compiler and observer agree on native Run control.

Capture with `--relations` (which implies `--all-slots`) for Eq evidence.
`native_cell_examples.py TRACE OUTPUT` exports local typed input Eq partitions,
input scalars, and separately post-Run input/RHS partitions and scalar labels.
Eq IDs are normalized to local class positions rather than used as numeric
features. Three tests check target isolation, sort-sensitive normalization and
missing evidence. The original scalar values retain exact types; this is a data
export, not a floating encoding.

The extractor alone does not certify synthetic provenance: use the validated
synthetic generation/native execution pipeline and keep its artifact manifest.
Do not feed arbitrary real Run captures to synthetic-only training. This output
has not yet been connected to ridge fitting.

Latest inspected Bake reference: `afc6b4d8` (passive capture attribution). It
separates observed capture work from forced materialization and explicitly does
not treat logical history as physical owner evidence. Accordingly these samples
mark ownership **unobserved**: common Eq classes do not certify a parent, actual
constructor witness, liveness or legal retirement. A future native parent/witness
export must provide those before training ownership transitions. No CPU executor
changes were made, and no GPU correctness or speed improvement is claimed.

## Passive source evidence

Build `capture_rhs_results` with `--features slot-transfer-audit` to export
existing instance parent/continuation and retained query witnesses alongside
slot observations. `cell_observation` copies only the already retained witness
projection; no extra lookup or history retention is introduced. Null/absent
witnesses stay unknown. The sample exporter joins by exact Run/binding ordinal
and checks rule identity. Evidence remains separate from input features and
labels; it does not itself prove retirement or ownership transfer.

On the context/canon fixture, both default and `sparse-cells` builds produced
nine observations but **zero parents and zero retained query witnesses**.
Their complete per-Run binding records and final graph equal the earlier capture.
See `native-source-evidence-report.json`. This is evidence that this compiled
fixture is insufficient for ownership training, not a successful ownership
capture. Next input preparation must exercise a baked continuation catalog.
These two builds used the current dirty workspace; unrelated native changes
were preserved and are not part of this commit. No speed claim or performance
campaign. Four Python extraction tests and a focused Rust witness projection
test cover alignment and preservation of missing/actual evidence.

## Observed catalog preparation

`bake_synthetic_capture PROGRAM OUTPUT REPORT` (runtime Cargo example, features
`iterative-bake,spine-shapes`) now prepares the missing catalog. It executes the
synthetic program, derives stage leaves from its actual shape profile, installs
producer roots, collects actual continuation choices, emits query handoffs, and
checks every exported Run graph and ordered binding against the original before
writing the candidate. Limits are bounded (32 leaves; default catalog limits,
support 1 for small synthetic cases). This is one offline discovery round, not
an optimizer speed result. Input must come from the validated synthetic pipeline;
the tool accepts a Program and does not itself attest that input's provenance.

Reusing the context/canon fixture yields one leaf and two observed joins. Running
the catalog through `capture_rhs_results` with `slot-transfer-audit,sparse-cells`
exports 9 examples, 4 direct continuations and 14 retained query witnesses. The
ordinary parent field remains absent. All original Run snapshots and ordered
bindings agree; the capture's independent native audits pass. See
`native-baked-capture-report.json`. This replaces the previous zero-witness
preparation for this fixture; it does not fill missing evidence by inference.

Latest inspected neighboring Bake revision `e215b801` lowers observed physical
ancestry into ownership fragments. Its observed borrowed FactRefs demonstrate
why cursor parents cannot substitute for actual constructor owners. Our exported
FactRefs are actual retained query evidence, but we still need completed source
execution mapping and current liveness/ownership checks before labelling token
retirement. No ownership transfer labels or model accuracy gains claimed here.

## Query-time physical owner context

The diagnostic binding callback now resolves *retained* witnesses before RHS
execution and exports their current visibility and physical source Cell metadata.
It uses existing forwarding, Cell storage and visibility APIs, not key searches
or Eq-based owner inference. These are offline capture costs. The ordinary
execution path remains unchanged. Mutable function witnesses have no guessed
Cell owner.

`native_cell_examples` adds input `owner_context`: local owner sharing groups,
source template/operation roles, the existing completed flag and visibility.
Raw Cell numbers remain in evidence only; bijective Cell renaming leaves these
features unchanged. Missing projections remain missing. Template IDs are local
categorical roles, not globally comparable numeric model inputs. A false
completed flag on an initial fact does not mean it is invalid.

For the baked context/canon fixture: 14 retained witnesses, all visible, 4 owned
by completed RHS Cells. Original per-Run bindings and final state are unchanged.
See `native-owner-context-report.json`. Five Python tests cover source alignment,
label separation, typed partitions and owner-sharing/renaming behavior. This has
not yet been fitted with ridge. A completed owner and a direct continuation do
not establish that the source has no other consumers or may be retired; no
ownership-transfer labels are asserted.
