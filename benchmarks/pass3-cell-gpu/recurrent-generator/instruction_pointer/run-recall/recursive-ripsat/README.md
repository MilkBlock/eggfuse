# Recursive RipSat Composition 的第一轮 RL

Neural Execution，exclusive。策略在单线程 CPU 上生成请求，Rust Cell Runtime 通过冻结的 CCP v0.1 执行、核验和发布。训练、验证和评估的在线路径都从自身提交推进。本文另列的原生 teacher 接管只检验组合接口的语义。

## 开放边界

固定 48 个原主体、原 Recipe、GNN 的静态编码和 30 个多入口投影。Bake 为消费规则的每个输入角色编译一份续接契约，保存规则、来源角色、其余独立操作数的表类型。末步可能产生的具名端口由原生 receipt-contract 给出。条件端口必须实际发布，参与寻址的是 (token, op, version)。运行时只在主体完成后开放末步的实际回执；退役或更新会移除旧版本的开放接口。已开放的实例可以参与多次组合。未形成输出的成功请求仍按原生账本计费和计效。

本轮对一元和二元消费规则启用快捷续接。普通 B 保留全部既有父数和残余流。策略可以在原子和组合模板之间选择、沿开放接口续接、由两份不同实例的端口组合，或把可选的续接推迟一次。Defer 保存来源、版本、规则和角色，在后续有 B 分派且目标规则获调度时重新检查。Defer 期间普通流继续运行。没有生成 H × K 的布局目录。

Extend 从一个已完成主体出发时，另一个普通操作数由 B 的既有字段桶和父指针绑定。以普通事实触发时可使用另一角色最新发布的开放端口。Compose 的具名寻址指令读取目标类型最新的开放端口，若仍是自身可读前一个。这是受限的地址指令。每页至多在原末事件和仍位于该页的最近开放端口上做额外决策。其余合法机会继续走 B 的原有路径。这里没有按字段等值精确过滤，也没有把多个高层实例预先组对后送入分类器。

只有被原生接受的后缀，才可以从当前 Run 的残余流里排除相同的版本化父元组。新后缀的署名 token 必须等到下一次发布才能提供新的具名输出。不会为了 Extend 或 Compose 重新签发前缀步骤；其他事件独立产生的重复提案仍须付费。抽象深度以完成的原 RipSat 为 1，后缀继承所有已用高层父节点的最大深度加 1。

## 原生接口核对，离线

sum-bits 中，模板 13 的末步 552.op1 和事实 487.op1 支持 Run 106 的后缀 605。另一个实例使用模板 5 的 2251.op9 和模板 20 的 2265.op7 支持 Run 291 的后缀 2266。两个前缀不重叠。分别在原生重放中接管已有主体，后继签发一次，六项检查覆盖终图、调度、写入、RHS、恢复和事件，接受总数均为 7,265。原生有效操作账本分别将 1 次有效操作归给 605 和 2266。这些证据来自完全指定的已知证明。[原生见证](native-witness.json)

## 策略和实验设计

- 原 B 使用上一轮 wired B + 已验证多入口及默认静态优先级。冻结 B + 开放 Bake 使用相同参数和新的动作接口。RL B 使用相同开放接口、相同父指针及同一个 BranchNet，初始化逐张量等于 wired B。B 的旧模板图编码来自已有 GNN，未训练另一个路由器。目录外的续接规则复用 B 的 Recipe 结构特征。
- 训练只用 sum-bits 前 192 个 Run。用四次镜像参数空间探索更新 B 的最后两个线性层，每对策略从初态独立执行，使用相同的稀疏动作探索种子，正负顺序交替。每条轨迹用一个终端回报，包括早期选择对后续可见状态的影响。有效操作来自原生 settled-operation 账本，每份后缀只按其自产生的新增操作计效。没有为触发高层、形成更深链或重复引用父节点发放额外奖励。
- 当派生事实命中数低于原 B 时，收益严格低于任何达标轨迹。达标后，回报为相对于 B 的有效操作变化，扣除一半的付费请求与选择成本相对变化，以及一半的实际运行时间相对变化。训练用的成本代理把 CCP 请求、模板末端选择、稀疏动作和契约选择相加。它含确定性 lowering；字段检索的比较次数独立报告。墙钟包含检索、神经推理、签发、核验、通信和增量 Memory，离线编译和复核分别处理。
- dot-product 的前 192 个 Run 作为验证。fact、loopfact、sum-divisors 从初态执行到完整调度结束。沿用这些已研究过的程序，不作新盲测声明。报告最后一次更新的权重，每个程序对照同一 Coverage 和终图 SHA。训练总回报的四次更新不足以估计收敛或分离计时噪声。
- 历史 EPT = 原生有效操作 / 实际 CCP 请求，EPS = 原生有效操作 / 独立执行秒数。新增绑定、学习动作和候选访问另计。一个 Extend 成功后，同一事实也可能原本就会由 B 推导，后缀自产的有效操作与相对 B 的事实增量分列。

## 独立执行结果

三个完整程序均以 original → open → rl 和 rl → open → original 各计时一次。下表为两次运行的 EPS 中位数。dot 仅用于验证，单次执行 192 个 Run。各程序三组命中相同派生事实数、终图 SHA 相同。

