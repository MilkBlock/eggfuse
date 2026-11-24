# Cell Communication Protocol v0.1

The ordered-pipe profile connects one generator to one exclusive EggFuse Cell CPU executor. A request selects a Bake template, its ordered input addresses, any primitive instructions to run, their data dependencies and the observations to return. The executor may reuse an identical explicit computation or keep intermediates local. It checks every proposed proof and executes admitted effects under the compiled source schedule. It may not discover candidate parents, extend a request graph, issue a missing proof, or use an offline reference as feedback.

## Session, identity and visibility

Start `cell_token_replay online-ccp-v0.1 PROGRAM - audit [RUN_LIMIT] --ept`. Before any binary bytes the server emits a UTF-8 JSON line with `protocol="Cell Communication Protocol"`, `version=[0,1]`, `program_sha256` (digest of the exact artifact bytes), `transport="ordered-pipe"` and `commit_scope="source_run"`. Validate these before issuing work. Each process connection starts a fresh identity namespace. Additional JSON keys may be ignored. A changed binary layout, opcode meaning, value tag or visibility contract requires a separately negotiated version. Reuse of a connection after a framing error and reconnection/replay of an unacknowledged commit are outside this profile.

A generated Cell has a positive, session-unique token ID, its immutable rule/template and the input references signed by its proof request. Initial owners have negative odd IDs. Repair owners have negative even IDs and use the merge template. Owner zero denotes a local operand. A port is named by (owner, original template instruction ordinal). Its live incarnation also has a version. Constructor reuse and repair forward this address to the **actual returned witness**. A row marked forwarded remains addressable by its original name at its published version. Advancing a version invalidates older reads; retirement removes a port from live memory. CPU row indices and hashes do not establish identity.

All batches in an open source Run use one immutable graph snapshot. The client can send independent batches without waiting for individual responses. One seal closes the source Run. Its admitted proofs execute in the original native rule/commit order, with duplicate signing decided in admission order. Seal is the only graph publication boundary in this profile. A request batch may contain successful, failed and dependent operations together. A successful scalar value can feed later scalar instructions immediately. An admitted proof's RHS ports can first be consumed after publication. A failure before the commit acknowledgement leaves its outcome unconfirmed to the client. This profile provides no crash durability.

## Request and response buffers

All integers use little endian, with no padding. One header consists of four tag bytes, two u16 version words (0,1), then three u64 words (sequence, source Run, graph epoch). Sequence starts at one and advances by one for every request batch and seal throughout the session. The server validates the entire header before consuming operations.

| Request section, in order | Layout |
|---|---|
| Envelope | Header tagged `CCPQ` |
| Counts | Four u32 words: magic 0x31585443, operation count N (1..65536), reference count M (0..1048576), zero |
| Operations | N rows of five i64 words: kind, unique positive request/owner ID, scheduled rule ordinal, primitive query ordinal or −1, cumulative exclusive end in the reference array |
| References | M rows of four i64 words: owner, op, version, column |
| Observation | N bytes. Bit 0 requests the opaque field hash. Bit 1 requests the typed actual value. Zero asks for status alone. Other bits are reserved. |
| Seal | A separate envelope followed by counts (magic,0,0,1) and no body |

Kind 0 **PROVE** supplies one (owner,op,version,−1) per table premise, in query order. Rules without table premises take zero references. Kind 1 **COMPUTE** names a primitive at the query ordinal; each input is a named field, a literal from that instruction (0,−1,0,0), or the successful, sort-compatible result of an earlier operation in the same batch (0,zero-based operation index,0,0). Kind 2 **READ** names one committed field (owner,op,version,column) and uses pc = −1. To observe selected exported proof fields, issue named READs after publication. A local value remains usable by dependent instructions even if its observation mask is zero.

