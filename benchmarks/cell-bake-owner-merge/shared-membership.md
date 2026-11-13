# Shared sparse membership replaces per-instance position records

The region census found repeated actual fact membership, but the completed-owner
representation still stored a slot index beside every value and an operation
index beside every fact. These positions are now an immutable shared `Layout`.
A completed source retains its metadata, a layout reference and two base offsets.
Its backing arrays contain values, hashes and lifecycle states, without a second
copy of the slot/operation positions. Range ends derive from the shared layout.

This is a runtime replacement in the opt-in completed-owner path, not a second
fact graph. The ordinary Cell and its arrays are removed at the existing checked
idle-Run takeover. Fact lookup, mutation, extension and source restoration read
positions from the layout. Constructor identities, query indexes, stable FactRefs
and worker publication ordering are unchanged.

The layouts specialize **storage membership**, not executable Cell identity.
Equal numeric positions may share across templates because operator identity
still comes from the source metadata and existing executable template. This
sharing never proves Eq, visibility, a returned constructor address or an RHS.
Sparse missing operations stay absent; foreign results do not become local facts.

The initial implementation interns exact position lists at takeover time. It
charges each lookup/reuse and exposes retained layout count and estimated layout
bytes. The interner owns one reference; retiring/replacing the final source drops
the layout entry. It retains no historical catalog or per-producer consumer list.
A future Bake-owned membership specialization may remove this runtime preparation,
but the current change does not claim to compile it away.

Lifecycle remains per source and fact: each source keeps its started epoch; a
fact has its own hash and a default/exception/retired state. Sharing membership
never shares mutable state. Parallel arrays avoid preserving padding from the
old operation/hash/state row after moving the operation number into the layout.

Restoring a source gathers its own slot/value and operation/state pairs. Other
sources' payload addresses remain unchanged. Existing merge admissions still
refuse to flatten a physical owner with unrelated live siblings; existing segment
fallback remains in force. Dynamic union and retirement do not mutate layouts.

## Acceptance and limits

The frozen runtime comparison uses the unchanged four `prefix-all` artifacts,
with the previous grouped-dispatch runtime as the saved control. The script
records source revision plus patch digest, freezes both example executables,
checks intermediate Runs and terminal state, and requires all existing runtime
work counters to agree. Complete Graph and Program teardown counts include the
new interner, layout arrays and split fact buffers. Source/structure counters
alone are not proof of compression. Execution peaks include Program, Executor
and diagnostics; they are not Graph-exclusive peaks or RSS.

The ownership integration suite passes 59 tests. Ten fact-state tests and two
fact-storage tests pass, including a new sparse-layout fixture with different
source epochs and values, independent hidden state, source-only restoration and
release of the final shared layout. This is standalone Cell CPU validation, not
a new native egglog acceptance or performance result.

This does not yet remove per-source metadata or the composition/address/index
obligations. It does not implement stage-switch RHS generation or establish the
requested large egraph compression. It replaces a concrete repeated membership
representation on the route toward that larger takeover.

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/shared_membership.py out/cell-bake-owner-merge/batch out/cell-dispatch-storage out/cell-shared-membership benchmarks/cell-bake-owner-merge/shared-membership.json
```

## Measured result

All 2,652 saved Run checks and four terminal checks pass. Existing runtime work
counters are identical. The first collector stopped because passive-check reports
omit a separate terminal flag; inspection confirmed the terminal comparison runs
before report emission. The corrected collector reused the same frozen binaries
and completed checks rather than rebuilding or repeating the semantic batch.

| case | Graph before | Graph after | reduction | live membership layouts | execution-peak change |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 658,935 | 654,127 | 0.73% | 70 | -4,810 |
| loopfact | 585,105 | 579,953 | 0.88% | 79 | -5,154 |
| sum-bits | 1,773,131 | 1,741,931 | 1.76% | 129 | -30,154 |
| dot-product | 1,720,731 | 1,689,019 | 1.84% | 97 | -31,686 |

Retained Program is unchanged in every workload. Runtime interning performs
777/697/2,504/2,326 checks with 707/618/2,356/2,221 reuses; these are newly paid
preparation operations, not free compiled dispatch. Restoration event counts
remain 2/0/23/10, with the original source-sized restoration semantics. The
membership layout counts differ from the earlier region census because this
representation shares position arrays without including operator/template codes
or grouping multiple logical sources into one layout. Source metadata still
selects the actual operator and remains independently stored.

This is a small measured Graph reduction. It does not establish a latency gain,
reduce the number of live facts, or meet the 30%-of-original target. The next
structural replacement must remove source metadata/address maintenance and enable
checked stage completion; refining integer packing here is not the main path.
