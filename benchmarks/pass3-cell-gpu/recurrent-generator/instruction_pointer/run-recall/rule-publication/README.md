# 逐规则执行状态与真实 EggCC 的完整 Token 生成

**dirty 已经能控制模板选择，但网络仍频繁把预算花在无法完成的父绑定上。** 在相同的 96 个付费请求下，加入 dirty 和 watermark 后，fact、loopfact、sum-divisors 三个程序覆盖的参考事实和有实际贡献的请求数全部下降。正式对照由 net.rule_condition 选择 none、dirty 或 both；调用现有 native 入口时，带状态的策略会自动读取原生发布观测。默认策略保留 A。

## 状态如何到达模型

1. Rust CellHistory::observe 在实际 publication 同步导出当前 Run、epoch、dirty 检查开关、终止标志和所有已调度规则的 (rid, watermark, dirty)。watermark 与公开 CCP 帧核对；dirty 由原生只读观察文件提供，CCP v0.1 的线上字节格式不变。每个独立进程使用自己的观察文件。本次只增加神经读取，没有改动 Rust 调度器。在读取当前帧时核对 Run、epoch、终止位、规则次序和水位。帧不符直接报错。状态在新 publication 更新，同一窗口内多次 Submit 复用该帧；新逐请求 Response 立即加入可读 KV，尚未发布的端口不能作为父地址。[帧校验](../../rule_publication.py) · [原生观察器](../../../../../../engine/cell-runtime/src/cell_tokens.rs)
2. 签发 Higher 时，现有客户端实际发出 body 第 0 步 rid 与所选父引用。原生 Submit 先核验请求属于当前窗口的规则，再依据 check_dirty 与该 rid 的 dirty 判定触发，随后才依次核对父引用、完整绑定、水位、guard、输入与重复。Higher 后续每一步都有自己的 rid、原生触发检查与回执。一个入口被唤醒不能证明整段 Higher 可执行。本轮比较的是这个客户端 v0.1 路径。每个审计执行另开 admission observer，事后按请求 ID 核对实际 rid、Run、epoch、检查开关和 dirty；内部续接逐一核对 rid。合计 33,280 次付费请求全部对账。[客户端与内部续接](../../cell_kv_runtime.py) · [原生准入](../../../../../../engine/cell-runtime/src/token_transaction.rs)
3. GNN 的结构码、已执行 Cell 身份与历史 Response 的静态结构引用仍从原缓存读取。对菜单中的模板 t，用其实际入口 rid 从本帧取原始量，在模板向量的前两个维度添加 dirty 和 watermark/(32+watermark)；A 两项均无，B 仅第一项，C 两项均有。模板 Query、对 KV 的读取、最终模板打分和取得首父后的同族变体评分都使用本页的向量。静态缓存不被改写。首父及后续父地址仍由原地址网络使用静态模板、当前状态和具名前缀预测。它们没有直接接收新的逐规则数值。check_dirty 开关仅供核对，不作模型输入。本轮也没有将未探索计算量或最终贡献当作可观察输入。[模板读出](../../cell_kv_model.py) · [同族选择及完整 CE](../../selected_cell_model.py)
4. 全局 Query 仍读取 Run、epoch 与接受、更新、退役三个计数；端口 KV 读取所属实例、类型、字段表示、父引用、版本年龄与转发状态；逐请求回执参与 Attention，但不进入可绑定父域。保留已有静态类型构造约束、静态具名字段投影、页内完整具名 Token 不放回和固定 Seal。CPU 不按 dirty 删除、换选或重抽模板；所有仍可构造的模板继续被神经打分。没有语义 join、跨角色水位比较、教师在线输入、inactive penalty 或独立预测头。观测侧通道的读写和本页特征构造计入 B/C 的墙钟。输入是用户指定的原生执行观测，超出仅凭 CCP 字节帧可还原的信息。

## 同数据、同预算的训练与干预

A/B/C 都从同一结构化 CE 基线按种子初始化，保留 8,576 个可训练参数。每臂两个训练种子 71、113，每个种子 512 次 AdamW 更新，8,192 次完整 Token 曝光。每次取四个状态，各取四个原生核验的正例。状态抽样 75% 来自已有同构/异构 Wake 配对，25% 来自已有多尺度 Higher 语料；后者用原生重放补回每状态的规则观测，并逐项核对历史快照。每个种子的三组训练抽样序列摘要完全一致。EggCC 的训练目标与反事实均未进入这些权重。数据取自小型程序，不能视为对 EggCC 分布上的充分训练。[训练与配对数据](../../trigger_training.py) · [曝光和序列摘要](training.csv)

