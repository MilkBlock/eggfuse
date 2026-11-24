# 前缀续接与 Higher Cell 直接路由

**Neural Execution，exclusive，CCP v0.1。** 所有独立轨迹从输入事实启动，沿用 Cell Stream、原生水位和已核验回执。运行的是 Rust standalone Cell CPU 与 PyTorch 生成器，工作负载来自 EggCC 与 CYK。冻结原末层、Transaction 控制、旧目录及其静态图编码。接收器、网络检查点和目录的 SHA-256 见[版本清单](artifacts.json)。覆盖分子是终图对齐的不同参考派生事实；EPT 和 EPS 的分子是签名账本归属的有效原子变更。付费量含失败、重复和计算请求。原生融合布局入口单列，完整阶层请求与 CCP 展开的逐步请求各按自身入口计费。实验没有启用精确搜索补齐。

## 最早可达的缺口

在上轮 **局部前缀** 模型的实际签名轨迹上，逐 Run 隔离运行一次精确 next-Run，从自己的前一发布状态取得可核验的具名见证。原生 recall 按输入绑定排除已用其他证明完成的目标。仅在下表的离线反事实中注入首个遗漏 Run 的见证，后续由同一个冻结模型继续独立执行，观察最终事实身份。

| 程序 | 最早漏掉的不同绑定 | 注入并继续后的终图变化 |
|---|---|---|
| fact | Run 79，规则 251，2 个，均到达末层后被挡住 | 找回 2 个 CellSpineApplied183、8 个 ExprIsPure；剩 1 个 SubTuple |
| fact，沿上行反事实继续诊断 | Run 91，规则 144，1 个，同为末层拒绝 | 找回 SubTuple，终图 SHA 与参考一致 |
| sum-divisors | Run 12，规则 294，8 个，均到达末层后被挡住 | 找回 8 个参考事实，原已覆盖事实全保留；其余 4,873 个缺失事实未因此恢复 |

该归因检验的是一组干预足以恢复哪些事实。它没有证明某一条具体证明不可替代。这里的召回和干预结果均不计入神经成绩。[11 个事实与具名父引用](miss-fact.json) · [第二次干预](miss-fact-second.json) · [sum-divisors 的首批遗漏](miss-sum-divisors.json)

## 可完成性、完成数量与展开成本

loopfact 加四个训练 grammar，MPS 650 步。向后投影已完成证明；同一部分路径可能有多个原生赢家。对选中的小型后缀域穷举**类型相容**的后缀，用离线原生核验逐一标注；只有完整检查该域且没有合法完成才可标无解。大域未穷举的已见赢家数是下界；没有正例而又未查完的样本忽略存在性损失。在可审计的域上，用基线实际 bucket 遍历测得的后续打分访问数监督成本。该成本标签衡量原子访问数，运行时另测墙钟。

训练集有 1,379 个可完成前缀、1,851 个确认无解、2,343 个未知，共核验 77,273 个具名请求。重训得到逐张量相同的权重。新训练未使用 fact、sum-divisors 或两份测试 grammar；这两个 EggCC 程序曾用于架构开发。盲测指标只针对本次留出。fact / sum-divisors 的可完成性平均精确率分别为 .812 / .971，对应已知样本阳性率 .426 / .828。sum-divisors 中审计到的真实平均完成数 .954，预测 .376；平均展开访问 1.745，预测 .457。排序对正例有辨别力，但低估了工作量，特别是有多个结果的前缀。受 72 个类型后缀及每程序最多 65,000 次离线核验预算限制，这些回归误差不能外推到全部大域。[训练清单](continuation-fit.json) · [留出评估](completion-eval-sum-divisors.json)

独立解码中，每个可达前缀均获得服务。预测的可完成概率与预计完成数/成本用于选择粗细两种神经字段地址。低优先级部分在同一冻结快照内继续展开；每轮计数核对所有延期项均已服务。细地址由 Bake 已给出的共享字段、已有神经向量的 LSH 码构造。实际执行在 CPU 上排序、定位和读桶，索引构建与访问计费。第二个共享字段可用时使用第二个字段码，否则使用同一字段的额外投影位。启用 Response 计算查询的角色保留原路径。对于有 seminaive 要求的终端角色，可以从同一神经桶中直接读该规则的 delta 区间。实际 teacher 证明上的细地址审计中，fact 的 1,774 次关联读取、sum-divisors 的 19,544 次均保留。此检查覆盖已记录的见证；完整性结论限于实测程序与既有检索域。末层门槛仍会拒绝完整请求。

