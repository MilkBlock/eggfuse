# Existing witnesses, residual matching, fragment publication

Scope: standalone Cell CPU, not the native egglog runtime. Starting point:
`762beb0f`, frozen `out/condition-bake/runtime-query-classes-final`.

The preceding Raytrace execution still performed 1,962,583 port-domain queries
and 8,475,767 key candidate checks; query-class filtering did not reduce these
counts. Search took 5.748 s, RHS 3.687 s and repair 0.927 s in the previous
measurement. These are an opportunity inventory, not a prediction of speedup.

## First: consume existing witnesses before another complete lookup

Checked `multi_stage.routes` already identify producer effect positions for
consumer atoms. A committed Entry identifies its current producer. Reuse that
position for a complete-key read, after checking the current live row, table,
arity and every key value. No new history, per-producer consumer list or cached
equality is required. Failure is a positive-hint miss and uses the old lookup;
it is never a proof that the table contains no match.

The complete functional Spine path first tries its existing history/root cache,
then this producer-local witness. It obtains the producer once per eligible
seed. The residual register path additionally checks seminaive ownership and
retains its original expansion, primitive guards, assignment checks and order.
See `register-prefix-design.md` for that gap and its certificate.

Charge context/route probes, donor reads, stale reads, verified witness hits and
remaining global lookups separately. A hit discharges an actual fallback lookup,
not a committed mutation. No new Cell or receipt packet is allocated for a hint.

## Fragment publication and completion scope

After the witness/prefix checks, reuse immutable fragment
wiring and existing instance locations for internal delivery. Preserve ordered
last-writer selection, receipt forwarding, visibility, and independently timed
consumer Runs. Expand completion read scope only with complete candidate and
input-dependence proofs; commits retain source order and invalidated reads fall
back. Exact implementation, checks and measured costs will be recorded here as
each part is implemented. No speed claim follows from reduced counters alone.

The publication candidate uses the existing shared `anchor_ops` code. For an
Entry-owned permanent table, a fragment stores its source-step slot, starting
ordinal and compact receipts. After repair, each receipt is forwarded and
checked visible. The existing Entry publication slot, rather than another
temporary hash table, selects the greatest source ordinal. Only winners create
published cursors. Unready receipts remain in their original fragment until a
legal publication boundary. Non-owned tables, missing receipts and visibility
changes retain the complete old path. This removes the intermediate receipt-map
insert/remap and the second Entry lookup; it does not skip observable RHS writes
or run consumers ahead of their source schedule.

The final scope extension targets a separate artificial boundary: completion
read batches currently stop when a shape exceeds the 16-site local condition
budget, although the stable-port domain still supplies a complete ordered
candidate set. Such a source can use exact port-key guards for every candidate
and participate in the same immutable read epoch. The local condition budget
stays bounded. No candidate prefix may be treated as complete. The unchanged
input-root read set invalidates later cached tasks when either union operand
touches an input class; output/epoch/visibility refresh and ordered retirement
remain at commit. Count these exact-domain tasks and their candidate preparation
separately from shared-condition tasks, and do not infer parallel speedup from
larger batches.

Implementation and final evidence are recorded in [README.md](README.md),
[validation.json](validation.json) and the [normal campaign](normal/README.md).
The actual workloads produced zero local witness/prefix hits. The experiment
does not pass the joint inference/process performance gate; these routes must
not be credited for the small observed combined timing changes.
