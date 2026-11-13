# Completed sources inherit immutable stage metadata

The authoritative frame census already showed no remaining parent links in the
completed sources. More parent-chain reclamation cannot remove these records.
Instead this change moves template identity, completed operation prefix and
symbolic-slot mode from every completed source into its existing shared sparse
layout. Completed state is guaranteed by transfer admission. Each source retains
its actual started epoch and recipe depth; neither is a property of the shared
stage. Metadata is reconstructed when read or when restoring that source.

This replaces fields rather than introducing another registry. Membership now
shares only across identical template/stage/mode as well as identical slot and
operation positions. This can increase layout count relative to membership-only
sharing, so the full Graph measurement must include both that cost and smaller
source records. There is no runtime fact graph or new consumer subscription.
It is a storage specialization of completed Cells, not a proof permitting any
additional rule skip or RHS execution.

Existing actual fact values, hashes, visibility, source IDs, exception states and
foreign-result handling remain authoritative. Unsealing one source reconstructs
only its own metadata/arrays. Sibling payload addresses and stages remain intact.
No bulk materialization is introduced for unexpected unions. Layout retirement
still follows the last actual source reference; history is not retained.

The runtime library passed 209 tests with sparse Cells and storage metrics.
The added test distinguishes template/prefix/mode while sharing different epochs
and depths, then restores one source without moving its sibling and checks that
the last retirement releases the shared layout.

Reproduce the four-workload memory and saved Run audit (no timing campaign):

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 -c 'import sys; from pathlib import Path; sys.path.insert(0,"benchmarks/cell-bake-owner-merge"); from shared_membership import run; run(*(Path(p).resolve() for p in ["out/cell-bake-owner-merge/batch","out/cell-shared-membership","out/cell-shared-stage","benchmarks/cell-bake-owner-merge/shared-stage.json"]),variant="shared-stage",control_pattern="{case}.json")'
```

The harness freezes newly built examples, preserves the previous variant, uses
identical program digests, compares every saved Run and terminal check, and
requires existing completion-work counters to remain equal. Full Graph and
retained Program allocation measurements are separate. These are actual
standalone Cell CPU measurements; they are not native egglog acceptance or RSS.

## Measured result

All 2,652 saved Run checks and four terminal checks pass. Existing completion
work counters are equal and retained Program bytes are unchanged.

| case | Graph before | Graph after | reduction | shared stage layouts |
| --- | ---: | ---: | ---: | ---: |
| fact | 654,127 | 645,935 | 1.25% | 162 |
| loopfact | 579,953 | 572,285 | 1.32% | 174 |
| sum-bits | 1,741,931 | 1,702,627 | 2.26% | 256 |
| dot-product | 1,689,019 | 1,648,851 | 2.38% | 202 |

The completed source header now measures 48 bytes on this machine. The increased
shared-layout storage is included above; whole execution/transfer allocation
peaks also decrease in all four cases. This is a modest reduction, not evidence
of the requested large egraph compression. Instance and fact counts are not
reduced, and the unchanged work counters demonstrate no additional RHS skip.
The next structural takeover must eliminate source/fact/index obligations from
proved cross-stage closures, rather than keep subdividing this header.
