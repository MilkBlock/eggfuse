# Joint repair, external readers and subscription granularity

Four training families supplied 258 typed producer–reader edges appearing in at least two training programs. A descriptor contains the producer table, reader table and key column. Each arm gets eight descriptors and can attach at most two readers to one producer. The runtime accepts an edge only when the reader's actual constructor key refers to a previously created, live, eligible constructor with that canonical result. It preserves original row identities and source visibility. Initial facts, functions, containers, ambiguous or retired donor addresses keep their original behavior. This is subscription grouping on the standalone Metal engine. It does not retire source row payloads.

The first selector ranks observed edges where the donor is the actual resumed Spine pivot. The second counts uses where a subsequent committed union touches the donor result and the linked reader key. The third chooses among distinct equal-budget libraries, including the first two and portfolios penalizing unrelated member wakeups. Selection uses the lowest family-average paired whole-inference cost on **training programs only**. This is an empirical price for the entire library, including admission, notification, key repair, collision checks and publication. The cheapest nonempty portfolio had a penalty coefficient of 4. Even that portfolio cost more than the row-only baseline on average during calibration. A policy allowed to decline this investment should retain the baseline. [Frozen training catalog](catalog.json) · [Calibration samples](training.json) · [Source split and native contracts](CORPUS.md)

## Figure 38. What does learning from a union change?

| Held-out program, resident P3 | Row baseline | Continuation support | Joint repair support | Training-priced |
| --- | ---: | ---: | ---: | ---: |
| gemm-bias-relu, notifications | 6,114 | 5,979 | **5,473** | 5,682 |
| same run, median ms | **1,972.7** | 2,002.7 | 2,003.5 | 2,007.0 |
| stable-argmax, notifications | 3,196 | 3,135 | **2,868** | 2,950 |
| same run, median ms | **644.5** | 662.7 | 662.6 | 658.1 |

Joint repair learns different edges, including `AddContext → Concat`, and reduces the logical notifications by about 10% on each held-out family. Port masks keep the repair inspection count at the row baseline. The number of mandatory external key probes and comparisons remains a substantial cost. No tested selector produced a whole-inference win on either held-out family. [Per-program matched arms, oracle credits, timings](selection.json)

## Figure 39. Does adding a reader really extend the old group?

The producer-only arm installs a checked port mask on each eligible producer even when there is no reader; it took 1,917.3 / 619.5 ms on the two held-out sources. The one-reader arm took 1,945.5 / 634.8 ms. Nested two-reader groups took 1,945.9 / 628.2 ms. In gemm-bias-relu all 402 first pairs survived, and notifications fell from 6,114 to 5,657 to 5,524. On stable-argmax all 236 survived and notifications fell from 3,196 to 2,951 to 2,887. The key index and physical witnesses still require normal boundary handling. These figures are from a separate eight-order matrix.

A greedy second reader can take an instance that would have anchored a later first reader. The nested arm gives an available first-reader slot priority, and only admits a second reader if its table cannot act as a producer anywhere in the frozen library. The audit compares **every** original producer's first child by physical row ID. A paired five-Run source changes only the external demand flag. With both internal reader types admitted, adding an out-of-library reader increases notifications from 3 to 4 and key probes from 2 to 4. In both cases the two real collisions still execute. [Paired source and checks](counterfactual.py) · [Exact counterfactual results](external-control.json) · [Nested growth timings](nesting.json)

## Figures 40 and 55. Does fewer logical notifications mean fewer actual memory reads?

Figure 40 fixes all attached readers and instances. Per-row entries notify every affected row. An instance entry expands its wake to members and leaves exact validation to repair. The port-mask entry registers current classes with per-member affected columns. A union merges these registrations, marks precise member slots, and falls back to ordinary field inspection on the joining epoch. All variants retain the ordered dirty frontier, full-key collision tests, forwarding and external publication.

On gemm-bias-relu, row / instance / mask modes took 1,967.7 / 1,971.0 / 2,012.9 ms. The instance mode visited 266,492 rows, compared with 266,173 for both other modes. All three performed 3,897 key probes, 674,008 collision-candidate comparisons and 2,431 collisions. The simple membership representation reserves 198,656 additional metadata bytes; the tested port dictionary reserves 8,751,104 bytes including its capacity for future groups. Reservation and useful work are different metrics.

The dense root directory visited **467,264 data words** under all three policies despite the difference in logical wake count. This motivated Figure 55. The sparse variant retains the dense data and adds a summary bit per nonempty data word. The GPU consults this summary before loading the corresponding data word and propagates summary bits with the root. On gemm-bias-relu, row subscriptions now read 4,522 data words and took 1,937.6 ms; stable-argmax went from 138,237 to 2,241 data words and 643.2 to 632.5 ms. These data-word counts exclude accesses to the summary itself. The gemm-bias-relu row arm made 19,941 summary inspections and 24,829 summary updates and reserved 1,060,800 additional bytes. [Verified summary costs](summary-cost.json) Its storage and accesses are paid in wall time. These small speed differences apply to this paired matrix and device. [Directory matrix and ten rotated timings per arm](directory.json)

## Acceptance and reproduction

Each arm runs from its offline program and initial image without future events as inputs. The capture arm records eligible birth edges, the actual resumed pivot and pre-link union incidences on device. Training labels can look back at these events; runtime membership only uses the frozen catalog and the current birth. The trace counts live semantic incidence; the online notification count also includes retained subscriptions to retired addresses. Coverage checks distinguish these populations. Calibration uses four train families. A separately frozen matrix uses two development, two held-out and two anchor programs. The CPU observer and GPU reference were independently matched at every Run. Each device arm checks ordered bindings, writes, Spine origins, union log, physical state and typed final rows. Each resident timing sample starts from restored input, disables work counters and checks its full event output. Compilation, reset and offline training are outside resident time. [Census and native validation](CORPUS.md)

```sh
ws=/Volumes/EggFuseWorkspace
root="$ws/experiments/NEW-repair-corpus"
ref="$ws/experiments/pass3-atlas-integration-20261120"
weights="$ws/experiments/rotary-axes-20261119/packed-1703/final.pt"
dir=benchmarks/pass3-cell-gpu/co-repair
# First generate the CPU/GPU references using CORPUS.md.
python "$dir/capture.py" "$root" "$ref" "$weights" "$root/profiles"
python "$dir/experiment.py" "$root" "$ref" "$weights" "$root/profiles" "$root/paired"
python "$dir/directory.py" "$root" "$ref" "$weights" "$root/paired/catalog.json" "$root/directory"
python "$dir/nesting.py" "$root" "$ref" "$weights" "$root/paired/catalog.json" "$root/nesting"
```
