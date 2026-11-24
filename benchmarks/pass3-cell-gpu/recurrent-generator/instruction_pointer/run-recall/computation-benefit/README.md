# 提前计算的收益、回执证据与独立 Cell 生成

**Neural Execution / exclusive**，冻结 CCP v0.1，在 standalone EggFuse Cell CPU executor 上执行。训练使用 Metal，在线神经推理使用单线程 CPU。七个 workload 上，残差模型与固定提前计算产生的原生接受证明轨迹逐字节一致，包括具名父端口、版本、顺序和 repair 事件。残差保住了 A 的终图覆盖。EggCC 的新增覆盖为零。两个严格留出的计算布局给出了更窄的正结果，模型能自行连接多个原语，也会因检索拿到错误的计算结果而漏掉事实。

## A 到 B 的退化

在 A 自己推进的每个 Run 冻结快照、规则调度、8-bit LSH 候选域和逐层访问顺序。同一组完整路径同时计算旧 A 和上一轮 B 的分数，由 A 签发。影子 READ 会改变协议句柄编号，赢家按本次对齐的原生回执识别。两例各另有 2 个无父提交，均获接受。A 的终图哈希、签发证明数和全部接受数均与原实验核对。

| EggCC | 完整路径打分 | A / B 达到签发门槛 | A 的有父赢家中 B 保住 | 每 Run 配平实际名额后的 A / B 赢家数 | 首次漏掉赢家 / 独立状态哈希首次分歧 |
|---|---:|---:|---:|---:|---:|
| fact | 12,972 | 9,945 / 1,221 | 373 / 492 | 366 / 373，合计名额 1,221 | Run 6 / 6 |
| sum-divisors | 460,193 | 376,778 / 14,927 | 1,232 / 1,809 | 1,223 / 1,221，合计名额 14,872 | Run 6 / 7 |

两个生成器都遍历调度表，根和中间前缀共用 A。对 A 发起的 7 和 93 次成功计算，B 都会保留同一检索路径。第一个直接丢失发生在完整绑定的分数跨过签发阈值时。配平组按每 Run 两组实际可签发数的较小值，分别取同域中最高分的这么多项，测量已知 A 赢家的保留数。B 独有路径的语义价值需要另外签发核验。两个独立轨迹后续覆盖的差距包含漏推的后继。

| 完整证明读出的反事实 | fact 保留 A 赢家 / 492 | sum-divisors 保留 A 赢家 / 1,809 |
|---|---:|---:|
| B 原样 | 373 | 1,232 |
| 只给类型 | 0 | 0 |
| 去掉显式类型及其池化贡献 | 423 | 1,504 |
| 替换为上一个同类型的值 | 371 | 1,223 |
| 抹掉 B 状态分支中的成功、新鲜度、转发标记 | 458 | 1,660 |
| 在同一候选域，抹掉递归打分中的原字段向量及共享字段点积 | 209 | 537 |

执行器仍检查真实版本、类型和可见性。另做检索位置的影子干预，原 8-bit 桶覆盖全部带共享键的 283 和 1,261 个原生赢家。只翻转查询地址的一位，原赢家在这些桶中的出现次数均降至零。这与表中固定访问域后对决策向量做消融是两种实验。各个干预测的是特定通道，其他通道仍可携带相关证据。[同快照逐阶段结果](shadow.json)

## 训练与对照

- **A** 使用先前的哈希回执、递归生成器和计算路由。**fixed** 对每个有可用计算布局且普通检索桶非空的前缀执行静态配方，再检索伙伴。
- **residual** 冻结 A 的递归证明参数。关闭增量分支时，直接走 A；启动训练后的分支时，神经解码器在静态类型和可见端口范围内逐步选择原语、具名输入、此前的局部输出和程序结束。另一个预测值控制是否在读取候选前执行。成功回执的哈希进入冻结的字段检索器，类型化值进入单独的 Value Encoder，与静态规则特征和递归状态一起打分。加性修正从零初始化，在同一路径上只能提升最终证明分数。整个独立状态的 Coverage 仍须实测。
- **full** 使用同样的计算与检索接口，联合调整 A 在路径上使用的初始状态、输入编码、GRU、分数以及新的值分支。残差组和 full 组各训练 400 步，证明拟合涉及 2,417 和 7,836 个参数。两组沿用相同冻结检索键、同一监督、相同优化步数。边界、调度和 Cell Stream 游标沿用基线。每个神经程序的结束指令单独计费。
- 18 个训练程序，包括 EggCC loopfact、普通 grammar、多种操作数顺序、双分支、局部依赖链及两个大扇出输入。各自从同一初始状态比较四种提前计算范围，并以正反顺序各运行一次。相邻干预只改变一个桶占用区间的计算选择。54 个区间对照的最终状态哈希均相同。训练效用取访问量、失败或重复证明数、付费请求数、实测在线时间的相对减少量等权平均，各分量用两臂较大值归一化。墙钟包括执行、响应、编码、通信及训练探针计数。这是指定的多目标权衡；减少拒绝和减少 token 有部分重叠。信用按区间分给该区间内的训练前缀，无法精确到单个请求。
- 拟合使用 2,874 条区间样本、27,037 个原生标注的完整路径。执行过且在至少一个区间产生正收益的静态配方提供结构示范。另对同 sort 的不同局部计算结果做可执行的操作数替换，失去原本可复现的参考终图时加强原选择的监督。共有 138 条指令示范和 88 条有歧义的操作数示范，加权后分别为 292、254 条。部署只看到单步原语和可用操作数。这个实验测量有示范和反事实信用的结构泛化，不能推出从零发现算法。训练特征不包含数值化的 token ID。冻结的 A 曾用过 fact 和 sum-divisors，新分支只在 loopfact 上接触 EggCC。[实际训练成本对照](paired-inputs.json) · [训练明细](training.json)
- 新的四步布局留出有序操作数和 grammar 种子。在权重冻结后增测了全新种子的五步拓扑，训练集中最长为四步。两份受益模型均在归档成本数据上重复训练，权重逐字节复现。

