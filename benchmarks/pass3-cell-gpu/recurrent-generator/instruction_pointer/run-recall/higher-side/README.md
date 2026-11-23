## A signed fork with an independent side input

An external root can now carry one independent, versioned side premise for the final hop of a higher Cell. The policy reads every port of the required type in the sealed root snapshot, including old ports. A small learned pointer scores the typed ports conditioned on the fields of the proposed root's own parents, and can abstain. It uses a learned weighted comparison of 64-bit field codes and a shared nonlinear scorer. Relational compatibility is learned from examples of actual completions. No host-side comparison or candidate binding enumeration supplies the answer. IDs do not enter the numerical scores. The root Actor remains frozen.

The receiver checks the named side's presence, type and version at issuance. The root, each internal return and the final two-parent binding still go through their ordinary native source semantics. When the consumer runs, the side keeps its originally signed version. The fork arm also arms the old closed continuation from the same admitted root. Invalidating the side at issuance leaves this closed branch available. A seminaive child cannot consume a pair when both signed versions precede its own watermark. In that case the receiver omits the request before either parent is read for verification. Internal token numbering is reserved consistently across this optimization.

**Training.** Sum-bits supplied the prior 32-join iterative Bake catalog. Thirteen joins have an independent side; the training pass followed their recorded native root and child references up to the first scheduled Run for each hop. It chose the recipe with the most root-visible completions per producer on sum-bits and dot-product. Three side units qualified. The head took 320 MPS updates on 133 positive and 1,027 negative root examples, using sampled negatives during training. At inference it scores the full legal typed domain. The cutoff is the learned score beating the fixed null score of zero. Training labels used the teacher's recorded address. Alias-aware validation below reveals legal alternative addresses these labels miss. The programs used for evaluation have previously guided system development. This study covers existing Bake templates.

**Pointer diagnostic.** When given the actual teacher root, 229 root instances across three programs had a recorded completion in the three selected recipes at the stipulated schedule. On 123, a recorded side and version was already present. The model chose the recorded address on 70; native substitution credited the same committed binding on 119. Among the other 106 roots, 57 substitutions still produced the same committed binding using a different address already visible at root issuance. In total 176/229 had their recorded completion recovered by this conditional experiment. These probes used the teacher's internal pivot and schedule. Deployment must also issue an accepted root and obtain its actual returned port. [Pointer diagnostic](conditional.json) · [All catalog paths](opportunities.json).

**Live controls.** Closed uses the previous higher Cell policy. Side replaces the closed continuation when the learned pointer chooses a side. Fork retains both continuations. Across three full programs, side alone signed 10,925 commits; closed signed 10,947; fork signed 10,974 of 20,428. All assist arms reproduced the ordered schedule, RHS, writes, resumes, events and final graph. The signed and residual components of the effective-operation ledger sum to the independent exact reference at every audited execution. With search disabled, fork still diverged on Runs 7, 8 and 11. Sum-divisors still hit a source panic at Run 85.

| Program | Closed → fork signed commits | Closed → fork paid tokens | Closed → fork effective signed operations | Fork accepted side steps |
|---|---:|---:|---:|---:|
| fact | 1,254 → 1,251 | 3,804 → 3,801 | 904 → 904 | 12 |
| loopfact | 1,044 → 1,042 | 3,713 → 3,702 | 788 → 786 | 8 |
| sum-divisors | 8,649 → 8,681 | 24,783 → 24,795 | 4,951 → 4,967 | 65 |

The source counts charge every paid external token, successful or otherwise. The template and attached side address are part of the same request. The per-token metric alone omits the cost of scoring extra ports; inference, verifier and residual timings are recorded separately. Four alternating end-to-end CPU comparisons on each small program include the actual side head, the pure exact baseline and the zero-cost teacher proposer. Fact measured 329.33 → 331.94 signed operations/s (two of four pairs better), and loopfact 304.14 → 303.18 (one of four). No repeatable throughput gain is established. Sum-divisors has a full semantic and work audit and no paired throughput measurement. [Paired trials](density.json).

**Reproduction.** ROOT contains the prior native captures and training manifest. Use the prior frozen opaque root Actor as WEIGHTS. The included pointer directory holds the frozen side head and the selected template shapes. The before-watermark ablation uses the receiver from commit 7e31b21b; the final receiver includes commit 0134478e. Keep these builds separate when reproducing the verifier work comparison.

```sh
cargo build --locked --release -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay
mkdir -p "$ART"
python side_boundary.py "$ROOT" "$ROOT/sum" "$ART/opportunities.json" --cases sum dot fact loopfact sum-divisors
python side_pointer.py "$ROOT" "$ROOT/sum" "$ART/fit"
python side_pointer_audit.py "$ROOT" "$ROOT/sum" "$HEAD_DIR" "$BINARY" "$ART/conditional.json" --cases fact loopfact sum-divisors
for name in fact loopfact sum-divisors; do
  python higher_cell.py run "$ROOT" "$BINARY" "$WEIGHTS" "$CLOSED_CATALOG" "$ART/$name-closed.json" --case "$name" --arm owned --ept
  python higher_cell.py run "$ROOT" "$BINARY" "$WEIGHTS" "$CLOSED_CATALOG" "$ART/$name-fork.json" --case "$name" --arm owned --ept --side-head "$HEAD_DIR" --keep-closed
done
python higher_density.py "$ROOT" "$BINARY" "$WEIGHTS" "$CLOSED_CATALOG" "$ART" "$ART" --cases fact loopfact --side-head "$HEAD_DIR"
```

On the otherwise identical receiver before the watermark optimization, 624 internally issued side continuations yielded 85 distinct commits. Inspecting both signed versions before verification removed 427 attempts and 737 named reads; 197 side attempts remained, with 85 accepted and 112 rejected for incompatible bindings. Per-program external issuance, accepted commits, effective-operation attribution and final states agreed across the two receivers. The closed-only arm still used 285 fewer verifier reads in aggregate. [Native assist and before/after attribution](assist.json) · [Unassisted runs](exclusive.json).