交换实验在给定真实状态上只改变送入既有评分器的逐规则特征，保持公共 Memory、具名地址、模板目录、回执和权重不动。下表为对同一具名完整 Token 的平均概率，先在原生 Run 4 验证它可增加新事实，随后 Run 6 验证它失活。两类程序各 6 个未见实例，交换真实唤醒的规则，保留目标此前签发/未签发两种历史，重复使用两个训练种子。表内为全部条件观测的均值。

| 模型与推理输入 | 唤醒窗口 | 失活窗口 |
|---|---:|---:|
| A，无逐规则输入 | 48.40% | 48.40% |
| B，仅 dirty | 96.40% | 0.39% |
| C，dirty + watermark | 96.41% | 0.38% |
| C，仅交换两个 rid 的 dirty | 0.41% | 96.75% |
| C，消融 dirty | 约 48% | 约 49% |

保留 dirty、交换或清零 watermark 后，这组配对的概率变化很小。不能由此推出水位对原生执行或所有 Recipe 均无用。另在 A 策略自主运行得到的同一批真实 EggCC 快照上，比较有可构造活跃和失活入口同时存在的窗口。fact、loopfact、sum-divisors 的 A 活跃入口概率质量分别为 74.1%、51.8%、74.0%；C 为 99.5%、97.3%、99.8%。相同 C 权重循环置换 dirty 后分别降至 91.8%、82.0%、93.4%。循环置换保留状态总量，多条规则仍可能碰巧保留原位值。该实验测量首次抽样的概率质量，不等于整页或整条轨迹的接受率。采样为种子 71 的前 32 个 Run 及之后每 32 个 Run 的首页，三个程序的混合窗口各 6、7、6 个。[训练状态干预](pairs.csv) · [EggCC 同快照干预](egg-opportunity.csv)

## 自主执行与付费去向

使用既有 donor 静态链接得到的 12 个短/中 Higher 和全部 Primitive。正式运行从初始化自由生成，抽样和地址种子 193；每窗口两页、每页三槽。三个预算分别为最多提供 384 个生成槽、最多 96 个实际付费请求、完整固定调度。完整调度的实际 Run 数可随已提交效果变化。每个条件都做了两个训练种子、独立的完整记录及正反序两次计时；核对三次实际事实、终图、请求回执、费用与有效操作完全相同。诊断记录与离线核验不进入正式 EPS。单线程 CPU 进行神经推理，不同负载并行跑在同机，墙钟有波动。下表每格为 Coverage / EPT / EPS，全部轨迹按种子平均。

| 负载与预算 | A | B | C |
|---|---|---|---|
| fact，384 槽 | 5.80% / .398 / 50.4 | 5.58% / .381 / 48.8 | 5.58% / .381 / 48.4 |
| loopfact，384 槽 | 6.52% / .334 / 42.3 | 6.16% / .292 / 37.6 | 6.12% / .290 / 36.7 |
| sum-divisors，384 槽 | 1.66% / .853 / 99.2 | 1.60% / .806 / 96.1 | 1.60% / .806 / 96.4 |
| fact，96 付费 | 3.62% / .885 / 99.2 | 3.44% / .870 / 97.5 | 3.44% / .870 / 98.0 |
| loopfact，96 付费 | 4.45% / .724 / 82.5 | 4.05% / .620 / 69.8 | 4.00% / .615 / 69.4 |
| sum-divisors，96 付费 | 1.39% / 2.260 / 229.0 | 1.31% / 2.125 / 212.4 | 1.31% / 2.125 / 204.3 |
| fact，完整调度 | 6.79% / .092 / 8.9 | 6.83% / .075 / 6.7 | 6.83% / .075 / 6.8 |
| loopfact，完整调度 | 7.64% / .080 / 7.8 | 7.28% / .073 / 7.3 | 7.24% / .072 / 7.2 |
| sum-divisors，完整调度 | 1.85% / .189 / 17.6 | 1.81% / .170 / 15.8 | 1.79% / .186 / 17.7 |

固定 96 请求时，三个程序 A → C 的平均未触发分别为 50 → 45.5、48 → 50、49 → 48。完整绑定失败分别为 27.5 → 32、25 → 32.5、29 → 38。有原生新增有效操作的请求数分别由 12 → 11.5、13.5 → 8、13.5 → 6；最终不同参考事实数由 40.5 → 38.5、49.5 → 44.5、111.5 → 105。fact 中少掉的 4.5 次未触发与增加的 4.5 次绑定失败在均值上相抵。对同一请求个体不能做这种一对一因果解释。完整调度中，fact 的 C 只多覆盖 0.5 个参考事实，却从 1,382.5 增到 1,714 个付费请求，EPS 从 8.91 降到 6.82。三个程序的 C 与 A 在完整调度下均无同种子同终图配对。[全部计数](results.csv) · [逐种子与正反序墙钟](runs.csv) · [事实身份差异](matched.csv)

