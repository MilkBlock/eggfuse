# 独立执行的递归前缀与 Higher Cell 替代

Neural Execution / exclusive。两个学习器均在 MPS 实际训练；单线程 PyTorch 签发、Rust standalone Cell CPU 接纳以及实际 RHS 执行和发布。EggCC 是工作负载来源。正式 CCP v0.1、原 A 的末层参数、Productivity 和事务控制保持冻结。仅在标为诊断的独立分支和事后核对中启用精确搜索。前一轮的神谕计时、重放和训练数据准备见[上轮报告](../generation-frontier/README.md)。

## 在网络自己的状态上定位漏项

对 A 的每一个独立 Run，从其实际签名请求重建前一边界，隔离运行一次原生搜索取得该快照的标准见证。再观察 A 的表达、调度、父端口版本/可见性、实际访问的 bucket、递归前缀、末层、签发、原生接纳。观察前后整个签名带、终图 SHA 和付费数相同。用原生投影绑定再核对替代证明。同一个模型 Run 和参考执行的同序号 Run 可能已被调度到不同 stage。

| 程序 | 独立 Runs | 快照上标准见证 | 签名路径命中 | 首失于前缀 | 首失于末层 | 含替代证明的不同绑定 |
|---|---:|---:|---:|---:|---:|---:|
| fact | 464 | 547 | 440 | 106 | 1 | 494 |
| sum-divisors | 547 | 2,039 | 1,477 | 548 | 14 | 1,811 |

这组标准见证由当时可见的实际行取得。两组的模板、寻址、签发后原生拒绝等环节在这些见证上均记零。fact 的 106 个前缀漏项中有 54 个由其他证明完成；sum-divisors 的 548 个中有 332 个由其他证明完成。另以参考证明的递归来源和版本投影到独立快照，fact 有 73 个缺原父来源、1 个版本不同、1,546 个当轮调度不同；sum-divisors 对应 416、51、8,573。其余参考 Run 若发生在模型停止之后则没有同序号模型快照。此口径不能排除等价父来源。缺少上游事实的证明不会出现在第一张表的分母。[fact 全 Run](funnel-fact-all.json) · [sum-divisors 全 Run](funnel-sum-divisors-all.json)

### 独立反事实

表中计数为终图可见的不同参考派生事实，已扣除输入。检索开放使用相同类型与可见性下的分块稠密访问。所有干预均从头独立运行，保留原生规则调度、字段计算和核验。

| 保留其余设置，仅改所列环节 | fact / 1,120 | sum-divisors / 8,018 |
|---|---:|---:|
| A，零阈值 | 363 | 1,404 |
| 末层全部签发 | 382 | 1,611 |
| 检索全部开放 | 363 | 1,404 |
| 检索与末层开放 | 382 | 1,611 |
| 递归前缀全部放行 | 1,109 | 3,137 |
| 前缀与末层开放，保留 LSH | 1,120 | ≥5,359（180 秒） |
| 三层全开，逐项扫描 | ≥99（50 秒） | ≥332（50 秒） |
| 全开放的原生见证对照 | 1,120 | 8,018 |

预算行给最后已发布状态的实测下界。原生见证对照在它自己已签名的前缀上 fork，通过精确搜索定位可接受元组，然后在另一条真实 CCP 流上重新以具名父引用签发；两程序均复现参考 SHA。它测量表达与可见性允许的端点，原生顺序、过滤和用时归于神谕。它没有测得按神经候选顺序无预算穷举的终点。逐次工作量/同步/拒绝原因见原始 JSON。[干预明细](reach.csv) · [fact 神谕](oracle-open-fact.json) · [sum-divisors 神谕](oracle-open-sum-divisors.json)

## 训练后实际找到了哪些新事实

在上一代递归状态和按字段分开的局部表示上训练一个前缀续接模型，和 A 的原分数取最大值，末层沿用 A。监督包含已出现于完整 teacher 证明的部分路径，以及在同类型候选中扰动的未记录部分路径。后者可能含合法别证，属于弱负例。训练材料是 loopfact 和四份 grammar，按程序重命名地址，420 步。完整模型额外读取下一角色可见端口的均值和逐维最大值；消融将这 48 维置零、复用同一权重，配对试验中直接省去该读取。没有把身份、未来回执或原生见证输入在线模型。[前缀训练清单](prefix-fit.json)

| 单独执行至调度结束 | fact 事实数 | 超出 A 六阈值并集 | sum-divisors 事实数 | 超出 A 六阈值并集 |
|---|---:|---:|---:|---:|
| A 原前缀放宽一个 logit | 581 | 201 | 2,082 | 533 |
| 学习续接，含下一角色池化 | 934 | 554 | 2,206 | 719 |
| 同权重，仅用局部前缀 | 1,109 | 729 | 3,137 | 1,578 |

