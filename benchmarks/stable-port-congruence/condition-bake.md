# Conditional-template compilation: single-thread experiment

This experiment targets the standalone Cell CPU runtime, not native egglog.
Its reference is the frozen single-thread `--local-congruence` path after the
duplicate dynamic lookup and domain-selection fixes. The fastest
`--repair-ports --entry-publications` path remains a separate control.

## Opportunity before implementation

The complete Raytrace pilot performs 55,413,157 signal visits, 105,558,365
signal-slice steps and 12,161,275 exact key-candidate checks after the preceding
fix. A signal slice includes uses in every field, although a bound query needs
the signal in a particular column. Local congruence plans currently pair sites
by field layout and leave operator discrimination to runtime. They also retain
reflexive and repeated equality predicates.

Existing fragment profiles measure actual cross-frame bindings saved and
transition probes. They do not measure condition-specific savings, and their
scores overlap. Iterative Bake has a work ledger for stable ports, but its
replay configuration currently cannot enable that backend. It must execute the
intended backend before its scores can describe this experiment.

## Compiler facts and remaining obligations

- Checked symbolic wiring proves which column uses a signal. A candidate for a
  bound column can omit sites using the signal exclusively in other columns.
- A port-program ID identifies a layout, not an operator. Operator exclusions
  must account for every concrete template sharing that layout; a profile is
  never an equality or coverage proof.
- Reflexive equality is true; duplicate unordered equality pairs need one
  check. Explicit future union instructions are not compile-time assumptions.
- Fact liveness, current equality, scalar guards, external aliases and ordered
  collision publication remain runtime obligations. A false condition is not
  permanently false. Activation in a later stage must observe equality already
  established in an earlier stage.
- Any lookup routing is shared static template code, not a per-instance reverse
  consumer list. Oversized or uncompiled shapes retain a complete fallback.

## Admission

Use identical frozen inputs, interleaved fresh single-thread processes and
separate allocation diagnostics. Compare final state and ordered schedule;
focused semantic audits additionally cover partial conjunctions, lifetime,
cross-stage activation and survivor order. Record new routing work and static
code cost as well as removed candidate work. A smaller operation count alone
does not establish a speedup. Results are recorded in `../condition-bake/`;
the current checkpoint does not pass the two-workload timing gate.

## Implemented candidates

1. Keep the bound column when selecting an equality domain. Prepare shared
   symbol/column slice positions once during graph setup, with a complete
   column-filtered fallback for training-only shapes. The serialized program
   and marker identities do not change. These are setup-time compiled routes,
   not a claim that the artifact already contains a machine-code kernel.
2. Use the stable-node directory itself to check owned-fact lifetime and table
   identity. The former Cell-directory and fact-directory lookups duplicated
   that authoritative representation. The legacy representation keeps its own
   checks. Compile local conditions using the union of typed operators for
   every template sharing a port program; remove disjoint operator pairs,
   reflexive equalities and repeated unordered equalities within a condition.
3. Retain the concrete template in the existing frame metadata slot formerly
   occupied by the port-program ID. Its marker still gives the shared program.
   A query can now read the immutable operation's table before looking up a live
   node. This adds no frame fields, consumer lists or per-union index repair.
4. Compile the concrete operations into shared operator-tag arrays instead of
   decoding template instructions on each lookup. A frame keeps one code ID;
   native-port programs use a compact parallel pointer array. Interning uses
   the checked port program and exact operator sequence, so templates with
   different operators cannot share an incompatible code. Only ownership setup
   prepares this code; ordinary artifact validation does not pay its compilation
   cost. The artifact's marker format and symbolic shape IDs stay unchanged.
5. **Rejected runtime experiment, retained as a source patch:** after exhausting
   a birth-hint bucket, prove absence if every current Eq
   input root belongs to a Cell that has never received a parent edge. The
   admitted scalar fields are immutable and recursive Eq containers are
   excluded, so an existing matching key could not have migrated from another
   birth ID. This runs only for ordinary lookups with no dirty table facts;
   completion and unknown cases retain their complete domains. The summary is
   enabled lazily with port-key matching, seeded from existing base/delta
   edges, and updated before each later parent insertion. It is coordinator
   metadata, not a producer/consumer index or a snapshot layer. Large external
   IDs conservatively decline proof. Clearing Parents permanently invalidates
   an already-enabled proof directory because retained birth hashes would no
   longer have the monotone-equality guarantee.

The incoming-edge bitmap is deliberately coarse: all imported equality IDs
share Cell 0, so one incoming union may prevent proofs for unrelated imported
roots. This is a performance limitation, not permission to accept a false miss.
Counters distinguish proof checks, accepted misses, declines at Cell 0, bitmap
writes, growths and retained capacity. Static code, routes and all required
fallback work remain in the measurement.

Paired timing rejected this fifth candidate: the proof mostly skipped cheap
domains, removing only about 3% of signal visits while adding its checks and
maintenance. Its implementation has been removed from the active runtime; the
patch and all measured failures remain in `../condition-bake/`. The shared-code
checkpoint also has no two-workload performance admission: Raytrace improves,
but sum-bits process time does not. Subsequent work must target whole irrelevant
groups before instance enumeration instead of adding more per-signal filters.

The first pilot is a negative admission example: sum-bits slice visits nearly
halve but inference is unchanged and process time increases slightly. Raytrace
improves only about 2.4%. It is not admitted independently. Full pilot records,
including subsequent candidates, live in `../condition-bake/`.

The replay configuration fix is committed separately as `ff5e6bc4`. Its test
checks discovery both enabled and disabled, nonzero new-backend work, no legacy
key completions, and equal state/schedule/ordered RHS/write/resume stamps. It
does not turn the existing equally weighted operation ledger into calibrated
time, and does not establish that the selected catalog beats the fastest path.
