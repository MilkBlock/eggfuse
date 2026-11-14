# Read an owned constructor index without joining the whole producer

The last actual Raytrace execution continued construction and registration on
workers for 91,637 Cells, but encountered 1,552 whole-table waits in 1,567
background regions. Source admission overlapped only 24,196 instances, down
from 64,905 before fusion. Inference did not improve. The guard ran before
trying the compiled root continuation, so even an existing result or an
independent fresh root waited for an entire producer wave.

The merged activation-bounded Bake catalog reuses existing Entry/result capture
instead of enabling another population of records. Its latest Raytrace witness
experiment saved only 2,974 point queries; it cannot by itself remove this
runtime ownership fence. The current typed root plan already proves that each
tail constructor depends on the root or its descendants and has no remaining
ordered/fallible suffix. Use that proof and the actual canonical index before
adding more recipes, bindings or runtime consumer relationships.

During eligible open-admission registration, the existing table index now has
one shared allocation. The worker retains the sole mutating lease. A proven
root admission can read its bucket under a short read lock, while registration
takes a short write lock per inserted row. Ordinary source writes and arbitrary
queries still cannot access a leased table. Closed registration regions and
unleased indexes retain their direct, unlocked access. Returning the owner
unwraps the same allocation; it does not copy or merge a second index.

Root admission runs before the whole-table fence. An exact hit fills the current
instance using its actual witness, including a foreign owner or hidden existing
constructor. An exact miss can queue the already-compiled fresh cone. The
ordinary fallback still obtains the table owner before constructing. No source
publication or port binding is moved to an unordered thread by this change.

Two exclusions make the read valid while new rows are being registered:

- The key hash cannot match an in-flight root hash. A hash collision remains a
  conservative fence; a digest never proves equality or grants a missing value.
- No key operand may reference a Cell in the unclosed wave's original source
  ID range, including nested Eq values and earlier already-adopted Cells. The
  compiler's fresh-cone proof makes every internal newly registered key depend
  on such a value. Keeping only unfinished owners would be insufficient: later
  workers can still use results of earlier adopted Cells.

The wave already retains its original source order and root hashes. The new
range is two IDs, not a producer-consumer graph. Pending next-wave dependencies,
settled ownership keys, frozen equality epochs, exact key comparison, source
error order, foreign-result identity and Run publication remain live. Open
registration still requires empty original fact frames, so all earlier visible
facts remain available to the source lookup. An absent worker-owned fact slot
cannot conceal an exact root candidate once both exclusions hold.

Costs include the Arc/lock allocation per leased table, row write locks, root
read locks and checking the wave range. Registry byte accounting charges those
allocations. The new root read/hit/job counters measure actual takeover, not
saved key comparisons or thread utilization. Existing result reads are still
source work. The bounded next buffer can still wait when full, and unresolved
same-table effects still require owner return.

A deliberately paused producer verifies that the source can reuse an existing
same-table witness, admit a new same-table root, and construct in another table
before releasing the worker. It then accepts one earlier Cell, invalidates the
later suffix, runs the newly admitted root, and applies union/repair. Separate
tests cover a shared bucket's single ownership, exact hash-collision misses and
hidden witnesses. Integration fixtures compare every Run graph, binding order,
foreign returns, learned composition, deletion and first-error behavior.

Full workloads and sequential timing must compare against both the prior
table-owned implementation and the original merged-Bake control. Inference,
source overlap, remaining table waits, allocation/event bytes and port binding
all remain part of acceptance. Removing a whole-wave wait by introducing short
locks is not itself evidence of a speedup or fully parallel execution.

Job 485 passes 222 runtime tests, 119 compiler/runtime integration tests,
76 ownership tests with storage instrumentation, 100 default-backend runtime
tests and a no-default-feature compile. An earlier new fixture incorrectly
started its next RHS while the prior source frame was still active; it now
uses the ordinary promotion boundary. Another test invocation omitted the
existing `iterative-bake`/transfer-audit feature; the final invocation includes
it. Neither failed invocation is counted as acceptance.

