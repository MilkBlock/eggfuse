# Scaling the RipSat portfolio on Pass 3

The normal Bake CLI can build **670 distinct positive constructor fragments** from dot-product and jacobi-1d. All 670 relink at 952 source sites in each of sum-bits and 3mm. The ordered template IDs agree across targets. A second Bake invocation reproduced both complete catalogs byte for byte. These are conditional RHS programs for an already matched source rule. Independent cross-Run parent selection and fresh-port publication have their own grammar and proof requirements.

## What a token proves

Bake enumerates connected subgraphs of two to five constructors within a single source RHS segment. An ordered traversal from the result canonicalizes local operation names and independent instruction order while retaining operand order, sharing, types and boundary slots. A copy projects its source. Union, mutable effects and other non-constructor operations bound each segment. Initialization rules are excluded. Literal and upstream values enter through the occurrence's boundary wiring.

Each projected program gets an isolated native egglog donor with a typed input frame. The native proof must reach saturation, pass the exporter, record an application, and derive the exact result on the supplied ports. Replay checks the root was initially absent and that every intermediate lookup succeeds in the final graph. This exercises a generated local context. Runtime generality comes from relinking the exact source constructor instructions, since one ground saturation does not prove an arbitrary rule guard. The fragment grants no authority to skip the original LHS or publish a future result. Native rebuild and constructor interning still own actual IDs.

Before commitment the single- or multi-root issuer places the selected template variant in its existing page header. On acceptance the Rust verifier checks the source template, physical parents and version through its existing path. At covered physical constructor instructions the source frame executes the predecoded constructor call at the original ordinal and collects its actual receipt. Other instructions, prior history transfers and Run boundaries retain their normal paths. The audit counts each selected root, actual instruction and fully dispatched fragment separately.

The independent cross-Run experiment removes the generic twelve-route sampling cap for source routes supported by the current named Let grammar. Grounding real source epochs and checking the local write/read history licenses a second Let edge, 24/op4 → 65, alongside 143/op1 → 55. The existing fresh Set certificate remains available in the combined comparison. The extra Let edge supplies zero additional committed children on the two held-out workloads.

## Deployment and evidence

The offline PyTorch head fits ridge coefficients to seven static features on 24 generated local contexts per donor shape. Its local reward counts fresh constructor identities surviving in the synthetic terminal context. This is a proxy for source FEPT. A held-out execution supplies no training samples or model features. In the Rust session a single CPU thread scores every eligible source site with the frozen weights once during setup, before any target token is issued. The size control selects the largest eligible fragment. The ordinary root network, named parents, existing cross-Run templates and verifier are common to both controls.

The deployment target uses offline MPS training with PyTorch CPU fallback disabled. On the recorded host the queued MPS training process failed to reach Apple's Metal compiler service (job 2891, exit 134). The scores and workload measurements here use an explicitly CPU-trained PyTorch control checkpoint. Both inference and verification in these measurements execute in the native Rust Cell session. This is the standalone EggFuse Pass 3 runtime, with an independent exact source execution for the graph audit.

| Workload | Available / issued / fully executed shapes | Accepted fragment roots | Full fragment completions | Dispatched ctor ops | Final original identities from those ops |
|---|---:|---:|---:|---:|---:|
| sum-bits | 670 / 60 / 30 | 1,817 | 935 | 3,462 | 936 |
| 3mm | 670 / 52 / 21 | 56,838 | 33,287 | 105,056 | 33,268 |

The final column is a subset of the existing FEPT numerator. Size selection attributes 33,248 of the same final 3mm identities to its dispatched operations. The ridge head changes attribution by 20 without changing the final graph or number of external proposals. On sum-bits, union and union plus fragments each issue 12,534 proposals for 2,691 visible nodes (0.214696 FEPT). On 3mm both issue 554,339 for 92,658 (0.167150 FEPT). Only the signed cross-Run routes eliminate independent proposals in this experiment.

The complete single- and multi-parent issuers ran with their exact residuals disabled. The independent source oracle agreed on 7,265 / 7,265 committed RHS ordinals across 1,428 Runs for sum-bits, and 294,917 / 294,917 across 4,260 Runs for 3mm. This includes the existing generators. The fragment-only coverage is given in the table. Ordered RHS, effective writes, Spine resumes, unions, schedule and final graph agreed. The saved sum-bits choice validator also passed its reviewed contract.

Median native execution in the same binary took 23.33 ms for ordinary exact search and 33.61 ms for the fragment policy on sum-bits. On 3mm these were 836.52 ms and 1598.33 ms. The latter resident request took 1844.55 ms including dispatch, configuration and response, compared with 1077.66 ms for exact search. The experiment timed four resident repetitions after warmup. The size of the template dictionary alone has not closed the gap to exact search.

See [target identities and counts](manifest.json), [exact and neural controls, source parity, terminal credit and timing](results.json), [fresh-process RSS](rss-results.json), and the [checked cross-Run archive](donor-evidence/trust.json). The resident native timer includes source execution and verification. Resident request time additionally includes configuration delivery, portfolio decoding, the Rust forward, setup and response transfer. Neither time includes offline native saturation or training. The RSS window starts at native execution entry after policy setup. Each RSS arm has four fresh sampled processes and four unsampled controls.

## Reproduction

Use the mounted external workspace and its shared FIFO. The commands below run from the external worktree with the existing compiled donor and target bundles. Choose a fresh output directory.

```sh
e=/Volumes/EggFuseWorkspace/experiments
d=benchmarks/pass3-cell-gpu/ripsat-scale
o="$e/my-ripsat-scale"
n=target/release/examples/ripsat_donor_graph
small="$e/compact-holdouts-20261121-v1"
job() { ~/.local/bin/eggfuse-job run --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse "$@"; }
job cargo build --release --locked --offline -p eggfuse-cell-compiler --example ripsat_donor_graph
job python "$d/prepare.py" "$e" "$n" "$o"
job env PYTHONPATH=benchmarks/pass3-cell-gpu/joint-witness python "$d/build.py" "$o/build"
job env PYTORCH_ENABLE_MPS_FALLBACK=0 python "$d/train.py" \
  --donor "$small/dot-product-1703/program.json" --donor "$small/jacobi-1d-1703/program.json" --out "$o/weights.json"
job python "$d/study.py" "$e" "$o/build/session" "$n" "$o" "$o/study" --checkpoint "$o/weights.json"
job python "$d/rss.py" "$e" "$o/build/session" "$n" "$o" "$o/study/results.json" "$o/memory/results.json"
```

For the recorded CPU training control, pass `--device cpu` explicitly to the training command. To check an individual cached library, use `explicit-parent-cell-composition/bake.py ripsat-fragments --check LIBRARY --native NATIVE --target TARGET --donor DONOR1 --donor DONOR2` from the Pass 3 benchmark directory. Regenerate cross-Run donor evidence with the existing donor capture, produce and archive commands, adding `--all-certifiable` to capture. A new capture has new receipt hashes and needs its own independent index.
