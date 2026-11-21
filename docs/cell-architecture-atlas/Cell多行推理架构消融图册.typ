#set document(title: "Cell 多行推理架构消融图册", description: "模板端口表示、共享策略与跨 Run 推理的配对实验设计", keywords: ("EggFuse", "Cell", "GNN", "multi-row", "ablation"))
#let navy = rgb("#162f42")
#let muted = rgb("#4c6171")
#let teal = rgb("#236960")
#let violet = rgb("#775692")
#let amber = rgb("#946422")
#let hair = rgb("#cfdbdc")
#let sans = ("Avenir Next", "Hiragino Sans GB", "Heiti SC")
#let serif = ("Libertinus Serif", "Songti SC")
#set text(font: sans, size: 10pt, lang: "zh", fill: navy)
#set par(leading: 0.60em, justify: false)
#set page(width: 230mm, height: 190mm, margin: (x: 15mm, top: 15mm, bottom: 15mm),
  header: context grid(columns: (1fr,auto), text(7.4pt,fill: muted)[EGGFUSE  /  RESEARCH NOTES], text(7.4pt,fill: muted)[CELL ARCHITECTURE ATLAS]),
  footer: context grid(columns: (1fr,auto), text(7.4pt, fill:muted)[2026.11.21   ·   实验设计与证据], text(8pt,fill:teal)[#counter(page).display("1")]))
#let linebar() = line(length:100%,stroke:0.6pt+hair)
#let tag(body, color: teal) = box(stroke: 0.55pt+color,radius:3pt,inset:(x:5pt,y:2pt),text(size:8pt,fill:color,body))
#let kicker(body) = text(9pt, fill:teal,weight:"bold",body)
#show heading.where(level: 1): it => it.body
#let title(body) = heading(level:1, text(font:serif,size:23pt,weight:"bold",body))
#let label(body) = text(9pt,fill:teal,weight:"bold",body)
#let small(body) = text(8.6pt,fill:muted,body)
#let card(name,body) = block(width:100%,inset:(left:8pt,right:6pt,top:4pt,bottom:4pt),stroke:(left:1.6pt+hair))[
  #label(name) #linebreak() #text(size:10pt,body)
]
#let plates = json("plates.json")
#let guide = json("planned-guide.json")

#kicker[研究图册   /   神经 e-graph 执行]
#v(2mm)
#text(font:serif,size:33pt,weight:"bold")[Cell 多行推理架构消融图册]
#v(1mm)
#text(size:13pt,fill:muted)[共享模板如何说明端口，多行策略如何分配同一张图的推导义务]
#v(2mm)
#align(center,image("figures/00-overview.svg",width:87%))
#v(1mm)
#small[图 00　早期受控两规则 PyTorch 原型。离线计划提供编译器确定的端口接线；make 预测绑定，finish 直接读取 GPU 上的 Pair。独立 CPU 审计核对来源与覆盖。完整 Pass 3 的递归提案与补查见图 56。]
#v(2mm)
#grid(columns:(1fr,1fr),gutter:9mm,
  card([研究问题],[网络能否从上一 Run 生成的 token 继续提出 Cell，并以少量验证关闭真实义务，使整轮加速？]),
  card([现有边界],[图 71 的选择性模型覆盖 99.83%–99.97% 的源 RHS，图 75 的根／子配方直接构造超过 99% 的新 Cell。整轮仍慢于精确 Rust。]))
#v(1fr)
#linebar()
#small[指标更正　显式父 FEPT 要求模型点名全部独立父实例。图 153、155–165 的类别、范围与补找父实例结果为外部传输诊断；0.819、0.973 均已撤出 FEPT 成绩线。]

