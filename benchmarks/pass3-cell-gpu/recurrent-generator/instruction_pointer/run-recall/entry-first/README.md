# 从有证据的入口构造 Cell 闭包

**Neural Compilation / 离线**用于构造和强制接管。**Neural Execution / exclusive**使用同一套 B 字段检索和冻结的 CCP v0.1，在 standalone Rust Cell Runtime 独立执行。三臂分别为原 B、使用原 B 权重读取新布局，以及为新布局重训 B 的末级模板选择。每个程序每臂完整执行两次。

## 从已有输入能编出什么

训练目录只用 sum-bits 构造。从已提交根的实际表引用开始，先从 Recipe 契约编译后继，再在训练 tape 上检查哪些可执行。某一步的全部表 atom 都必须能接到已有入口引用或更早步骤的具名端口，且至少一个输入来自上一步。缺少独立证据时停止该方向。自定义 merge 的扩展位置读取真实构造回执。原生调度第一次允许消费时，指定版本仍须成立。repair 通过已发布的事件地址进入，不能从一次普通 Set 推测出一次 repair。五个程序共有 22 个读取 repair 的根提交，此次构建规则未在这些根上找到可执行的两步闭包。[repair 专项](repairs.json)

本轮静态探索每层最多保留 48 个有支持的前缀，最长 8 步，每条规则每个前缀最多展开 16 种类型接线。计有 13,024 次扩展因还需外部表停止，54 次因静态歧义预算停止。1,908 个被检查的扩展中有 159 个在训练轨迹有支持。按新增覆盖的具名绑定选出 48 个，每个都在至少一次原生完整重放中实际取代了后继请求。最终有 42 个两步、3 个三步、3 个四步布局。本轮只探索逐发布组的连接链；同组并行、更多独立入口和超过预算的接线仍可由原 B 的普通生成路径处理。[构建计数和逐模板实证](construction.json)

对照使用相同训练程序、原生端口描述、最大深度和 48 项选择预算，按 trace-first 枚举连通子图，允许额外入口绑定。排序扣除额外绑定并对已覆盖的内部提交去重。26,512 个发现的子图中 4,828 个在训练记录上就绪。两个构建器访问的候选总体不同，选后按同一项数比较。

| 48 项目录 | 内部加根的总步骤 | 外部具名槽总数 | 根以外仍需绑定的外部槽 | 在 fact / loopfact / sum-divisors 出现就绪实例的模板数 |
|---|---:|---:|---:|---:|
| trace-first | 188 | 202 | 91 | 27 / 33 / 47 |
| entry-first | 105 | 153 | 0 | 24 / 29 / 48 |

具名槽按端口角色计数，同一实例的两个不同端口可以占两个槽。已支持模板在某个程序有合法入口，只能证明至少有一个可执行实例。将工作负载换成 dot-product，两个目录的就绪模板分别为 33 和 29。[目录和汇总](summary.json)

## 373 个阻塞模板

在原目录上重建 sum-bits 和 dot-product 的全部已记录出现。每次出现依次检查入口外部引用、发布与调度、内部回执的身份和版本，记录首先失败的义务。同一模板可以在不同实例上遇到不同阻塞，按其最常见类别归组。363 个模板主要遇到晚到的外部回执，9 个主要遇到内部版本变化，1 个主要遇到不同的实际内部 witness。全部 2,192 次出现分别有 2,037 次晚到、135 次内部版本变化、16 次内部 witness 不同、4 次入口版本不同。逐项记录附有可回查的程序和根 token。[373 项审计](373.json)

## 已知合法入口时能接管多少

先对所有已观察可行实例的内部 teacher 提交取并集，给出所选目录在这些证明上的宽松上限；再按可省父角色数做非重叠贪心打包，直接删除这些 teacher 子请求，由原生图执行入口派发。每个程序整段重放均核对调度、写入、RHS、恢复、repair 事件及终图 SHA。两种目录都通过。覆盖多少个提交与创造多少个新的派生事实口径不同。下表的绑定数是省去的子步骤具名操作数，已扣除新增的入口绑定。

