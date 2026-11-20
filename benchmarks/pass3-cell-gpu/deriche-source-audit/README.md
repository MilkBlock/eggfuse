# Deriche: an exact source check for a truncated learned parent search

The isolated standalone Rust engine and its independent default-feature source reference both execute the frozen 5,687-Run Deriche Pass 3 schedule. With learned providers disabled in the integrated binary the full graph and every ordered RHS, effective write, Spine resume and union agree. The older packaged three-view, radius-two joint checkpoint also matches all 635,818 RHS and directly constructs 450,414 of the 452,913 new physical Cells. It touches its candidate cap twice without changing the source result. Reaching a counter threshold is insufficient evidence of an incorrect result. [Same-build exact and older joint controls](controls.json)

The narrower one-view integrated stack exhibits a real difference. We stopped the original executor after Run 819 and captured the ordered RHS rule and complete slot-value row of every accepted binding. All three arms used the same program and original source schedule. The two learned arms differed only in the pointer-expansion budget.

| Run 819, always-run | Same-build exact | One million attempts | Eight million attempts |
|---|---:|---:|---:|
| All accepted RHS bindings | 12,914 | 9,794 | 12,914 |
| Rule 249 accepted bindings | 7,280 | 4,160 | 7,280 |
| Missing rule 249 bindings | 0 | 3,120 | 0 |
| Extra rule 249 bindings | 0 | 0 | 0 |

The other rules were individually identical. At eight million, the entire ordered output and the graph immediately after Run 819 both match the control, byte for byte under the source digests. [Per-rule counts, sample missing binding and output hashes](run819.json)

Rule 249 binds a DoWhile, reads the contexts of its two operands, selects a Const in the loop output context, and reads the input type. Its RHS publishes lsr-inv for that loop and the constant rewritten into its input context. The sealed plan has five parent-pick instructions and grammar width four. The failing cap counts intermediate learned pointer extensions while the rule constructs combinations. An admissible pointer prefix can be expensive and produce no complete tuple. Counting one million such extensions and then returning a partial enumeration allowed structurally verified RHS records to pass while 3,120 legal ones were omitted. A finite larger cap checks this case; a complete production configuration must either finish the frontier or report a genuinely unvisited branch before claiming saturation.

Eight million also restores the complete measured Deriche trajectory: 5,687 source Runs, all 635,818 RHS with matching neural winners, 450,414/452,913 directly constructed physical Cells (99.45%), every effective write, Spine resume, union, source schedule and the final graph. Rule 10 still reaches the eight-million threshold at Runs 3,561 and 4,533 with seven parent picks. A correct measured endpoint and a hit counter neither prove that all branches were explored nor license skipping budgets elsewhere. [Full same-binary counterfactual and independent oracle](complete.json)

## Reproduction

Use the frozen bundle, tied port tables and independent CPU executables in the external workspace. The optional diagnostic records selected-source occurrences and cap events. It has no authority to supply parent addresses.

```sh
d=benchmarks/pass3-cell-gpu/deriche-source-audit
e="$EGGFUSE_ARTIFACT_ROOT"
b="$e/extra-pass3-transfer-v1/deriche-1703"
python "$d/diagnose.py" "$e/integrated-cpu-build-v2/session" "$e" "$b" "$e/NEW-deriche-controls"
python "$d/build.py" "$e/NEW-cap-build"
python "$d/cap.py" "$e/NEW-cap-build/session" "$e" "$b" "$e/NEW-run819"
python "$d/cap.py" "$e/NEW-cap-build/session" "$e" "$b" "$e/NEW-complete-audit" --full --caps 0 8000000
python "$d/verify.py"
```
