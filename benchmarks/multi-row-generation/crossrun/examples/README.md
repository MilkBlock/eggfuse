# 用 Python 训练和推理

`train.py` 使用 `import eggfuse` 构造两条规则的模型，计算激活、父引用和字段的损失，在 Metal 上执行反向传播与 Adam 更新，保存 `model.safetensors` 和 `fit.json`。`infer.py` 用相同的编译计划加载这些权重，执行 make 和 finish，一次返回两个 Run 的实际输出。

在 Apple Silicon 的 MLX 环境安装本仓库的 Python 包。示例采用 NumPy，完整实验使用 MLX 0.32.4 和 NumPy 2.5.4。下面的命令可从任意工作目录执行。`repo` 指向当前 checkout，`artifacts` 指向存有前一轮反馈模型的实验目录。

```sh
repo=/Volumes/EggFuseWorkspace/worktrees/eggfuse
artifacts=/Volumes/EggFuseWorkspace/experiments
examples="$repo/benchmarks/multi-row-generation/crossrun/examples"
plan="$repo/benchmarks/multi-row-generation/crossrun/compiler/plan.json"
python -m pip install "$repo/python" numpy

python "$examples/train.py" --arm aux --seed 1703 \
  --parent "$artifacts/multi-row-streaming-20261118/feedback-1703" \
  --output ./aux-example

python "$examples/infer.py" --checkpoint ./aux-example --plan "$plan" > prediction.json
```

快速冒烟时，在训练命令加 `--steps 2` 并换一个新的输出目录。默认训练 2000 步，batch 32，Adam 学习率 0.0003。`--arm learned` 在两个 Run 都预测字段，`--arm static` 从编译计划投影字段，`--arm aux` 在静态投影的基础上增加训练期字段损失。切换为 1709 时也需选择 `feedback-1709` 父权重。仅推理时可以直接给 `--checkpoint` 指定实验已训练好的目录。

训练样本、标签分配求解器和 streaming 父权重属于实验资产。示例默认相对于脚本查找 `crossrun/data/crossrun_data.py` 和 `allocation/assignment.py`；如单独复制示例，使用 `--assets /path/to/benchmarks/multi-row-generation`。`--data train.npz` 可显式读取已有 `a,b,requests,target1,target2` 数组。训练器让 GPU 先产生一组槽位提案，随后在 CPU 上把无序监督标签对齐到这些输出槽，再按这些标签更新参数。推理入口仅接收源表、权重、编译计划和选定的 mask。

默认输入中 `A0` 和 `A1` 都是 `[3,1]`，`B0` 是 `[3,2]`，第一条 Request 指向 `(A1,B0)`。用 `--input input.json` 可替换 `a`、`b`、`requests` 三个原始表。`--mask parents` 在第二个 Run 屏蔽 Pair 中两个显式父引用，`--mask parents_latent` 同时屏蔽连续 latent。

```python
import eggfuse
import mlx.core as mx

model = eggfuse.load_model(checkpoint, plan)
(make, finish), pair_token = eggfuse.infer(model, a, b, requests, mask="none")
mx.eval(make, finish, pair_token)
```

`make` 和 `finish` 各返回 `active`、`pointers`、`fields`。`make["pointers"]`指向 A/B 实例。`finish` 的两个引用指向实际生成的 Pair 槽位和 Request 槽位。对于单图，`pair_token` 形状为 `[1,8,90]`，这是第二个 Run 消费的实际 GPU tensor。CLI 输出完整 Pair tensor 和所有槽位的激活、指针与字段，包括未激活槽位；解读提案时使用相应 `active` 位。

验证时将 wheel 离线安装在仓库外的独立目录，并在该目录执行完整 aux/1703 训练和保存后加载推理。两个实现的初始参数、4096 图训练输入、首批监督分配、首批 logits、生成 token 及损失均相同。首批所有参数梯度的相对 L2 差异约为 2.94×10⁻⁹，重复运行原始反传的相应差异约为 2.99×10⁻⁹。在这台机器上，相同配置的 2000 步重训得到不同的最终权重；原 `fit.py` 自身重跑也出现该现象。在固定同一最终权重后，三种 mask 的 CLI 输出均与原研究实现逐位一致，包括两阶段离散输出及完整 Pair token。实验中六组得分对应各自存档的原始 checkpoint。逐项数值、权重与 wheel 哈希记在 `example-validation.json`。
