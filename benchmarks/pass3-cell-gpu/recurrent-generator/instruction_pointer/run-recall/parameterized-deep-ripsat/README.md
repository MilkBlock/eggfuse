# 整数参数化与深层 Cell 泛化

Neural Execution，exclusive。模型使用固定 B 事件生成器和原有父端口检索，在 standalone Rust Cell Runtime 独立执行。核验器只消费具名请求。另有两项离线检验，分别用训练好的 GNN 交换整数载荷，以及用仓库 vendored egglog 重放 CSUnit-000004 的观察契约。

## 结构与实例

控制组为 5851734b 的冻结 10,000 项目录和权重。实验组在原目录的相同顺序上，使用 sum-bits 和 dot-product 的相同 72,434 次训练曝光、283 次 Metal 更新。父模型冻结。规则结构保留有序查询、原生 effect、类型、操作数引用、源 ruleset、seminaive 属性和写表引入的 merge 程序。模板结构保留 Run 组、边界复用及具名生产者 PC。源规则显示名称和临时寄存器名不进入结构签名。

整数按类型在结构中变成参数。每个规则保存从参数到实例值的绑定；组合时显式记录规则内参数如何引用布局级参数。RipenInput 序列化地址有独立的边界命名空间。结构签名中的参数号、寄存器号及端口 PC 各有不同用途。对于现有 IR 没有显式参数来源的字面量，沿用视图的同类型、同值共享约定；这不构成两个独立业务量必然相等的证明。执行仍使用目标程序的具体规则、值、原生 guard 和原 Run 边界。结构回退链接只接受唯一的目标规则，并复核跨步骤共享及接线。老目录仍按精确规则身份链接。

**10,000 → 10,000**。其中 7,031 项有整数参数，4,070 项存在跨步骤共享，224 个实际使用的规则在这个签名下仍有 224 种。这个数字对应有序的现有 IR。代数等价、独立步骤重排、外部输入最小化都不在本次去重口径内。[全目录审计](int-parameters.json)

交换训练程序中两个 i64 载荷 1 与 10¹⁶，固定接线、边界地址和权重。在同一 CPU 上重新计算每个模板的编码。旧 GNN 有 6,520 项变化超过 10⁻⁶，最大分量差为 0.06904。参数化 GNN 的 10,000 项全部逐位相同。这个探针测量结构不变性；实例换值可能改变 guard 的正确答案。[训练编码探针](relabel.json)

## 独立执行

在完全相同的可链接模板集合上，三个程序分别保持原终图 SHA。下面是单次执行的确定性计数，时钟和全部工作量保存在逐次结果中。

| 程序 | 命中参考事实，旧和新 | CCP 请求，旧 → 新 | 完整深层实例，旧 → 新 |
|---|---:|---:|---:|
| fact | 768 / 1,120 | 301,761 → 301,737 | 20 → 22 |
| loopfact | 946 / 1,112 | 265,927 → 265,910 | 18 → 16 |
| sum-divisors | 3,089 / 8,018 | 4,951,170 → 4,951,136 | 73 → 66 |

另外开放结构链接，三个程序的静态兼容目录均扩至 9,570 项。新链接的 1,615、1,573、1,562 项中，整数绑定发生变化的数量均为零。旧规则的完整 JSON 指纹还会受显示信息影响。三个程序的参考事实数仍然相同。此组单次执行，单列费用。

同一批 668 个训练未见布局，在相同精确链接域、给定正确根规则的 teacher 事件上，实际选中的就绪实例所覆盖的不同步骤数，fact 为 10 → 0，loopfact 为 31 → 33，sum-divisors 为 263 → 280。这是条件识别指标，跨程序改善并不一致。[留出布局](held.json) · [控制组](../deep-ripsat-10000/held.json)

## 原生反例

CSUnit-000004 的原始 ripened.egg 以及改写前后的小程序均由 vendored egglog 实际执行。具名 Const 输入已是一条表行，四个角色来自这行的列，计入的额外父寻址节省为零。3 个边界标记和 2 个 i64 成本可在观察快照中直接核对。对调两个成本而保留地址后，实例上的比较赢家确实反转。

更优旧值、等成本不同 term、原始哨兵三种情形，一次无条件 set 经原生 Smaller helper 处理后的最终 ExtractedExpr 与参考一致。等成本时它额外发布可匹配的 Smaller。两次 Run 之间插入读取规则，原调度可见哨兵，提前直接写入会漏掉该观察。51 个组合的导出认证均为 unavailable。以上结果不足以授权替换源调度或删除公开的 constructor 行。[12 项原生检查](const-projection.json) · [独立外部输入审计](../semantic-inputs/README.md)

## 复现

在 instruction_pointer 下运行，ROOT、DATA、WEIGHTS 沿用原始深层目录实验。OUT 是本次结果目录。CCP 请求包含实际下放步骤；神经证明请求另扣下放步骤。EPT 使用 signed_ops / paid，EPS 使用 signed_ops / wall；参考事实覆盖有单独分母。模型训练、静态导入和离线核对均在在线计时之外。部分测量有机器并发，仅作计时记录。

```sh
OLD=run-recall/deep-ripsat-10000
python int_parameters.py "$ROOT/sum/program.json" "$OLD/catalog.json" counts.json --targets "$ROOT"/{fact,loopfact,sum-divisors}/program.json
python deep_ripsat.py "$ROOT" "$WEIGHTS" "$OUT" --frozen "$OLD/catalog.json"
python integer_relabel_probe.py "$ROOT/sum/program.json" "$WEIGHTS" "$OLD" "$OUT" probe.json
python deep_event_transfer.py "$ROOT" "$WEIGHTS" "$OUT"
python deep_event_rollout.py "$DATA" "$OUT" fact loopfact sum-divisors --arms 2 --concrete-only --reps 1 --offset 11
python deep_event_rollout.py "$DATA" "$OUT" fact loopfact sum-divisors --arms 2 --reps 1 --offset 20
python csunit_projection.py "$ROOT/fact/bake/saturated-rule-composition/cells/CSUnit-000004" "$NATIVE_EGGLOG"
```

同域旧 / 新模型采用两次交错顺序的配对执行。结构链接单独测一次。每次记录的完整终图、签发、原生拒绝原因、候选访问、时钟、EPT 与 EPS 见[独立执行汇总](independent.json)及[逐次原始结果](raw)。三个程序、三个组均正常到达调度末尾；相同程序各组终图哈希相同。没有把这一终止状态认作精确参考不动点。最小分支的 Cargo compile、run、bench 和已审定的 sum-bits 选择语义检查通过。
