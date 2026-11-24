# CCP v0.1 conformance and independent execution

**Neural Execution / exclusive.** The paired runs use the same native standalone EggFuse CPU executor, compiled program, eight-bit LSH, frozen Compose, field encoder and computation router. The router consumes hashed result observations through the shared field encoder. The protocol conformance fixture separately exercises selective raw-value observations. Rust executes only named requests. All four cases ran to schedule end.

| Workload | Derived reference facts | Paid operations | Signed effective operations | EPT | EPS, CTX1 / CCP | Synchronizations, CTX1 / CCP |
|---|---:|---:|---:|---:|---:|---:|
| [grammar-7300147](grammar-7300147.json) | 256/256 | 470 | 256 | 0.5447 | 4,878.6 / 4,967.5 | 26 / 23 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | 256/256 | 984 | 256 | 0.2602 | 4,955.6 / 4,846.3 | 25 / 21 |
| [fact](fact.json) | 363/1,120 | 9,954 | 562 | 0.0565 | 297.2 / 289.6 | 565 / 550 |
| [cyk801](cyk801.json) | 6,567/6,567 | 50,257 | 6,567 | 0.1307 | 2,025.1 / 2,069.8 | 329 / 239 |

The full accepted proof tape (including parent versions and repair certificates), all verdict counts and endpoint SHA matched between transports on each program. The three grammar endpoints matched their references. The EggCC fact result matched its CTX1 endpoint and recovered 363 of 1,120 reference derived facts. The new profile publishes the last Run's memory delta even on a run-limited exit. Offline replay and reference alignment are outside online elapsed time.

Synchronization counts include one collection of one or more outstanding batches and one source-Run boundary per seal. The native CPU serves batches in order; the client can overlap up to four independent batches. The result files contain the raw verdicts, native timings, client conversion/packing, index and memory update timings, batch sizes, visits, model score counts and artifact digests. A single ordered pair per case characterizes this implementation. These timings do not establish a speedup. Publication still scans signed returns, and the Python adapter retains indexed port views. The protocol leaves the decision to seal to the issuer. This experiment uses the existing end-of-stream policy.

**Training control.** Repeated both existing training recipes on Metal at seed 12931, disjoint from the grammar evaluation seeds. The one-step run used 402 contrast pairs and the chain run used 718. Each produced a byte-identical checkpoint to the corresponding frozen artifact used on both transports. There was no additional label for scheduling or raw-value decoding. [Training records and model provenance](../transactions/README.md)

**Wire checks.** The native fixture pipelines three batches and collects the last ticket first. It checks request association, raw integer and string reads, chained computation, a repeated computation served from cache, zero-observation intermediates, future local dependencies, stale versions, a pending proof output and its versioned read after commit. Wrong version, sequence, Run and epoch fail at the envelope. A single-Run execution publishes all 17 signed owners on exit. Full teacher replay of sum-bits published 7,265 signed owners plus one typed repair event and reproduced the reference schedule, RHS count, writes and state SHA. These teacher figures are protocol controls. Rust golden bytes also cover floating-point bits, sets and structural keys.

From the instruction_pointer directory, set ROOT to the existing recursive experiment artifact tree and SUM to its sum-bits capture directory. Use a Python environment with torch and numpy.

```sh
cargo build --release --manifest-path ../../../../engine/cell-runtime/Cargo.toml --features cell-token-ept --example cell_token_replay --target-dir "$ROOT/unified-scale/build"
python ccp_conformance.py "$ROOT/unified-scale/build/release/examples/cell_token_replay" "$ROOT/recursive-agent/grammar-4691132" --repair-corpus "$SUM"
python ccp_compare.py "$ROOT" "$OUT" grammar-7300147 grammar-stride3-split-7300147 fact cyk801
```

[Normative wire format and visibility rules](../../../../../../docs/CELL_COMMUNICATION_PROTOCOL_V0_1.md)

[Learning the frozen protocol on independent neural rollouts](../protocol-learning/README.md)
