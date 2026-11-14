# Higher-reuse synthetic continuation inputs

The generator now exposes `--reuse` (default remains 0.35). It controls reuse of
existing typed Eq ports while building random rule query fragments. The seed,
reuse probability and fragment count are replayed by the existing validator.
This is not a model-guided filter or a new source of real Run training values.

Using the existing three Eggcc context rules, seeds 20261600..20261603 and
`--reuse .8` produced three bounded-saturation inputs and one rejected input
(oracle budget exhausted). The rejection remains recorded. Actual GPU
predicted-source feedback with the existing synthetic-only head produced 22
accepted/labeled samples, eight generated-source consumers and 14 physical owner
row releases across the three successful cases. CPU semantic and label audits
pass. This is the selected-family standalone prototype, not full Eggcc GPU
execution. No timing comparison.

The verified witness-pair census still found zero distinct-logical/same-physical
pairs, despite five logically repeated pairs. Exact query fact deduplication is
present, but this experiment does not prove it explains all missing cases.
Owner-aware model width was therefore not enabled for this training run.

Adding these three inputs to the prior 25 synthetic contexts and refitting the
same ridge (alpha 10, no gradients) regressed development validation:

| Case | Previous exact states | Expanded exact states |
|---|---:|---:|
| GCD | 25/41 | 19/41 |
| LCM | 80/99 | 30/99 |

Direct-source GCD dropped 17/26 -> 13/26; direct-source LCM 60/78 -> 10/78.
The new head is **not promoted**. These results show distribution sensitivity,
not that synthetic training is impossible. Additional data must be paired with
feature/target ambiguity and coverage analysis; successful graph audits alone
do not establish a better learned predictor. GCD and LCM are recurring development
cases, not pristine holdouts.

`dense-reuse-training-results.json` preserves the generation outcome, execution
counts, owner census, model metrics and exact fit command. Large captures and
weights remain on the external SSD. Five generator tests pass, including replay
at reuse 0, .8 and 1 and rejection of invalid probabilities. The coverage tool
now accepts `--sources DIRECTORY` when captures and input documents are stored
separately; it still checks both source replay and capture hashes.