| 程序 | entry 内部提交并集上限 | 实际少发的外层请求，trace / entry | 净替代的具名绑定，trace / entry |
|---|---:|---:|---:|
| fact | 287 | 313 / 182 | 412 / 267 |
| loopfact | 278 | 330 / 171 | 456 / 274 |
| sum-divisors | 3,401 | 3,549 / 2,131 | 4,717 / 3,020 |

表中实际接管来自原生具名图接口。内部原子步骤都照常执行，原生按 Run 批量提交的同步节省为零。独立 CCP 对照对每个下放步骤继续付费。各程序两种目录均保留逐实例打包清单与原生回执。[entry 接管](entry) · [trace 接管](trace)

另在上述实际接管的后继上，给定其真实 delta 事件，在同一 teacher 快照执行 B 的父检索两次，分别启用和关闭已核验绑定跳过。每个规则扣除已完成元组后的签发序列做摘要核对。entry 在 fact、loopfact、sum-divisors 上实际少访问 106、138、1,245 个候选位置，分别少形成 210、212、2,534 份 B 提案。相应 posting 探测的保守计数上界是 411、553、7,228，另计已完成位置的索引和检查。地址访问的毛节省不能直接抵扣这部分工作。在同一冻结状态下，另沿每个已核验目标的具名路径执行 B 的真实 LSH 窗口及逐层网络打分，计量到达末层的次数和原本会签发的次数。B 的每个前缀独立打分，因此无关兄弟不会改变该具名路径的分数。这项边际计量在全部三个 entry 组与两个 trace 组逐项吻合完整双跑。trace 的三组分别少访问 233、290、3,064 个末层候选，少形成 363、394、4,264 份 B 提案。trace 的 sum-divisors 全域双跑在单个高扇出 Run 花费数分钟，本报告只采用全部目标的路径边际实测，未给出该组完整扫描总量。这里的输入来自 teacher，未作为独立运行的候选过滤器。

## 网络自主执行

B 先从发布事件生成规则和角色，在父指针搜索之前，同一个共享打分函数在 primitive 与该入口家族的 Bake 布局之间选择终端动作。选中布局后，根的实际绑定和原生接受仍是内部计算启动条件。后续只能读取静态接线指定的版本。每个源 Run 仅用已获接受的具名元组跳过重复；其余候选保留。重复提案、内部付费步骤、同步和识别成本全部计入原口径。

父检索和 B 的原模板树固定。对 B 末级共享打分器进行 16 轮增量训练，输入为发布事件向量、根和后继的结构特征及内部接线规模。每个选项在运行时实际打分；没有为每个模板配置独立签发器。仅使用 sum-bits 的训练事件，11 个布局从末级训练监督中留出，dot-product 单列评估。沿用的历史 B 曾使用 loopfact 训练，三个 EggCC 程序也已参与过往开发。这里评估本轮目录和末级模型的迁移。[训练](training.json) · [留出布局](unseen.json)

| 程序和指标 | 原 B | 新目录，冻结 B 权重 | 新目录，重训 B 末级 |
|---|---:|---:|---:|
| fact，参考派生事实 / 1,120 | 764 | 768 | 766 |
| 候选访问 / CCP 请求 | 6,959,377 / 297,736 | 7,036,096 / 298,458 | 7,019,351 / 298,266 |
| EPT / EPS 两次 | .003674 / 94.4、78.3 | .003686 / 83.2、83.3 | .003678 / 80.6、83.6 |
| loopfact，参考派生事实 / 1,112 | 944 | 946 | 946 |
| 候选访问 / CCP 请求 | 4,950,439 / 263,560 | 3,979,622 / 265,611 | 3,979,746 / 265,615 |
| EPT / EPS 两次 | .004310 / 107.3、87.8 | .004288 / 93.8、52.7 | .004288 / 97.8、89.2 |
| sum-divisors，参考派生事实 / 8,018 | 3,085 | 3,088 | 3,085 |
| 候选访问 / CCP 请求 | 89,399,870 / 4,930,837 | 118,489,910 / 4,915,431 | 89,399,840 / 4,930,999 |
| EPT / EPS 两次 | .000876 / 36.2、32.2 | .000880 / 25.2、24.8 | .000876 / 29.4、32.5 |

