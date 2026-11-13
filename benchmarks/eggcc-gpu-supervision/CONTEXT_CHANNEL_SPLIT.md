# Separate contextual channels: numerical acceptance unfinished

Two opt-in whole-Cell GPU models compare historical/adjacent source separation.
Both use eight channels, the same chronological source edges and full input
interface, fixed role projections and unchanged output encoding. `class-history-repeat`
places the same four role channels in both halves, normalized by sqrt(2).
`class-history-split` places adjacent sources in the first four channels and
historical sources in the last four. Route vector norms match; both models have
the same feature width and fixed random feature matrix. No GPU dynamic branch
or backpropagation is added. Historical source lifetime remains unproved.

Models use the same expanded training manifest and original validation manifest.
Boundary policies use the expanded validation manifest. No test-driven selection
is performed. Source depths and edges are unchanged from broad history; storage
and readout width increase compared with the four-channel baseline.

The repeat control passes numerical checks. Its validation-selected MSE policy
recovers 4,231/5,454 test partitions with 723 false and 1,947 missed Eq pairs;
partition selection recovers 4,329 with 839 false and 1,839 missed pairs. These
are standalone boundary diagnostics, not committed mutations or native acceptance.

The split model passes whole-token numeric checks, but boundary selection aborts
in validation: all scores are finite and within the numeric tolerance, maximum
absolute CPU/GPU difference 8.682697781647875e-6, yet **two classifications cross
the fixed 0.5 threshold**. The stricter threshold-agreement gate remains intact.
No split-model test result is reported, and no superiority claim is justified.
`context-split-validation-failure.txt` retains the exact failure. The next step
is to identify the near-threshold queries and define an audited uncertainty path,
not silently widen tolerance or count the incomplete run as a pass.

Reproduce training using `multi_entry_ridge.py` with `--channels 8` and each of
`--encoding class-history-repeat` / `--encoding class-history-split`, keeping the
expanded training/original validation/test paths from the historical experiment.
Run `select_eq_readout.py` with each resulting model and the expanded validation
manifest. Use fresh output stems matching each mode. The three successful JSON
reports retain provenance; binary weights and raw diagnostics stay on the SSD.
The route test verifies disjoint channels, preservation of role vectors and
matched norms. Focused route, history, replay and boundary tests pass (26 tests).
The generic readout error now includes numeric metrics so future failures can
be diagnosed without weakening acceptance.
