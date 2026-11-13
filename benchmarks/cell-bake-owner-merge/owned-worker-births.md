# Canonical ownership continues constructor Cells on workers

The preceding activation-bounded Raytrace catalog saved 2,974 of 4,332,972
queries, without expanding worker mutation scope. The installed catalog already
provides source Entry wiring, component symbols and actual-result demands.
The next opportunity is to execute the existing fresh-cone instruction plan
under canonical ownership, preserving those proofs through worker suspension.
Adding more recipe IDs does not remove the ownership backend rejection.

This change gives both ordinary execution and batch admission the same Entry
setup. Suspension moves that Entry with the original Cell; adoption restores it
before births and clears it on success or error. Exact root hits and prepared
resumptions supply their actual returned witnesses. A shared worker cone retains
only foreign returns before its first local birth, and only while an active
Entry still needs result evidence. These transient candidates are validated in
source order before the first birth; no bindings, consumers or retained history
are duplicated. Candidate count and allocated bytes are charged separately.

The worker fills actual row storage and resolves duplicate pure roots through
the existing peer result slots. Source adoption still calls `activate_fields`,
which installs ownership and binds the compiled ports exactly once. It no longer
replays constructor lookup/key preparation for the completed cone. The old
registration fast path still assumes `owned:false` and reverse subscriptions;
it remains ineligible for ownership rows. Unit table registration can retain
its independent eligibility. Stable-port, digest and local-union backends keep
their existing birth-time constraints.

This is a worker construction takeover, not parallel ownership registration or
complete removal of serial publication. No claim that all threads are full is
made. Source/effect/error order, union epochs, actual foreign result identity,
Run visibility, deletion/recreation and residual queries remain authoritative.
The newly possible in-flight source observation is `pending_completion`, not a
proof of a saturated RHS. Tests still require exact graphs/bindings and exact
source-ordered composition proposals; they no longer require serial and
parallel saturation diagnostics to have identical pending populations.

Job 423 passes 119 compiler/runtime integration tests, including three new
ownership worker cases. Job 426 passes 217 runtime unit tests and 76 ownership
tests with storage instrumentation, plus the no-default-feature compile.
Workload validation and timing follow as a separate experiment; these tests
alone do not establish a speedup. Comparisons use entire control then candidate.
