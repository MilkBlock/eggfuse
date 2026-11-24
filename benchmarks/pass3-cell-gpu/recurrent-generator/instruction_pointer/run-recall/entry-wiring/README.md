# B 的模板选择如何使用 RipSat 接线

**Neural Execution，exclusive**。三个 EggCC 程序在 standalone Rust Cell Runtime 上独立运行至原调度结束。离线反事实和独立执行分别计量。B 先从发布事件选择模板，再寻找根的具名父引用。原字段检索、CCP v0.1、回执可见性、根接受条件和按已完成具名元组跳过候选的行为沿用 cfa17e2d。原子步骤实际下放时仍计费。运行时使用冻结目录和训练权重；所有监督均在离线生成。模型与原生二进制的 SHA-256 见 [summary.json](summary.json)。

## 接线在哪里丢失

Recipe 的模板图已有操作、变量槽和输入边。[GraphBank](../../ripsat_policy.py) 以生产步骤的状态为消息源，用生产 op 对应的节点、op 位置、消费 atom 和消费槽位编码边。已有 CellScorer 对每一步聚合这些消息再读出布局向量。原 entry-first B 的 Family 独立生成了另一份描述，它使用根规则的计数特征、后继计数特征的均值、步数和连线数；这条路径从未调用 GraphBank 或 CellScorer.encode。

本次将已训练的 Recipe Actor 和 RipSat CellScorer 保持冻结，一步 Primitive 和多步 Bake 布局通过同一套图编码。B 仍用原 BranchNet 以及相同的 16 维事件输入。对 32 维静态读出按事件角色旋转，将最后两个坐标加到最前两个坐标以适配 B 原有的 30 维静态输入。每个坐标都参与，降维仍可能造成碰撞。模板序号仅用于定位编码和核验，不进入神经特征。图编码只在 Bake 阶段运行，部署时按目录结构指纹验证缓存。

在 sum-bits 有监督的根家族中，原表示有四对布局在同一根角色下完全重合，新表示有零对。模板 25 和 34 的唯一区别是从根取 op 2 或 op 1。回归检查同一事件的实际 B 分数，并检查交换两个选项时分数随接线交换。这个表示可以表达不同选择，仍要实测网络是否根据上下文切换偏好。

## 离线监督

只用 sum-bits 的根事件训练。对待比较的选项从同一已接受根出发，按具名接线和真实版本编排后继。对在 tape 找到的完整接管分别强制执行，重叠实例放在不同原生重放中；逐轮核对调度、写入、RHS、恢复、repair 事件和终图。对 tape 未匹配的布局，如果首个后继有具名操作数，另用原生核验器在实际调用的快照上测其结果。首步原生拒绝才记一次无收益付费。缺少实测成本的替代证明、后续完成情况未知的首步匹配、缺失观察等保留为未知。

同一根上的 Primitive 是额外成本为零的比较基点。每个已完成选项用真实 B 检索窗口和逐层分数测出能省掉的父候选及原子提案；从提案节约中扣去实际下放的内部请求。先按净付费请求节约排序，持平时按少访问的末层位置和单父事件数排序。该成本以指定根和新证据角色成立为条件；打分、索引和同步的整机成本另在独立执行中计时。每一对有实测成本差的选项产生一个 pairwise logistic 监督，等收益和未知选项均不产生该比较。

sum-bits 的 1,348 个完整接管在 4 次原生重放中通过。2,075 个首步请求得到原生拒绝，366 个根分别拥有至少两个测得正收益的布局。两组从相同的 B 权重出发，使用相同的 2,094 条根事件记录、3,827 对严格比较、16 轮更新及种子。rank 使用原规则摘要，wired 使用 GNN 接线读出。11 项布局整体留出本次排序训练。已有 GNN 的预训练曾使用 sum-bits 和 dot-product，这些原程序及三个 EggCC 评估程序均有历史开发记录。留出成绩说明对本轮排序监督的迁移。[原生反事实与单根成本](costs) · [训练配置](fit.json)

| 程序 | 有实测正收益的留出上下文 | 选中有收益的留出布局，rank → wired | 在全部已测上下文选择正收益布局，rank → wired |
|---|---:|---:|---:|
| dot-product | 316 | 115 → 151 | 470 → 571 / 1,227 |
| fact | 67 | 22 → 37 | 147 → 147 / 403 |
| loopfact | 91 | 33 → 46 | 139 → 162 / 354 |
| sum-divisors | 822 | 272 → 358 | 1,831 → 2,090 / 5,662 |

