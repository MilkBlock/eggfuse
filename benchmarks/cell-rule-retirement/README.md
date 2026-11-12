# Rule-owner retirement

This change runs in the actual standalone Cell CPU executor. It is not native
egglog performance, and this checkpoint contains work counts rather than a new
timing campaign. The control is `b8fbf090`, whose runtime is `2ae7b97e`.

The previous catalog already releases an individual rule's completion task
when that rule's queries finish. However, that task only selected Cell winners
and ordered residuals separately. Its return still made the coordinator merge,
sort and deduplicate the entire partial-coverage result. This was a remaining
source dependency after the completion-event takeover. The previous Unit
registration diagnostic accounted for only about 0.63% of inference, so this
iteration targets query retirement before widening that smaller boundary.

The existing typed rule input layout, depth/source ordering and successful
query instances are sufficient evidence. No new catalog, marker, fact graph,
bindings copy or per-producer subscriptions are added. Worker completion now:

1. Selects Cell winners by input, depth and original witness/pivot.
2. Orders residuals through the existing expansion path. It verifies their
   input order and stably sorts any uncovered unsorted route.
3. Linearly merges the two ordered streams, preferring the Cell instance on
   equal input and dropping duplicate speculative candidates. Prepared values,
   actual witnesses and the numeric Cursor token stay with that instance.
4. Returns the final RHS array. The source releases losing Cursor roots and
   seals the retained tokens or legacy origin mappings **in place**.

The old source-side concatenate/sort/dedup and result-array reconstruction are
removed from this path. Small tasks still execute inline; making them pool
tasks would add dispatch cost. `final_merge_worker_rows` and
`final_merge_inline_rows` count input candidates to this final merge, including
duplicates; they are not committed RHS mutations. `final_merge_comparisons`
includes the residual order check, any residual sorting and the linear merge.
It is separate from the existing Cell winner-comparison counter. The output
array still owns the same instances; its capacity is allocated once for the
combined input, instead of growing the selected-winner array while appending.

This makes the rule completion event perform all ordering work within its
coverage. Across Runs, the original Cell outputs still project into Shared
Entries at the original visibility boundary. This iteration neither discovers
new dominators nor removes the source Run query/effect fence. Cursor roots,
residual enumeration, delta ownership, actual foreign witnesses, retirement,
source error selection and ordered effects remain live obligations. No public
effects are committed while the Run's query errors are still unresolved.

## Work and validation

Same frozen sum-bits and Raytrace catalogs, four query workers, features
`cell-absorption,view-ports,parallel-publication`, and the preceding run flags:

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Final merge | sum-bits | Raytrace |
| --- | ---: | ---: |
| Candidates handled by a worker | 0 | 106,597 |
| Candidates handled inline | 538 | 7,145 |
| Worker share of these candidates | 0% | 93.7% |
| Input comparisons | 1,155 | 321,619 |

This percentage describes this one operation, not overall CPU utilization.
The previous implementation performed this final merge on the source. No
speedup is inferred from migration counts. The last recorded whole-runtime
four-worker regression remains unresolved until a later timing checkpoint.

Final states, all 1,428/16,883 ordered Run summaries, logical effect counters,
query counts, Cursor retention/release and sealed slot counts exactly match the
control. The unchanged native sum-bits acceptance is `pass`, using saved
exports whose CPU hash matches this new execution. Raytrace is an exact
differential check; it is not an extension of the native proof contract.

147 runtime tests and 84 integration tests pass. The new tests vary arrival
order, depth ties, residual order, sparse input slots, prepared outputs and
direct/legacy origin storage, and require the source to preserve the returned
array and slot addresses. An incomplete residual fails without consuming its
Cursor owner. Existing integration tests check actual per-Run snapshots and
binding order, including errors, deletion, unions and late inputs. Forced
hash/Bloom collision runs pass. Legacy/no-default and all-feature builds pass.
The README compile, run and single-repeat bench smoke commands also pass; that
bench invocation is not a comparative performance result.

Recheck saved execution artifacts without rerunning performance:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-rule-retirement/semantic-acceptance.json
python3 benchmarks/cell-rule-retirement/check.py out/cell-events out/cell-rule-retirement benchmarks/cell-rule-retirement/results.json
```

The remaining major opportunities include source query admission/Cursor
handling and shared RHS adoption. Function identity assignment still imposes
source-prefix order; moving the final query merge does not remove that fence.