#pagebreak()
#kicker[阅读指南   /   如何比较两种架构]
#v(1.5mm)
#title[一次只改变图中指定的机制]
#v(3mm)
#grid(columns:(1fr,1fr),gutter:9mm,
card([同一图与同一预算],[一个 row 是同图的一条 token 序列；八行各一项与一行八项可以有相同容量。batch 是不同输入图。固定总槽数后，还要记录不同布局的顺序轮数、计算量和等待。]),
card([同一见证与同一判据],[消费者必须读到模型实际生成的父槽。两个 Pair 的字段即使相同，只要父实例地址不同，就属于不同义务。完整图要求所有合法义务恰好出现一次，字段及祖先也正确。]))
#v(4mm)
#label[贯穿图册的反事实样本]
#v(1.5mm)
#block(fill:rgb("#f0f5f5"),width:100%,radius:4pt,inset:9pt)[
  #text(font:serif,size:13pt)[Pair#sub[0] = (A#sub[0], B#sub[0], k, x, y)　　Pair#sub[1] = (A#sub[1], B#sub[0], k, x, y)]   两次输入具有相同的图和值。只把一个 Request 的目标从 A#sub[0] 改为 A#sub[1]，请求的槽位、tag 和其余项保持不变。finish 必须跟随这一次变化；审计读取实际父引用。
]
#v(4mm)
#label[图例与实验状态]
#v(1.5mm)
#grid(columns:(1fr,1fr),gutter:8mm,
 [#tag("静态 / 模板",color:teal)　#tag("学习 / GPU",color:rgb("#305e81"))   #small[绿色是共享计划或编译器已确定的结构；蓝色是神经状态、策略或学习型模块。]],
 [#tag("训练信号",color:violet)　#tag("验证 / 就绪",color:amber)   #small[紫色虚线是仅训练时使用的监督边；箭头表示数据依赖。灰色空心格、× 或虚线载荷在各图内标出屏蔽。]])
#v(3mm)
#small[“待验证”表示给定对照尚无项目结果；“已测配对”表示运行过明确配对的模型；“已测干预”表示改动冻结模型可见的输入。任务边界变化不能直接作单组件因果解释。]
#v(3mm)
#label[优先顺序]
#v(1mm)
#text(size:10pt)[先建立 1×8 单行正确性与跨规则共享头，再单独测试端口编码。锁定可用表示后按 1×8 → 2×4 → 4×2 测零样本展开；出现重复和遗漏后才比较集合监督、团队 RL 和信用分配。最后放开启用行数与就绪门控。]
#v(1fr)
#linebar()
#small[各页底部的档案号在末页对应仓库证据或原始文献。所有提议图均为结构示意，不含预测跑分。]

#pagebreak()
#kicker[候选架构   /   组件之间怎样连接]
#v(1.6mm)
#title[从模板端口到共享的 row 策略]
#v(2mm)
#text(size:11pt,fill:muted)[一种待测组合把模板编码、实例选择与轨迹级训练接在一起。通过图 01、02、04、05 逐项替换其中一处，可分辨收益的来源。]
#v(3mm)
#image("figures/00-proposal.svg",width:100%)
#small[总图 A　左侧从模板结构生成端口向量；中间结合当前实例和父引用，由各 row 共用的策略选择绑定。右侧用已生成的集合判定覆盖，虚线只出现在训练。GNN、共享头、两行 RL 已分别实测；组合策略仍需同任务配对。]
#v(3mm)
#grid(columns:(1fr,1fr),gutter:8mm,
card([训练时],[先让单 row 在八个顺序位置上生成整套义务，学会跟随显式父引用。复制权重到两个 row 后，再用精确轨迹审计提供联合训练信号。]),
card([部署时],[冻结编码器并缓存每个模板的端口向量，记录编译版本。GPU 策略读取当前实例，生成下一 Run 直接可消费的 token。静态投影沿所选引用读取 RHS 字段。]))
#v(1fr)
#linebar()
#small[相同模板可出现于多个 row 和 locality。模板编码在这些实例间共享，当前实例的父引用、可见性和未完成义务随运行而变。]

#for (i,p) in plates.enumerate() {
  pagebreak()
  if p.id == "38-repair-bake" {
    kicker[讨论回顾   /   图 38–75 的实验动机]
    v(2mm)
    title(guide.title)
    v(2mm)
    for item in guide.findings {
      card(item.at(0),item.at(1))
      v(1.7mm)
    }
    label[实验次序]
    v(1.5mm)
    table(columns:(37mm,24mm,1fr),stroke:(bottom:0.45pt+hair),inset:(x:4pt,y:3.1pt),
      ..guide.order.map(r => (text(size:9pt,weight:"bold",r.at(0)),text(size:9pt,fill:teal,r.at(1)),text(size:9pt,r.at(2)))).flatten())
    v(1fr)
    small[本节数字来自既有实验 S8、S10、S12、S24、S28–S30。各图按所验证的真实工作负载、原型或反事实注明范围。]
    pagebreak()
    kicker[实验协议   /   共享的正确性和计时口径]
    v(2mm)
    title[怎样判定一次 Cell 提案值得执行？]
    v(3mm)
    for item in guide.contract {
      card(item.at(0),item.at(1))
      v(3mm)
    }
    label[选择、验证与发布]
    v(1mm)
    text(size:10pt)[同一个 union 待办已含旧类、新类和实例地址。一行若选择只改结果槽的变体，验证器仍要检查外部读者及键碰撞。另一行若重复认领，只给实际关闭的工作记一次收益。GPU 单独执行的实验须在设备上完成补查。]
    v(1fr)
    small[拟测容量写参数个数，库大小另报模板数与字节；每实例状态、训练集基础组和生成样本分别计数。]
    pagebreak()
  }
  let n = str(i+1)
  if n.len()==1 { n="0"+n }
  grid(columns:(1fr,auto),align:(left+horizon,right+horizon), kicker([图 #n　/　#p.section]),tag(p.status,color:if p.status.starts-with("待") {violet} else {teal}))
  v(1.7mm)
  title(p.title)
  v(1.4mm)
  text(size:11pt,fill:muted,p.q)
  v(3mm)
  image("figures/"+p.id+".svg",width:100%)
  v(1.8mm)
  text(size:10pt,p.arms)
  v(3.5mm)
  grid(columns:(1fr,1fr),gutter:8mm, card([固定条件],p.fix), card(if p.status.starts-with("待") {[验收指标]} else {[判据与读数]},p.measure))
  v(1fr)
  linebar()
  grid(columns:(1fr,auto),gutter:5mm,small(p.note),text(size:8.2pt,fill:teal,[#p.src]))
  if "observation" in p {
    let obs=p.observation
    pagebreak()
    kicker[图 #str(i+1)　/　实测曲线]
    v(1mm)
    text(size:15pt,font:serif,weight:"bold",obs.title)
    v(1mm)
    align(center,image("figures/"+obs.figure,height:114mm,width:100%,fit:"contain"))
    v(1fr)
    small(obs.caption)
  }
}

#pagebreak()
#kicker[冻结结果   /   选择哪些基线]
#v(2mm)
#title[字段正确之后，覆盖还差多少？]
#v(2mm)
#text(size:11pt,fill:muted)[开放父引用时，两个种子在相同的 512 张非空碰撞图上运行。每张图只有在全部 Result 义务恰好出现一次、字段和实际父均正确时才计入通过数。]
#v(3mm)
#image("figures/00-results.svg",width:100%)
#small[总图 B　横轴为通过的图数，图示 0–80，分母始终为 512。圆、方两个点是两个种子，连接线只用于对读，不表示置信区间。数据取自 S2。]
#v(3mm)
#grid(columns:(1fr,1fr),gutter:8mm,
card([从生产者看],[辅助头版本分别向 255、277 张图供齐所需父。消费者仅完成其中的 65、67 张；已有正确父仍未完成的分别是 190、210 张。这是图 01–07 的实际目标。]),
card([从训练监督看],[字段投影让合法绑定的字段读出正确。额外的训练期字段监督在碰撞集上带来改善，两个种子的遗漏却仍有 550、579 项，分母为 910 个合法绑定。]))
#v(1fr)
#linebar()
#small[以上只使用存档的六个权重。数值后端的对齐检验见 S1；重新训练的单个模型不并入这些配对结果。]

#pagebreak()
#kicker[实验登记   /   从候选到保留]
#v(2mm)
#title[在相同正确性下比较速度]
#v(3mm)
#table(columns:(27mm,1fr,1fr),stroke:(bottom:0.5pt+hair),inset:(x:5pt,y:4pt),fill:(x,y)=>if y==0{rgb("#e5eff0")},
 [*门槛*],[*冻结与测量*],[*如何取舍*],
 [数据隔离],[种子、最终 checkpoint、同一组反事实请求预先固定。按源码家族与组合模板划分。],[一个程序的参数变化、Run 窗口和重编号留在同一 split。未知模板与新行数分别统计。],
 [语义],[非空完整率；合法绑定恰好一次；父引用、字段、阶段、有效写入和最终状态。],[分别给出遗漏、重复和非法提案。另报“生产者已供齐全部所需父”时消费者的通过率。],
 [耗时],[主口径为单图原始输入上设备至两 Run 完成、解码、同步。离线训练、编码缓存及事后 CPU 审计单列。],[同机同输入轮换顺序，报告每条件中位数、原始样本、完整合法非空图/秒。未达语义门槛时同时展示质量与时间。],
 [资源],[参数量、训练更新与采样数、批内活跃 row、顺序轮、通信量与峰值显存。],[重叠绑定不重复计收益。压缩率不替代有效推理吞吐。],
)
#v(4mm)
#label[三条优先实验的反证]
#v(1.5mm)
#text(size:10.5pt)[*端口 GNN（图 01）*　若在整族留出的组合模板上无法超过编译器角色特征，就无需为该任务增加图编码成本。 *零样本展开（图 04）*　若单 row 自身不能在非空图上完整推导，先记录单行瓶颈；多行失败不能全部归因于同步。 *RL 分工（图 05）*　若同预算多行监督达到同等或更高的正确吞吐，则 RL 的额外采样与信用估计没有得到收益证明。]
#v(3mm)
#small[真实负载扩展：新增的 8 个 Bril 家族均已取得逐 Run 来源、union 前订阅和键修复记录，完成 CPU／GPU 核对与原生终图验收。4 个训练、2 个开发、2 个留出。档案 S8、S31。]

#pagebreak()
#kicker[证据目录   /   复核路径]
#v(2mm)
#title[回到原始记录]
#v(2mm)
#small[下列仓库路径相对 EggFuse 根目录。配套 README 提供可点击链接；以 68193237 的源码和冻结记录为本图册基线。]
#v(3mm)
#set par(spacing: 0.12em)
#let src(k,l,p) = grid(columns:(10mm,55mm,1fr),gutter:3mm,text(fill:teal,weight:"bold",k),text(size:8.9pt,l),text(font:("Menlo","Arial"),size:7.8pt,p))
#src("S1","PyTorch 独立前向、MPS/MLX 对照","benchmarks/multi-row-generation/torch_crossrun/README.md")
#src("S2","跨 Run、两种子、父碰撞和掩码","benchmarks/multi-row-generation/crossrun/results/metrics.tsv")
#src("S3","自由槽、遗漏、重复与重放","benchmarks/multi-row-generation/allocation/README.md")
#src("S4","覆盖监督与结构留出","benchmarks/multi-row-generation/coverage/README.md")
#src("S5","真实历史、屏蔽训练和同行干预","benchmarks/multi-row-generation/streaming/README.md")
#src("S6","规范符号、连续状态与 12 轮验收","benchmarks/multi-row-generation/typed/README.md")
#src("S7","二维地址、模板投影与确定性检查","benchmarks/multi-row-cell/README.md")
#src("S8","8 个真实可运行的 Bril 源码家族","benchmarks/eggcc-diversity/manifest.json")
#src("S9","长期执行契约、原有设计与证据","docs/MULTI_ROW_EGRAPH_NEURAL_PLAN.zh.md")
#src("S10","图 01–02 实测结果","benchmarks/multi-row-generation/port_ablation/README.md")
#src("S11","模板局部等价分区准入","docs/cell-architecture-atlas/template-eclass.md")
#src("S12","图 20 已证等价分区实测","benchmarks/multi-row-generation/eclass_ablation/README.md")
#src("S13","图 03 多端口地址与迁移","benchmarks/multi-row-generation/address_ablation/README.md")
#src("S14","图 04 零更新展开","benchmarks/multi-row-generation/width_ablation/README.md")
#src("S15","图 05 两行监督与 RL","benchmarks/multi-row-generation/credit_ablation/README.md")
#src("S16","图 06 实际门控跳算","benchmarks/multi-row-generation/gate_ablation/README.md")
#src("S17","图 07 消费者就绪与源边界","benchmarks/multi-row-generation/readiness_ablation/README.md")
#src("S18","图 14 局部状态与边界证书","benchmarks/multi-row-generation/locality_ablation/README.md")
#src("S19","图 15 延迟 union 与观察点","benchmarks/multi-row-generation/union_ablation/README.md")
#src("S20","图 16 组合接管与旧端口","benchmarks/multi-row-generation/ownership_ablation/README.md")
#src("S21","图 17 证明编码与验证成本","benchmarks/multi-row-generation/proof_ablation/README.md")
#src("S22","图 18 私有成员与退出条件","benchmarks/multi-row-generation/integral_ablation/README.md")
#src("S23","图 19 预算、关闭与恢复","benchmarks/multi-row-generation/stopping_ablation/README.md")
#src("S24","图 21–22 初图与多行执行","benchmarks/pass3-cell-gpu/README.md")
#src("S25","图 23–29 逐 Run 验收与耗时","benchmarks/pass3-cell-gpu/ACCEPTANCE.md")
#src("S26","图 30–32 常驻与阶段归因","benchmarks/pass3-cell-gpu/profile/README.md")
#src("S27","图 33–34 混合路径","benchmarks/pass3-cell-gpu/hybrid/README.md")
#src("S28","图 35 常驻端口选择父行","benchmarks/pass3-cell-gpu/unique-parent/README.md")
#src("S29","图 36 集合与 union","benchmarks/pass3-cell-gpu/set-memory/README.md")
#src("S30","图 37 块级上限","benchmarks/pass3-cell-gpu/block-ceiling/README.md")
#pagebreak()
#kicker[新增实测   /   数据与源码]
#v(2mm)
#title[复核共同修复与父引用实验]
#v(4mm)
#src("S31","真实程序与 union 观察","benchmarks/pass3-cell-gpu/co-repair/CORPUS.md")
#src("S32","图 38–40、55 成本消融","benchmarks/pass3-cell-gpu/co-repair/README.md")
#src("S33","图 46 输入编码与宽度","benchmarks/pass3-cell-gpu/key-signals/README.md")
#src("S34","图 41 固定空间的选择","benchmarks/pass3-cell-gpu/region-admission/README.md")
#src("S35","图 56 递归生成与验证","benchmarks/pass3-cell-gpu/recurrent-generator/README.md")
#src("S36","验证回执与真实提交","benchmarks/pass3-cell-gpu/recurrent-generator/receipts/README.md")
#src("S37","组合上限与多波生成","benchmarks/pass3-cell-gpu/recurrent-generator/receipts/composable-proposals.md")
#v(5mm)
#linebar()
#pagebreak()
#kicker[证据目录   /   生成与验证]
#title[整段生成、精确投影与设备放置]
#v(5mm)
#src("S38","待验父端口与交叉重放","benchmarks/pass3-cell-gpu/recurrent-generator/pending/README.md")
#src("S39","真实失效与多重支持","benchmarks/pass3-cell-gpu/proof-retirement/README.md")
#src("S40","整段神经生成","benchmarks/pass3-cell-gpu/whole-pass-generation/README.md")
#src("S41","一次检查封闭饱和前缀","benchmarks/pass3-cell-gpu/coverage-certificate/README.md")
#src("S42","结构见证与精确整数投影","benchmarks/pass3-cell-gpu/numeric-projection/README.md")
#src("S43","神经策略在 CPU 和 GPU 的放置","benchmarks/pass3-cell-gpu/neural-device/README.md")
#src("S44","容量与训练来源","benchmarks/pass3-cell-gpu/neural-capacity/README.md")
#src("S45","三组部署与整数事务","benchmarks/pass3-cell-gpu/verifier-placement/README.md")
#src("S46","单项见证与桶覆盖","benchmarks/pass3-cell-gpu/bucket-coverage/README.md")
#src("S47","Rust 与 Metal 验证器","benchmarks/pass3-cell-gpu/native-forest/README.md")
#src("S48","冷模板与零更新的库增长","benchmarks/pass3-cell-gpu/cold-templates/README.md")
#src("S49","整数回执与后继选择","benchmarks/pass3-cell-gpu/interactive-policy/README.md")
#v(4mm)
#pagebreak()
#kicker[证据目录   /   完整 Pass 3]
#title[源提交、物理归因与所有权消融]
#v(3mm)
#src("S50","单动作的绑定、叶和组合","benchmarks/pass3-cell-gpu/action-granularity/README.md")
#src("S51","变长端口证书","benchmarks/pass3-cell-gpu/variable-certificates/README.md")
#src("S52","在线成员存储与切换","benchmarks/pass3-cell-gpu/online-storage/README.md")
#src("S53","修复训练与反例","benchmarks/pass3-cell-gpu/repair-training/README.md")
#src("S54","八槽预算下的多行所有权","benchmarks/pass3-cell-gpu/row-admission/README.md")
#src("S55","集合监督与工作奖励","benchmarks/pass3-cell-gpu/row-reward/README.md")
#src("S56","CPU 权威图与 GPU 增量验证","benchmarks/pass3-cell-gpu/verifier-deltas/README.md")
#src("S57","真实集合存储与容量阶梯","benchmarks/pass3-cell-gpu/set-representations/README.md")
#src("S58","完整源分母与独立见证","benchmarks/pass3-cell-gpu/coverage-target/README.md")
#src("S59","同一执行器的联合归因","benchmarks/pass3-cell-gpu/joint-witness/README.md")
#src("S60","首个精确检查前的多父批次","benchmarks/pass3-cell-gpu/ordinary-witness/README.md")
#src("S61","明确驱动物理分配的子端口","benchmarks/pass3-cell-gpu/joint-merge/README.md")
#src("S62","稀疏缓存与压紧候选","benchmarks/pass3-cell-gpu/ordinary-shortlist/README.md")
#src("S63","有版本的特征复用","benchmarks/pass3-cell-gpu/joint-score-sharing/README.md")
#src("S64","共享学习编码与固定签名","benchmarks/pass3-cell-gpu/tied-query-keys/README.md")
#src("S65","实际根配方与物理 ID","benchmarks/pass3-cell-gpu/joint-root-cells/README.md")
#src("S66","真实父发布 → 子 RHS 与下一轮库增长","benchmarks/pass3-cell-gpu/higher-order-bake/README.md")
#src("S67","冻结端口投影、签名桶与完整源执行","benchmarks/pass3-cell-gpu/baked-port-codes/README.md")
#src("S68","真实 CPU 行数与策略梯度","benchmarks/pass3-cell-gpu/adaptive-row-policy/README.md")
#src("S69","源水位选择编译入口","benchmarks/pass3-cell-gpu/fresh-entrances/README.md")
#src("S70","增量多父签名与过期剪枝","benchmarks/pass3-cell-gpu/incremental-neural-index/README.md")
#src("S71","计算请求小批与等容量流式对照","benchmarks/pass3-cell-gpu/request-transactions/README.md")
#src("S72","合并门控奖励与合成预训练","benchmarks/pass3-cell-gpu/merge-reward/README.md")
#src("S73","原生存储的 owner、旧视图和实测字节","benchmarks/pass3-cell-gpu/physical-composition-reward/README.md")
#src("S74","两个已存 owner 的真实转移与代次反例","benchmarks/pass3-cell-gpu/existing-owner-transfer/README.md")
#src("S75","学习端口签名的前缀可行性","benchmarks/pass3-cell-gpu/learned-prefix-feasibility/README.md")
#src("S76","封存元组的错误归因与多视图","benchmarks/pass3-cell-gpu/learned-atom-constraints/README.md")
#src("S77","训练负例和额外二进制端口容量","benchmarks/pass3-cell-gpu/collision-trained-ports/README.md")
#src("S78","冻结程序在两个更大负载上的源核对","benchmarks/pass3-cell-gpu/prefix-transfer/README.md")
#src("S79","Deriche 完整枚举、预算与分页","benchmarks/pass3-cell-gpu/complete-generation/README.md")
#src("S80","编译提取的双父整数端口","benchmarks/pass3-cell-gpu/pair-source-frontier/README.md")
#src("S81","按需算术端口与整数签名复用","benchmarks/pass3-cell-gpu/lazy-equation-ports/README.md")
#src("S82","发布时维护的单父可读视图","benchmarks/pass3-cell-gpu/published-single-headers/README.md")
#src("S83","六个程序的联合端口优化与 CPU 基线","benchmarks/pass3-cell-gpu/composed-cpu/README.md")
#src("S84","已认证 CPU 的行数与并行评分","benchmarks/pass3-cell-gpu/composed-row-dispatch/README.md")
#src("S85","移动已检查绑定与 Run 内票据","benchmarks/pass3-cell-gpu/verified-binding-transfer/README.md")
#src("S86","水位证明的阈值与代次","benchmarks/pass3-cell-gpu/suffix-watermarks/README.md")
#src("S87","已存 owner 的真实配对回报","benchmarks/pass3-cell-gpu/owner-action-policy/README.md")
#src("S88","在父选择之间插入完整键请求","benchmarks/pass3-cell-gpu/connected-request-plans/README.md")
#src("S89","按变更端口激活连接请求","benchmarks/pass3-cell-gpu/changed-request-roots/README.md")
#src("S90","修补订阅签名与 union 依赖","benchmarks/pass3-cell-gpu/incremental-request-ports/README.md")
#src("S91","学习两种父生成器的条件回报","benchmarks/pass3-cell-gpu/request-route-policy/README.md")
#src("S92","跨规则共享前缀或完整属性键","benchmarks/pass3-cell-gpu/shared-verifier-prefix/README.md")
#src("S93","自然放置、物理动作与真实训练回报","benchmarks/pass3-cell-gpu/prospective-owner-placement/README.md")
#src("S94","部署路径的类型化密封回执","benchmarks/pass3-cell-gpu/lean-root-receipts/README.md")
#src("S95","真实动态 Graph 的完整驻留曲线","benchmarks/pass3-cell-gpu/placement-lifetime/README.md")
#src("S96","单父投影的本机代码生成","benchmarks/pass3-cell-gpu/native-verifier-bake/README.md")
#src("S97","跨 Run 无结果证书和物理字段核验","benchmarks/pass3-cell-gpu/run-result-certificates/README.md")
#src("S98","完美地址选择的实际执行对照","benchmarks/pass3-cell-gpu/perfect-receipt-replay/README.md")
#src("S99","两种执行器分别进行原生 PGO","benchmarks/pass3-cell-gpu/native-backend-pgo/README.md")
#src("S100","同一 PGO 二进制内比较跨 union 订阅","benchmarks/pass3-cell-gpu/profiled-request-ports/README.md")
#src("S101","首次安置的单次配对回报","benchmarks/pass3-cell-gpu/prefix-placement-return/README.md")
#src("S102","页内共享局部前提与完整键结果","benchmarks/pass3-cell-gpu/page-premise-programs/README.md")
#src("S103","真正发行的角色字典凭证","benchmarks/pass3-cell-gpu/factored-receipt-pages/README.md")
#src("S104","多父 Cell 块的可执行后缀","benchmarks/pass3-cell-gpu/batched-cell-verifier/README.md")
#src("S105","直接消费页和函数结果的坐标","benchmarks/pass3-cell-gpu/coordinate-cell-block/README.md")
#src("S106","两轮页程序准入与返回值头","benchmarks/pass3-cell-gpu/iterative-page-library/README.md")
#src("S107","有序效果块与延迟写入者","benchmarks/pass3-cell-gpu/ordered-effect-blocks/README.md")
#src("S108","共享反向边及原生修复","benchmarks/pass3-cell-gpu/ordered-repair-reuse/README.md")
#src("S109","稳定 Cell 身份下的物理寻址","benchmarks/pass3-cell-gpu/paged-cell-ids/README.md")
#src("S110","同图执行的页验证、RHS 和修复","benchmarks/pass3-cell-gpu/block-execution-ceiling/README.md")
#src("S111","由已验证的页槽直接接续物理根","benchmarks/pass3-cell-gpu/block-root-transfer/README.md")
#src("S112","发行时的 union 端点证书","benchmarks/pass3-cell-gpu/issuer-union-position/README.md")
#src("S113","反向查找之前的神经字段定位","benchmarks/pass3-cell-gpu/union-location-witness/README.md")
#src("S114","由正向证据恢复的 owner 订阅","benchmarks/pass3-cell-gpu/implicit-owner-subscribers/README.md")
#src("S115","先密封全 Run 在线提案","benchmarks/pass3-cell-gpu/run-proposal-waves/README.md")
#src("S116","验真前的真实私有 Cell","benchmarks/pass3-cell-gpu/speculative-cell-batches/README.md")
#src("S117","预测整波物理分配需求","benchmarks/pass3-cell-gpu/speculative-allocation-policy/README.md")
#src("S118","全 Run 预发行与真实物理激活","benchmarks/pass3-cell-gpu/wave-cell-allocation/README.md")
#src("S119","严格具名的批内共享分配","benchmarks/pass3-cell-gpu/group-named-cells/README.md")
#src("S120","整批具名位置的训练与留出验证","benchmarks/pass3-cell-gpu/batch-allocation-ranking/README.md")
#src("S121","原址发布的 Cell 页宽与存活","benchmarks/pass3-cell-gpu/resident-slab-ablation/README.md")
#src("S122","跨 Run 空槽回用","benchmarks/pass3-cell-gpu/recycled-resident-slabs/README.md")
#src("S123","批量 Cell 的内联 fact 槽","benchmarks/pass3-cell-gpu/inline-fact-lanes/README.md")
#src("S124","不可变页身份与单次领取","benchmarks/pass3-cell-gpu/sealed-lane-claims/README.md")
#src("S125","跨规则共享未发布的同布局 Cell","benchmarks/pass3-cell-gpu/cross-rule-cell-pool/README.md")
#src("S126","整波发行后的物理需求预测","benchmarks/pass3-cell-gpu/wave-demand-policy/README.md")
#src("S127","用真实父端口证明单父候选可省略","benchmarks/pass3-cell-gpu/single-pivot-certificates/README.md")
#src("S128","整波计数与跨规则共享池","benchmarks/pass3-cell-gpu/sealed-wave-shared-pool/README.md")
#src("S129","固定每 Run 布局字节的模型分配","benchmarks/pass3-cell-gpu/wave-budget-routing/README.md")
#src("S130","等待批量验证的紧凑提案页","benchmarks/pass3-cell-gpu/packed-single-waves/README.md")
#src("S131","成功函数行的正见证直传","benchmarks/pass3-cell-gpu/single-scalar-handoff/README.md")
#src("S132","五负载组合执行验收","benchmarks/pass3-cell-gpu/verified-wave-execution/README.md")
#src("S133","构造节点的首次发布与终图留存","benchmarks/pass3-cell-gpu/token-constructor-births/README.md")
#src("S134","真实进程 RSS 的共同水位与兑现时刻","benchmarks/pass3-cell-gpu/verified-wave-rss/README.md")
#src("S135","跨 Run 精确父端口与版本复用","benchmarks/pass3-cell-gpu/single-delta-frontier/README.md")
#src("S136","从后继角色反查候选根","benchmarks/pass3-cell-gpu/reverse-role-frontier/README.md")
#src("S137","多父凭证随实例移交","benchmarks/pass3-cell-gpu/instance-root-handoff/README.md")
#src("S138","integral 根凭证跨 Run 验证","benchmarks/pass3-cell-gpu/integral-root-certificates/README.md")
#src("S139","有效节点与签名、行策略的消融","benchmarks/pass3-cell-gpu/token-yield-policy/README.md")
#src("S140","整组 integral 消费者外部包免发","benchmarks/pass3-cell-gpu/integral-packet-suppression/README.md")
#src("S141","标量负证据与部分 integral 免发","benchmarks/pass3-cell-gpu/integral-filter-joint/README.md")
#src("S142","免发与相同内存水位","benchmarks/pass3-cell-gpu/integral-yield-rss/README.md")
#src("S143","已付费的生产者权限","benchmarks/pass3-cell-gpu/paid-producer-families/README.md")
#src("S144","两次跨 Run 的迭代式证明库","benchmarks/pass3-cell-gpu/iterative-integral-certificates/README.md")
#src("S145","枚举前的单父类别动作","benchmarks/pass3-cell-gpu/causal-single-class/README.md")
#src("S146","按 FEPT 回报训练门控","benchmarks/pass3-cell-gpu/fept-policy/README.md")
#src("S147","独立展开的二父桶动作","benchmarks/pass3-cell-gpu/generative-pair-buckets/README.md")
#src("S148","单父与二父动作联合消融","benchmarks/pass3-cell-gpu/joint-fept-actors/README.md")
#src("S149","公共根跨度与学习键集","benchmarks/pass3-cell-gpu/generative-pair-families/README.md")
#src("S150","宽二父与学习单父联合执行","benchmarks/pass3-cell-gpu/wide-fept-composition/README.md")
#src("S151","相关算术端口的生成","benchmarks/pass3-cell-gpu/compound-family-ports/README.md")
#src("S152","非空复合区域的稀疏目录","benchmarks/pass3-cell-gpu/sparse-family-regions/README.md")
#src("S153","三父及以上根窗口的机会界","benchmarks/pass3-cell-gpu/baked-prefix-window/README.md")
#src("S154","FEPT 完整组合路径与内存水位","benchmarks/pass3-cell-gpu/compound-fept-model/README.md")
#src("S155","纯具名的静态组合与迭代训练","benchmarks/pass3-cell-gpu/explicit-parent-cell-composition/README.md")
#src("S156","显式多输入接线的离线核对","benchmarks/pass3-cell-gpu/strict-composition-opportunities/README.md")
#src("S157","两个实际返回供给一个真实后继","benchmarks/pass3-cell-gpu/strict-dual-return/README.md")
#src("S158","过滤叶模板与显式父静态组合","benchmarks/pass3-cell-gpu/filtered-explicit-parent/README.md")
#src("S159","真实供体局部饱和与历史","benchmarks/pass3-cell-gpu/ripsat-donor-evidence/README.md")
#src("S160","RipSat 到具名静态程序","benchmarks/pass3-cell-gpu/ripsat-strict-programs/README.md")
#src("S161","来源和历史的独立拒绝测试","benchmarks/pass3-cell-gpu/ripsat-strict-acceptance/README.md")
#src("S162","最终证据的四组推理与 RSS","benchmarks/pass3-cell-gpu/ripsat-neural-bake/README.md")
#src("S163","相同供体中间实例的两步授权","benchmarks/pass3-cell-gpu/ripsat-publication-chain/README.md")
#src("S164","按原 Run 消费明确的 Set 发布","benchmarks/pass3-cell-gpu/ripsat-set-receipt/README.md")
#src("S165","两步发布凭证的联合矩阵","benchmarks/pass3-cell-gpu/ripsat-publication-matrix/README.md")
#src("S166","CPU 计算请求与真实私有所有权转移","benchmarks/pass3-cell-gpu/ripsat-higher-cell/README.md")
#src("S167","直接与高阶验证的活跃版本索引","benchmarks/pass3-cell-gpu/ripsat-receipt-locality/README.md")
#v(2mm)
#label[两篇用于构造对照的原始文献]
#v(1.5mm)
#text(size:9pt)[*M1*　Gilmer 等，#emph[Neural Message Passing for Quantum Chemistry]，ICML 2017。#link("https://proceedings.mlr.press/v70/gilmer17a.html")[PMLR 原文]。 *M2*　Foerster 等，#emph[Counterfactual Multi-Agent Policy Gradients]，AAAI 2018。#link("https://arxiv.org/abs/1705.08926")[论文原文]。]
#v(1fr)
#small[版次 31　·　2026 年 11 月 21 日　·　图的 SVG 与生成源码随文档提供，可在修改架构后更新。]
