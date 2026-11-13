# Generated Cell consumption through constructor assignment and union

This standalone GPU experiment advances beyond isolated union instances. It uses
three original Eggcc context rules (283, 290 and 293), the audited Pascals snapshot
before Run 467, and device-controlled repeated matching/completion to saturation.
The original rules connect AddContext with Get and Single; Get also carries a
scalar index. Inputs are imported once. No CPU matching is supplied between Runs.

## Constructor assignment

The native `Graph::set_inner` constructor path establishes a missing constructor
row with the supplied value, or unions that value with an existing result. This
is distinct from mutable function assignment. `lower_constructor_sets.py` lowers
only typed, slot-operand constructor sets into:

```
temporary = construct(table, arguments)
union(temporary, supplied_value)
```

This uses existing GPU constructor completion and typed union instructions in
source order. The compiler records the original operation, lowered position and
temporary slot. Mutable function sets stay unsupported; literal and ill-typed
constructor sets are rejected. Snapshot import continues to reject hidden reuse.
No native runtime files are changed.

This is deliberately a coverage implementation, not a storage optimization.
Each lowered site adds a slot; a missing constructor may allocate a temporary
identity and immediately merge it. The three-rule example has two lowered sites
and allocates five IDs in total. Those allocations and extra unions are not
claimed as work saved. A direct supplied-result implementation can remove this
extra work later, after preserving the same semantics.

## Real result

- 98 imported constructor rows; 40 accepted new Cell instances.
- Four new instances actually consume a generated Cell as an input witness.
- 34 physical owner rows released by existing matched takeover.
- Four Runs; semantic changes are true, true, true, false.
- Per-Run match counts are 33, 33, 35, 35; **each rule's count** also agrees with
  the independent original-rule CPU oracle.
- Every completed Run's graph passes the CPU comparison, not just the final one.
  Normalized fact counts are 95, 97, 96, 96. Congruence can collapse facts, so a
  decreasing count is not interpreted as deletion or a stopping criterion.
- All selected joint witnesses pass lifetime/generation/port checks and complete
  enumeration checks. Final views are complete within the imported family.

Accepted Cell instances are not counted as 40 new graph mutations: some actions
reuse existing constructors or perform already established unions.

## Independent checking

`reference_union_family.py` now supports constructor creation and constructor set
in addition to copy and union. It interprets the **unlowered original rules**;
a separate execution of the lowered rules checks the transformation itself.

Fresh identity order is not semantic. `compare_graph` anchors every imported ID,
then maps constructed results through complete constructor facts. It requires an
injective correspondence of equivalence classes, equality of the complete local
fact set, and an explanation for every allocated root. This rejects both missing
unions and false merges, including aliases that a mere fact-count check misses.

The GPU retains small owner/slot boundary snapshots for auditing, with no host
readback between Runs. They are checked after execution against independent CPU
snapshots. This increases diagnostic storage; timing includes that diagnostic
configuration and does not establish runtime speedup. No native full-Eggcc
semantic acceptance is implied by this projected-family check.

22 relevant tests pass, including lowering without modifying original recipes,
mutable/typed rejection, independent partition comparison, union-enabled joins,
ordered GPU union, matched ownership, and existing residual training tests.

## Captured data and remaining work

`context-construct-union-witnesses.npz`, under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee`, saves the actual selected floating
source inputs, predicted tokens, bindings and lifecycle evidence. Its distinct
schema `device-composed-witness/v1` has **no training target labels**. Metadata
contains the original and lowered Cell recipes and source/model hashes. It must
not be passed off as the earlier supervised v2 corpus. Exported logical arrays
occupy 10,234,860 bytes; the binary archive is kept outside Git.

The default ridge is not retrained here. New lowered templates change structural
roles, and their prediction accuracy remains to be evaluated. Exact GPU kernels
still establish completion; this is not evidence that learned floating inference
alone executes the family. Full stages, unsupported scalar/mutable effects,
CPU correction integration and broad coverage remain open.

Latest inspected Bake reference: `0e3a5152`. Its boundary audit distinguishes a
visible constructor outside the local proof from an absent constructor. This GPU
path likewise uses actual existing result witnesses and preserves local coverage
checks; neither lowering nor an observed result grants proof over omitted tables.
Owner transfer does not imply ownership of every external result. The next data
step is to label these actual generated-source witnesses, with their scalar inputs
and real returned-result identities, rather than synthesizing historical paths.

Reproduce with the existing audited snapshot and frozen token model:

```
python benchmarks/eggcc-gpu-supervision/audit_construct_union_family.py TRACE MODEL OUTPUT \
  --rules 283,290,293 --snapshot-run 466 --capacity 128 --ticks 24 --capture CAPTURE.npz
```

Only one original source ruleset is projected in this experiment. Multi-stage
schedule composition must retain original Run visibility and cannot be inferred
from this single-stage result.
