# 两个 RipSat 的具名接线能接管多少计算

本实验在原生 egglog Runtime 上运行。基线是 80c5706d 的递归 B。训练使用同一 GNN、同一 B 打分头、同一父指针参数及同一 RL 回报。独立执行使用冻结 CCP v0.1。三个完整 EggCC 程序使用此前已评估过的程序，dot-product 单列前 192 Run。

## 可以由一次决策执行的工作

旧 Compose 从两个开放端口签发一个 Primitive。新动作在寻找伙伴之前由 B 选择一段参数化 Recipe。两个入口各指向一个已命名证据，后续读可以指向任一所选主体的成员及其具名操作，也可以指向本次组合已提交的步骤。一次选择可以指定同一 Run 的多个兄弟规则和后续 Run 的汇合。源事件已绑定时，只需新绑定一个伙伴。每个后继步骤所需的新增独立绑定数为零，实际具名读取仍有成本。

训练目录仅使用 sum-bits。沿真实具名引用寻找两入口的后继，最多 8 步、根之后 32 Run，从 33 种观察到的多步接线留下额外有效操作为正的 16 种。按原生 Recipe 的具体规则签名链接到新程序，遇到缺失或歧义就不链接。动作描述复用已有规则读出，并编码后继的角色、成员位置、操作和发布组。源事件发生在 B 原有的稀疏调度页上。双主体伙伴指针对异主体、类型相容且组合满足规则水位的开放端口打分。遍历开放索引、父指针打分、底层普通候选访问和模板打分分别计数。打分前没有按字段值过滤伙伴。

Runtime 用首次发布的真实回执锁定地址和版本。下一组等到所需规则共同被调度再执行；退役、版本变化、缺少条件回执、原生拒绝或重复都会保留普通 B 的执行机会。只有原生接受的精确具名元组会从剩余搜索中扣除。每个内部签发继续按 CCP v0.1 付费。部分实例失败后普通 B 继续处理残余分支。

**能力正例。** 两个各含两步的 RipSat 分别发布两个端口。一次组合读取其中两对不同的端口，执行两条兄弟规则，在下一阶段将其输出汇合。实际 CCP 实现给定两个主体入口后，签发了全部三步、产生 3 个有效操作，整个程序 7 份请求均接受并复现精确终图。原生布局重放另核对调度、写入、RHS、事件和恢复序列。这个手工构造的例子只测结构表达与执行，未参与训练或 EggCC 成绩。[规则](two-bodies.egg) · [原生与 CCP 回执](oracle/fixture-witness.json)

## 给定正确伙伴的离线上限

使用 teacher 已签发的二元根、两个不重叠的已完成主体，或一个已完成主体加一个 Fact。表中“受益根”表示同一个正确根至少有一份已链接的接线能续接出一个有效操作；按根分别选最优可能重复占用同一后继。最后四列另取完整匹配并按末端访问节省排序，贪心取互不重叠实例，一起在原生 Runtime 实际接管。该打包给出一个已实现值，所有匹配后继的去重并集另给出乐观的边界。

| 程序 | 双主体受益根 / 正确根 | 主体加 Fact 受益根 / 正确根 | 非重叠实例 | 接管后继 / 有效操作 | 少访问的末端候选 | 净省后继 CCP 请求 |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits，训练 | 0/44 | 63/1,072 | 50 | 80 / 78 | 81 | 1 |
| dot-product | 0/52 | 16/888 | 18 | 22 / 13 | 22 | 0 |
| fact | 0/12 | 0/304 | 3 | 3 / 0 | 3 | 0 |
| loopfact | 0/16 | 5/252 | 8 | 12 / 5 | 12 | 0 |
| sum-divisors | 0/67 | 135/2,581 | 103 | 151 / 132 | 151 | 0 |

五次联合原生接管均保持完整参考终图、调度、写入、RHS、事件和恢复记录。搜索数字来自同一 teacher 快照上冻结 B 对精确路径的边际访问计数，仅计算新鲜根角色的普通末端探查。sum-divisors 的所有完整匹配后继即使忽略竞争，去重后合计也只对应 171 次末端访问。132 是受托完成的原生有效操作；两次执行的语义结果相同。[逐程序上限、接管实例及原生检查](oracle)