## Full workload coverage

Implementation `1f1ce92f` passes job 487's native sum-bits final-state acceptance
(`pass`). Ordinary sum-bits and Raytrace retain exact final state, all 1,428 /
16,883 Run summaries and logical effect counts. The unchanged 408-recipe
sum-bits catalog also retains final state, all 1,428 Run summaries and effects.
Raytrace and the learned catalog are differential checks, not native proofs or
full-program per-Run graph snapshots.

| Raytrace work | Table-owned `843c1ca0` | Shared root admission `1f1ce92f` |
| --- | ---: | ---: |
| Background registered Cells | 91,637 | 91,541 |
| Background registration regions | 1,567 | 1,565 |
| Whole-table wait encounters | 1,552 | 99 |
| Root reads of the live index | 0 | 69,135 |
| Existing results reused through those reads | 0 | 684 |
| Fresh roots admitted through those reads | 0 | 68,451 |
| Source instances admitted with a producer outstanding | 24,196 | 106,823 |
| Empty event polls | 19,832 | 100,827 |
| Scheduler jobs | 216,434 | 216,430 |
| Registry bytes | 12,733,032 | 12,758,704 |
| Returned frame bytes | 20,267,536 | 20,290,656 |
| Registry event bytes | 4,318,080 | 4,505,280 |
| Key queries | 3,974,623 | 3,974,601 |

Whole-table waits fall 93.62%, but the original queries mostly remain and all
2,151,665 ownership signal bindings still occur. The slightly different task
and lookup counts can follow event grouping; logical effects are exactly equal.
New locks and more polling are paid work. Empty polls already use an atomic
readiness check, so their count alone does not establish mutex contention.

The covered path remains absent in both sum-bits variants. Coverage in Raytrace
therefore cannot explain their timing changes. These counters come from separate
validation executions, not the timed samples; diagnostic nanoseconds from them
must not be divided by a timing median to estimate idle time. The new index
sharing, guard order and additional source overlap are measured together.

## Sequential timing and decision

Job 491 completes the entire control, then the entire previous experiment,
then the entire candidate under one timing lease. All 114 process-boundary
guards pass. Each group has one warmup; sum-bits variants have five measured
samples each and Raytrace has three. These are fresh same-lease comparisons,
not absolute times reused from earlier experiments.

| Inference median | Control `62c5f984` | Previous `843c1ca0` | Candidate `1f1ce92f` | vs. previous |
| --- | ---: | ---: | ---: | ---: |
| Sum-bits | 24.317 ms | 32.701 ms | 30.681 ms | -6.17% |
| Raytrace | 4.882279 s | 5.479990 s | 5.352683 s | -2.32% |
| Existing sum-bits catalog | 23.867 ms | 32.807 ms | 32.350 ms | -1.40% |

All medians improve relative to the preceding experiment in this trial, but
remain 26.18%, 9.63% and 35.54% slower than the original merged-Bake control.
**Speed admission still fails; the branch stays experimental and unmerged.**
The prior Raytrace samples rise from 5.325463 to 5.693962 seconds and overlap
the candidate range (5.339204 to 5.366571). No samples are removed. This short
grouped trial does not isolate a stable 2.32% code effect, nor establish that
the removed table wait accounted for most runtime cost.

Actual lookup and job counts remain almost unchanged. The source still performs
root lookup and admission before each worker cone, including scanning its tail
operands to recover parent-projected inputs. The next candidate is to derive
only external input demands from the same typed Cell plan, then consume that
layout directly. This would delete repeated operand/definition scans without
adding a binding copy or runtime dependency graph. It is not implemented in
this checkpoint and receives no savings credit. Exact captured values,
foreign result identities, pending dependencies and error order must remain.

`shared-root-admission.json` records sample values, hashes, validation, work and
the admission decision. Passing semantics and removing a structural wait do not
establish the requested overall parallel speedup.
