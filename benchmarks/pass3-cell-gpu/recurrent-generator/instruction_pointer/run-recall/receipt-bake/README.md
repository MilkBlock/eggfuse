# Recipe 条件回执与 RipSat 入口

本轮包含离线 Bake、teacher 轨迹上的具名核验，以及冻结模型在 standalone Rust Cell Runtime 上的 Neural Execution / exclusive。CCP v0.1、模型参数、编码向量、父指针、签发预算与源 Run 边界沿用原实验。程序来自 EggCC；独立执行计时测量本仓库的 Rust Cell Runtime。CPU 未在独立执行中查找缺失的父证据。

## 编译与消费

新编译的 program.json 携带 receipt_contract。Rust 根据已解析的 Recipe 和 merge 程序计算端口布局与具名操作数，加载时核对契约。源 query、effect、merge、control、entry_schedule 继续定义条件、参数和执行顺序。普通表 instruction 完成的路径具有具名返回。自定义 merge 构造操作占用扩展位置，读取和 primitive 在 merge bytecode 中占位，repair 的构造回执归实际的运行时事件。实例的具名返回可以转发到已存在的行。只有当前可见的真实版本可以用作证明。

新制品的 Bake 布局、Catalog 接口与事务计划均读取编译契约。旧格式保留原读取方式，便于重建冻结对照。独立实验使用原编译制品、旧权重和原有模板向量，仅替换由训练程序确定的布局接线。对旧程序可用原生 receipt-contract 命令输出同源描述。

在一个已选接线和已调度规则内，request_frontier 可以从已绑定角色推导当前可提出的计算、仍需寻址的外部引用、待发布的内部依赖和已失效的路径。plans() 使用同一份原生 operand options。完整引用允许提出请求，最终的 guard、水位和可见性由原生核验。三个 EggCC 程序和两个 CYK 程序用于对照事务计划。其中多步 grammar 的六个已出现计划均使用事务内先前计算的值。[计算计划核对](plans.json)

## 模板 4790

loopfact 中，第四步的 effect 3 可以触发自定义 merge。其第 0 个内部操作返回 Smaller，对应具名 op 8。若本次 Set 未进入该 merge，或者没有该构造回执，末步不能沿这条接线执行。其他证明仍可由普通生成器提出。核验器始终读取实际返回的 witness。

根 1012 在 Run 185 的三个原有端口均已可见，前三个槽首次消费于 185、185、186。槽 3 首次可见和首次消费均为 191，来自第 4 步在 Run 190 的返回。将整段入口推迟到 191 会越过前三步已实际执行的 Run。按末步拆分可分别在原调度上启动，前段读三个外部槽，后段读两个。内部接线版本一次绑定三个外部槽，保留发布边界，然后由第 5 步读取真实的 op 8。

16 个 loopfact 实例中，拆分与内部接线两种方案各通过 80 次具名步骤核验。16 次过早请求遇到未触发规则，16 次引用未来生产者遇到未知输出，16 次使用错误版本被拒。原生图执行入口接受合法接线，拒绝不存在的输出位置。[逐实例的可见与消费 Run、原生回执](regression.json)

另外逐个固定这 16 个根。在其余请求沿用 teacher 的条件下，删除对应的四个后继请求，让原生图执行入口从唯一签名根和三个入口引用实际派发后四步。每次完整执行都完成一个五步实例、接受全部 1,419 个提交，参考终图、Run 序列、写入、RHS、恢复和事件逐项一致。这是受控执行，不能记为网络主动识别或端到端加速。[原生接管](takeover.json)

## 一万项冻结目录

只在训练用 sum-bits 与 dot-product 上选定替换接线，每个 UID 选择最常出现的合法变体，平局用布局序排序。一个外部槽的全部读取都需匹配同一模板内较早发布组的具名生产者和消费表。可启动实例另要求入口版本实际存在、内部返回在生产后的首个发布边界存在，并在原消费 Run 命中 teacher 绑定。训练轨迹可以给出接线机会，未来输入无法变成入口参数。

| 指标 | 结果 |
|---|---:|
| 入口外部具名槽总数 | 70,343 → 69,867 |
| 可缩减的槽数 | 476 |
| 接线可缩减的模板 | 397 / 10,000 |
| 原本无就绪训练实例且接线可缩减 | 397 / 5,210 |
| 原本无就绪训练实例且冻结改写后确有就绪训练实例 | 24 / 5,210 |