## 独立执行

每个 workload 四臂、四次交替配对，共 112 次独立运行，全部到达原生调度终点。Coverage 计终图中不同的参考派生事实，初始事实除外。EPT 分子为实际签名的有效原子操作，分母含全部 READ、COMPUTE、PROVE 和神经程序结束指令。EPS 使用包含完整在线成本的墙钟。偏离参考的轨迹可以产生其他有效操作，仅比较 EPS 会偏向提早失去后继的模型。

| 程序 | 策略 | Coverage | 付费 token | 访问量 | EPT | 中位 EPS | 中位秒 | 残差比 A 快的配对／4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [cyk801](cyk801.json) | A | 6,567/6,567 | 50,257 | 200,389 | 0.13067 | 2,144.0 | 3.0634 |  |
| [cyk801](cyk801.json) | fixed | 6,567/6,567 | 50,069 | 195,269 | 0.13116 | 2,153.6 | 3.0494 |  |
| [cyk801](cyk801.json) | residual | 6,567/6,567 | 50,237 | 195,269 | 0.13072 | 2,140.7 | 3.0677 | 1 |
| [cyk801](cyk801.json) | full | 3,033/6,567 | 3,248 | 10,060 | 0.93381 | 11,891.2 | 0.2552 |  |
| [fact](fact.json) | A | 363/1,120 | 9,954 | 33,156 | 0.05646 | 297.5 | 1.8889 |  |
| [fact](fact.json) | fixed | 363/1,120 | 10,025 | 33,051 | 0.05606 | 291.9 | 1.9258 |  |
| [fact](fact.json) | residual | 363/1,120 | 10,150 | 33,051 | 0.05537 | 293.4 | 1.9157 | 1 |
| [fact](fact.json) | full | 164/1,120 | 497 | 6,063 | 0.63984 | 375.5 | 0.8468 |  |
| [sum-divisors](sum-divisors.json) | A | 1,404/8,018 | 376,873 | 727,022 | 0.00537 | 217.6 | 9.3012 |  |
| [sum-divisors](sum-divisors.json) | fixed | 1,404/8,018 | 376,985 | 726,810 | 0.00537 | 214.9 | 9.4172 |  |
| [sum-divisors](sum-divisors.json) | residual | 1,404/8,018 | 377,179 | 726,810 | 0.00537 | 214.6 | 9.4309 | 0 |
| [sum-divisors](sum-divisors.json) | full | 529/8,018 | 1,628 | 31,024 | 0.53931 | 357.4 | 2.4569 |  |
| [grammar-25112473](grammar-25112473.json) | A | 200/200 | 330 | 2,922 | 0.60606 | 4,140.6 | 0.0484 |  |
| [grammar-25112473](grammar-25112473.json) | fixed | 200/200 | 354 | 2,890 | 0.56497 | 4,200.0 | 0.0476 |  |
| [grammar-25112473](grammar-25112473.json) | residual | 200/200 | 386 | 2,890 | 0.51813 | 3,880.7 | 0.0515 | 1 |
| [grammar-25112473](grammar-25112473.json) | full | 116/200 | 112 | 1,058 | 1.03571 | 4,158.3 | 0.0279 |  |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | A | 256/256 | 984 | 4,188 | 0.26016 | 4,576.8 | 0.0560 |  |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | fixed | 256/256 | 1,206 | 3,584 | 0.21227 | 4,355.9 | 0.0588 |  |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | residual | 256/256 | 1,238 | 3,584 | 0.20679 | 4,187.4 | 0.0611 | 0 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | full | 156/256 | 292 | 901 | 0.53425 | 6,185.6 | 0.0252 |  |
| [grammar-benefit-held-11901371](grammar-benefit-held-11901371.json) | A | 147/147 | 466 | 2,092 | 0.31545 | 4,209.9 | 0.0349 |  |
| [grammar-benefit-held-11901371](grammar-benefit-held-11901371.json) | fixed | 147/147 | 826 | 1,680 | 0.17797 | 3,785.6 | 0.0388 |  |
| [grammar-benefit-held-11901371](grammar-benefit-held-11901371.json) | residual | 147/147 | 850 | 1,680 | 0.17294 | 3,305.9 | 0.0445 | 0 |
| [grammar-benefit-held-11901371](grammar-benefit-held-11901371.json) | full | 87/147 | 113 | 642 | 0.76991 | 3,466.5 | 0.0251 |  |
| [grammar-benefit-held-deep-11901379](grammar-benefit-held-deep-11901379.json) | A | 83/83 | 204 | 830 | 0.40686 | 3,565.3 | 0.0233 |  |
| [grammar-benefit-held-deep-11901379](grammar-benefit-held-deep-11901379.json) | fixed | 83/83 | 424 | 668 | 0.19575 | 3,251.7 | 0.0255 |  |
| [grammar-benefit-held-deep-11901379](grammar-benefit-held-deep-11901379.json) | residual | 83/83 | 444 | 668 | 0.18694 | 2,735.0 | 0.0303 | 0 |
| [grammar-benefit-held-deep-11901379](grammar-benefit-held-deep-11901379.json) | full | 45/83 | 80 | 191 | 0.56250 | 2,672.7 | 0.0168 |  |

