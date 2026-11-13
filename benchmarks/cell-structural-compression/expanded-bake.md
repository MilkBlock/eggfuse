# Expand selection from one actual catalog execution

The accepted selected-Unit catalog was captured once (1,428 Runs), producing
1,588 fragment records, including local pair projections. These overlap and do
not count as distinct executions. Offline Bake explored depth 4/8/16 and budgets
256/1024/4096. The largest budget also admitted one observed activation, rather
than requiring two. This affects selection only, never typed proof obligations.

The previous limits were hardcoded. They now default to the same 256 fragments
and 16,384 instruction handles, with explicit bounded overrides (up to 4,096
fragments and 1,048,576 handles). Zero activation thresholds are rejected. Loading
an expanded catalog still derives every substitution. Forty-one ownership tests
pass, including expanded limits, invalid routes, and same-source snapshots.

Three distinct extremes were executed, charging the whole Graph:

| Budget / extent / minimum activations | Graph bytes | Versus accepted 2,502,270 |
|---|---:|---:|
| 1024 / 16 / 2 | 2,501,902 | -368 |
| 4096 / 4 / 1 | 2,523,142 | +20,872 |
| 4096 / 16 / 1 | 2,646,630 | +144,360 |

All three have identical final-state digests. They have not received full Run
admission; none replaces the accepted configuration. More paths and deeper
components are not sufficient credit for runtime memory compression. The largest
candidate selects 1,371 paths, yet uses more Graph storage.

These results motivated the user's requested multi-input batched learning. See
`../cell-batched-learning/README.md` for the shared-catalog experiment. Expanded
budgets remain an opt-in selection facility, not a default runtime cost.

Reproduce with `train_unit_closures` on `unit-selected-program.json`, then
`bake_unit_closures PROGRAM PROFILE OUTPUT --expanded`. The text result records
all nine offline candidates and the three executed configurations. Generated
programs and trace files are not tracked.
