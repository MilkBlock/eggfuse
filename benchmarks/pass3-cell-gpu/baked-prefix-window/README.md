# What could a higher-arity root window save?

The complete live interpreter counts how many actual external tuples descend from disjoint blocks of 16 or 64 publicly ordered root rows for each query with three or more independent parents. It registers each lease candidate and its features before exploring any rows in that block. It records the number of sealed descendants at the block boundary. This **measures the opportunity** for a future fixed-size verifier action. No grouped high-arity packets are issued in this study; the native path still issues every ordinary tuple. The simultaneous singleton and two-parent bucket controls are the measured joint-fept-actors configurations.

Each training example has independent parent count, actual window extent, fresh root count, three table size bins, and presence of a fresh remaining role. The causal features do not include the eventual subtree size. The donor table learns the mean possible return (descendants minus the cost of one new packet) for each condition using real dot-product and jacobi-1d. Conditions with insufficient examples back off to a more general shape. The rule ID is available only for audit. CG and 3mm are held out. The ideal per-window upper bound can choose the best action after observing all descendants and charges one packet for each selected window. For nonsuppressed windows it pays the normal literal tuple count. A real packet would also need usable public membership, learned port constraints and cheap exact expansion, which this study has not established.

| Held-out program | Width | Windows offered | Windows saving at least one packet | Actual high-arity tuples | Donor-selected packet savings (projected) | Hindsight upper bound on savings |
|---|---:|---:|---:|---:|---:|---:|
| CG | 16 | 272,333 | 1,421 | 13,787 | +1,745 | 11,232 |
| CG | 64 | 69,234 | 1,087 | 13,787 | +4,835 | 12,108 |
| 3mm | 16 | 935,300 | 3,729 | 44,805 | −8,415 | 38,472 |
| 3mm | 64 | 235,438 | 2,568 | 44,805 | −33,127 | 40,968 |

Most ranges have zero return. 3mm's window-64 upper bound covers 40,968 of the remaining 44,805 external tuples, but donor-estimated choices would cost 33,127 more packets. The positive CG transfer and negative 3mm transfer are both included. Paying for every surveyed model decision, including unselected ranges, would further reduce the projected rate. This result motivates using evidence about actual shared port keys to find active roots before paying for a proposal. The sum of this diagnostic and another engine's observed savings must not be reported as a measured FEPT.

The histogram covers every high-arity residual from the same-binary native joint reference; it also matches per-rule physical activity on CG and 3mm. No production graph results or substitution paths are extrapolated from a histogram.

```sh
python build.py "$EXP/prefix-window-build"
python study.py "$EXP" "$EXP/prefix-window-build/session" "$EXP/prefix-window-data"
python bake.py
python verify.py
```
