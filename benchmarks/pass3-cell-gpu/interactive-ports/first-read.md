# First-parent selection ablation

The frozen interactive issuer scores each candidate first port using a fixed role vector. Its ranking between two live L ports cannot change when only R ports change. Retrying other L ports can recover complete results while hiding this limitation. The original training target also rewards any L even when it leads to a dead end. Only the first read changes in this study. The conditional second pointer, issuer, skip decision and named Rust receiver use the same frozen checkpoint.

All training banks are synthetic. Productive labels reward any live L with a live matching R, or abstention when there is none. Dense training supplies three competing Ls, sparse training one. Additional controls vary steps, hidden width, inclusion of realistic distractors and the original any-L objective. The shared reader applies learned sender and receiver weights to observable port roles and liveness. The eight scalar channels share those weights. Sender contributions sum over the whole bank, and each candidate reads from the same summary. There is no runtime join-label input, action tuple bank or receiver search. Source fields are restricted to eight scalar values in this experiment.

The arms share a 4,096-bank held-out diagnostic and 48 fresh native initial states (16 absent, 16 reuse, 16 fresh). Initial tag presence varies within each group. Numbers below are exact first-choice counts / complete native graph, RHS, writes and schedule matches. The stricter query-resume comparison remains 16/48 for the original and shared readers. Seeds 1703 and 1709 are shown in order; the original checkpoint is fixed.

| Intervention | First choice /4096 | Native /48 |
|---|---:|---:|
| Original | 851 | 48 |
| Local scoring, productive labels | 1839 / 1839 | 16 / 16 |
| Context, 40 updates | 1839 / 1839 | 16 / 18 |
| Context, 600 updates | 4053 / 4093 | 44 / 42 |
| Same 600 updates, sparse training | 2033 / 1990 | 22 / 18 |
| Same 600 updates, reward any L | 799 / 873 | 48 / 48 |
| Context, width 8 | 2330 / 2507 | 40 / 28 |
| Context, width 96 | 4096 / 4096 | 45 / 48 |
| Context, varied distractors | 4055 / 4085 | 41 / 44 |
| Shared scalar weights, varied distractors | 4096 / 4096 | 48 / 48 |

Original versus shared on the 48 native cases: 382 versus 224 pointer queries, 3,164 versus 1,974 candidate scores, 96 external proposals each, 160 receiver parent reads each, and 32 internal continuations each. The shared reader additionally encoded 384 port rows (one snapshot per case), reduced them into 48 summaries and read each summary against its ports. The query reductions are not time or FLOP reductions. Only the shared reader's 35 new trainable parameters were trained on top of the 1,382-parameter frozen policy. It uses CPU inference. Timings, arbitrary scalar domains and EggCC end-to-end parity require separate evidence.

Run reader_ablation.py with the compiler, interactive native executable, exact reference executable, original pointer.pt and an external output JSON path. The script exports the combined shared-reader checkpoints beside its detailed results. The receiver constraints and counter semantics remain those of the interactive-ports experiment.
