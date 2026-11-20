# Credit assignment for two recurrent native CPU rows

At each real source Run, two rows get four waves. The static owner is a hash of the typed entrance and physical source address. Within each row, later waves see their own generated token; an issued task cannot be reissued in this Run. The compiler provides unique-key suffixes and 15 checked macro continuations. The model selects the anchor and whether to issue a macro. Rust verifies it and commits in source order. All arms retain exact residual completion.

Only the four training families supply the native observations, training reward labels and cost calibration. An exhaustive training diagnostic measures which presented roots can actually win. The join labels match a native root to the offline Bake target by leaf and actual binding ordinal. A macro can earn at most one later ordinal. Coverage labels and timing-model values never enter the online forward pass.

Each seed starts from its one-emission checkpoint, receives 100 shared warm-start updates, then four copies train for another 160 updates. Each receives identical draws of source windows and a fixed sample budget. A training unroll feeds the row's own sampled output into the next step. Greedy deployment uses the identical native state and compiled verifier in each condition.

* **Supervised** maximizes the probability of an available valid unclaimed binding or abstention, along with the conditional unit loss. It uses no individual expert row labels.
* **Team** adds a policy-gradient term for unique achieved root and child ordinals. Both rows receive the joint reward and a moving baseline.
* **Weighted** uses a fitted marginal-time reward. Actual attempts and different root/suffix work and later completions enter the price. The per-Run and per-bank terms are action-independent and cancel from the advantage. Ordered publication, notifications and waiting are included in the full native Run measurements used for calibration.
* **Weighted CF** keeps the weighted objective and replaces one row with abstention while holding its peer fixed. Overlapping child conclusions get a single credit.

The calibration fits paired Run times on the four training programs, winsorizing at 1% / 99%. Fitted coefficients are noisy predictors of aggregate source work, not causal prices for individual operations. Negative measured net values can favor abstention. This trial evaluates that choice directly in the running system. [Calibration](calibration.json)

| Workload / seed | Supervised RHS | Team RHS | Weighted RHS | Weighted CF RHS | Supervised / team inference ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 447 | 449 | 382 | 382 | 34.26 / 34.38 |
| sum-bits/1709 | 453 | 456 | 399 | 404 | 33.73 / 34.34 |
| dot-product/1703 | 413 | 418 | 320 | 320 | 31.73 / 31.29 |
| dot-product/1709 | 424 | 426 | 339 | 348 | 31.14 / 31.51 |
| gemm-bias-relu/1703 | 435 | 441 | 349 | 349 | 59.48 / 59.40 |
| gemm-bias-relu/1709 | 442 | 452 | 365 | 373 | 62.03 / 63.18 |
| stable-argmax/1703 | 363 | 364 | 306 | 306 | 33.96 / 34.08 |
| stable-argmax/1709 | 375 | 377 | 327 | 335 | 33.99 / 33.74 |

The team objective increased distinct commits on both anchor programs and seeds, modestly relative to the remaining full-program gap. The weighted policies reduce actual coverage in those four pairs. The common small action vocabulary and eight-slot ceiling dominate these improvements. All arms have source-aligned ordered RHS, writes, Spine, unions and final graph. Disabling residual search misses initialization at Run 1. Timings include ten ordered pairs of native full Pass 3 executions (timed arm order rotates and reverses). [Raw work, missing known roots and timings](results.json)

Reproduce with the external workspace PyTorch environment during training and the default native CPU during evaluation. Use `capture.py CORPUS REFERENCE ACTION_MODELS COMPOSE_TARGETS AUDIT_BINARY OUT` then `train.py OUT ACTION_WEIGHTS DONOR_PROGRAM TRAIN_OUT`. Run `evaluate.py AUDIT_BINARY REFERENCE CORPUS TRAIN_OUT ROW_ADMISSION_REFERENCE RESULTS_OUT`. All output directories must be new.