| Response section, in order | Layout |
|---|---|
| Envelope | Header tagged `CCPR`, echoing sequence and snapshot, then u64 value-arena length in bytes (max 64 MiB) |
| Aligned receipts | N rows of four i64 words: request ID, status, echoed pc, hash bit pattern (zero unless requested and available) |
| Value ends | If any operation requested a value, N cumulative exclusive u64 offsets into the arena. Otherwise absent. |
| Value arena | Contiguous bytes. Empty slices denote absent observations. A zero-length string or empty set has a nonempty encoding. |

Each observed value starts with a u8 tag. Tag 0 carries a u64 snapshot-local equivalence-class identity. Tag 1 carries an i64. Tag 2 carries the exact 64-bit floating-point payload. Tag 3 carries a u64 byte length followed by UTF-8. Tag 4 carries a u64 count followed by that many tagged set elements in runtime order. Tag 5 encodes a structural key DAG: u64 root index, u64 node count, then for each node a u8 anchor flag, a length-prefixed UTF-8 label, a u64 child count and that many u64 node indices. The optional hash uses the legacy runtime field encoder. Hashes are opaque within a compatible encoder build; cross-language consumers requiring the value or portable storage use the tagged encoding.

Status discriminants are frozen in this order starting at zero:
`accepted, duplicate, untriggered_rule, arity, unknown_output, retired, hidden, type, version, binding, watermark, unbound_primitive, guard, unbound_input, computed, bad_dependency, invalid_computation, pending_port`.
Consumers derive status masks in bulk from column 1. `accepted` means proof admitted; `computed` covers successful READ and COMPUTE. An attempted read from an admitted owner in the same Run reports `pending_port`; the network can issue a new versioned request after publication. Failed, forward and cross-batch local dependencies supply no value. Malformed framing, invalid descriptor offsets, a reused request identity, an unscheduled rule or a version/sequence/snapshot envelope mismatch terminates the session. A seal has no immediate binary receipt.

## Publication and shared memory

The server emits one JSON control line followed by typed delta buffers before each source Run. The line contains `run, epoch, rules` (scheduled rule/watermark pairs), `committed_through_run`, `final_publication` and counts for the six arrays below. Read all arrays before processing the next header. In the last publication the schedule is empty, the epoch is the last committed epoch, and the Run number is the next publication slot. Apply the delta, then read the terminal JSON report. There is no further request or seal. This applies also when a run limit ends execution immediately after a write.

| Count | Element layout |
|---|---|
| typed_rows | Six i64 words: owner, op, table, new version, forwarded flag, cumulative field-hash end |
| typed_hashes | u64 field hashes in table-column order |
| typed_retired | Two i64 words: owner and op |
| typed_accepted | Two i64 words: newly admitted-and-executed owner and rule |
| typed_repairs | Fourteen i64 words: system owner, origin Run, merge table, first visible Run, two triples (parent owner,op,version), input-hashes-present flag, two hash bit patterns, cumulative repair-op end |
| typed_repair_ops | i64 exported original merge-instruction ordinals |

Register new owner types, retire invalid addresses, then update the addressable fields and their index from the published rows. Each row replaces its prior version. The current client stores Python address maps/views backed by these arrays. Native publication still scans the return registry to identify changes. The data plane uses copied pipe buffers. Control headers and the terminal audit report use JSON. Batch compute pipelines run in FIFO order on the CPU and can overlap independent generator work. This profile does not promise concurrent graph writers or device-to-device transfer.

## Accounting and conformance

Charge one paid token per PROVE, COMPUTE and READ, including cache hits, pending, failed, rejected and duplicate requests. Batching, internal DAG edges, observation selection and seals add no signed atomic operations. EPT divides distinct signed effective operations by all paid tokens. EPS divides the same numerator by inclusive online elapsed time. Report coverage against the declared reference, candidate visits and scores, index and memory updates, batch sizes, receipts and synchronization separately. Host/client overlapping timers are not additive. Existing routing uses shared field encoding and a learned bucket projection; include the LSH bucket visits and dense scores inside each visited bucket.

Run the native conformance probe and paired protocol rollout from the benchmark directory. They cover the wire contract and the policy respectively. [Tests and measurements](../benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer/run-recall/ccp-v01/README.md)