| 同终图组 | fact 付费 Token / EPT | sum-divisors 付费 Token / EPT | sum-divisors 中位 EPS |
|---|---:|---:|---:|
| 原局部前缀模型 | 97,755 / .01341 | 1,554,312 / .002786 | 141 |
| 前缀完全放行，旧地址 | 158,281 / .00828 | 5,969,994 / .000725 | 115 |
| 学习逐前缀选择粗细地址 | 147,485 / .00889 | 4,126,027 / .001050 | 126 |
| 学习触发细索引，此后同一规则深度复用 | 111,726 / .01173 | 1,969,015 / .002200 | 146 |
| 固定细地址，直接读 delta 区间 | 96,935 / .01352 | 1,614,141 / .002683 | 154 |

所有 EggCC 组都到达调度结束，fact 同为 1,109/1,120、sum-divisors 同为 3,137/8,018。逐组验证了相同终图 SHA 和 1,311 / 4,331 个有效操作。未增加新事实。前缀主组在 CYK801 和两份留出 grammar 上均保持完全覆盖。固定细地址在 sum-divisors 减少约 32% 的候选打分访问，但仍签出 1,466,314 个重复证明。开关 delta 子索引，端口位置遍历从 23,086,144 减至 3,177,584，实际打分数均为 3,152,609。固定细地址的收益不能归到新训练的模型。[前缀工作量、每组配对基线与胜数](prefix.csv)

## 同一 Bake 目录上的稀疏激活

A 对每个可选布局用冻结识别器逐项打分。B 从当前根状态直接输出模板 ID 或空选项，用一次仿射运算计算该根菜单的全部 logits。C 有两种实现。并行地址位路由预测使用位和只与当前菜单有关的二进制地址位；树形路由先决定是否使用布局，再在静态编码树上逐层预测左右子树，在线只访问选择的路径。单叶菜单只需使用位。未选中布局时沿用 primitive；核验失败仍收费。两种 C 都有逐根的空选项判定成本。

B 与地址位路由在 MPS 联合拟合 600 步；树形路由在相同训练来源单独拟合 600 步。根条件来自当时可见的端口，不展开内部推导。训练组沿用上一轮对生产者配对与完整布局的隔离；静态 Bake 元数据早已存在。离线测激活召回时，对 teacher 已发生的根事件，用已知可执行的布局集合作标签，分母为菜单内至少有一个已知正确布局的根。各个分组可能重叠。实际独立生成另计无效根、空选项、实际完成与接管。

| sum-divisors，全菜单 | 已知正根选中正确模板 / 1,850 | 留出配对 / 1,068 | CCP 实际少访问 | CCP 净省 Token | 原生融合净省 Token |
|---|---:|---:|---:|---:|---:|
| A 全菜单识别 | 1,308 | 314 | 124 | −63 | 124 |
| B 直接模板 ID | 802 | 0 | 106 | −1 | 106 |
| C 并行地址位 | 121 | 17 | 8 | −1 | 8 |
| C 二叉树寻址 | 280 | 179 | 14 | −116 | 14 |

四组与同入口纯原子基线分别核对终图 SHA、覆盖和有效操作数。fact 的原生融合净省 Token 分别为 46、39、2、4；CCP 则分别多付 15、1、1、16。两个测试程序上，直接模板分类均未选择正确的留出布局或配对。树形路由在 sum-divisors 留出的三步以上正根中命中 2/432；该数是标准根上的布局识别，独立执行中实际完成的实例另有原始回执。合用高覆盖局部前缀时，CCP 的 B 在 sum-divisors 保持 3,137 个事实：少访问 191 个候选，同时多付 52 个 Token。全菜单分组的 1,404 个事实属于原子替代实验的独立基线，不与高覆盖组混算。

### 目录增长与实际收益

冻结的 4,096 项库中，只从每个根原有的合格菜单按原顺序取八分之一、二分之一、全部。sum-divisors 实际可激活数为 65、115、199，fact 为 64、114、198。没有新增模板。在 sum-divisors 上，A 的实际识别打分从 215,364 增至 850,810。树形路由的空判定约 215,000 次，另访问的分支从 57 增至 293,866。全菜单时 A 的 CCP 识别中位时间约 .139 秒，B 约 .065 秒，树路由约 .096 秒。三者每次选择 Higher 实际省去的低层访问分别为 124/211,280、106/106,561、14/147,099。B 的单次仿射很便宜，但其模板 logits 仍线性增长；树路由减少目录评分的同时也漏掉了大量有效激活。

CCP 按展开的每个 PROVE 付费，在这里不能把已接管的原子请求全部算为净省。原生融合一次支付整份签名布局。比较均保留原子替代和获确认后跳过具名候选的逻辑。[两条入口的成本、EPS、冷启动与每次激活的净节省](routing.csv) · [目录增长与激活召回图](activation-recall.pdf) · [留出配对、布局和长布局的完整分母](router-recall-sum-divisors.json)