在 sum-divisors 能同时测到 25、34 成本的 273 条根事件记录中，228 条打平。其余 45 条中，34 条应选 25，11 条应选 34。wired 对这 45 条全部偏向 25。按 B 真正看见的输入（事件向量逐字节及根角色）分组，45 条中有 44 种输入，1 种输入的监督冲突。在该样本上逐输入记忆的事后上限为 44/45。训练程序的 16 条严格比较中也始终偏向 25，答对 12 条。这是一个具体的偏好学习失败，无法以模板表示相同来解释；逐输入记忆上限本身不说明跨程序可预测性。[逐程序排序与并列项诊断](ranks)

## 独立执行

| 程序 | 模型 | 覆盖的参考派生事实 | 完整 Bake 实例 | 候选访问 | 付费 CCP 请求 | EPT |
|---|---|---:|---:|---:|---:|---:|
| fact | 原摘要 + 成本排序 | 766 / 1,120 | 80 | 6,962,702 | 293,441 | .00373840 |
| fact | GNN 接线 + 成本排序 | 764 / 1,120 | 84 | 6,959,260 | 297,736 | .00367440 |
| loopfact | 原摘要 + 成本排序 | 944 / 1,112 | 80 | 4,950,337 | 263,545 | .00431046 |
| loopfact | GNN 接线 + 成本排序 | 944 / 1,112 | 92 | 4,950,288 | 263,539 | .00431056 |
| sum-divisors | 原摘要 + 成本排序 | 3,090 / 8,018 | 350 | 86,048,421 | 4,889,339 | .00088519 |
| sum-divisors | GNN 接线 + 成本排序 | 3,085 / 8,018 | 392 | 89,399,230 | 4,930,770 | .00087633 |

对照过去的 [原 B 与旧监督](../entry-first/README.md)，wired 在三个程序上逐一复现了原 B 的终图。在 sum-divisors，旧监督完整执行 47 个 Bake 实例，wired 执行 392 个；相对原 B，wired 少访问 640 个候选，净省 67 个 CCP 请求，仍需 583,873 次末级选项打分。两种新排序器在 loopfact 达到相同终图，wired 多完成 12 个实例，少访问 49 个候选，净省 6 个请求。在其余两个程序，换读出后两组终图不同。每次独立运行的接受、重复、拒绝原因、原生核验、同步和时间均见 [逐次记录](independent)。这些程序均在 schedule_end 结束，终图未达到完整参考覆盖。

反序配对各执行两次，数据恢复后按历史 CCP 程序文件 SHA-256 逐字节核对三个 EggCC 输入。中断的运行不计入。各次 EPS 与墙钟见下表和汇总。样本量用于查看波动，达不到 E4 的加速认定条件。

| 程序 | 原摘要 EPS，两次 | GNN 接线 EPS，两次 | 原摘要秒数，两次 | GNN 接线秒数，两次 |
|---|---:|---:|---:|---:|
| fact | 85.67、93.12 | 84.32、91.62 | 12.81、11.78 | 12.97、11.94 |
| loopfact | 93.50、106.20 | 94.19、98.87 | 12.15、10.70 | 12.06、11.49 |
| sum-divisors | 35.45、36.54 | 35.33、35.60 | 122.10、118.44 | 122.31、121.37 |

## 复现

在 instruction_pointer 目录执行，DATA 提供原生 replay 二进制、冻结父指针与字段检索权重；ROOT 提供各程序的 program、capture、tape 与 memory。WEIGHTS 为 SHA 以 13e209c6 开头的 Recipe Actor。单线程 CPU，训练集仅为 sum-bits。

```sh
mkdir -p "$OUT"
cp run-recall/entry-first/entry/catalog.json "$OUT/catalog.json"
python entry_wiring.py "$ROOT/sum/program.json" "$OUT/catalog.json" "$WEIGHTS" run-recall/parameterized-deep-ripsat/event-gnn.pt "$OUT/graph.pt"
for n in sum dot fact loopfact sum-divisors; do
  python entry_counterfactual.py "$DATA" "$ROOT/$n" "$OUT/catalog.json" "$OUT/$n-cost.json"
done
python train_entry_ranking.py "$DATA" "$ROOT" "$OUT"
python entry_readout_audit.py "$DATA" "$ROOT" "$OUT" sum dot fact loopfact sum-divisors
for n in fact loopfact sum-divisors; do
  python entry_rollout.py "$DATA" "$OUT" "$n" rank wired --rep 0
  python entry_rollout.py "$DATA" "$OUT" "$n" wired rank --rep 1
done
python entry_wiring_results.py "$OUT" "$REPORT" "$DATA/unified-scale/build/release/examples/cell_token_replay"
```

68 项 Python 测试通过，CPU 的 sum-bits compile、run、bench 通过。重新导出并核对 sum-bits 的 marker-handoff 语义结果为 pass。
