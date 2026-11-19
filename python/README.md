# EggFuse for Python

The `eggfuse` package exposes the experimental two-Run Cell model on Apple Silicon with Metal. Its first Run emits Pair instance tokens. Its second Run consumes those tokens and the Request rows to generate Result witnesses. The package loads the learned, static-projection and auxiliary-training checkpoints from the cross-Run experiment.

Build an installable wheel from a repository checkout and install it into the environment that will run MLX.

```sh
uv build --wheel python --out-dir dist
python -m pip install dist/eggfuse-0.1.0-py3-none-any.whl
```

`compile_projection(source, *, compiler_binary, output_path=None)` accepts scheduled `.egg` text or a `pathlib.Path`. Supply the path to the Rust executable built by the following command. The program compiles the source and runs the `make`, `finish` schedule. The Python binding reads the output-column routes from the typed recipe.

```sh
cargo build --release --locked -p eggfuse-cell-compiler --example real_completion_dataset
```

```python
from pathlib import Path
import eggfuse

# join.egg contains the A/B -> Pair and Pair/Request -> Result rules followed
# by (run-schedule (seq (run make) (run finish))).
plan_path = Path('plan.json')
eggfuse.compile_projection(Path('join.egg'),
                          compiler_binary=Path('target/release/examples/real_completion_dataset'),
                          output_path=plan_path)
model = eggfuse.load_model(Path('checkpoints/static-1703'), plan_path)
a = [[3, 1], [3, 2], [5, 0], [7, 3]]
b = [[3, 2], [3, 0], [5, 1], [1, 2]]
requests = [[0, 1, 0], [2, 2, 3], [0, 2, 2], [3, 3, 1]]
stages, pairs = eggfuse.infer(model, a, b, requests)
print(stages[1]['active'].tolist(), pairs.shape)  # (1, 8, 90)
```

Each of the four A/B rows holds `[key, value]`. Keys use 0–7 and values use 0–3. Each of the four requests holds `[A row index, B row index, tag]`, with all three values in 0–3. The API accepts single graphs or a leading batch dimension. Arithmetic and selection execute on the device. Both output dictionaries contain `active`, `pointers` and `fields` with shapes `[batch,8]`, `[batch,8,2]` and `[batch,8,3]`. The first stage points to A/B rows. The second points to a generated Pair slot and a Request row. Outputs are model predictions. Whole-graph correctness requires checking legal witnesses and full coverage.

The checkpoint directory contains `fit.json` and `model.safetensors`. The loader checks the recorded hashes of the weights and the serialized plan file. `projection_recipe(plan)` accepts a plan dict or file and returns the immutable routes used by `CrossRun(arm, routes)`. Calling the model directly returns differentiable logits and the generated Pair tensor. `decode(logits)` converts the logits to the same discrete fields returned by `infer`. With `training_heads=True`, the `aux` arm exposes its field heads for supervision. `infer(..., mask='parents')` hides explicit references from the consumer; `parents_latent` also hides latent values.

The wheel includes Python code for this model and its recipe reader. The compiler executable, checkpoints and workload data are separate inputs. Its supported combination is two direct-projection rules and the 4×2 layout with four A/B/Request entries. The API describes the model's current interface and capacity.
