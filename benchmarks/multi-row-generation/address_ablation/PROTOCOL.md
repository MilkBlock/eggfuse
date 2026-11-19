# Figure 03. Rotary addressing on multiple rows of multi-port Cells

Freeze before fitting. Compare four matched scorers: flat token address rL+t;
separate (row, token) axes; separate (row, token, port) axes; and one packed
address (rL+t)P+p including the port. All have 48 rotary channels, the same
content/port features, candidate set, loss, parameter budget and per-seed
initialization. The packed arm tests whether simply putting all address
information into the rotation suffices. Disable CPU fallback. Do not filter
candidates, inverse-map predicted pointers on CPU, or fill missing parents.

Every Cell holds P separately addressable port records. The first Run has one
query per destination port; it must follow a source-issued reference and emit
the selected source's actual identity and value in a new token. The assignment
of source origins to generated slots is permuted. Finish receives only this
generated frontier and requests specified in the ORIGINAL address space. It
must find the generated parent slot, which is not supplied. Both Runs check
physical references; equal scalar payloads cannot rescue a wrong parent.

Fit from scratch on 512 graphs in each of four layouts (2,3,2), (2,4,3),
(3,4,2), (4,3,3), fixed data seeds 91000..91003. For each initialization seed
1703/1709, use 1024 Adam updates at 0.002, batch 32, cycling layouts and drawing
the same per-graph indices. Supervise both inferred pointer distributions;
never pass a target into model.forward. No early stopping or endpoint-based
tuning. Save initial hashes and final weights.

Evaluate 128 fresh graphs per panel. From the SAME 4x3x3 graphs (seed 92001),
produce independent full physical relayouts into 6x2x3, 2x6x3 and 4x3x3,
including per-Cell port reordering. The relayouts hold cell count and active
port count constant. Test a new port count 4x3x4 (seed 92002) and its 6x2x4
relayout. Stress 8x6x4 (seed 92003) and its 4x12x4 relayout, also with the
same logical inputs across each pair. Ports 0..2 occur during training;
port 3 is held out as an ordinal. Reused within-width permutations in the small
vocabulary are possible; distinguish fresh applied maps from an unseen operator.
The experiment concerns address resolution with known requests and fixed
emission slots, not discovery of all witnesses or variable-number generation.

Measure both per-Run and cumulative exact graphs; cross-row and within-row
pointer accuracy, wrong Cell versus right Cell/wrong port, resident parent
availability, zeros/duplicates/omissions, mapped-back discrete predictions
and query/value consistency. End-to-end batch-one MPS time includes raw
address/value transfer, both Runs, returned real token and synchronization;
per-layout address constants can be resident. Report 32 rotating-order samples
per arm after warmup. Keep results when accuracy differs. Compare continuous
state under relayout descriptively if relevant; separate this from a canonical
whole-state or saturation guarantee. Also test address resolution on saved real
neural Pair origins from Figure 20 as a separately identified offline transfer.