**为何真实执行仍有大量未触发。** 在完整自主轨迹结束后，使用该页当时实际发布的表类型、完整菜单及原始 dirty，离线把页面分成“存在活跃也存在失活的可构造入口”和“全部可构造入口失活”等类别。相同种子独立重放，逐轨迹核对事实、终图、计数及回执。三个程序、两个种子合计，混合页面中的未触发从 A 的 222 次降至 C 的 19 次。C 在全失活页面实际签发 7,784 次，占其全部 7,803 次未触发的 **99.76%**。此时重新分配候选间的相对概率无法产生一枚已触发的签发；当前固定发页策略会继续取样，只在构造域或本页未取叶子耗尽时提前返回。该分组只在运行后统计，模型没有看到“全失活”结论。这样可以同时解释混合页面中的选择改善与完整调度中的持续浪费。独立轨迹长度也会变化，因而 222 与 19 是计数。[每个程序、种子、页内槽位及首个原生结果](windows.csv)

EPT 分子为 Rust EPT ledger 的 signed_external 和 signed_internal 有效原子事件数之和，分母含每次内部实际付费请求。productive 是至少拥有一项此类有效事件的请求 ID 数。Coverage 仍使用初始化后 constructor-aligned 参考事实；一次写入或 union 与一个最终参考事实没有一一对应。对比保留所有事实集合。[事实与终图](facts.csv)

## Higher 的逐签发验收

上轮 329 次来自多个目录、不同权重。本轮三组共享多尺度目录，使用本轮重新训练的权重。仅统计真实 EggCC 完整调度，不重复计时或预算前缀：

| 输入 | Higher 签发 | 未触发 | 绑定失败 | guard 失败 | 入口接受 | 内部请求 / 接受 | 完成 | 可归属有效原子操作 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 211 | 164 | 40 | 6 | 1 | 3 / 2 | 0 | 6 |
| B | 137 | 101 | 36 | 0 | 0 | 0 / 0 | 0 | 0 |
| C | 131 | 99 | 32 | 0 | 0 | 0 / 0 | 0 | 0 |

fact、种子 113、Run 66 的请求 290 是唯一打开的实例。它签发五步 Higher 585，原生入口为规则 505，三个父引用均通过核验，入口带来 5 个原生有效操作。后续规则 286、506 被接受，分别贡献 0 和 1；规则 507 的 guard 失败，剩下的一步没有执行。由此可定位部分执行，但没有完整实例可用于估计真实 EggCC 的净压缩。受控留出任务的 A/B/C 分别完整完成 3/4/5 个 Higher，证明内部接续、最终回执和效果归因都能被记录。[每一枚 Higher、具名父引用、内部步骤及最终实际效果](higher.csv)

原生首个失败之后未核验的维度记为 unknown。accepted 与 duplicate 都已通过前置绑定和 guard；绑定被拒只说明整组输入未通过；guard 失败只指原生遇到的失败条件。最终效果来自运行结束后的 EPT origins，按真实根和内部请求 ID 归并，包括部分执行带来的贡献。它是实际记账的效果，不是“删除这个 Higher 后，一定会少掉的终图事实”的反事实证明。

## 复现

起点为研究提交 a1bf0562。原始训练权重、三次运行原始记录、原生配对和逐请求归因在 ARTIFACT_ROOT/conditional-value/rule-publication，文件摘要保存在 [manifest.json](manifest.json)。运行目录为 benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer。前置资产及 CPU Native Runtime 版本与[上一轮](../foundation-curves/README.md)相同。

```sh
export ARTIFACT_ROOT='/Volumes/Extreme SSD/eggfuse-experiments'
export CELL_DATA=/tmp/dfm-local/data
export CELL_COMPILER=/tmp/cost-audit-build/release/eggfuse-cell-compiler
export CELL_REPLAY=/tmp/cost-audit-build/release/examples/cell_token_replay
export PYTHON=/tmp/egg-txn-ml/bin/python
sh trigger_reproduce.sh
"$PYTHON" -m unittest test_rule_publication test_foundation_curves test_constructible test_feedback_memory test_state_transition test_competition test_selected_cell test_interface_role test_operand_read test_value_read test_compatibility test_cell_kv test_token_embedding
```

38 项相关测试通过。另运行本地 Cargo compile、run、bench 和既有 sum-bits 导出合同核验，语义状态为 pass。正式性能测量使用项目 CCP v0.1 原生运行器。
