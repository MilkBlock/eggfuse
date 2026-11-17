# 多 row 生成：稳定输出接口与长接续

本实验关注同一张图内多个 row 能否快速生成可互相引用、可供下一轮消费的 token。它是 MLX/Metal 独立神经原型，不是实际 egglog/eggcc 引擎，也没有压缩目标。

## 任务和数据流

每个 row 有多个 token，batch 维才表示不同图。第一轮从打乱分布的 A/B 输入选择匹配端口，生成 Pair；之后反复组合 `L.next = R.key` 的 Cell，输出四个字段 `L.key, R.next, L.value, R.aux` 和父引用。每轮把上一轮生成的状态直接交给网络，没有 CPU 匹配回填或 teacher 中间状态。

这轮有两种输出接口：

- `continuous`：下一轮消费网络的原始 64 维连续状态。
- `typed`：网络仍预测所有字段及匹配指针，但把自己预测的四个类别转成规范 one-hot，40 维符号码加 24 维零填充，再交给下一轮。训练使用 straight-through 梯度估计；推理不读取正确答案，错误预测不会被纠正。

所以 typed 的结果证明的是**网络生成的离散接口可持续接续**。它没有证明任意连续 latent 可以隐式、无损地保存图状态。两个模板仍是手工给定；本实验没有学习 Bake 模板。

## 12 轮检查

协议在 [PROTOCOL.md](PROTOCOL.md)。两种表示均从头训练，数据、6000 步预算、维数、行内查询交互与种子配对。训练图有 6/8 个锚点，训练深度为 2/3/4。

验收使用两个留出的无标号结构：16 个锚点的双尾链（8 rows × 2 tokens），以及 12 个锚点的尾链入二环（3 × 4）。每个结构有 256 个随机编号、布局和数值样本，**不是 512 种独立拓扑**。拟合前检查它们的无标号结构签名均不在训练和以前检查过的数据里。

| 输出接口／种子 | 双尾链：12 轮全部正确 | 尾链入二环：12 轮全部正确 |
| --- | ---: | ---: |
| continuous / 1703 | 3/256 | 10/256 |
| continuous / 1709 | 0/256 | 6/256 |
| typed / 1703 | 256/256 | 256/256 |
| typed / 1709 | 256/256 | 256/256 |

“全部正确”要求从第一轮起每轮指针、字段、二维引用地址均正确，实际传递的状态可解码出所声明的字段。某次错误之后偶然恢复正确，不算通过。独立 NumPy 进程从保存的真实输出重新审计，另外检查非有限值、one-hot 格式、零填充、模型哈希和读出绑定；四份 fresh panel 审计均通过。CPU 审计不执行网络，也不修改输出。

路径长度按 1、2、4……翻倍，但有限尾链的端点很快进入周期。因此 12 轮是生成接口反复消费的压力检查，不代表完成了 12 层全新规则，也不是饱和证明。

失败对照完整保留：原两轮连续模型的冻结八轮检查，以及继续训练到四轮的失败结果，见 [depth](../depth/README.md)。不能只保留 typed 的正面结果。

## 含验证的速度

完整报告见 [因果基线](../causal/README.md)。以下是**两轮**生成的单图中位数，包含初始特征构建、上传、神经生成和 GPU 检查；不包括离线训练和事后 CPU 审计。两种布局各计时 32 个图，每个模型均为 32/32 正确。

| 布局／种子 | typed 批量生成 | 因果逐 token，K/V 缓存 | 比值 |
| --- | ---: | ---: | ---: |
| 8×2 / 1703，32 个输出 token | 1.486 ms | 12.037 ms | 8.10× |
| 8×2 / 1709，32 个输出 token | 1.488 ms | 11.585 ms | 7.79× |
| 3×4 / 1703，24 个输出 token | 1.520 ms | 9.221 ms | 6.07× |
| 3×4 / 1709，24 个输出 token | 1.509 ms | 8.949 ms | 5.93× |

这些速度不能当作 12 轮速度，也不是相对 egglog 的提速。因果模型训练来源和预算不同，比较不是只有架构改变的消融。32 个样本的中位数也不等于大规模 GPU 稳态吞吐。

## 尚未证明的互补性

输出位置目前由源锚点固定，一锚点一输出。网络学习选择匹配对象及计算字段，程序已经承担了基本分工。跨 row 父引用确实由神经指针选择，但没有证明网络能自主分配任务、决定输出数量、处理两个 row 抢同一个 ownership 或跨 row union。

下一项应取消“一锚点一输出”的便利条件，设置零个／多个合法匹配、重叠候选和待完成义务。先冻结可审计契约，再比较完整覆盖率、重复、遗漏、冲突、跨 row 引用错误、修正轮数和每秒完整合法批数。只看 token/s 会奖励快速生成重复或无效 token。压缩率不作为验收指标。

## 复现

在硬盘工作区，所有计算使用共享队列。示例：

```sh
~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python \
  benchmarks/multi-row-generation/typed/train.py \
  /Volumes/EggFuseWorkspace/experiments/NEW-typed-1703 \
  --representation typed --seed 1703

~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python \
  benchmarks/multi-row-generation/depth/audit_saved.py \
  /Volumes/EggFuseWorkspace/experiments/multi-row-token-interface-20261118/typed-1703/two_tails.npz
```

连续对照改用 `--representation continuous`；种子另跑 1709。连续模型验收失败退出 1 是记录到的实验结果，不应忽略或重试到通过。原始文本结果在 `results/`，二进制权重和轨迹留在硬盘实验目录、不进 Git。[来源账本](../depth/results/provenance.json)记录任务退出码、模型结果与代码哈希。
