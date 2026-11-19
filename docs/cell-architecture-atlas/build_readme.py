"""Build the browser-readable edition from the same plate descriptions as Typst."""
from pathlib import Path
import json

ROOT=Path(__file__).parent
panels=json.loads((ROOT/'plates.json').read_text())
out=["# Cell 多行推理架构消融图册",
     "[排版 PDF](Cell多行推理架构消融图册.pdf) · [Typst 源文件](Cell多行推理架构消融图册.typ) · [独立矢量图](figures/) · [绘图源码](draw.py)",
     "基线提交 `68193237`，2026-11-20。阅读重点是同图多个 row 能否快速生成互补 token。每次 Run、一次神经发射和一个训练更新是三个不同的时间单位。实线表示数据流，紫色虚线表示训练监督，灰色空槽或 × 表示未启用或被屏蔽的通道。每个分面的小写字母和图下说明对应。",
     "![当前的离线编译、GPU 前向与 CPU 审计](figures/00-overview.svg)",
     "![候选的模板端口 GNN、共享 row 策略和训练奖励](figures/00-proposal.svg)",
     "建议先用编译器端口角色做基线，检验跨规则共享和单 row 的绝对正确性；然后冻结权重展开到多行，测零样本覆盖损失；最后才比较监督、RL、动态启用行数与同步策略。图 01–02 已完成两叶 Bake 接口的单 row 对照；03 已比较四种多端口寻址，04 已测单行零更新展开，05 已比较监督与 RL 分工，06 已测行门控和物理跳算，07 已测全局屏障和局部就绪，08–13 给出已有机制的对照，14 已测两个局部状态与带版本的跨域回复，15 已测延迟 union 与构造器修复，16 已测双行接管与旧端口转发，17 已测原子与组合证明，18 已测 integral 退出和分配曲线，19 已测预算、停止证据和检查点恢复，图 20 单列静态可证明端口等价分区。图 21–22 记录真实 Pass 3 输入读取的通过项和整图差异。",
     "## 本轮架构取舍",
     "同图多行执行时，直接训练目标宽度的集合监督比两个 RL 对照更稳定（图 04–05）。来源地址、等价判断和成员版本需要各自核验（图 03、14–17、20）。局部就绪与 integral 能把计算提前，验收要追踪结果是否按原槽发布（图 07、18）。声明饱和时仍须检查在途消息、待办和未发布的变化（图 19）。这些结论来自各自的配对原型；生产 eggcc 全流程、多 GPU 扩展和它们的组合吞吐仍需独立测量。",
     "## 对照索引",
     "| 图 | 实验问题 | 状态 |\n|---:|---|---|\n"+"\n".join(f"| {i:02} | [{p['title']}](#a{i:02}) | {p['status']} |" for i,p in enumerate(panels,1))]
for i,p in enumerate(panels,1):
    out.extend([f'<a id="a{i:02}"></a>\n\n## 图 {i:02}　{p["title"]}',
                f'**{p["status"]}。** {p["q"]}',
                f'![{p["title"]}](figures/{p["id"]}.svg)',p['arms'],
                f'**固定条件。** {p["fix"]}',f'**判据与读数。** {p["measure"]}',f'{p["note"]}　档案 {p["src"]}。'])
out.extend(["## 现有配对数据", "![冻结检查点的第二 Run 完整非空图数](figures/00-results.svg)",
            "横轴是通过数，两个种子均以 512 张碰撞图为分母。应同时检查整图正确、合法引用、重复和遗漏。运行时报告等正确性下的延迟和每秒正确非空图；数据按源码家族、模板接线和随机种子冻结。完整实验登记与反证条件见 PDF 倒数第二页。",
            "## 证据与图源",
            "\n".join(f"- {k}　[{title}]({url})" for k,title,url in [
                ('S1','PyTorch 实现与计时','../../benchmarks/multi-row-generation/torch_crossrun/README.md'),
                ('S2','真实两规则与掩码统计','../../benchmarks/multi-row-generation/crossrun/results/metrics.tsv'),
                ('S3','无锚点集合生成','../../benchmarks/multi-row-generation/allocation/README.md'),
                ('S4','软覆盖监督','../../benchmarks/multi-row-generation/coverage/README.md'),
                ('S5','分轮历史干预','../../benchmarks/multi-row-generation/streaming/README.md'),
                ('S6','12 轮连续与符号接口','../../benchmarks/multi-row-generation/typed/README.md'),
                ('S7','确定性 Cell 机制','../../benchmarks/multi-row-cell/README.md'),
                ('S8','额外 eggcc 工作负载和家族拆分','../../benchmarks/eggcc-diversity/manifest.json'),
                ('S9','长期架构与源语义契约','../MULTI_ROW_EGRAPH_NEURAL_PLAN.zh.md'),
                ('S10','单 row 的头共享与 Bake 编码实测','../../benchmarks/multi-row-generation/port_ablation/README.md'),
                ('S11','模板局部等价类的证据与冻结协议','template-eclass.md'),
                ('S12','图 20 四臂两种子实测','../../benchmarks/multi-row-generation/eclass_ablation/README.md'),
                ('S13','跨 row/位置/端口寻址及真实前沿迁移','../../benchmarks/multi-row-generation/address_ablation/README.md'),
                ('S14','图 04 单 row 零训练展开与消费者诊断','../../benchmarks/multi-row-generation/width_ablation/README.md'),
                ('S15','图 05 两行监督、团队奖励与反事实信用','../../benchmarks/multi-row-generation/credit_ablation/README.md'),
                ('S16','图 06 实际 GPU 行门控与执行计数','../../benchmarks/multi-row-generation/gate_ablation/README.md'),
                ('S17','图 07 精确与学习型就绪调度、逐 Run 审计','../../benchmarks/multi-row-generation/readiness_ablation/README.md'),
                ('S18','图 14 全图状态、局部状态与边界证书','../../benchmarks/multi-row-generation/locality_ablation/README.md'),
                ('S19','图 15 延迟 union、同余修复和空结果失效','../../benchmarks/multi-row-generation/union_ablation/README.md'),
                ('S20','图 16 双行组合、旧 cursor 与 generation','../../benchmarks/multi-row-generation/ownership_ablation/README.md'),
                ('S21','图 17 原子证明与组合宏的验证成本','../../benchmarks/multi-row-generation/proof_ablation/README.md'),
                ('S22','图 18 私有成员原槽发布与退出条件','../../benchmarks/multi-row-generation/integral_ablation/README.md'),
                ('S23','图 19 精确停止、学习门与检查点恢复','../../benchmarks/multi-row-generation/stopping_ablation/README.md'),
                ('S24','真实 Pass 3 输入编码与多行集成','../../benchmarks/pass3-cell-gpu/README.md'),
                ('M1','Gilmer 等，ICML 2017，消息传递神经网络','https://proceedings.mlr.press/v70/gilmer17a.html'),
                ('M2','Foerster 等，AAAI 2018，反事实多智能体信用分配','https://arxiv.org/abs/1705.08926')]),
            "## 重新生成",
            "在本目录运行以下命令。SVG 保留可编辑文本及矢量连线；Typst 排版和 Markdown 使用同一份 `plates.json`。参考渲染使用 macOS 的 Hiragino Sans GB 与 Songti SC。",
            "```sh\npython3 draw.py\npython3 build_readme.py\npython3 verify_evidence.py\ntypst compile Cell多行推理架构消融图册.typ\n```"])
(ROOT/'README.md').write_text('\n\n'.join(out)+'\n')
