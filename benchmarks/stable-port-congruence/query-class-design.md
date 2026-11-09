# Compile future operator coverage before enumerating instances

This is the next experiment, not an implemented or admitted speedup. The
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
Use a range jump to skip an incompatible class, and preserve the final ordered
fact candidate set. Native signals require the same static class check.

If the certificate is absent, too large or inapplicable during training, keep
the complete existing path. A fallback must never use a truncated mask.

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
