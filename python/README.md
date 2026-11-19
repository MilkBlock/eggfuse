# EggFuse offline tools

Install with `python -m pip install ./python`. The wheel supplies the compile and verify commands. Compilation calls the repository's Rust executable; verification runs on NumPy and consumes the predictions after device inference completes.

```sh
cargo build --release --locked -p eggfuse-cell-compiler --example real_completion_dataset
python -m eggfuse compile scheduled.egg --compiler-binary target/release/examples/real_completion_dataset --output plan.json
python -m eggfuse verify --plan plan.json --input graph.json --predictions predictions.json
```

The compiler accepts the supported direct-projection recipe with the ordered make and finish schedule. The verifier checks both committed target relations of the fixed two-rule source contract, including the actual parent slot selected by each Result proposal. Exit status 1 reports an incomplete or invalid prediction. Training and inference live in the [standalone PyTorch directory](../benchmarks/multi-row-generation/torch_crossrun/README.md). Release 0.2 exposes `compile_projection`, `projection_recipe` and `verify_crossrun`. The MLX implementation used for historical measurements is archived in the benchmark tree.
