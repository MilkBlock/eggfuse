# First-parent evidence on native EggCC snapshots

This CPU diagnosis runs the frozen reference schedule, captures the input to an individual rule before matching and evaluates a synthetically trained model offline. The receiver has not been replaced in full EggCC. A positive label is a legal parent tuple at the captured LHS snapshot, not a committed RHS or a final-graph node.

Capture takes the first two dirty occurrences of each rule per log2 size bin, with one to 512 physical rows across its two schema tables. Only two distinct table atoms, distinct variable fields per atom, and one shared slot qualify. The bank includes all visible rows in the two tables, with physical reference, version and the canonical join column. The source compiler supplies the two table roles and column positions. All rows reach the model, not a prejoined set of candidate pairs. Snapshots may have no solutions. Evaluation uses equality of typed canonical values and the source seminaive watermark. The captured shared values in these four workloads are Eq and Text.

Training samples both positive and negative cases, competing operands, fresh/stale parents and near-colliding symbols. No EggCC row trains the network. Each port has four static fingerprint components from a hash of its typed value. Dense floating-point set aggregation sees all rows; role and freshness gates are learned. The same conditional follower head receives the selected parent, target row freshness and fingerprint overlap. The plain first scorer learns an unrestricted readout over the set summary. The structured variant supervises the two message gates and imposes the source watermark's disjunction at readout. This treatment changes structure and supervision together. A collision of all four fingerprint components can fool the follower; the exact named verifier must still check real addresses and actual port values.

sum-bits and dot-product were diagnostic cases. jacobi-1d and conjugate-gradient were evaluated only after freezing the two checkpoints. `results.json` contains first and second scoring counts, exact tuple counts, and false positives and misses. The structured scorer recovered all observed tuples. It generally scored more second ports than the unconstrained model because it kept previously missed roots. The all-left reference is an ideal role-prefilter that tries every actual L port; it is a pointer work comparison only. No native runtime speedup is claimed. Hash encoding, dense fingerprint channels, matrix traffic, the exact reference and snapshot construction are not represented by the scalar pointer-score count.

```sh
D=benchmarks/pass3-cell-gpu/join-port-diagnosis
python "$D/build.py" "$OUT"
python "$D/export.py" "$OUT/session" "$BUNDLE" "$OUT/sum-bits.gz"
# Repeat export for dot-product, jacobi-1d and conjugate-gradient.
python "$D/transfer.py" "$OUT/plain.json" "$OUT/sum-bits.gz" "$OUT/dot-product.gz"
python "$D/transfer.py" "$OUT/structured.json" "$OUT/sum-bits.gz" "$OUT/dot-product.gz" --structured
python "$D/transfer.py" "$OUT/held-out.json" "$OUT/jacobi-1d.gz" "$OUT/conjugate-gradient.gz" --structured --checkpoint "$OUT/structured.pt"
```
