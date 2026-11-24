# Cell 生成、后继优先级与 Higher Cell

**Neural Execution，exclusive 与 teacher shadow 独立运行。** 在线实验使用真实的 EggFuse standalone Cell CPU 执行器和原生核验器，模型在 CPU 单线程推理，两套新参数在 Metal 训练。所有独立组关闭精确搜索补全。主实验走 CCP v0.1，计算路由、Observe、Submit、Seal 和逐 Run 可见性沿用各自的基线。Higher Cell 使用同一原生执行器已有的布局入口，另有同入口原子对照。[程序、执行器和权重指纹](manifest.json)

## 独立执行

在相同的零签发阈值下，新的三目标模型在 sum-divisors 找到 1,583 / 8,018 个参考派生事实，A 找到 1,404 个。付费 Token 减少 42.3%，候选访问从 727,022 增至 980,565。两个计数记录不同的工作。模型拒发更多完整路径，同时推进了更多后续 Run，547 → 619。原生回执中的重复从 330,185 降到 177,187，guard 拒绝从 41,135 降到 35,743。fact 的零阈值覆盖保持 363 / 1,120。

| 零阈值独立终点 | A | B 类型化 | 冻结残差 | 固定先计算 | 新三目标 |
|---|---:|---:|---:|---:|---:|
| fact / 1,120 | 363 | 227 | 363 | 363 | 363 |
| sum-divisors / 8,018 | 1,404 | 770 | 1,404 | 1,404 | 1,583 |
| CYK801 / 6,567 | 6,567 | 6,567 | 6,567 | 6,567 | 6,567 |
| 五步留出 grammar / 83 | 83 | 44 | 83 | 83 | 83 |
| 新输入种子 36719037 / 81 | 81 | 81 | 81 | 81 | 81 |

六个签发阈值为 −6、−3、−1、0、1、3，应用于完整的有父绑定。根与中间前缀保留现有门槛，零父初始化沿用原约定。模型可持续输出，池内无固定名额。每个阈值让模型从初始输入独立跑到原生调度终点。资源预算取上一轮 A 的 Token、候选访问、在线秒数各自的 10%、50%、100%，报告预算内最后一次完整发布的状态；同时测量十等分 Run 边界。新输入和单列验证程序使用本轮 A 的成本。资源切点对应同一次独立轨迹的不同执行前缀。Run 内尚未发布的工作只会在下次发布后获得覆盖信用。[各点 Coverage、EPT、EPS 与经验 Pareto 前沿](endpoints.csv) · [覆盖率与成本曲线](coverage-cost.pdf) · [三项指标图](frontier.pdf) · [预算前缀](budget-prefixes.csv)

**相同 Coverage 的比较会改变结论。** 在 sum-divisors，A（−1）与新模型（−3）都达到 1,613 个参考事实，终图哈希相同，签名有效操作同为 2,216，访问同为 1,063,868。付费量 404,140 → 399,485，减少 1.15%。若只和 A（−3）的 434,293 比，会放大收益。fact 中 A（−6）达到 382，新模型在这组六点中最高 373。sum-divisors 两者的六点最高覆盖相同。单独用验证 grammar-17122 的结果选点，先最大化覆盖，再最小化付费量，余下并列选最接近零的阈值，A、B、残差和新模型都选中 0。EggCC 六点最高值用于描述曲线。相同事实数可对应不同事实集合，配对 JSON 提供终图哈希供比较。[等覆盖观测点](matched-coverage.csv)

Coverage 分子是终图中匹配的不同参考派生事实，扣除初始已匹配事实。EPT、EPS 分子取原生账本中归属已签发请求的有效出生、写入、union 和可见性改变。在偏离参考的执行中，该账本可以包含参考终图以外的操作。分母分别是所有神经计算、取值、证明及显式神经控制指令的付费量，和从启动执行器到调度结束的在线墙钟，包括核验、索引、序列化、阻塞、Memory 更新和拒绝。离线重放和参考对齐不进入在线时钟。有些很高的阈值只留下少量多操作的初始化请求，EPT 会上升，Coverage 会很低。每个独立点的 JSON 保留 accepted、按原因拒绝、duplicate、同步、分项耗时、事务大小和 Run 数；精确补全数均为零。

逐一对齐参考事实身份后，sum-divisors 的零阈值净增 179 个来自找回 221 个、同时丢失 42 个。把六个阈值各自的独立终图取并集，新模型在 fact 覆盖的 378 个事实全部出现在 A 的并集中，A 还额外覆盖 6 个；sum-divisors 上新模型并集为 1,613，A 额外覆盖 15 个。并集仅用于审计可达事实，实际各次运行仍单独计分。本次没有找到一个 A 在六个操作点都漏掉、由新模型独自发现的 EggCC 事实。[按事实身份与表分解](fact-identity.json)

四次交替配对的零阈值中位 EPS 如下。每项包含完整在线成本。

