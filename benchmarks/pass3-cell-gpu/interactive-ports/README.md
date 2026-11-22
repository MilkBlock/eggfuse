# Conditional port reads and interactive ownership transfer

This is a narrow CPU experiment. PyTorch chooses concrete token references in a live three-Run Rust process. The program, input facts, and typed multi-stage route come from the ordinary EggFuse compiler. There is one two-step compound action in this family. The native receiver uses the named-only matching entry; the exact reference runs in a separate process after model rollout.

| Run | Policy action | Receiver behavior |
|---|---|---|
| first | Choose an L export from the entire memory. Use its observed content to score every port for the R export or abstain. Retry another previously untried first port if needed. Choose leaf or compound at issuance. | Verify both named references, version, types and scalar equality, then execute Both. Return its actual physical result under owner slot 0. The compound reserves the sole compiled Both → C wire. |
| advance | Read the updated memory. Decide whether to propose C independently and whether to use Tag to propose D. | For an admitted compound, check its specific returned Both at the next legal boundary and execute the internal C rule. Return C under the same logical owner, slot 1. A standalone C exports slot 0 of its own owner. |
| finish | Select an observed C export for Use or abstain. | Reject invalidated handles. Read the named live premise and run the source effect on success. |

Every lookup by the pointer scores the full bank, including retired exports; the only retry mask records addresses actually tried in that Run. Model keys are cached until an export or retirement changes their features. Stable handles and versions travel losslessly alongside those features. The receiver initially exposes all input rows once. Later replies contain only actual returns, births and handle invalidations. On constructor reuse, authority for that physical result moves to the new export. The model sees the old handle's invalidation and can still erroneously propose it. The receiver never resolves an old handle to a replacement. Constructor interning while executing the RHS still uses native graph lookup.

Pointer training uses random synthetic banks and complete legal operand labels, with a learned abstention option for each read. The role and stage schedule are fixed. The first-parent retry loop and the two-action stage budget are supplied by the harness. Supervision teaches pointer selection and liveness. The decision to suppress the independent C proposal is learned separately: from identical snapshots run send vs skip under both leaf and compound, and optimize their observed return difference. Root leaf/full choice uses a second paired native rollout holding the continuation policy fixed. The cost proxy charges one per external packet, one eighth per physical parent read, one per rejection, and 100 for failing the graph/RHS/write/schedule contract. This training contract also compares every non-resume graph event. All resume and full-event differences are separately reported by the strict diagnostic. These weights are operation proxies, not latency measurements.

The family has at most one matching L/R pair and one independent Tag per input, three L distractor/search opportunities, a finite scalar alphabet and a fixed three-step schedule. The receiver supports one issuer per rule per Run and checks the compiler's verified multi-stage route before admitting the compound. Reuse cases start with an existing Both and C. This adapter does not load the full iterative RipSat catalog. It provides neither general equality/epoch invalidation nor a learned saturation scheduler. It does not establish EggCC coverage, FEPT, or speed. The positive full-block action is always advantageous when the root matches in this family; the continuation skip action has both signs of return. The fixed full policy is an important control.

Build the isolated sessions with fresh output directories. The study uses single-thread PyTorch CPU training and inference.

```sh
D=benchmarks/pass3-cell-gpu/interactive-ports
python "$D/build.py" "$NATIVE"
python benchmarks/pass3-cell-gpu/search-work-ledger/build.py "$REFERENCE"
cargo build --release --locked -p eggfuse-cell-compiler
python "$D/study.py" "$PWD/target/release/eggfuse-cell-compiler" "$NATIVE/session" "$REFERENCE/session" "$OUT"
python "$D/check.py" "$OUT/results.json"
```

The external results retain per-case checks and counterfactual returns. The tracked summary includes all paid proposals, full-bank scores and physical named reads. Both root policies reached the same states and ordered RHS on held-out inputs. On productive paths, the historical native executor records query-resume events that explicit verification does not reproduce. The strict trajectory comparison consequently remains a difference even when every graph event, write, RHS, and Run agrees.