| 程序 | 组 | Coverage | 有效操作 | CCP 请求 | EPT | EPS | 候选访问 |
|---|---|---:|---:|---:|---:|---:|---:|
| fact | original | 764/1,120 | 1,094 | 297,747 | 0.00367426 | 86.06 | 6,959,260 |
| fact | open | 764/1,120 | 1,094 | 297,798 | 0.00367363 | 86.42 | 6,959,269 |
| fact | rl | 764/1,120 | 1,094 | 297,798 | 0.00367363 | 86.87 | 6,959,269 |
| loopfact | original | 944/1,112 | 1,136 | 263,554 | 0.00431031 | 100.60 | 4,950,287 |
| loopfact | open | 944/1,112 | 1,136 | 263,617 | 0.00430928 | 102.13 | 4,950,314 |
| loopfact | rl | 944/1,112 | 1,136 | 263,617 | 0.00430928 | 102.21 | 4,950,314 |
| sum-divisors | original | 3,085/8,018 | 4,321 | 4,930,806 | 0.00087633 | 35.41 | 89,399,221 |
| sum-divisors | open | 3,085/8,018 | 4,321 | 4,930,896 | 0.00087631 | 34.80 | 89,399,270 |
| sum-divisors | rl | 3,085/8,018 | 4,321 | 4,930,891 | 0.00087631 | 34.17 | 89,399,270 |
| dot | original | 1,220/1,942 | 1,742 | 25,560 | 0.06815336 | 87.63 | 13,785,082 |
| dot | open | 1,220/1,942 | 1,742 | 25,577 | 0.06810807 | 84.10 | 13,785,092 |
| dot | rl | 1,220/1,942 | 1,742 | 25,574 | 0.06811606 | 83.61 | 13,785,092 |

每条 RL 轨迹的 192 个 Run 内有 52–54 个 Run 实际发生开放动作。在 8 条探索轨迹中共选了 3,899 次 Extend 和 228 次 Compose；各轨迹和原 B 均命中 776 个参考事实，原生账本均为 979 个有效操作。最后两层共 2,113 个参数实际改变。此轮参数探索主要得到了成本差异，未观察到有效操作或 Coverage 增量。

| RL 组 | 最大已发布深度 | Extend / Compose 接受数 | 后缀自产有效操作 | 额外绑定槽（已签发） | 跳过的底层末级候选 | 净候选访问变化 |
|---|---:|---:|---:|---:|---:|---:|
| dot | 3 | 3 / 0 | 1 | 20 | 6 | +10 |
| fact | 2 | 2 / 0 | 0 | 55 | 4 | +9 |
| loopfact | 2 | 2 / 0 | 1 | 67 | 4 | +27 |
| sum-divisors | 2 | 2 / 0 | 1 | 90 | 4 | +49 |

sum-divisors 的后缀接管跳过 4 个末级候选，同时 B 的伙伴指针多打了 53 次分，净增 49 次候选访问。另有 474,434 次页中位置比较单独计数。新增开放动作 3,765 次，原 B 末端选择少 1 次，合计多 3,764 次末端或开放决策。多付费 85 个 CCP 请求。195 次 Compose 中有 165 次两个端口都早于规则水位，30 次进入原生核验均因绑定失败被拒。60 次 Extend 签发中 58 次绑定失败，2 次接受，共自产 1 个有效操作。

dot 的续接实际生长至深度 3。三个完整程序中 RL 都只生长至深度 2。双主体组合在完全指定的原生接管里成立，独立策略的 Compose 接受数为零。保留原 B 性能基线。后续对 Compose 最直接的检验，是在规则水位允许的命名端口中让现有父指针选择伙伴，并单列伙伴寻址的访问和时间。

[所有组的计数与逐次耗时](results.json) · [独立执行记录](independent) · [训练回报与探索轨迹](training)


## 复现

在 instruction_pointer 目录执行。DATA 使用现有原生 replay、字段检索和 recursive-agent/multi.pt；fact、loopfact、sum-divisors 使用原目录，sum 和 dot 分别在 DATA/recursive-agent/sum 与 DATA/recursive-agent/dot 提供 program、capture、memory 和 tape。每次独立执行使用私有临时目录。训练只需要训练程序的原生环境、参考覆盖基线和既有 checkpoint。teacher tape 仅用于单列的接口诊断。

```sh
mkdir -p "$OUT"
cp run-recall/entry-first/entry/catalog.json "$OUT/"
cp run-recall/multi-entry/entry-contracts.json "$OUT/"
cp run-recall/entry-wiring/{graph,wired}.pt "$OUT/"
python recursive_ripsat_study.py "$DATA" "$OUT" sum train --limit 192 --steps 4 --seed 431
python recursive_ripsat_study.py "$DATA" "$OUT" dot original open rl --limit 192
for case in fact loopfact sum-divisors; do
  python recursive_ripsat_study.py "$DATA" "$OUT" "$case" original open rl --rep 0
done
for case in loopfact fact sum-divisors; do
  python recursive_ripsat_study.py "$DATA" "$OUT" "$case" rl open original --rep 1
done
python audit_recursive_ripsat.py "$DATA" "$OUT/catalog.json" sum "$OUT/native-witness.json"
python recursive_ripsat_results.py "$OUT" "$OUT/results.json"
python -m unittest discover -p 'test_*.py'
```

训练回报包含实测墙钟，重训得到的参数会随机器负载变化。要逐次复现本次策略的动作和有效操作，直接将发布的 recursive-rl.pt 放进 OUT。逐次记录包含原生各类回执、推理计数、付费、同步、核验秒数和墙钟。精确补全工作量为零。不同运行组均未达到这些 EggCC 程序的参考不动点。

78 项 Python 测试通过。最终实现额外独立重跑 fact，复核了终图、动作、付费、后缀操作及递归回执。最小 CPU 路径完成 sum-bits compile、run 和五次 bench，使用既有导出的 marker-handoff 语义验收为 pass。同一 Rust Runtime 的纯精确执行单列其内部计时与参考 SHA，和以上 Python 策略加原生核验的独立端点具有不同 Coverage。[精确执行记录](exact.json)
