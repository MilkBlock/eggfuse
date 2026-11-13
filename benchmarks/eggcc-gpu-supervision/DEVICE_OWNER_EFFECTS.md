# Owner-backed constructor/copy writes and token refresh

This advances the bounded GPU runtime mechanism, not native Eggcc correctness or
full ruleset saturation. No gradients or new prediction model are introduced.

Constructor and copy kernels now read arguments through the same owner/slot
projection used by matching. A write into an exclusive identity-layout owner
uses that physical row. Shared or remapped payloads require a free owner row:
the writer's logical fields are copied into an independent row before changing
the destination. Other Cells keep their original owner and values. Scalar
numbers/codes/validity follow the same copy, not a separate binding registry.

Detachment is planned before constructor identity resolution, so lack of storage
blocks the effect before allocating an ID. It is committed only for an effect
that actually succeeds. Conflicting constructor witnesses do not consume the
planned owner or advance next_id. Old owner storage is freed only if no present
logical aliases remain. Physical generations advance without wrapping. Explicit
outstanding readers block writes even when a spare row exists. These tests do
not establish a concurrent reader protocol; original Run read boundaries remain
required.

Both kernels preserve effect_pc order, mark tokens dirty, and settle only the
last successful effect. Token refresh now reads current owner-backed roots and
slot validity, without creating a retained dense logical payload copy. It clears
the dirty flag only under the existing completeness/Eq premises. A refreshed
encoding is not proof that a learned prediction or stage saturation is correct.

## Integrated device test

One compiled Metal function runs:

    sealed ownership transfer -> multi-source query -> ridge -> owner allocation
    -> construct H -> token refresh -> subsequent Cell query of H

Three logical Cells use two physical payload rows. The new Cell reuses the
released row, stores the actual new constructor identity 500, and the later
query reads [92, 500] with valid floating inputs. The old source still references
the shared owner. There is no intermediate CPU state readback. Model coefficients
are seeded test weights, not an accuracy evaluation of a trained model.

Additional tests verify shared-copy detachment, preservation of the other Cell's
Eq and scalar fields, pending effects under capacity exhaustion, reader guards,
and no owner/identity consumption for failed constructor resolution. 150 related
tests pass. Existing dense-state behavior remains covered by the same tests.

## Costs and boundaries

Detachment copies the writer's full logical payload and adds a physical owner.
It can therefore undo part of a previous storage merge. Planning scans logical
owner references; the current implementation uses dense masks and functional
array updates that may allocate whole arrays. A zero logical-copy count is not
a byte-transfer or speed claim. No real-workload memory or speed result is given.

These direct kernels and query/admission paths are connected. The higher-level completion controller and nested schedule now support owner-
backed Eq/union completion in bounded tests (DEVICE_OWNER_UNION.md). Automatic
matched-source takeover scheduling, remaining primitives/mutable effects,
retirement/reclamation and whole-workload semantic audits remain outstanding. This
is not yet an owner-backed end-to-end Eggcc execution.

Bake branch 89714c74 rejected an eager queued-union join trial: additional joins
increased retained source frames, signals and Graph memory. This implementation
therefore reports actual alias retention and detachment obligations rather than
counting joins as saved work. It does not relax pending-union or frozen-reader
admission guards or delete logical source identities needed for future queries.