### 配对墙钟与适用范围

停止其他实验进程后，CCP 纯原子与直接模板预测各再独立执行四次，轮换先后。fact 的中位墙钟为 1.910 / 1.915 秒，sum-divisors 为 9.735 / 9.572 秒。直接预测在两个程序上都只赢 2/4 对。再计入路由菜单准备时间，直接预测分别为 1.990 和 9.646 秒。相同终图下，此实验未建立稳定的 CCP 墙钟优势。原生融合可以减少付费请求，但融合入口的一枚布局 Token 在 CCP 入口会展开为多枚请求。主表其余批次与部分其他研究任务共享机器，具体秒数应结合逐对差值解释；CYK 泛化检查与目录子集实验各为一次独立执行。

在前缀实验的同一组四次配对中，固定细地址加 delta 子索引的 fact 墙钟中位数由 6.351 降至 6.279 秒；sum-divisors 由 30.146 降至 28.097 秒，两项均赢 4/4 对。后者付费 Token 增加 59,829。终图相同使得本组可以比较 EPT 和 EPS，但 EggCC 距离参考不动点仍有缺口。所有时间均为 standalone Cell 实验入口；本文没有测得对生产 egglog 引擎的加速。[逐次配对计时](pairs.csv) · [逐次执行、请求与核验记录](executions.jsonl)

此前同程序上四次配对的原生 teacher 神谕重放，中位墙钟约为 fact 0.150 秒、sum-divisors 0.253 秒，两者均到达完整参考终图。与之相比，报告中约 6 秒和 28 秒的前缀生成仍只覆盖部分参考事实。[fact 神谕计时](../generation-frontier/oracle-fact.json) · [sum-divisors 神谕计时](../generation-frontier/oracle-sum-divisors.json)

### 复现

从 `benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer` 运行。ROOT 中包含冻结的输入轨迹、上一轮的局部前缀终图、支持 next-Run 审计的 release 版接收器；训练使用 PyTorch，在本机使用 MPS，独立解码使用 CPU。绘图需要 Matplotlib。下面的完整组与子菜单共享同一冻结目录。训练见证、精确反事实和影子召回统计仅用于离线。

```sh
ROOT=/Volumes/EggFuseWorkspace/experiments/cell-prefix-routing-20261124
DONOR=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123/sum
O=run-recall/prefix-routing
python prefix_misses.py "$ROOT" "$O" fact sum-divisors
python prefix_misses.py "$ROOT" "$O" fact --second
python completion_training.py "$ROOT" "$O"
python evaluate_completion.py "$ROOT" "$O" fact sum-divisors grammar-36719037
python template_routing.py "$ROOT" "$O" "$DONOR"
python template_routing.py "$ROOT" "$O" "$DONOR" --tree
python routing_evaluation.py "$ROOT" "$O" "$DONOR" fact sum-divisors
python prefix_service.py "$ROOT" "$O" --cases fact sum-divisors --reps 4
python prefix_service.py "$ROOT" "$O" --cases fact sum-divisors --arms local cached fresh-fine --reps 4 --offset 4
python prefix_service.py "$ROOT" "$O" --cases cyk801 grammar-36719037 grammar-benefit-held-deep-11901379 --reps 1
for tx in ccp fused; do
  python run_template_routes.py "$ROOT" "$O" --cases fact sum-divisors --transport "$tx" --reps 4
  python run_template_routes.py "$ROOT" "$O" --cases fact sum-divisors --transport "$tx" --modes atomic tree --reps 4 --offset 4
done
for f in 0.125 0.5; do
  python run_template_routes.py "$ROOT" "$O" --cases fact sum-divisors --transport ccp --fraction "$f" --modes full direct sparse tree --reps 1
done
python run_template_routes.py "$ROOT" "$O" --cases fact sum-divisors --transport ccp --modes atomic direct tree --learned-prefix --reps 1
# Run with the other experiment processes stopped.
python run_template_routes.py "$ROOT" "$O" --cases fact sum-divisors --transport ccp --modes atomic direct --offset 8 --reps 4
python summarize_routing.py "$O" --plot
```

报告保留 202 次独立执行的原始计数。汇总程序逐次核对终图、有效操作、原子访问与净付费；配对取同程序、同前缀设置和同一重复编号。53 项 Python 测试通过。README 的最小 CPU 分支完成 Cargo compile、run 及 5 次 bench；用既有 sum-bits 导出执行语义验收得到 `pass`。该验收独立于上表 EggCC 模型的独立执行覆盖率。[检查点、接收器与输入版本](artifacts.json)