A 六个终图的并集各有 384、1,628 个派生事实。局部前缀模型各漏掉其中 4、69 个。它虽找到新的事实，两组 EggCC 终图仍与参考 SHA 不同。CYK801 为 6,567/6,567，两个留出 grammar 分别为 81/81、83/83，三者均复现参考 SHA。EggCC 两程序曾用于前几轮开发；本轮前缀训练没有使用它们。这里的结果不能说明池化增强有效，也没有区分所有可能的前缀阈值策略。

| 同终图与相同有效操作数，四次交替 | 全开前缀付费 → 学习续接 | 候选访问 | EPT | 中位 EPS | 学习续接墙钟胜数 |
|---|---:|---:|---:|---:|---:|
| fact，1,311 有效操作 | 158,281 → 97,755 | 390,976 → 305,590 | .00828 → .01341 | 209 → 201 | 0/4 |
| sum-divisors，4,331 有效操作 | 5,969,994 → 1,554,312 | 12,349,891 → 4,635,185 | .000725 → .002786 | 120 → 142 | 4/4 |

A 原预算的 EPT 分别为 .05646 和 .00537，明显高于高覆盖点。EPS 为带原生信用的有效变更除以实际墙钟，EPT 的分母含计算请求和重复、被拒的签发；逻辑匹配不计作变更。报告使用运行时的 signed_ops，不拿参考派生事实数充当分子。墙钟含 CPU 队列、检索、编码、推理、同步、核验和内存更新。其他实验进程在同一台主机上运行，配对方向及离散程度见原表。先前 teacher 回放的中位墙钟约 0.15 秒和 0.26 秒；上述同终图比较不构成相对原生执行的加速。[四次逐对计时](pairs.csv) · [覆盖与成本图](reach-cost.pdf)

## Higher Cell 能接管哪份工作

同一根边界上选择 primitive 或带 Bake 布局的 Higher Cell。识别只看当时已可见的根输入和模板。内部读取只走已预签的静态接线、实际返回端口和锁存版本。B 继续普通枚举；C 在打分后排除同快照、同规则、同角色顺序、同版本且已原生接纳的原子元组；D 在访问对应终端候选前排除该位置。下一次发布必须确认实际接纳 token。解码器保留其余 bucket 成员、不同证明和后继 Run 的新版本。未闭合的中间前缀仍需访问，局部索引定位和候选前缀的筛查也付费。事后包装、重复请求借用赢家以及按未执行预测跳过均未启用。

下表每行的 A/B/C/D 有相同终图 SHA、相同的有效操作数及覆盖数。为隔离布局接管，四组均关闭提前计算分支，故 A 的计数与上一节略有不同。

| 入口与 workload | A 原子付费 | B 附加 | C 抑制重复 | D 免访问 | D 相对 A 少访问 | D 识别打分 | A → D 中位 EPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| CCP v0.1，fact | 9,947 | 10,008 | 9,962 | 9,962 | 46 | 7,878 | 297 → 295 |
| CCP v0.1，sum-divisors | 376,781 | 376,968 | 376,844 | 376,844 | 124 | 850,810 | 205 → 192 |
| 原生融合布局入口，fact | 9,947 | 9,947 | 9,901 | 9,901 | 46 | 8,019 | 297 → 286 |
| 原生融合布局入口，sum-divisors | 376,781 | 376,781 | 376,657 | 376,657 | 124 | 851,318 | 168 → 154 |

CCP v0.1 把已选择的布局展开为批量 PROVE，每个内部请求都计 Token。fact 内部 61 次有 46 次接纳，sum-divisors 的 187 次有 124 次接纳。在冻结 ABI 下省去重复签发后仍比 A 多付 15 和 63 个 Token。原生融合对照沿用 Rust 的 JSON layout 入口，一次预签整个布局，可从 A 净省 46 和 124 个 Token。D 免去的是实际打分访问，逐入口比较才有相同的包装口径。两种入口均未建立净 EPS 收益。[全组 EPT、EPS 与识别时间](higher.csv)

