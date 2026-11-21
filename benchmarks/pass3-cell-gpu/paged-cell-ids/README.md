# Locality of physical Cell addressing on complete source inference

An emitted fact refers to a Cell by its logical u32 identity and operation number. A group of ordered RHS bindings can create many successive identities, while union, verification and repair later revisit a subset of those identities. This makes it possible to change physical record placement without modifying any visible reference or owner. No workload name or rule number affects the layout.

The hash control uses the default ordinary FxHashMap. The arena control reuses the existing sparse backend's dense live-record arena, linking only that storage type into the ordinary runtime: lookup maps a stable ID to a physical vector slot, and removal swaps in the final record and fixes its reverse slot. The two paged variants partition logical IDs into groups of 16 or 64. A presence bitmap and popcount locate each Cell in a sorted, compact per-page vector. Birth and retirement may shift later records in that page, and an empty page releases its vector. A faraway ID uses a sparse directory. If contiguous growth later reaches an outlier page its existing backing migrates into the direct directory. Each stored record retains its actual id for existing iteration and source callers.

The same instrumented source produces four separately linked release binaries with the same allocator; a separate default EggFuse process supplies the vanilla time and original source reference. Every specialized binary is also measured with actual exact search and its own learned providers disabled. Learned and exact programs are interleaved in one timing matrix, with four samples after warmup. Detailed runs compare the independent per-Run RHS, effective writes, union, Spine, source schedule and final graph. Learned runs also preserve the original sealed stream, parent selection, commit ancestry and actual physical allocation IDs. The layout counters measure physical occupancy at the terminal boundary. A separate fresh-process experiment measures OS high-water RSS including startup and export.

| Program | Default exact | Hash exact / learned | Dense arena exact / learned | Page 16 exact / learned | Page 64 exact / learned, ms |
|---|---:|---:|---:|---:|---:|
| sum-bits | 20.78 | 21.60 / 31.79 | 21.49 / 30.82 | 21.64 / 31.68 | 21.34 / 31.32 |
| conjugate-gradient | 354.66 | 375.42 / 664.06 | 361.77 / 619.65 | 357.50 / 644.74 | 372.09 / 632.00 |
| 3mm | 924.73 | 960.04 / 1,962.14 | 899.59 / 1,810.46 | 903.10 / 1,847.42 | 904.67 / 1,845.54 |

| Program | Live Cells | Page 64 records inserted / retired | Record slots shifted | Reserved record capacities: hash / arena / page 16 / page 64 |
|---|---:|---:|---:|---:|
| sum-bits | 2,875 | 5,996 / 3,121 | 8,695 | 3,366 / 4,096 / 4,608 / 4,828 |
| conjugate-gradient | 35,238 | 97,267 / 62,029 | 664,288 | 53,165 / 65,536 / 55,644 / 70,544 |
| 3mm | 94,210 | 230,008 / 135,798 | 1,451,250 | 97,840 / 131,072 / 132,188 / 158,340 |

| Whole-process peak RSS, MiB | Hash | Dense arena | Page 16 | Page 64 |
|---|---:|---:|---:|---:|
| conjugate-gradient | 464.48 | 460.72 | 462.58 | 462.98 |
| 3mm | 747.09 | 746.31 | 743.33 | 738.52 |

The dense arena had the lowest measured learned median on all three inputs. The packed pages retain a record id for the existing iterator interface, and moving later entries during rank changes creates extra work. Source order, original pointers and fresh allocation traces remain identical. The slot capacities use each implementation’s own record representation and do not directly measure bytes. The Rust storage test covers replacements, deletion, a moved outlier after directory growth, u32::MAX and both page widths. [Timings and terminal occupancy](results.json) · [Process high-water samples](rss.json)

```sh
d=benchmarks/pass3-cell-gpu/paged-cell-ids
python "$d/build.py" "$EXP/cell-layouts"
python "$d/study.py" "$EXP" "$EXP/cell-layouts" "$EXP/cell-layout-study"
python "$d/peak.py" "$EXP" "$EXP/cell-layouts" "$EXP/cell-layout-study/results.json" "$EXP/cell-layout-rss"
cargo test --manifest-path "$EXP/cell-layouts/tree/Cargo.toml" --offline --locked --release -p eggfuse-cell-runtime --lib --features precomputed-forest,slot-transfer-audit,receipt-page64 sparse_keys_rank_and_retirement
python "$d/verify.py"
```
