# Issue a whole Run of neural proposals before validation

The ordinary CPU path seals a rule's chosen parent pages, checks its exact suffix and proceeds to the next rule. This treatment makes two separate passes over the active rules of an immutable Run. In source order, the actual singleton and multi-parent neural issuers first seal every offer in the wave. The singleton consumes its own preceding recurrent state exactly once. The multi-parent provider builds the original source pages and records its watermark bounds. The second pass verifies held offers, resumes Spine and executes the original ordered commit and rebuild. The graph is borrowed in its original state and no page can publish an effect early. Epoch, rule occurrence and watermark identify every deferred batch. Empty rule sites are tracked as well. Pending work must drain at the wave boundary. There is no training trace, externally supplied winner or CPU matching fallback. Source-known full-key requests and other checks used by the original proposer are still part of issuance.

| Pass 3 | Vanilla | Prior rule-local | One rule | Eight rules | Whole Run, ms | Maximum held proposals / rule sites |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.45 | 31.36 | 31.24 | 31.42 | 31.47 | 401 / 222 |
| conjugate-gradient | 334.92 | 638.24 | 659.83 | 663.34 | 634.55 | 7,100 / 222 |
| 3mm | 898.47 | 1,899.89 | 1,913.13 | 1,893.03 | 1,847.82 | 15,968 / 222 |

The two maxima are independent. On 3mm, 1,812 waves contained more than one model-issued rule site and 862 contained both parent providers. The complete Run arm sealed 845,168 singleton offers and 220,972 multi-parent tuples. All accepted and rejected offers were genuinely generated online before any of that wave’s post-issue validators. The Run boundaries, actor decision digest, raw signed streams, every surviving source parent, physical allocation, ordered effects and final graph are preserved. Four rotated resident samples at seed 1703. [Full source and wave evidence](results.json)

```sh
d=benchmarks/pass3-cell-gpu/run-proposal-waves
python "$d/build.py" "$EXP/run-waves"
python "$d/study.py" "$EXP" "$EXP/run-waves/session" "$EXP/run-wave-results"
python "$d/verify.py"
```