识别器以 sum-bits、loopfact 的边界样本训练 450 步。按原始规则对哈希先留出配对，再从其余结构中留出完整布局，拟合时同时排除这两组的正负标签。全目录竞争时成功的布局均长两步。限制菜单做留出测试时，未见配对在 fact / sum-divisors 完成 22 / 63 个实例，未见布局完成 20 / 56 个；只允许留出的三步及以上布局时完成 **18 / 50 个三步实例**。最后一组实际接管 36 / 100 次原子访问，无净额外付费。它使用已 Bake 的模板；静态编码和历史目录均已有这些模板，因此这里的泛化范围是新识别器的训练标签及其配对。受限菜单的完成数不能当作全库自主激活的成绩。[识别训练](higher-training.json) · [三步 fact](higher-fact-Dunseen-long-0.json) · [三步 sum-divisors](higher-sum-divisors-Dunseen-long-0.json)

### 同时启用高覆盖前缀与替代

在 CCP 上固定新前缀，对比 primitive 与全目录 D。fact 两边同为 1,109 个事实，D 少访问 94 个候选，付费从 97,581 增至 97,632。sum-divisors 两边同为 3,137 个事实，D 少访问 260 个候选，却做了 4,339,213 次布局打分，付费从 1,552,440 增至 1,552,635。两个工作负载均核对了终图 SHA 和有效操作账本。单次联合试验只用于检验两项改动是否能够同时生效。[fact 联合运行](higher-fact-D-learned-0.json) · [sum-divisors 联合运行](higher-sum-divisors-D-learned-0.json)

## 复现与验收

数据及签名轨迹保存在移动盘的 `/Volumes/EggFuseWorkspace/experiments/cell-structural-reach-20261124`。沿用上一轮带原生成果的 CCP 入口；独立审计与融合接管需从本轮源码构建 `cell-token-ept` 示例程序。运行下列 Python 命令时工作目录是 `instruction_pointer`；使用装有 NumPy 与 PyTorch 的 Python。绘图另外使用 Matplotlib。先用 `cargo build --release -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay` 构建，再将 `EXE` 设为产物绝对路径。可将 out 指向新目录，避免覆盖发表的原始结果。

```sh
export PYTHONHASHSEED=0
ROOT=/Volumes/EggFuseWorkspace/experiments/cell-structural-reach-20261124
DONOR=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123/sum
out=run-recall/structural-reach
python live_reach_funnel.py "$ROOT" "$out" "$EXE" fact sum-divisors --all-runs
python live_open_oracle.py "$ROOT" "$out" "$EXE" fact sum-divisors
python train_reachability.py "$ROOT" "$out"
python reachability_rollout.py "$ROOT" "$out" --cases fact sum-divisors --arms A terminal prefix dense terminal-dense terminal-prefix open --seconds 50
python reachability_rollout.py "$ROOT" "$out" --cases sum-divisors --arms terminal-dense terminal-prefix --repeat 1 --seconds 180
python reachability_rollout.py "$ROOT" "$out" --cases fact sum-divisors --arms relaxed learned learned-nolook --seconds 200
python reachability_rollout.py "$ROOT" "$out" --cases cyk801 grammar-36719037 grammar-benefit-held-deep-11901379 --arms A learned learned-nolook --seconds 180
for i in 2 3 4 5; do
    if [ $((i % 2)) = 0 ]; then arms="learned-nolook prefix"; else arms="prefix learned-nolook"; fi
    for arm in $arms; do
        python reachability_rollout.py "$ROOT" "$out" --cases fact sum-divisors --arms "$arm" --repeat "$i" --seconds 200
    done
done
python higher_replacement.py "$ROOT" "$out" --donor "$DONOR" --cases fact sum-divisors --reps 4
for subset in layout pair unseen-long; do
    python higher_replacement.py "$ROOT" "$out" --cases fact sum-divisors --arms D --blind "$subset"
done
python higher_replacement.py "$ROOT" "$out" --cases fact sum-divisors --arms A D --learned-prefix
python generation_higher.py "$ROOT" "$out" --cases fact sum-divisors --verified-receiver "$EXE" --reps 4
python structural_results.py "$out" --plot
```

`reach.csv` 只收集独立解码，`pairs.csv` 检查同 SHA 同有效操作，`higher.csv` 检查两种传输各自的四组接管数。原始 JSON 保留签发数、原生重复数、按原因拒绝数、核验时间、GPU 训练设备、索引和同步等该入口支持的计数。神经执行中剩余精确搜索为零；终图未重合的独立执行以实际调度结束计，无法据此声称已达到参考不动点。基准 CPU compile、run、bench 均跑通；90 个 Rust 库测试、50 个 Python 测试通过。既有 sum-bits 导出经 choice_diagnosis 得到 pass，这是既有导出的语义验收。新增接管由本次运行的原生回执、终图对照和按 Run 确认覆盖。权重、程序和基线构建摘要见[文件清单](artifacts.json)。
