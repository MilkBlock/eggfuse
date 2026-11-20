# Shared scores on the native high-coverage joint Pass 3 path

One Rust CPU graph runs the learned single-witness policy, fast multi-witness shortlist and checked merge-child allocator together. The exact control uses the ordinary native Cell CPU executor. Training is unchanged. The timing compares whole source inference on sum-bits, dot-product and two held-out families, using both seeds. The high single checkpoint allows explicit residual work. The certified checkpoint uses its checked feature mask, with no single residual; both regimes use the sealed learned multi policy with no multi residual.

### Why two candidates can share a score

The single policy seals every row decision for a rule occurrence before checking any proposed match. Only after the batch is sealed does it update its recurrent state. Therefore weights, rule id and recurrent input are fixed while those offers are scored. Identical numeric feature vectors can reuse the original forward result bit for bit. A cache lives only for that occurrence and its construction and destruction are charged on every call.

The high model caches all fourteen encoded bytes. Its faster encoder precomputes static query metadata once; it still reads all dynamic fields that contribute to its score. In the certified checkpoint six dynamic feature columns have exactly zero weights, verified by the model loader. The table/pivot arity and remaining shape columns are fixed for a rule, leaving just the freshness bit. The specialized path keeps two optional floating-point scores on the stack, computed lazily by the original forward. It performs no floating-point reassociation or approximate interpolation.

A separate stale control prunes a verifier read only *after* the original raw proposal, score and recurrent transition have been generated. The predicate requires a seminaive single table pivot, no suffix instructions, and a source version earlier than the watermark. No other row or primitive can make that binding fresh. On the certified model, the extremely stale cases normally already abstain; the post-issuance control can consequently save no verifier work. The header-only follow-up uses the native visibility/epoch accessor for candidate scoring. The full row remains available to a real verifier.

| Arm | Candidate feature / scoring path | Stale verification |
| --- | --- | --- |
| Off | Original full row and forward for each proposal | Original |
| Full key | Original features, per-occurrence 14-byte hash key | Original |
| Static | Compile static columns once; full-feature cache or two certified scores | Original |
| Stale | Original full row and forward | Prune proven stale single-atom candidate |
| Static + stale | Static encoder and cache | Same prune |
| Header + stale | Certified model alone reads only freshness/liveness for scoring | Same prune |

The neural raw hash includes every candidate identity, native address/version, activation/guard bits, score bits and initial-source flag. There is also a separate hash of every recurrent state word. For each arm, the verifier compares these to the unoptimized joint pass, checks the multi-tuple raw hash, both complete winner ledgers, merge-gate decisions and child identities, the complete physical allocation stream and per-binding allocation ownership. It independently checks full ordered RHS inputs, writes, Spine, schedule, birth/union events and final state. The exact control is allowed to have different proposal costs because it uses ordinary source search.

## Main paired timings

| Program / seed | High unshared → static + stale ms | Certified unshared → two scores ms | MLP evaluations, original / high cache / certified cache |
| --- | ---: | ---: | ---: |
| sum-bits/1703 | 84.3 → 78.9 | 76.5 → 70.1 | 70,366 / 8,682 / 2,584 |
| sum-bits/1709 | 82.8 → 78.0 | 81.2 → 72.5 | 70,366 / 8,682 / 2,584 |
| dot-product/1703 | 81.9 → 77.9 | 78.6 → 72.8 | 62,558 / 7,074 / 1,995 |
| dot-product/1709 | 86.0 → 80.7 | 84.8 → 74.2 | 62,558 / 7,074 / 1,995 |
| gemm-bias-relu/1703 | 252.9 → 242.6 | 245.5 → 219.2 | 196,265 / 14,157 / 2,638 |
| gemm-bias-relu/1709 | 243.0 → 228.7 | 237.8 → 220.0 | 196,265 / 14,157 / 2,638 |
| stable-argmax/1703 | 82.2 → 81.7 | 77.5 → 74.7 | 65,649 / 7,469 / 1,635 |
| stable-argmax/1709 | 82.3 → 78.7 | 76.5 → 69.8 | 65,649 / 7,469 / 1,635 |


Across eight high-checkpoint pairs, the median relative reduction from static features and shared scores was 4.70%, or 5.35% with safe stale verification pruning. Across the eight certified pairs, the simpler two-score cache plus static features reduced complete inference by a median 8.55%. The stale control alone moved noisy wall times in both directions. Reading only headers further reduces the measured single feature/score work, but whole-pass differences versus the already cached version vary.

## Where the remaining time goes

The separate header-only study also measures the source scheduler phases and the learned multi-witness path. The following numbers are medians of eight paired full executions for seed 1703. The single and multi columns are subphases of source search. Each column has its own median, so adding medians is not an exact time decomposition.

| Program | Exact / joint full ms | Exact / joint source search ms | Single features+score / single verify ms | Multi candidate generation+seal / multi verify ms | Joint RHS / repair ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 26.9 / 74.5 | 11.7 / 61.7 | 3.8 / 11.6 | 34.2 / 6.9 | 7.8 / 2.5 |
| dot-product | 23.3 / 78.7 | 11.1 / 66.5 | 3.7 / 12.0 | 37.8 / 7.9 | 8.1 / 1.6 |
| gemm-bias-relu | 48.4 / 219.1 | 21.2 / 192.7 | 10.3 / 37.6 | 110.5 / 24.2 | 16.1 / 5.8 |
| stable-argmax | 24.8 / 69.6 | 11.0 / 56.7 | 3.6 / 12.1 | 30.2 / 6.1 | 8.0 / 2.5 |

The multi-witness phase includes frame/index preparation, candidate enumeration, shortlist handling and sealing before its exact verifier. The improvement from caching single scores was insufficient to beat the exact native source engine in any pair. This profile isolates a genuine reduction in repeat forwards; it does not attribute every remaining millisecond to neural matrix computation.

After warmup, eight wall samples rotate each compared arm and reverse the order on alternating trials. The native inference timer includes all per-occurrence cache work, policy forward, verification, source effects and residuals. The second wall measurement includes stdin/stdout IPC, graph initialization, request setup, hash/export and JSON result traffic of the persistent benchmark session. Raw decision/ticket hashes are produced in **separate audited runs**, outside the timing samples. [Matched decisions and paired samples](results.json) · [Header-only phases and paired timings](header-results.json)

## Reproduce

The isolated overlay is applied after the shortlist and merge-child overlays; no GPU computation is used in these runs.

    dir=benchmarks/pass3-cell-gpu/joint-score-sharing
    python "$dir/build.py" "$OUT/build"
    python "$dir/study.py" "$OUT/build/session" "$REF" "$FAMILIES" "$CAPTURE" "$POLICIES" "$MULTI" "$CERTIFIED_PATTERN" "$OUT/main"
    python "$dir/study.py" "$OUT/build/session" "$REF" "$FAMILIES" "$CAPTURE" "$POLICIES" "$MULTI" "$CERTIFIED_PATTERN" "$OUT/header" --regimes certified --modes off static-stale header-stale

POLICIES identifies the frozen high-recall single configs, sealed plans and merge configs from the preceding joint study; CERTIFIED_PATTERN accepts a per-seed path containing {seed}. The physical-id trace is checked separately for each workload, seed and checkpoint.
