# Independent LCM validation and dynamic completion coverage

The frozen five-program model is evaluated on another original validation program,
LCM, at saved Run boundary 514. It is not refitted or threshold-tuned on LCM.
Rules 283/290/293, exact effect authority and the existing owner-transfer protocol
remain unchanged. This is a selected-family GPU prototype, not full Eggcc or an
accepted learned replacement for exact execution.

## Real execution

LCM generates 99 Cells; 21 consume generated sources. Both exact-source encoding
and predicted-source feedback complete three Runs, release 25 owner rows and pass
all independent unlowered CPU graph and per-rule match comparisons. The first Run
requires 52 new original constructors, making it materially different from GCD.

The two captures have 454 identical shared symbolic arrays and identical CPU target
tokens. All 21 generated-source consumers change floating inputs under feedback;
one direct selected-source instance also changes through its boundary neighborhood.
Maximum feature change is 0.547907 and prediction change is 0.127894. This is real
predicted-source consumption, not a replay with the experimental flag ignored.

| Prediction metric | Exact source encoding | Predicted generated sources |
| --- | ---: | ---: |
| Exact partitions | 82/99 | 82/99 |
| Direct-source exact | 71/78 | 71/78 |
| Generated-source exact | 11/21 | 11/21 |
| False pair merges before closure | 10 | 9 |
| False pair merges after closure | 13 | 13 |
| Missed pair equalities | 35 | 35 |

CPU-correct target tokens decode 99/99. The learned errors therefore persist even
before feeding predicted sources back. GCD's zero observed false merges did not
generalize to LCM. No candidate is promoted to authorize graph mutations.

## Count the positive work, not just complete partitions

`audit_device_match_readout.py` now separately reports the dynamic quotient queries:
true positives, false positives, false negatives, precision and recall. Static
proven Eq pairs are excluded and quotient duplicates are counted once. These
counts differ intentionally from the expanded pair counts above. Empty precision
or recall denominators report null, not artificial perfection.

It also reports the baseline which performs *no learned Eq completion*, retaining
only the static proof. This exposes how many complete partitions need no additional
positive prediction.

| Validation with feedback | GCD | LCM |
| --- | ---: | ---: |
| Static-only exact partitions | 30/41 | 77/99 |
| Model exact partitions | 35/41 | 82/99 |
| Dynamic quotient queries | 206 | 524 |
| Positive dynamic queries | 18 | 37 |
| Correct positive predictions | 8 | 16 |
| Incorrect positive predictions | 0 | 4 |
| Missed positive predictions | 10 | 21 |
| Dynamic recall | 44.44% | 43.24% |

Thus 85.4% complete-partition accuracy on GCD does not mean the model completes
85.4% of the new Eq work. Improving recall while controlling false merges remains
essential. These diagnostics change no acceptance rule or decision threshold.

## Observable context remains distinguishable on these samples

The combined 269 samples (five training programs plus exact-source GCD and LCM)
have 14 conflicting resident-input groups, with empirical maximum 238/269 exact
predictions. Extended boundary vectors have 255 distinct inputs and no conflicting
labels. The independent one-hop structural signature has 244 distinct inputs and
also no conflicting labels. These empirical statements do not establish sufficiency
for arbitrary graphs or robustness to floating perturbation.

For live captures the ambiguity audit now removes the already appended boundary
columns when computing the resident-input baseline. It first checks that those
columns exactly match the independently saved boundary array. Otherwise the old
baseline would accidentally contain the new feature and conceal its contribution.

The next modeling step should examine how boundary messages are conditioned by the
consumer Cell and its completion conditions, rather than assume a wider neighborhood
or less accumulated error alone fixes the problem. Further independent test cases
are still required; these two programs remain validation cases.

## Live training schema fix

`calibrate_semantic_family.align_features` accepts both historical offline captures
(base features plus separate boundary columns) and live captures whose actual model
input already contains those columns. It appends once, verifies an existing tail,
and preserves an already trained extended coefficient matrix. A missing/mismatched
layout or an implicit truncation is rejected. It also records exact versus predicted
source modes in training provenance rather than claiming every source is exact.

Actual 41-by-2177 GCD live and feedback matrices pass this interface without added
columns or coefficient changes. This turn does not train on GCD or LCM; the interface
fix enables subsequent training-partition feedback collection.

## Cost and current Bake reference

Instrumented GPU compile/upload/execute time is **268.557 s** for exact sources and
**257.627 s** for feedback. CPU reference plus audit for the first mode is 0.260 s.
These single captures are not speedup evidence; both are far from the desired
execution efficiency. They include exact GPU query/completion and diagnostic capture,
not only ridge GEMMs. Snapshot extraction and final file output are separate.

The first process was confirmed live and sampled in MLX evaluation while waiting;
it subsequently exited successfully and was not restarted. A new optional `--progress`
flag logs fixed evaluation flushes (tick and elapsed time) without reading token counts
or steering GPU schedule decisions. Feedback used 16 ticks with one flush each.

Latest inspected Bake is `d05475b0`. Its actual next-catalog observation increases
full local RHS coverage from 160 to 196, but has not eliminated execution work;
source-layout factoring projections are rejected after charging their metadata and
stage exceptions. Likewise, these GPU features and retained predictions must not
be credited as removal of exact query, constructor or boundary work.

## Reproduction

ROOT = `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`. Use the project MLX Python:

```
python audit_construct_union_family.py ROOT/union-corpus/validation-019-lcm.trace.json ROOT/five-program-boundary-model.npz ROOT/lcm-live-boundary-execution.json --rules 283,290,293 --snapshot-run 514 --ticks 16 --flush-every 1 --order-queries --boundary-context --experimental-boundary-model --capture ROOT/lcm-live-boundary-witnesses.npz
```

Repeat with `--predicted-source-feedback --progress` and separate `lcm-feedback-*`
outputs. Label with `label_composed_witnesses.py` using the same trace/model and
original corpus manifest, snapshot 514. Run `audit_device_match_readout.py` with the
unchanged five-program decoder and `audit_prediction_feedback.py` on the two labeled
captures. Checked-in reports retain hashes, graph checks, coverage and costs.
