# Where the verified whole-wave executor spends time

The current packed singleton + negative certificate arm and the default CPU were sampled in fresh resident processes on 3mm and Deriche. Both consumed the entire original program, returned the same final graph and executed the same Run count. The external macOS sampler captured the main thread at a nominal 1 ms interval for seven seconds per process after a warmup. Each sample is assigned once to its innermost known execution owner or to work outside inference. Short inlined functions can be charged to their callers. Sample counts across different captures have separate denominators.

The multi-parent issuer/validator accounts for 2,130 samples on 3mm and 2,022 on Deriche. On 3mm, 355 of its samples are attributed to index construction and lookup, 251 to neural port-code evaluation, 363 to stack enumeration, 226 to the two-parent traversal and 97 to forward preparation. These include their costs in callees when a more specific issuer function was not found. Some compiler-inlined or unclassified multi-parent scopes remain in other_multi. None of these counts replaces measured full native inference latency. Per-request timings recorded during sampling include profiler perturbation.

Reproduce with the verified-wave-execution binary and the usual shared experiment root. Raw OS samples are kept outside Git. results.json identifies each raw sample by SHA-256 and retains all main-thread category totals.

```sh
python sample.py "$EXP" "$NATIVE" "$EXP/new-wave-profile"
python summary.py "$EXP/new-wave-profile" /tmp/issuer-samples.json
python verify.py
```