槽数按模板静态累计，不按实例频率加权；同一 Cell 的两个不同回执可占两个槽。这个分母不能换算为已经节省的检索次数。其余模板可能还受跨 Run 可见性、来源版本或外部事实等约束。本实验只识别能证明为模板内自定义 merge 具名回执的外部槽。[全目录逐项](slots.csv)

| 程序 | 有就绪模板，原布局 → 允许原或特化证明 | 就绪的（模板，根）对 | 4790 的已核验实例 |
|---|---:|---:|---:|
| fact | 324 → 334 | 737 → 765 | 11 |
| loopfact | 447 → 457 | 794 → 836 | 16 |
| sum-divisors | 1,686 → 1,702 | 8,253 → 8,451 | 102 |

跨程序使用训练时已冻结的变体。每个有就绪改写的模板至少抽一个实例，另加所有 4790 实例，共 826 个步骤经原生重放命中预期提交。表内计数是 teacher 轨迹上的可行机会，并未强制神经策略选择。[分程序核对](audit.json)

## 独立执行

每个工作负载两轮配对，顺序交错。两臂达到调度末尾，逐程序的终图哈希和全部非计时工作计数相同。模型每个 UID 的识别分数仍使用冻结向量；改写发生在执行端的边界绑定。本实验没有测量重新编码或训练后的 GNN。

| 程序 | 参考派生事实 Coverage | 付费请求 | 候选访问 | EPT | EPS，原 → 改写，两次实测 |
|---|---:|---:|---:|---:|---|
| fact | 768 / 1,120 | 301,740 | 8,287,473 | 0.003639 | 74.97、61.63 → 78.40、78.87 |
| loopfact | 946 / 1,112 | 265,910 | 4,013,613 | 0.004257 | 109.55、108.08 → 109.40、87.32 |
| sum-divisors | 3,089 / 8,018 | 4,951,137 | 114,745,742 | 0.000868 | 28.88、27.88 → 29.04、28.73 |

EPT 和 EPS 的分子是 signed_ops，参考派生事实另计。相同终图下，两个布局组的新增实际候选节省和付费请求节省均为零。两次计时有机器负载波动，本轮不主张墙钟加速。[配对结果及模型摘要](independent.json) · [逐次签发、拒绝、访问、同步、耗时](raw)

## 复现

在 instruction_pointer 目录运行。ROOT 含原编译程序、M0 tape、capture 和逐 Run 端口导出。DATA 是已有独立执行工作区。BIN 指向以 cell-token-ept 特性编译的 cell_token_replay。两臂使用同一份已存在的权重。历史文件与最新的原生契约可用 recipe_sha256 对齐。

```sh
OLD=run-recall/parameterized-deep-ripsat
python receipt_bake.py "$ROOT" "$OLD/catalog.json" "$BIN" "$OUT"
python receipt_regression.py "$ROOT" "$OLD/catalog.json" "$OUT/catalog.json" "$BIN" "$OUT/regression.json"
python receipt_takeover.py "$ROOT/loopfact" "$BIN" "$OUT/catalog.json" "$OUT/regression.json" "$OUT/takeover.json"
python receipt_plan_audit.py "$BIN" "$OUT/plans.json" "$ROOT"/{fact,loopfact,sum-divisors}/program.json "$DATA"/recursive-agent/{grammar-36719037,grammar-benefit-held-deep-11901379}/program.json
mkdir -p "$OUT/control"
cp "$OLD/catalog.json" "$OLD/event-gnn.pt" "$OUT/control/"
cp "$OLD/event-gnn.pt" "$OUT/"
for name in fact loopfact sum-divisors; do
  python deep_event_rollout.py "$DATA" "$OUT/control" "$name" --arms 2 --reps 1 --offset 40
  python deep_event_rollout.py "$DATA" "$OUT" "$name" --arms 2 --reps 1 --offset 41
done
for name in fact loopfact sum-divisors; do
  python deep_event_rollout.py "$DATA" "$OUT" "$name" --arms 2 --reps 1 --offset 43
  python deep_event_rollout.py "$DATA" "$OUT/control" "$name" --arms 2 --reps 1 --offset 42
done
```