进一步在评估 tape 上直接查找结构机会，并开放两个已完成主体的所有成员。sum-divisors 的二元根增至 125 个，其中 59 个结果没有被后续证明直接引用。其余 66 个的最早消费均需要两个主体及其当时仍可见的匹配输入之外的证据。如果允许额外指定一条入口时已可见的外部引用，60 个根可接上一条后缀，31 个有有效操作；没有一个得到两步后缀。另发现 22 个三角色根的父引用分布在两个已完成主体内，根本身合计 6 个有效操作；本轮在线动作从二角色根进入。以上属于已记录证明、当前主体库与有界发现算法的机会，不涵盖所有等价证明或程序变换。[成员与第三证据诊断](oracle/sum-divisors-member-oracle.json)

## RL 与独立执行

从上一轮 recursive-rl.pt 开始，在 sum-bits 的前 320 Run 做四组镜像参数扰动，保留原有全轨迹 Coverage 约束、付费及墙钟回报。原权重 B 在相同前缀提供回报参照。八条探索轨迹合计选了 1,083 次结构 Extend 和 51 次结构 Compose，接受 9 个结构根、7 次后继签发，完整执行 1 个结构。七次后继归因到的新增有效操作合计为零。所有训练轨迹都产生了 1,677 个有效操作并覆盖 1,240 个参考事实，更新可利用的收益差主要来自成本。[回报](training.json) · [训练轨迹](training)

四组按“旧策略 → 仅修伙伴 → 加入结构动作 → 同结构继续 RL”执行，再逆序复测。前三组都使用上轮 RL 权重。每次从初始状态独立运行，核验器仅检查明确指定的计算。相同 workload 的四组产生相同的 state_sha。表中成本相对旧策略，EPT 沿用历史的原生有效操作 / CCP 付费请求，另报告将末端决策及开放动作计费的 EPT。EPS 使用从原生进程启动到关闭的实测时间，含寻址、索引维护、调度、通信、签发和核验。离线归因重放在计时区间之外。策略初始化和静态链接另作两次正反序计时。results.json 中同时给出按这两次初始化成本加回运行时间的 EPS 估计。

| 程序 | RL Coverage | 有效操作 | RL 付费 / 相对旧策略 | RL 候选访问增量 | 额外结构打分 | 横向 / 纵向实际跳过的末端候选 |
|---|---:|---:|---:|---:|---:|---:|
| dot-product 前 192 Run | 1,220/1,942 | 1,742 | 25,577 / +3 | +2 | 289 | 0 / 0 |
| fact | 764/1,120 | 1,094 | 297,797 / −1 | +274 | 182 | 0 / 0 |
| loopfact | 944/1,112 | 1,136 | 263,616 / −1 | +618 | 260 | 0 / 1 |
| sum-divisors | 3,085/8,018 | 4,321 | 4,930,893 / +2 | +3,156 | 582 | 0 / 1 |

在 loopfact 和 sum-divisors，RL 各签过一个结构 Extend 的根和一次纵向接续。每次实际签发两条规则，归因到的新增有效操作均为 0。两个已绑定主体引用提供了四条不同的具名边界读取，后继没有再寻找独立操作数。原有 B 在这两个例子各跳过一个已签位置；两组均未减少同等数量的上游模板决策。sum-divisors 的独立执行中伙伴指针多打 3,157 次分，抵消了那一次跳过。含控制决策的总计费减少 12，实际 CCP 请求增加 2。旧动作按最近发布选择伙伴，修复组在水位合法的开放回执中用原有父指针取最高分，两者都保留普通 B 的后续搜索。[各组逐次独立记录](independent) · [相同终图、决策、EPT、EPS 与配对墙钟](results.json)

## 在实际 Compose 决策时换对伙伴有多少用

单独重放仅修父指针组的独立轨迹。对每次网络已经选择 Compose 的上下文，记录所有合法水位的异主体开放端口，在运行结束后让原生规则逐个检查。匹配到同一输入签名时，比较赢家的实际签发顺序与当时的回执游标。审计重跑复现同一终图、动作、有效操作和付费请求。结果只约束这些事件、这个来源及当时开放的伙伴域。

