# 用 PyTorch 执行两条跨 Run 的规则

[model.py](model.py) 定义普通的 `torch.nn.Module`。[train.py](train.py) 负责数据、无序集合的目标分配、损失、反传和 Adam 更新。[infer.py](infer.py) 读取原始 A、B、Request 表，在设备上完成两次 Run。三个脚本均独立于 EggFuse 和 MLX。EggFuse 0.2 在训练之前生成 `plan.json`，在推理结束之后验证已保存的输出。

```python
import torch
from model import CrossRun, decode

model = CrossRun("aux", plan_path).to("mps")
model.load_state_dict(torch.load(weights_path, map_location="mps", weights_only=True))
with torch.inference_mode():
    stages, pair_token = model(a, b, requests)  # 三个输入已经在 MPS 上
    make, finish = decode(stages)
```

`CrossRun.forward` 将 `self.make(...)` 返回的 `pair_token` 直接传给 `self.finish(pair_token, requests, ...)`。每个图有 4 个 row，每行两个输出位置。Pair 的 90 个 FP32 分量包括 64 维 latent 以及激活、父引用和字段的离散编码。神经网络在两个 Run 都自由选择实例引用。`static` 和 `aux` 用编译器给出的列映射在设备上 gather 所选记录的字段。`aux` 的附加字段头只在训练损失中生效。CPU 只在离线训练期间对齐无序标签，设备推理完成后才下载结果供审计。MPS 验收关闭了 CPU 算子回退。

## 运行

可从仓库根目录执行下面的命令。已验证环境是 Apple Silicon、Python 3.14、PyTorch 2.15 及 MLX 0.32.4（仅用于比较）。训练和推理采用 [PyTorch 依赖](requirements.txt)，离线工具可另外用 `python -m pip install ./python` 安装。

```sh
t=benchmarks/multi-row-generation/torch_crossrun
plan=benchmarks/multi-row-generation/crossrun/compiler/plan.json
runs=/Volumes/EggFuseWorkspace/experiments
weights="$runs/multi-row-torch-20261119"
export PYTORCH_ENABLE_MPS_FALLBACK=0

# 从六份存档权重转换 final.pt 和配对的 initial.pt。
python "$t/convert.py" --mlx-root "$runs/multi-row-crossrun-20261119" --torch-root "$weights" --plan "$plan"

# 不提供 --input 时使用带有相同字段、不同父地址的例子。
python "$t/infer.py" --plan "$plan" --arm aux --checkpoint "$weights/aux-1703/final.pt" --device mps > predictions.json

# 从实验的配对初值训练。输出目录需要是新的。
python "$t/train.py" --plan "$plan" --arm aux --seed 1703 --init "$weights/aux-1703/initial.pt" --device mps --output new-aux-1703

# 分开进程运行外部编译、验证工具。graph.json 应与本次推理的 --input 对应。
python -m eggfuse verify --plan "$plan" --input graph.json --predictions predictions.json
```

训练默认 2,000 次更新，batch 32。为匹配原 MLX 实验，使用无一二阶矩偏差校正的 Adam，更新公式位于 train.py。训练使用冻结 NumPy 数据和训练期 Hungarian 分配。所有精度与后端计时对照均使用转换后的六个固定最终检查点。[离线工具说明](../../../python/README.md)

## 冻结模型的对齐结果

六个模型各有 139 个 FP32 参数，六份初始化及六份最终权重均按原键名、形状和字节严格转换为 PyTorch state_dict。左父、右父碰撞留出集各 256 图，采用相同的显式父引用开放、屏蔽父引用和同时屏蔽父引用及 latent 三种条件。共 9,216 图次，每个图次都包括两个 Run。两阶段所有槽位的激活、指针、离散字段与冻结 MLX 输出完全一致，完整覆盖判定、重复、遗漏、非法绑定和反事实父引用审计全部一致。额外的 1,152 次单图配对调用的离散输出也一致。跨框架连续 latent 有 FP32 数值差异，批量运行最大绝对差为 0.00020337。相等结论适用于上述离散输出及验收面板。[逐项结果](results/comparison.json)

下表合并左右碰撞面板，均为开放父引用。每个 seed 共享 512 张非空图、910 项源义务。延迟是每个模型在两个面板各 32 个同图单图调用共 64 个样本上的中位数，端点是两个 Run、解码和完整 Pair 张量完成设备同步。

| 模型 | 种子 | 两端第二 Run 完整图 /512 | 两端重复 / 遗漏 | PyTorch MPS eager | MLX Metal eager |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原字段头 | 1703 | 49 | 3 / 547 | 13.89 ms | 9.03 ms |
| 静态投影 | 1703 | 39 | 10 / 636 | 14.05 ms | 9.43 ms |
| 静态投影＋训练期字段头 | 1703 | 65 | 13 / 550 | 15.29 ms | 10.02 ms |
| 原字段头 | 1709 | 41 | 18 / 582 | 13.73 ms | 8.87 ms |
| 静态投影 | 1709 | 37 | 7 / 586 | 14.40 ms | 10.09 ms |
| 静态投影＋训练期字段头 | 1709 | 67 | 16 / 579 | 13.87 ms | 9.47 ms |

按种子、模型、左右面板分开的 12 个开放父引用计时条件，PyTorch/MLX 耗时比的中位数为 **1.48**，范围 1.43–1.58。两端均预热，输入相同且执行顺序逐样本轮换。样本窗口包括原始整数表设备上传、两条规则、离散解码及设备同步。训练、文件读取、CPU 审计和输出 JSON 序列化另计。这是两种 eager 实现的单图比较，旧版使用 mx.compile 的数字有不同的计时条件。

复现完整比较需同时安装 MLX，使用同一台机器上的两个后端。比较脚本从 benchmark 归档加载旧模型，生产训练和推理脚本只 import PyTorch（训练同时使用 NumPy 标签）。
```sh
python "$t/compare.py" --plan "$plan" --torch-root "$weights" --mlx-root "$runs/multi-row-crossrun-20261119" --output fresh-comparison.json
python "$t/summarize.py" fresh-comparison.json
```

单独用 PyTorch 从 aux/1703 的配对初值在 MPS 完成 2,000 步训练，最后重新加载权重，通过推理 CLI 生成两个碰撞面板。EggFuse 在独立 CPU 审计时得到左侧 43/256、右侧 30/256 完整图。这是新训练轨迹的一次观察，后端对齐表使用转换前后相同的冻结权重。[训练记录](results/fit.json) · [重训模型的事后验证](results/validation.json)

在边界检查中，make 的输出、finish 收到的第一个参数以及返回给调用者的 Pair 是同一个 MPS tensor 对象；对 finish 激活分数求导时，梯度可以回传至该张量的连续分量。[检查代码](check_handoff.py) · [结果](results/handoff.json)