完整配对的网络计数、CPU 核验、按状态分类的拒绝和重复、事务大小、同步次数、内存及索引维护成本都在对应 workload 的 JSON 内。每组都独立运行；精确引擎补全数为零。每次配对还交替测了纯精确执行和原生 teacher 重放。等 Coverage 曲线用首次达到相同参考事实数的已采样 Run 边界，给出了真实首次越过该 Coverage 的成本上界。[同 Coverage 成本曲线](matched-coverage.pdf) · [原始曲线数据](matched-coverage.csv)

在七个 workload 上 residual 的新增末端签发数均为零。它与 fixed 的访问量、成功回执驱动的查询数、签发的证明数和接受轨迹一致。这说明本轮学到了可以执行的计算结构，但在这些轨迹上仍相当于全用。对于五步留出布局，计算节省 162 次访问却多花 240 枚 token，最终 83 个派生事实相同。对两个 EggCC 程序，保护 A 避免了 full 的覆盖损失，同时没有新增有效 Cell。

## 计算结果是否包含可用证据

对冻结 residual 模型单独干预。关闭提前计算后，CYK801 仍达到 6,567/6,567，付费量从 50,237 升至 1,072,213。维持计算和回执状态，仅将成功回执用于检索的哈希替换为同一程序的其他成功结果，覆盖降至 2,917。三步、四步、五步布局对应从 256、147、83 降到 141、80、44。这支持检索地址使用了结果的具体内容。在这些干预中决策分支仍收到原本的类型化值，实验不能把收益归给 Value Encoder 对数值的理解。EggCC fact 替换了 45 个结果哈希，覆盖仍为 363；sum-divisors 替换了 102 个，覆盖从 1,404 降至 1,372。绕开尚未启用的分支时，六个干预 workload 的原生状态、请求数和逐类回执都与 A 相同。[独立执行干预](evidence.json)

## 复现

从 instruction_pointer 目录运行。ROOT 为上一轮的原生数据与构建目录。模型训练使用 PyTorch 和 NumPy，绘图可独立使用装有 matplotlib 的 Python 环境。保持 Python 哈希种子固定以复现相同快照的排序。

~~~sh
export PYTHONHASHSEED=0
OUT=run-recall/computation-benefit
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --cases $(python -c 'from benefit_corpus import sources; print(" ".join(n for n,_ in sources("")))')
python compute_pairs.py "$ROOT" "$ROOT/benefit-pairs"
python train_benefit.py "$ROOT" "$OUT" --paired-inputs "$OUT/paired-inputs.json"
python benefit_experiment.py "$ROOT" "$OUT"
python computation_shadow.py "$ROOT" "$OUT/shadow.json"
python benefit_evidence.py "$ROOT" "$OUT" grammar-stride3-split-7300147 grammar-benefit-held-11901371 grammar-benefit-held-deep-11901379 fact sum-divisors cyk801
python protocol_curves.py "$OUT" grammar-25112473 grammar-stride3-split-7300147 grammar-benefit-held-11901371 grammar-benefit-held-deep-11901379 cyk801 fact sum-divisors
python -m unittest discover
~~~

省略训练命令的 paired-inputs 选项可改用现场测得的成本。读取归档成本用于精确复现对应权重。影子诊断使用上一轮 protocol-learning 的 A、B 已签发原生轨迹，只用于事后确定首次状态差异。
