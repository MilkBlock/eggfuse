# Compile worker input capture from the Cell definition

The last actual Raytrace execution still admitted 203,620 root jobs and ran
216,430 scheduler jobs after removing most whole-table waits. It retained
2,151,665 ownership signal bindings and almost four million key queries.
The existing 408-recipe sum-bits catalog exercises inherited inputs, but adding
more recipes cannot remove the runtime's repeated classification of the same
instruction operands. The typed Cell definition already supplies slot
definitions, instruction order, constructor regions and the terminal Unit tail.

Previously root, local-prefix and dependent admission each walked all remaining
constructor operands and optional Unit operands. Each instance filtered literals,
checked whether a slot was already present, and searched definitions to distinguish
an external value from a result that its worker would produce. Repeated uses
performed that classification again. A local prefix also used an earlier
freshness boundary than the current instruction position.

The existing worker Plan now compiles one input span per eligible terminal entry.
Eligibility comes from the same root, isolated-tail and dependent-cone proofs
used by admission. An impossible local continuation is rejected before input
capture; noneligible positions carry no input span.
It preserves first-use order, eliminates duplicate slot demands, and excludes
results produced at or after that entry. Unit-only demands follow constructor
demands, with a separate end position so a constructor-only continuation does
not read them. Each demand retains its defining boundary: a local prefix keeps
its earlier results in the original fact slots rather than capturing them as
inputs. Identical ordered spans within a Plan share one slice.

All three admission paths consume this layout directly. A missing external
value is still fetched through the ordinary parent projection/canonicalization
and inserted in the same instance. Its existing values then move through the
same slot lease. There is no new binding copy, runtime fact graph, consumer list,
marker relation or separate history. The three operand scans and definition
searches in source capture are deleted, rather than retained as a fallback.

Worker internal operands also use a direct slot-to-definition array derived
from the same template. This replaces their repeated binary search for the
defining instruction. Existing actual aliases take precedence; this index does
not infer that a logical producer owns a constructor's returned result. Shared
peer resolution, retained prefix fields, exact candidate checks and equality
canonicalization remain authoritative.

Compiled span/demand storage and the direct definition array are charged in
the existing worker Plan payload. New layout-read and slot-check counters charge
actual preparation. Captured value reads/writes remain separately charged and
are not credited as eliminated work. Compiler derivation and larger templates
can affect Program loading, so inference and process/load time remain distinct.
The local-construction report advances to v5. Work credit requires both new
counters for v5 and charges them as work; older versions remain readable with
zero for those previously unmeasured counters. The removed operand scans were
not fully counted in older reports, so cross-version credit is not evidence of
an improvement. Frozen execution time remains the performance comparison.

Only already-proven queued terminal regions use these layouts. Mutable effects,
missing inputs, arbitrary partial regions, pending equality, source-order
conflicts and Run visibility retain their previous obligations. A capture does
not grant an early value to an internal result or move a Unit effect across a
boundary. Nonqueued local evaluation retains its original input access.

The new runtime fixture executes both a root and an existing local prefix with
repeated parameters projected from a parent, plus an external value used only
by the final Unit operation. Worker execution must equal ordinary execution,
including a later union/repair. It requires one external read for the local
prefix and two for the root, while preserving implicit internal results. A
second check ensures constructor-only capture does not fetch the later Unit
input. Existing integration tests retain foreign results, learned continuation,
every fixture Run graph, deletion/recreation, binding order and first errors.

This is an actual standalone Cell CPU change, not a native egglog patch.
Full workload acceptance and one whole-control/previous/candidate timing lease
must decide whether the removed scans outweigh new compiled storage. Root
queries, source port binding and the scheduler population are not eliminated by
this change; it is not a claim that all cores are occupied.

Validation before the workload experiment: queue job 501 passed 224 runtime
tests, 119 integration tests and 76 ownership tests with storage metrics. The
work-credit checks additionally require each new counter and verify that an
extra read/check costs one operation, while accepting historical v4 reports.

The first frozen version, `831acacc`, passed full ordinary sum-bits, Raytrace
and learned-catalog validation (job 506, including native sum-bits acceptance).
It compiled a span for every terminal-region position, however, and grew
Raytrace's worker Plan payload from 4,347,184 to 71,855,024 bytes. Job 508 was
cancelled while still queued, before any timing sample. Applying the existing
admission proofs during layout derivation removes unreachable suffix layouts;
a 512-operation independent-prefix regression checks that only its final
eligible entry retains a demand. The first version is not a performance result.
