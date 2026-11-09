# Compile future operator coverage before enumerating instances

The compiler and runtime feature is implemented and validated. The
[final single-thread campaign](../query-classes/final/README.md) improves
inference relative to the preceding shared-code experiment, but does not pass
the two-workload inference/process gate or beat the archived fastest path. The
shared-code checkpoint still visits about 55 million Raytrace signals. Its
typed field routes remove many fact reads after visiting a signal. The rejected
absence proof removes many cheap queries but only about 3% of signal visits.
The remaining opportunity is to skip a whole incompatible group before reading
its component, shape, fields or live-node directory.

## Static coverage across stages

For each concrete shared code and local port symbol, collect the operators used
by its immutable body. A checked baked continuation adds a static edge from the
producer's code/symbol to the receiver's code/symbol when Entry substitution can
share that port. The producer operation must have the Entry's actual table;
sharing a port-layout program ID alone is insufficient.

Propagate possible operators over those edges to a fixed point, including
cycles. This predicts possible uses, not future equalities or live facts. Its
unbounded closure can conservatively cover the runtime's bounded fragments.
Unknown continuations create a separate component and its existing boundary
signal; they do not silently append an uncompiled frame. Training, which can
create new continuations, must retain the unfiltered path.

Bake can emit interned operator masks and a class ID per code/symbol. A checked
certificate must cover every current body use and contain the receiver's mask
for every admitted substitution edge. This inductive check establishes future
coverage without trusting a profile as a semantic proof. The mask never proves
an Eq condition; current equality, scalar keys, lifetime and publication order
remain runtime checks.

## An immutable instance class

Record each shared shape symbol's first `(frame, local symbol)` as shared static
wiring. Appending a frame preserves that origin. The origin's concrete code and
symbol select a class covering all possible later uses, so activating a later
stage requires no class change or reindexing of the old signal.

The current `Signal { component: u32, symbol: usize }` has alignment padding on
the measured 64-bit target. A 32-bit class can occupy that space. Order boundary
signals by class, then component and symbol. This changes the representation of
the existing boundary set; it must not add a second per-producer consumer list.
Use a range jump to skip an incompatible class in the existing `TinySet` tree,
and preserve the final ordered fact candidate set. Singletons retain their
allocation-free representation. Native signals require the same static class
check. Stable node fields still store plain `(component, symbol)` addresses;
they do not need a class lookup or a redundant class field.

If the certificate is absent, too large or inapplicable during training, keep
the complete existing path. A fallback must never use a truncated mask.

The explicit `bake-cell-ownership --query-classes true` command emits a
`ownership_fragments.query_classes` certificate. Source profiles remain
compatible because the source digest excludes the complete fragments object.
That digest alone is insufficient: loading checks every current transition's
typed substitution edge. Existing runtimes can ignore this optional fragment
field; marker plan serialization is unchanged. Preparation is charged to load
or setup, never hidden in inference timing.

The Bake work ledger charges class probes and range jumps in addition to the
remaining signal/field work. It does not enumerate skipped members to fabricate
a savings count. Masks and origin wiring are shared static storage. Signals
remain 16 bytes on the measured 64-bit target and no per-instance subscription
or continuation rekey is introduced.

## Publication obligations from the same frozen continuations

The previous execution path widened query receipts to the complete query width
for every rule with a covered Entry, even when no admitted continuation could
consume those ownership anchors. The current fragment plan already proves which
receiver rules can append a frame (`active_rules`). Receipt selection now asks
the same `needs_ownership_entry` predicate that consumes anchors in RHS apply.
Only admitted receivers, or explicit training, gain the full ownership packet.
Other rules retain the original Spine alias plan and its independent receipt
requirements. This removes unnecessary packet expansion and copying before
publication; it is not a new per-producer subscriber graph.

The predicate is evaluated when a query binding is materialized, including the
shared-view path. Training may start after constructing an Executor and must
still capture the necessary anchors. Enabling ownership does not overwrite the
original alias plan, so repeated configuration cannot broaden it accidentally.
Existing direct Entry publications, receipt identity, last-writer ordering,
actual writes and lifecycle notices remain authoritative. This change does not
claim that all publication bookkeeping or the Run barrier has disappeared.

The normal experiment separates the previous shared-code binary, the new binary
without a classification certificate, and that same binary with the certificate.
The middle lane includes receipt pruning and class infrastructure; it is not a
pure receipt-only attribution. Historical fast code is a concurrent reference.
Report construction has its own timer; candidate classification can also change
the order visited by diagnostic checks, which must not be mistaken for faster
RHS execution.

## Costs revealed by the first campaign

The first candidate reduces sum-bits domain signal visits from 58,494 to 12,048,
but adds 48,367 class probes and 34,109 tree range restarts (class counters
include both ordinary constructor and foreign-condition queries). Many rejected
groups may be too small to justify restarting a tree range. An intermediate
variant therefore read at most four further Signal keys before seeking past a
larger group. It retained the next class's first key and did not read rejected
members' components or live-node directories. Its `query_class_key_reads`
counted successful boundary key reads; native signals only contributed a class
probe. It also accumulated counters locally until iterator destruction.

That variant reduced Raytrace range jumps from 11,076,813 to 851,775, but did
not improve inference relative to the simple grouped iterator. It is withdrawn
and preserved only as a reproducible patch and measurement ablation. The final
runtime retains direct class range jumps and excludes the extra lookahead and
counter state. No skipped-group cardinality is manufactured by scanning it.

The first Raytrace campaign also measures roughly seven seconds in report
construction. Its boundary consistency assertion did a linear membership scan
for every referenced port. The assertion now uses the existing ordered set's
membership lookup, preserving the same check. This affects reporting time and
whole-process time; it cannot be counted as faster RHS execution. The final
experiment reports inference, report construction and process time separately.

Runtime binaries for comparisons must be built with `-p eggfuse-cell-runtime`
alone. Building the compiler in the same Cargo invocation unifies its
`serde_json/preserve_order` dependency feature into the runtime, changing JSON
byte order and performance. The initial mismatched build was rejected before
timing admission; parsed states were identical, and isolated builds restore the
strict byte-for-byte state check. The compiler may be built separately to emit
the same checked classification certificate.

## Required evidence

- Correct mask closure for cross-stage chains and cycles, including port-layout
  sharing by different operators and activation after Eq is already true.
- Stable class identity across append, aliasing, partial deletion, retirement
  and recreation; no new instance subscriptions or class rekeying on union.
- Same ordered RHS, effective writes, resumes, state and schedule. Changing the
  boundary set's order must not change the constructor survivor.
- Actual class probes/range restarts and remaining signal visits, plus code
  size, validation/setup cost and allocations. Saved visits alone are not time.
- Paired single-thread sum-bits and Raytrace timing, with the fastest path kept
  visible. No promotion based only on improved internal counters.