sum-divisors 重训与原 B 的完整终图 SHA 相同。重训少访问 30 个候选，却增加 162 个付费请求、210 次同步和 584,015 次末级选项打分。签名有效操作均为 4,321。loopfact 的冻结与重训组也得到相同终图，重训比冻结多访问 124 个候选，多付费 4 次。与原 B 比较时轨迹发生了变化，不能把约 97 万的访问差异全算作静态跳过。两次测量各臂非计时工作计数逐项一致，测量期间存在其他任务负载，不能支持墙钟加速结论。[完整逐次记录](independent)

留出布局也解释了局部监督的局限。在 sum-divisors 已知存在可用留出布局的 639 个事件上下文中，冻结打分选中可用留出布局 458 次，重训降到 153 次。dot-product 上总体兼容选择由 527 / 1,958 提高到 1,367 / 1,958，其中实际选中有用布局由 495 降到 135。训练中，对 tape 上没有观察到合适闭包的事件给 primitive 标签；漏记的替代证明可能影响这些标签。当前监督提高了选择普通 primitive 的倾向。它没有证明共享末级能识别更高收益的抽象。

## 复现

在 instruction_pointer 下运行。ROOT 保存各原编译程序、M0 tape、capture 与 memory 导出，DATA 指向原 B 独立执行工作区，BIN 指向使用 cell-token-ept 特性构建的 cell_token_replay。独立实验使用单线程 CPU 推理。两次配对的臂序相反。

```sh
OLD=run-recall/parameterized-deep-ripsat/catalog.json
mkdir -p "$OUT"
python entry_obligations.py "$ROOT" "$OLD" "$ROOT/receipt-bake/catalog.json" run-recall/receipt-bake/slots.csv "$OUT/373.json"
python entry_closure.py "$ROOT" "$BIN" "$OUT"
python entry_ceiling.py "$ROOT" "$BIN" "$OUT" sum dot fact loopfact sum-divisors
python entry_trace_control.py "$ROOT" "$BIN" "$OUT"
python entry_repair_probe.py "$ROOT" "$BIN" "$OUT/repairs.json" sum dot fact loopfact sum-divisors
for directory in "$OUT" "$OUT/trace-control"; do
  cases="fact loopfact"
  if [ "$directory" = "$OUT" ]; then cases="$cases sum-divisors"; fi
  python entry_search_probe.py "$DATA" "$ROOT" "$directory" $cases
  python entry_marginal.py "$DATA" "$ROOT" "$directory" fact loopfact sum-divisors
done
python entry_model.py "$DATA" "$ROOT" "$OUT"
python entry_unseen.py "$DATA" "$ROOT" "$OUT"
python deep_event_rollout.py "$DATA" "$OUT" fact loopfact sum-divisors --arms 0 --reps 1 --offset 50
for name in fact loopfact sum-divisors; do
  python entry_rollout.py "$DATA" "$OUT" "$name" frozen trained --rep 0
  python entry_rollout.py "$DATA" "$OUT" "$name" trained frozen B --rep 1
done
python entry_results.py "$OUT" /path/to/report
```

Cargo 的 sum-bits compile、run、bench 均通过；既有导出的 choice_diagnosis 语义验收为 pass。Python 65 项测试通过。基准主体为仓库的 standalone Rust Cell Runtime。
