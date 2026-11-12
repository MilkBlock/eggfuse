# Owned RHS admission pipeline

This is the actual standalone Cell CPU, not native egglog performance. The
control is `f5bd0c91`. Frozen catalogs and source programs are unchanged.
This checkpoint records execution work and correctness, without a new timing
campaign. The previously measured whole-runtime regression remains unresolved.

## Opportunity and proof

The last catalog executed 81,258 constructor jobs in 3,388 bounded RHS queues
on Raytrace. Completion events already allowed source adoption to overlap the
workers, but filling a queue still stopped **admission of every later Cell**
until that queue had drained. Its 14,028 dependent admissions also show that
batch-local sharing must be preserved, rather than replacing it with an
independent-job-only executor.

The existing Cell definitions prove fresh constructor regions and typed
old/new Unit tails. The new admission proof requires no union anywhere in the
template, a job reaching the terminal region, and no earlier pending union or
dirty repair at dispatch. Transfer stops, unproved suffixes and short queues
keep their existing path. Ordinary instructions, actual result slots and the
source Run boundary remain authoritative; no additional fact representation
or per-producer consumer list is introduced.

A proven queue now transfers its existing jobs and effect owners to a bounded
background producer. The source continues admitting the next queue while that
producer computes. Independent jobs construct their original rows; dependent
jobs retain the existing finite peer directory, result slots, exact matching
and permitted duplicate computation. The source polls an ordered completion
prefix and adopts the original owners. Table-owner registration and exact Unit
duplicate invalidation remain connected to those actual rows.

Two original owner buffers are reused: one executing and one admitting, each
bounded to 64 parked Cells. The result mailbox also has only one bounded wave.
Empty polls use atomic readiness flags before locking. Worker panics join their
nested readers and wake the source; a missing result cannot silently strand
the receiver. The immutable parent epoch is released only after its producer
has stopped using it.

When a new constructor key refers to an older in-flight Cell, the source now
advances only until that Cell's required prefix has been adopted. Later jobs
in the wave may continue. These are exact owner references, not Bloom guesses.
Within the next unsubmitted queue, the original shared-job admission still
applies. Unproved dependencies and ordered writes retain the ordinary drain.

Across Runs, completed instances still supply the existing Shared Entry
projections at the original visibility boundary. This iteration discharges the
stop-and-join admission work within those compiled regions; it does not add
new dominators, permit next-Run reads of partial effects, or parallelize compact
Function-ID assignment. Source selection, effect order, error order, actual
foreign constructor witnesses, retirement and generation checks remain live.

## Measured work, not a speed claim

Same release features `cell-absorption,view-ports,parallel-publication` and flags:

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| All constructor jobs | 81,258 | 81,223 |
| Jobs in admission-overlapped waves | 0 | 41,789 |
| Such waves | 0 | 758 |
| New instances admitted while producer jobs remain unfinished | 0 | 17,191 |
| Cross-wave input waits narrowed to the needed Cell | — | 67 |
| Those waits released while other producer jobs remain unfinished | — | 5 |
| Ordinary dependency flushes | 217 | 219 |
| Total key lookups | 4,027,718 | 4,027,756 |
| Queue payload capacity, cumulative bytes | 80,107,640 | 95,111,216 |
| Completion payload capacity, cumulative bytes | 137,432,512 | 143,118,464 |

The 17,191 overlap observations are about 7.1% of the 243,426 admitted
instances. They check actual unfinished jobs **after** starting the instance,
not callbacks waiting in a queue. They depend on scheduling and are neither
thread utilization nor saved elapsed time. Most narrowed input waits did not
observe other jobs still unfinished at release; no broad stall-elimination
claim follows from them. Source admission itself still runs on the coordinator.

Additional owner buffers and event handling cost memory and work. The final
execution made 18,588 polls, including 16,358 empty polls, and 2,995 dependency
probes. There were 38 extra key lookups. Logical effects and the 129,123 Unit
candidates / 43,783 invalidations stayed exact. Whole-wave `wait_ns` spans now
also include overlapped admission; event receive waits are condition waits,
not worker idle samples. Work-count runs may overlap compilation and are not
used as performance comparisons.

sum-bits has at most 15 ready jobs, so it takes no background admission wave.
It retains 255 jobs and 14,012 key lookups. This is an explicit coverage limit,
not evidence of acceleration on that workload.

Intermediate work records are preserved. The first implementation repeatedly
reallocated the next owner buffer and drained on cross-wave dependencies. The
next revision reused two buffers and narrowed those dependencies, but lacked
the additional earlier-repair admission gate. Only the final runtime includes
all three changes; differences among these records are not controlled timings.

## Validation

151 runtime tests and 85 integration tests pass across the checked paths.
Handshake tests require source admission and first-prefix retirement before a
blocked producer can finish, preserve source result order, and verify panic
wakeup and no loss of undelivered results after producer completion. A 320-Cell
integration fixture exercises actual background waves, duplicate Unit writes,
same-Run invisibility, delete/recreate, union and a late arithmetic error. Exact
Run snapshots, binding audits and the surviving source-error prefix agree.
Union suffixes and an earlier queued union explicitly retain their fence.
Forced hash/Bloom collision checks pass. All-feature, sparse-only and legacy
builds pass, as do the README compile/run/single-repeat bench smoke commands.

Frozen sum-bits/Raytrace final states, all 1,428/16,883 ordered Run summaries and
logical effect counters match the control exactly. Native sum-bits acceptance
is `pass` using saved exports whose CPU state hash matches the new execution.
Raytrace remains an exact differential check, not an extended native proof.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-admission-pipeline/semantic-acceptance.json
python3 benchmarks/cell-admission-pipeline/check.py out/cell-rule-retirement out/cell-admission-pipeline benchmarks/cell-admission-pipeline/results.json
```

The remaining large boundaries are source root admission, shared index/identity
adoption and ordered effects. This change overlaps a proven part of those
stages; it does not establish full worker ownership or multi-core saturation.