| 程序 | Compose 决策 | 有水位合法伙伴的决策 | 原生逐对检查 | 有合法证明的决策 | 有尚未签发证明的决策 |
|---|---:|---:|---:|---:|---:|
| fact | 88 | 15 | 240 | 4 | 0 |
| loopfact | 144 | 25 | 619 | 6 | 0 |
| sum-divisors | 195 | 31 | 3,157 | 8 | 0 |

sum-divisors 的 3,157 对中，2,005 对绑定不符，576 对 guard 失败，576 对命中既有输入签名。这些有效替代证明集中在 8 次决策上，赢家在每次决策发生前都已签发。保持当前触发事件和开放证据集合，即使伙伴指针每次都选最优，三个程序仍合计只能新增 0 次签发。[独立状态原生反事实](oracle/sum-divisors-probe.json)

## 同终图成本

表中为旧策略到结构 RL 的变化。两个计时重复分别按正序、逆序运行。EPS 为两次直接计量的均值。不同程序的变化方向不同，sum-divisors 的差异小于轮间墙钟波动。

| 程序 | EPT | EPS | 正序墙钟秒 | 逆序墙钟秒 |
|---|---:|---:|---:|---:|
| dot | 0.06811606 → 0.06810807 | 84.16 → 84.03 | 20.65 → 20.74 | 20.74 → 20.72 |
| fact | 0.00367363 → 0.00367364 | 91.79 → 88.11 | 12.08 → 12.54 | 11.76 → 12.29 |
| loopfact | 0.00430928 → 0.00430930 | 103.91 → 107.70 | 10.72 → 10.56 | 11.15 → 10.53 |
| sum-divisors | 0.00087631 → 0.00087631 | 34.81 → 34.86 | 122.90 → 122.91 | 125.35 → 125.02 |

## 复现

从 instruction_pointer 目录运行。DATA 指向上一轮 recursive-ripsat 实验使用的原生程序、teacher tape、参考终图和冻结模型目录。OUT 使用一份新目录。训练只读取 sum-bits 环境和当前策略原生执行的回报；评估程序的三种 oracle 审计结果均未进入策略。可从本目录复制 structure-rl.pt 复现评估。重新训练采用实测墙钟作为回报的一部分，所得权重会受主机负载影响。

```sh
mkdir -p "$OUT"
cp run-recall/entry-first/entry/catalog.json run-recall/multi-entry/entry-contracts.json "$OUT/"
cp run-recall/entry-wiring/{wired,graph}.pt run-recall/recursive-ripsat/recursive-rl.pt "$OUT/"
python structure_recipe.py "$DATA" "$OUT" compile sum dot fact loopfact sum-divisors
python structure_members.py "$DATA" "$OUT" sum dot fact loopfact sum-divisors
python structure_takeover.py "$DATA" "$OUT" sum dot fact loopfact sum-divisors
python structure_study.py "$DATA" "$OUT" sum train --limit 320 --seed 431
for rep in 0 1; do
  arms=(recent pointer structure rl)
  if test "$rep" = 1; then arms=(rl structure pointer recent); fi
  for case in dot fact loopfact sum-divisors; do
    limit=()
    if test "$case" = dot; then limit=(--limit 192); fi
    python structure_study.py "$DATA" "$OUT" "$case" "${arms[@]}" --rep "$rep" "${limit[@]}"
    python structure_study.py "$DATA" "$OUT" "$case" "${arms[@]}" --rep "$rep" --setup-only
  done
done
python structure_partner_audit.py "$DATA" "$OUT" fact loopfact sum-divisors
python structure_results.py "$OUT" "$OUT/results.json"
cargo cell-compile --source run-recall/structure-compose/two-bodies.egg --output "$OUT/fixture"
"$DATA/unified-scale/build/release/examples/cell_token_replay" capture "$OUT/fixture/program.json" "$OUT/fixture/tape.json" audit --memory "$OUT/fixture/memory.jsonl" > "$OUT/fixture/capture.json"
python structure_fixture.py "$DATA" "$OUT/fixture" "$OUT/fixture-witness.json"
python -m unittest discover -p 'test_*.py'
```

83 项 Python 回归测试通过，包含第二父指针的水位掩码、同阶段分叉、发布等待、版本变化与原生拒绝。最小 CPU 路径通过 sum-bits 的 Cargo compile、run 和五次 bench；既有 sum-bits 导出通过 marker-handoff 语义验收。两个结论各自针对相应的执行路径。[语义验收记录](semantic.json)
