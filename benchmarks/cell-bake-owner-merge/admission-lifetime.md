# Isolate Program admission-scratch lifetime after the merge

The same frozen Raytrace inputs regress after `437d1e7c` in two sequential
trials (+8.47% and +3.31%). Graph/ownership/maintenance work counts are identical.
Both inputs carry a context admission policy, so the new unadmitted-plan removal
branch is not executed. Completed-owner transfer is not called by this runtime.
The other changed admission functions run during offline discovery/installation.

One activated source difference remains in Program loading: moving the admitted
`Vec<bool>` into the new `if let` releases it immediately after cut compilation.
The old code borrowed it and retained that scratch until the end of Program
construction. Borrow it again while preserving the new omission of unadmitted
plans. This is a controlled allocation-lifetime/code-generation intervention,
not evidence yet that allocation or code layout caused the regression. It adds
no execution path, query work, instance storage or scheduler synchronization.

A new Bake observation cannot diagnose this regression: the last original-source
witness experiment already establishes 280 fewer queries but no inference gain.
No cross-Run work is claimed saved by this diagnostic. Typed queries, admission
proofs, source effects, publication, visibility and residual matching must be
identical. Compare a frozen candidate to the actual merged runtime before
accepting any performance claim. If the intervention does not help, remove it.

Job 339 passes all 19 compiler integration tests, including context admission,
re-admission and unfiltered-policy cases, and the no-default runtime compile.
Full frozen workload validation and sequential timing follow. The original
witness catalog has only nine multi-anchor recipes out of 408, so changing
anchor preference alone is not a plausible broad-coverage follow-up.
