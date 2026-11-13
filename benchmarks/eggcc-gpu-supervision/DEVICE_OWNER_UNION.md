# Owner-backed Eq completion and nested Run execution

This connects the existing bounded exact Eq/congruence kernel to physical owner
storage and the completion/schedule controller. It is a local GPU runtime proof,
not whole Eggcc correctness, learned-completion accuracy or performance evidence.

## Stable identities and shared roots

Union operands are read through current logical projections and remain exact
stable IDs. During closure, logical Eq-use masks scatter into a physical-field
mask. Each referenced physical field gets the current registry root; every
logical alias observes that result and is marked token-dirty when its own Eq
state changes. Slot IDs and owner projections are unchanged by union. Root
refresh does not detach shared payloads or duplicate maintained logical roots.
Scalar/Eq alias conflicts and stale owner generations prevent settlement.

Completion now validates typed slots through owner reads, executes ordered union,
copy and constructor operations, reads scalar metadata from owner storage, and
refreshes each affected logical Cell token. Existing external-coverage and bounded
closure checks remain live. A budget limit or missing external view cannot advance
an unfinished union's effect_pc. Initial root columns are created in the proper
storage representation without falling back to a dense logical array.

An actual Metal compiler limit surfaced during integration: the accumulated
boolean invalid-state chain exceeded fused-kernel argument buffers. Closure now
collects flags and reduces them on GPU instead of building one long elementwise
OR chain. Numeric/semantic conditions are unchanged; no CPU synchronization or
compiler disabling was introduced. These reductions have a cost and are not a
performance claim.

## Integrated closed-family test

One compiled Metal execution performs:

    source payload takeover -> query/ridge/admission using freed owner
    -> union and congruence closure -> constructor H -> token refresh
    -> quiet Run -> next ruleset -> query H and admit its Cell -> quiet completion

The schedule consists of two nested saturation commands. Four logical Cells use
three physical payload rows. Successful Run stages are [0, 0, 1], with semantic
change flags [true, false, false]. Two new Cell records are admitted and one
constructor identity is allocated. Stable values [7,100,200,201] and subsequent
H inputs [200,201] survive shared-root updates; the source's roots become [7,7].
No intermediate device state is read back in that execution.

The same initialized local problem is run through the prior dense storage path.
Final valid slots/roots, logical keys, lifecycle flags, effect PCs, logical
generations, registry roots and Run/token/effect logs agree exactly. Floating
tokens agree within 3e-6. This compares final logical state plus Run work logs,
not exported full graph snapshots at every boundary or native egglog execution.
The small fixture supplies explicit closed-world query/visibility coverage; it
does not prove the real Eggcc catalog complete. Ridge weights are seeded test
weights, so no prediction-accuracy result is claimed.

Other tests cover all aliases of a shared source refreshing together, unchanged
stable IDs, stale physical epochs, incompatible Eq/scalar aliasing, and pending
unions under closure-budget/external-coverage gaps. 154 related tests pass.

## Outstanding requirements and costs

Physical Eq-use collection adds scatter work and logical aliases still each need
their own floating representation. The exact closure kernel retains dense
congruence comparisons. Fixed arenas and owner directories have not demonstrated
whole-workload memory or speed gains. Freeing payload capacity does not retire
logical source records or native routes.

The test installs a proved takeover before the schedule. Automatically compiling
and invoking further takeovers from actual successful matches inside Runs still
requires retaining the necessary source/generation evidence and discharging live
readers. Full initial-graph import, broader scalar/mutable rules, deletion and
retirement, CPU audit/correction integration, real multi-ruleset coverage proofs
and actual Eggcc end-to-end benchmarks remain unfinished.

Bake reference remains 89714c74: more eager joins increased retained source state.
No union/frozen-reader guard is removed and no join count is treated as a memory
saving. This change specifically verifies later Eq propagation through relocated
physical fields, which was missing from the earlier sealed-state takeover tests.
