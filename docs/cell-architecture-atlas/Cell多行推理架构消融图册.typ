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
  footer: context grid(columns: (1fr,auto), text(7.4pt, fill:muted)[2026.11.20   ·   实验设计与证据], text(8pt,fill:teal)[#counter(page).display("1")]))
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
#align(center,image("figures/00-overview.svg",width:92%))
#v(1mm)
#small[图 00　现行 PyTorch 路径。离线计划提供编译器确定的端口接线；make 预测绑定，finish 直接读取 GPU 上的 Pair。独立 CPU 审计在设备输出完成后核对来源与整图覆盖。]
#v(2mm)
#grid(columns:(1fr,1fr),gutter:9mm,
  card([研究问题],[同一张图的多个 row 能否同时生成不同的合法绑定，保留正确的跨行引用，并让下一 Run 直接使用这些结果？]),
  card([证据起点],[开放父引用时，静态投影加训练期字段头在两个种子下通过 65、67 张非空碰撞图，共 512 张。这个基线给分工留下了很大的改进空间。]))
#v(1fr)
#linebar()
#small[代码基线 68193237　·　图 01–16 已测模板表示、生成、协调与所有权转移。图 17–19 已测组合证明、私有接续与停止条件，图 20 检查模板等价类，21–37 涵盖真实负载与块级上限。图 38–55 含后续实测和待验证设计，见第 41 页。]

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
    kicker[讨论回顾   /   图 38–55 的实验动机]
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
    small[本节数字来自既有实验 S8、S10、S12、S24、S28–S30。图 38–40、46、55 已有实测，其余待测图单列。]
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
#v(5mm)
#linebar()
#label[两篇用于构造对照的原始文献]
#v(1.5mm)
#text(size:9pt)[*M1*　Gilmer 等，#emph[Neural Message Passing for Quantum Chemistry]，ICML 2017。#link("https://proceedings.mlr.press/v70/gilmer17a.html")[PMLR 原文]。 *M2*　Foerster 等，#emph[Counterfactual Multi-Agent Policy Gradients]，AAAI 2018。#link("https://arxiv.org/abs/1705.08926")[论文原文]。]
#v(1fr)
#small[版次 20　·　2026 年 11 月 20 日　·　图的 SVG 与生成源码随文档提供，可在修改架构后更新。]
