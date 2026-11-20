# Factor the actual issued parent page, then verify and bind through its coordinates

The original signed multi-parent page owns a contiguous, tuple-major array. Every parent repeats the source atom, tagged physical address and version. All tuples in a page already belong to one source Run, rule, layout and serial range. Each role in the tuple also has a fixed atom and address kind. This experiment moves that information to a role descriptor. The varying payload is two 64-bit words, a physical ID and a source version. Two versions of the same address are distinct entries.

The direct arm stores one such pair per tuple in every role. The dictionary arm interns distinct pairs separately per role in first-occurrence order. A constant role omits its coordinate lane. Depending on the number of distinct pairs the other lanes use 8, 16 or 32 bits per tuple. The selective arm stores a direct column when the dictionary and rank lane together are at least as large as the direct word array. The algorithm preserves original tuple order, so the certificate serial for position i is always the first serial plus i; no grouping decision can move a source RHS.

Flat, direct, dictionary and selective arms all stage the ordinary issuer's physical reference vector. The streaming selective arm writes columns as the neural issuer seals each tuple and finalizes each page at its ordinary 8,192-tuple boundary. Completed pages wait until generation is finished before the source verifier examines any tuple. Append order and all addresses come from the existing learned model, with no matching or address recovery by the page codec. Hash maps and wide working ranks are temporary costs of building a dictionary.

The verifier borrows the flat source or decodes one factored tuple into reusable scratch space. At binding, the original checked-slot recipe resolves that same page and slot again, then checks the actual source witnesses, versions and fields. The immutable page also exposes a role's word count, a checked word by role and coordinate, and the coordinate for a tuple/role. Adjacent tuples or neighboring pages need not share prefixes. This changes the actual issuer-owned representation used for binding. The [earlier prefix experiment](../composable-page-prefix/README.md) measured a prefix archive next to the executed flat page. The [typed-receipt experiment](../lean-root-receipts/README.md) measured reducing post-bind copying and production hashes.

## Accounting and checks

The native body counts the actual word arrays, rank lanes and role descriptors including their host sizes. Cumulative native retained bytes additionally charge the resident page object, Rc header and backing capacities of the flat vector or the owned packed arrays. The template layout is shared by all the arms. These cumulative charges do not measure simultaneous process RSS, allocator padding, temporary hash tables, diagnostic buffers or scalar CPU work. All setup during native inference, including dictionary hashing, scratch, sealing and decoding, is charged in the paired wall timing.

For an independent, deterministic export we use nine little-endian u64 header words: format ID, Run, rule, template, first serial, count, width, fault flags and encoding tag. Flat export uses four u64s per reference. Packed export uses 18 bytes per role header (atom, address kind, lane width and word count), then all 16-byte dictionary/direct words and the complete rank lane for that role. The native run reads its actual typed page. Detailed mode also retains the originally issued refs in order and checks each physical identity and version, writes the wire bytes, parses the complete stream and independently checks every decoded tuple. Selective batch and streaming modes must have byte-identical wire digests. A deliberately out-of-range packed coordinate must return a source failure. Altered versions, wrong source templates and withheld receipts must fail at the same source boundary as on flat pages.

All measurements are complete resident inferences in the standalone Cell CPU Pass 3 engine. The reference pairs one default exact CPU executable with one composed model executable. The learned paths have identical weights, two signed projections, shared singleton headers and lazy arithmetic. Detailed source checks cover every Run's ordered RHS inputs, effective writes, union, Spine, final graph, surviving parent witnesses, nested roots, original and wire issue hashes and fresh physical Cell IDs. Four rotated repeats follow one warmup at seed 1703.

## Native execution

| Source | Vanilla | Flat | Direct words | Forced dictionary | Selective | Stream selective, ms | Stream wins / 4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.77 | 33.95 | 34.15 | 34.97 | 34.15 | 33.13 | 2/4 |
| conjugate-gradient | 349.03 | 670.87 | 633.93 | 648.67 | 672.55 | 662.93 | 2/4 |
| 3mm | 894.34 | 1,970.53 | 1,980.59 | 1,916.33 | 1,967.34 | 1,923.11 | 2/4 |

| Source | Issued pages | Parent refs | Canonical wire flat → stream, B | Cumulative retained page charge flat → stream, B | Stream native descriptors / words / lanes, B |
|---|---:|---:|---:|---:|---:|
| sum-bits | 1,237 | 13,260 | 513,384 → 314,567 | 700,544 → 466,969 | 115,160 / 169,632 / 4,049 |
| conjugate-gradient | 2,628 | 189,794 | 6,262,624 → 2,517,431 | 8,969,824 → 2,850,549 | 261,640 / 2,109,344 / 101,133 |
| 3mm | 3,597 | 526,429 | 17,104,712 → 5,995,652 | 24,756,928 → 6,452,042 | 358,920 / 5,232,480 / 342,674 |

On 3mm the direct-role header alone brings the canonical image down to 8,843,362 bytes. The selective representation saves a further 2,847,710 bytes by interning repeated address/version pairs in 2,980 of its 8,973 role columns, including 619 constant lanes. The other 5,993 columns remain direct.

The 3mm stream removes 64.95% of canonical bytes and 73.94% of cumulative retained page charge. FNV stamping, preparing dictionary entries, resolving slots during verification, source checks and actual RHS still execute. The two best 3mm medians each beat flat in only two of four pairs. On CG the simple direct-word layout beat flat in all four pairs, but it retained more bytes than the selective page. No uniform full-pass speed advantage was established for dictionary encoding. This is an inference-page result, with no claim about steady Graph or process memory. [Measurements and source/physical digests](results.json)

The native coordinate regression also exercises dictionaries of 1, 256, 257, 65,536 and 65,537 entries. Each pair of consecutive source versions shares a physical function row, which checks that version cannot be dropped from the dictionary key. Every boundary round-trips through the canonical wire decoder.

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/factored-receipt-pages
python "$d/build.py" "$EXP/factor"
python "$d/study.py" "$EXP" "$EXP/factor/session" "$EXP/factor-study"
cargo test --manifest-path "$EXP/factor/tree/Cargo.toml" --target-dir "$EXP/factor/target" --release --locked --offline -p eggfuse-cell-runtime --lib --features precomputed-forest,slot-transfer-audit factor_coordinate_tests
python "$d/verify.py"
```