| 有效原子操作 / 秒 | A | B | 残差 | 固定先计算 | 新三目标 |
|---|---:|---:|---:|---:|---:|
| fact | 288 | 304 | 291 | 289 | 288 |
| sum-divisors | 211 | 360 | 214 | 216 | 179 |
| cyk801 | 2,056 | 2,008 | 2,043 | 2,099 | 2,024 |
| grammar-benefit-held-deep-11901379 | 2,674 | 2,040 | 2,112 | 2,464 | 2,572 |

sum-divisors 零阈值在线中位墙钟为 9.58 → 11.28 秒，新模型快于 A 的配对为 0 / 4。终图相同的 1,613 点，A（−1）为 12.01 秒、184.5 EPS，新模型（−3）为 12.29 秒、180.3 EPS，同样为 0 / 4。原生纯精确与 teacher 神谕重放在该程序的四次中位墙钟分别为 0.239 和 0.253 秒，两者均复现完整参考终图。单列原生对照不包含在线模型和神经通信成本。[配对中位数和胜负](paired-summary.csv) · [sum-divisors 原始配对](paired-sum-divisors.json) · [原生神谕对照](oracle-sum-divisors.json)

## 学了什么

冻结 A 的字段检索、递归表示和计算策略。新网络读取完整路径已有的递归状态、字段读取结果、规则结构特征与 A 的原分数，通过共享 MLP 分别预测合法性、本绑定在该 teacher 状态产生有效操作的可能性、后继需求。前两项在末端修正签发分数。第三项只重排当前块内所有达到门槛的证明；Run 结束前仍可全部签发。训练及运行都没有输入可学习的 token 编号或符号名字。

- 训练样本来自 loopfact 及四个 grammar，合计 4,448 份原生核验请求，包含 teacher 证明、桶内干扰、类型相容干扰和经原生核验的替代证明。loopfact 有 381 个不同 teacher 绑定找到了替代证明。合法性来自核验回执；新增性信用按语义绑定和该 teacher 的有效操作账本分配，同一绑定的替代证明共享标签。它衡量此绑定的潜在贡献；同批中的重复请求最终按实际原生账本计费。
- 后继需求使用被其他 teacher 请求实际引用的记录。另做 131 次删除重放，保留随后本会签发的具名请求，114 次减少参考覆盖，单次最多损失 987 个事实。对其中有经验证替代证书的 26 个再做替换重放，26 次都恢复参考覆盖。训练将删去该绑定的覆盖损失按 8 归一并截断，用作后继需求头的第二项监督。删除实验测量固定后续证书下的脆弱性，能另寻证明的 Agent 可能恢复。
- 三目标分支训练 480 步。`unranked` 保留同一检查点、候选和签发分数，仅关闭第三项排序。零阈值两者在四个主 workload 的独立终点、有效操作数和付费量一致。冻结的 A 主干曾接触 fact、sum-divisors，因此 EggCC 是架构开发对照。新分支和布局识别器均未以这两个程序拟合；种子 36719037 在本轮权重训练完成后生成，五步计算布局沿用已有的留出结构。[监督和逐项反事实](supervision.json)

**冻结快照与独立执行回答不同的问题。** 第一组在同一 teacher 轨迹最早 24 个 Run（较短程序取全部）上执行各阈值，所有神经提案交原生 recall 核对，每个 Run 的同一提交最多计一次。零阈值 fact 的 A 与新模型均为 66 / 112；sum-divisors 为 109 → 117 / 269。第二组从全程有提交的 Run 按时间等距取 24 个，teacher 仍逐步执行全部请求。fact 为 301 → 301 / 332，sum-divisors 为 295 → 292 / 299。分层组在 A 及其新分支上测量，这些决策头可从当前快照读取所需特征。两组样本选择不同，不能将其合并成整程 teacher 召回率。[逐阈值冻结结果](frozen.csv) · [跨全程分层 A](stratified-A.json) · [新模型](stratified-trained.json)

在第二组各 Run 的前 10% 签发中，用同一权重打开 Productivity 排序，fact 提前找回的、后来被 teacher 消费的提交从 29 降到 25，sum-divisors 从 53 降到 43（每 Run 向上取整，同组配平提案数）。早期 CYK801 快照中这一指标有所改善，不能外推到 EggCC。当前结果支持签发校准，尚无证据表明这种块内排序能够提升 EggCC 后继发现能力。[关闭排序](stratified-unranked.json) · [早期窗口关闭排序](shadow-unranked.json)

## 事前签发 Higher Cell

