# Training-scaled nonlinear features for resident Cell completion

The raw fixed projection was not saturated on the development captures: maximum
absolute preactivation was 1.382 (GCD) and 1.390 (LCM), with no entries above 3.
The experiment therefore changes input scaling, not a demonstrated saturation
problem. It uses the same 641 synthetic inputs and alpha 10. Real GCD/LCM captures
remain recurring development validation, never fitting data.

For each compiled Cell head, synthetic input means and standard deviations define
`P = fixed_random_projection / max(training_std, .02)`. Columns constant across
all that head's training rows have zero rows in P; raw input columns are retained.
Runtime computes `[x, tanh((x - training_mean) @ P)]`, then the centered ridge score.
The random seed, dimensions and ridge penalty are fixed, and there is no gradient
optimization. These statistics do not prove coverage of unseen scalar or graph
states. Removing constant columns from the nonlinear projection does not remove
them from the raw representation.

The GPU consumes raw assembled floating features directly in the head. It does
not calculate and discard the previous unscaled joint projection. Template
metadata determines the path at compile time; no new data-dependent GPU branches
or lookup tables are introduced. The existing exact matching, admission, effects,
ownership transfer and source-stage boundaries remain authoritative. This is an
accuracy improvement experiment for the selected three-rule family, not a complete
learned GPU executor or full Eggcc runtime.

Folding the mean into a bias caused f32 cancellation: the initial fit exceeded the
5e-6 score tolerance with a 2.48e-5 maximum discrepancy. Explicit centering fixes
that issue. CPU audit of the normalized head accumulates matrix products in f64
and rounds to f32; GPU execution remains f32. Legacy heads retain their original
reference arithmetic. The score/token thresholds and exact choice checks are not
relaxed. The intermediate normalized head passed GCD feedback (36/41) but failed
the LCM numerical gate at 5.48e-6; it is not accepted for LCM. The final variant
also excludes training-constant columns from nonlinear amplification.

The final offline result is GCD 36/41 and LCM 93/99, compared with the existing
merged head's 26/41 and 65/99. It persists 7,503,372 bytes for the three scaled
projection matrices and centers, in addition to 344,192 coefficient bytes and
64,664 readout normalization/bias bytes. This is stored model size, not measured
incremental GPU memory: the preceding implementation also instantiated projection
matrices. There is an extra centering subtraction, with the same projection
matrix dimensions as before. No speedup is claimed.

Tests cover normalized matmul and compiled GPU parity, raw-column retention for
training-constant dimensions, raw features entering live proposal evaluation,
capture replay, archive loading, and rejection of incomplete or malformed heads.
Artifact root: `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/matched-entry-gpu-v1`.
`normalized-active-fit-argv.json` records the final training command;
`normalized-active-classifier.json` records the complete offline result. Original
folded failure and intermediate normalized results remain separately preserved.

Final-weight feedback: GCD passes graph and label audits at 36/41 complete states
(23/26 direct and 13/15 generated-source), versus the previous feedback 25/41.
LCM graph execution passes, but numerical reconstruction still fails at 5.48e-6:
6/262 audited live score lanes exceed the unchanged 5e-6 tolerance. Those six
recorded/recomputed choices agree, but this does not override the numerical gate
or establish model semantic correctness. No accepted LCM feedback accuracy is
reported. The audit now writes a structured `passed:false` report identifying
these lanes and their fraction, and does not write a new training artifact.

The head remains explicitly selected experimental functionality, not a general
default. Both runtime argv files and label commands are saved as
`{gcd,lcm}-normalized-active-{argv,label-argv}.json`. The unresolved LCM failure
is `lcm-normalized-active-labels.json`; the tracked summary is
`normalized-joint-results.json`. Removing constant-column amplification did not
resolve that failure. Full GPU matching/effect authority and full Eggcc coverage
remain outstanding.
