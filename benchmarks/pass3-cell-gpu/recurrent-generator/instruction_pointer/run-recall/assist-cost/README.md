## Paired CPU costs on three complete EggCC programs

Four trials per workload alternated exact / assist / teacher replay and the reverse order. Each arm starts a fresh Rust process. The Python service is warm. All timed schedules and final hashes agree, and a separate audited pass also checks ordered effects and continuation events. The weights are frozen. The host is an Apple M3 Max, with one PyTorch CPU inference thread.

| Workload | Exact wall (s) | Teacher wall (s) | Assist wall (s) | Actor (s) | Named verification (ms) | Assist exact matcher (ms) | Assist faster than exact |
|---|---:|---:|---:|---:|---:|---:|---:|
| fact | 0.151 | 0.154 | 22.319 | 18.952 | 2.95 | 8.25 | 0/4 |
| loopfact | 0.140 | 0.145 | 20.816 | 17.778 | 2.85 | 7.82 | 0/4 |
| sum-divisors | 0.219 | 0.209 | 473.611 | 410.974 | 17.72 | 52.47 | 0/4 |

The separate native in-memory oracle omits decoding and export. Exact and oracle medians (ms) are fact 7.75/6.91, loopfact 7.86/6.57, sum-divisors 62.44/51.09. End-to-end times charge decoding and export. Only the assist arm uses the online port exporter and model IPC. Inputs to the oracle are pre-signed offline. Generating its proposals costs zero in this comparison.

The receiver counted 10,512 model-signed bindings that also appeared in ordinary match results. Complete-domain proofs removed 328 binding outputs from the ordinary path across these workloads. Native residual candidate visits remained at 26,167. The full proposal ledger and component timing medians are in [summary.json](summary.json). Raw records for each program preserve the paired order and times.