使用冻结的 4,096 项 Bake 库，选取其所有外部输入都能在根请求中具名的布局，以现有原生布局接收器执行。按程序规则结构重新映射后，fact 有 208 个适用布局，sum-divisors 有 209 个，尺寸为 2 至 7。模型输入为当前边界端口的表示、规则元数据和静态布局编码。在 sum-bits 与 loopfact 的 teacher 历史上训练 450 步，以实际完成且按时可用的布局为正例，采样未观察布局为弱负例。上线时为当前根选布局并在根提交前签发整张图，尚未发生的内部推导只能通过静态布线读取该请求之后的真实回执。每次请求最多选一个布局。无额外边界输入生成器。[识别训练](higher-training.json)

| 原生布局路径 | fact 原子 / 高层 / 混合 | sum-divisors 原子 / 高层 / 混合 |
|---|---:|---:|
| 派生事实覆盖数 | 363 / 3 / 363 | 1,404 / 3 / 1,404 |
| 总付费请求 | 9,947 / 1 / 9,947 | 376,781 / 1 / 376,781 |
| EPT | 0.0565 / 3 / 0.0565 | 0.00537 / 3 / 0.00537 |
| 完成的预签布局 | 0 / 1 / 47 | 0 / 1 / 121 |
| 高层内部获得信用的有效操作 | 0 / 1 / 49 | 0 / 1 / 141 |

混合组分别提出 1,690 和 211,277 份带布局的请求，完成的全部是曾在训练正例中出现的双步布局。纯高层组各完成一个初始化布局，后续缺乏足够的外部边界，因此 EPT = 3 只代表这一次请求。混合组的内部步骤确实执行，但原子生成器仍尝试签发它能发现的原子请求，总付费量和有效操作数均未减少。实验没有证明模型可以在测试程序上激活未见布局，也没有证明可替代内部签发。这里使用 native `online --layouts` 的现有逐 Run JSON 布局传输，三组关闭提前计算且走同一路径，序列化及核验纳入各自墙钟。CCP v0.1 的 proof 载荷没有 layout 字段；该实验验证原生预签和接管能力，传输时间只在三组内部对比。[fact 原生计数](higher_fact_mixed_0.json) · [sum-divisors 原生计数](higher_sum-divisors_mixed_0.json)

同一布局入口的四次交替计时中，fact 原子 / 高层 / 混合的中位 EPS 为 291 / 19 / 289，sum-divisors 为 177 / 19 / 163。高层单独执行的终图覆盖远低于另外两组。[fact 同入口原子对照](higher_fact_atomic_0.json) · [sum-divisors 同入口原子对照](higher_sum-divisors_atomic_0.json)

## 复现

已校验的输入镜像位于移动盘的 `/Volumes/EggFuseWorkspace/experiments/cell-generation-frontier-20261124`，`DONOR` 是同盘 `actor-eggcctraining-20261123/sum`。从本目录上两级的 `instruction_pointer` 运行，使用同一原生 release 二进制、上一轮训练产物和原始 teacher 数据目录。默认神经推理单线程，训练优先使用 MPS。所有学习与精确反事实只在各自训练资料上发生。预先的纯精确、神谕重放和 delta 验收沿用同一实验系列的已冻结检查，另对四个主 workload 重测 teacher 重放墙钟并核对 SHA。配对顺序正反交替，保存四次原始结果。图中的单独扫描是探索测量，配对端点以四次中位数作纵坐标。[上一轮及数据准备](../computation-benefit/README.md)

```sh
export PYTHONHASHSEED=0
out=run-recall/generation-frontier
python train_generation_targets.py "$ROOT" "$out"
python generation_frontier.py "$ROOT" "$out" --arms A B residual fixed trained
python generation_frontier.py "$ROOT" "$out" --arms unranked --cuts -3 0 3
python generation_frontier.py "$ROOT" "$out" --cases grammar-17122 --arms A B residual fixed trained --cuts 0 -6 -3 -1 1 3
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --extra-blind 36719037 --cases grammar-36719037
python generation_frontier.py "$ROOT" "$out" --cases grammar-36719037 --arms A B residual fixed trained --cuts 0 -3
python generation_shadow.py "$ROOT" "$out" --arms A B residual fixed trained
python generation_shadow.py "$ROOT" "$out" --arms trained unranked --cuts 0
python generation_shadow.py "$ROOT" "$out" --cases grammar-36719037 --arms A B residual fixed trained --cuts 0 -3
python generation_shadow.py "$ROOT" "$out" --cases fact sum-divisors --arms A trained unranked --cuts 0 --stratified
python generation_higher.py "$ROOT" "$out" --donor "$DONOR" --cases fact sum-divisors --reps 4
python generation_provenance.py "$ROOT" "$out" "$DONOR"
python generation_paired.py "$ROOT" "$out"
python generation_fact_sets.py "$ROOT" "$out"
python generation_report.py "$out"
```


完成 `python -m unittest discover` 的 47 项检查及 README 的 Cargo compile、run、五次 bench。使用已冻结的 sum-bits 导出运行 choice_diagnosis.py，语义验收返回 pass。该验收验证现有源程序的语义合同；独立神经组在 EggCC 的终图偏离如上单列。
