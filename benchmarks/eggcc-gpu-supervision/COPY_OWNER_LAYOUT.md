# Bake sealed copy aliases into GPU ownership layouts

The prior transfer compiler reserved a distinct destination slot for every source
slot, including effect copies of another retained value. Compound source Cells
therefore failed combined-payload capacity even when their distinct values fit.

`sealed_copy_aliases` symbolically executes only ordered slot definitions:
copy inherits the current value identity; any other destination write gets a new
identity. A later overwrite does not retroactively change an earlier copy.
Union never supplies a value-alias proof. The final source layout shares matching
consumer inputs and allocates one tail position per remaining distinct identity.
Ordinary source logical slots, tokens, query/effect definitions and Run boundaries
are preserved. No marker relation or parallel fact graph is introduced.

Runtime still requires sealed and visible source/target instances, matching rule
identities and generations, live physical owners, quiescent readers, complete
physical alias coverage and free destinations. It also compares every existing
payload column across the proposed source copy aliases. A disagreement rejects
the transfer without mutation. All logical readers are remapped through the
existing owner projection, and the released physical row's generation advances.
Copied-field metrics count unique physical destinations, not duplicate aliases.

The compiled alias array costs four bytes per slot per candidate. Runtime adds
per-column comparisons and can admit more plans; there is no per-source consumer
list, new reverse index or added payload slack. This is storage-capacity reuse,
not an established speedup or reduction in allocated arena/process bytes.

On the same 12 terminating two-producer inputs, with the same normalized head,
capacity and completed-Cell initialization, actual GPU owner releases increase
from 0 to 9. All 12 graph/lifetime/feature/label audits pass. Accepted instances
remain 75 and exact predicted states remain 62/75 (direct 36/48, generated 26/27).
Predicted tokens, target tokens, target classes, rules and generated-source flags
match the previous run exactly. Reconstructed features differ by at most
1.79e-7. The unchanged model weakness on direct producer-frame inputs remains.
Physical-alias witness-pair observations remain zero in this sample; releasing
owners does not prove that every later multi-source join shares a payload.

Tests include compiled GPU transfer into the original width, preservation of all
logical slot/root/validity reads, corrupted-copy rejection, overwrite ordering,
union exclusion, generations, occupied destinations, reader boundaries and chained
owner remapping. Seven existing owner tests, five matched takeover tests and two
new copy-layout tests pass. CPU egglog/Cell executor paths are unchanged.

Full runs are archived at
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/multi-frame-copy-owner-v1.tar.gz`.
Reproduce with `collect_enumerated_gpu.py` using the prior native probe, unchanged
normalized-active head, and `--producer-frames`, then `summarize_enumerated_gpu.py`.
The tracked result JSON gives prior/current manifest hashes and exact comparisons.
Full GPU learned matching/effect authority and general ownership coverage remain
unproven; this completes only the copy-alias takeover within tested coverage.
