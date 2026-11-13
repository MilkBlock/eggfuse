# Bake legal Eq partitions for bounded GPU selection

This is a frozen-model readout mechanism, not complete Cell matching, ownership
transfer or an autonomous Eggcc runtime. It uses the port-interaction ridge model
without refitting, threshold tuning or gradient descent.

## Static catalog and dynamic arithmetic

Bake first contracts equalities proved by the existing completed-effect compiler.
It groups the remaining classes by Eq sort, enumerates legal partitions for each
sort and projects their equalities onto the existing quotient query positions.
The bound is five classes per sort and 256 combined states. Larger families are
explicit CPU boundaries, not silently truncated catalogs. Nothing is enumerated
on GPU. Different sorts never merge.

For scores s and a catalog row m, minimizing squared distance is equivalent to
minimizing m dot (1 - 2s); the omitted sum(s squared) is common to all rows.
GPU uses a dense matrix product and argmin. The 0/1 rows represent exact candidate
partitions, not learned neural weights; real floating inference remains in ridge.
Ties within 1e-6 and nonfinite values are marked. Ties have deterministic ordering
by number of equalities then row order, but are not authorized to commit. Already
legal threshold outputs with strictly non-tied scores are unconstrained squared-
distance optima, so projection preserves them. It repairs inconsistent guesses
by possibly dropping equalities, not by blindly taking transitive closure.

## Held-out dot-product result

| Measure | Interaction readout | Legal partition projection |
|---|---:|---:|
| Exact partitions / 5454 | 4612 | 4665 |
| False equal pairs | 991 | 897 |
| Missed equal pairs | 1360 | 1434 |
| Nontransitive instances | 150 | 48 |
| False equal pairs after closure | 1174 | 973 |

Covered instances: 5247 / 5553; unsupported CPU marks: 306; ties: zero.
Covered partitions have **zero** nontransitive results; the remaining 48 occur
in the unsupported fallback. The older, smaller decoder had 4404 exact
partitions and only 613 false pairs: this combined approach still does not
improve every metric over that baseline and is not promoted automatically.

Legal states are not proven facts. CPU saved-label supervision finds 789 wrong
partitions (14.47% of 5454 comparable instances), including 603 wrong among
5148 unmarked comparable instances (11.71%). All outputs remain speculative;
checking only marked rows would miss those errors. No union, saturation or
ownership decision may rely solely on legality or the ready bit.

## Cost and supervision scope

Shared catalog payload is 105964 bytes across 3237 rows; the audited selection
requires 574285 multiply-adds. GPU projection wall time includes compilation,
upload and result synchronization, not steady-state throughput. Saved-label CPU
Eq checks take about .070 seconds for 5454 comparable instances (about 78k/s).
This is **not** native proof replay, graph reconstruction, or CPU runtime speed.
All relevant raw times and ratios are in the report. Numerical candidate and
ready-mask comparisons agree between CPU and Metal.

Five new tests cover Bell counts, complete small catalogs, static contraction,
typed sorts, resource boundaries, ambiguity/nonfinite handling, compiled GPU
selection, and preserving already legal outputs. Eighteen related tests pass.

## Reproduction and Bake alignment

Run audit_partition_readout.py with trace, model, model_report, weights,
selection_report, output. The trace/model are the frozen
class-history-neighborhood-input experiment; weights are
port-interactions-selection.npz. Exact hashes are recorded in the report.
Models and detailed data reside on /Volumes/Extreme SSD/eggfuse-artifacts/21ee.

The tracked Bake branch advanced to 6be77d9c. Its direct-source audit identifies
4021 actually matched multi-source applications even when Cursor ancestry is
absent. Such matches can seed composition, but do not prove source facts can be
retired. This GPU catalog derives only Eq legality from ordinary Cell definitions;
it supplies no retirement or ownership proof. Full takeover must still use actual
matched inputs, actual returned results, generations and source Run boundaries.
