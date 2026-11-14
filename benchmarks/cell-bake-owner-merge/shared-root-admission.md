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
