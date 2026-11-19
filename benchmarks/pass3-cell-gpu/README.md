# 从真实 Pass 3 的初始 e-graph 到可读的 Cell

图 23–29 已补齐逐 Run 的 RHS、写入、Spine 与严格终图，并测量正式端到端时间。[已验收架构、全部对照及复现入口](ACCEPTANCE.md)

## 图 21　什么信息必须写进输入？

一个已序列化的 e-graph 有两种不同的可寻址对象。**事实地址**是某个有序算子的物理成员（实例、成员号、端口）；**类地址**是一个有 sort 的等价类。向网络交付的输入包保留二者及其投影。原导出如果只有一个类地址，编码器就记录它能观察到的这条关系。历史推导中究竟选了哪个父，需要推导发生时另存见证。

一次真实例子是 `DUMMYCTX` 和 `InFunc("DUMMY")` 的结果都指向 `Assumption / Value(48)`。编码中这两行分别位于实例 36 和 39 的成员 0。网络可以读取任意指定成员；询问这个类有哪些来源时，正确结果包含两行。如果读者只拿到了 `Value(48)`，凭它挑任意一行来充当历史绑定就会伪造来源。

- 离线编码器按有序、带类型的构造器签名建立模板。当前的双成员布局只使用本快照中来源唯一的一条有向边；按形状出现次数安排无重叠的配对，其余事实使用单成员模板。例如 `u=Get(x,i); v=Single(u)` 可以共享一个模板，第二个成员的输入读第一个成员的结果类。多个外部记录仍可引用它。若另一个算子也产生 u，这条内部连线就不能据此唯一推导，编码会保留显式边界参数。每个模板声明自己的算子、列顺序和槽投影，每个实例只带模板号、参数绑定与可见性。单独保存导入次序优先级，以复现源实现对输入类的排序。这里是离线识别的初图布局，尚未将迭代 Bake 学得的任意深度模板用作通用输入语法。[编码实现](codec.py)
- 设备接受编好的整数指令、符号值、模板和实例描述符。实验用图 03 冻结的 packed 地址头从实际打乱顺序的实例库取描述符，再用共享端口头选择有序输入、结果或缺失位置。端口头只在合成的槽位声明上训练，物理位置与角色选择的合法性在 GPU 检查，错误会中止。语义内容沿所选引用实际读取。设备侧的等价类更新改变当前类投影，原始成员地址保持有效。此实验检验了网络寻址和读取的接口；规则查询的完整枚举由精确 GPU 代码承担。[端口头](ports.py) · [独立读取探针](reader.py)
- 在线进程只接收 `device.json` 和校验和绑定的 `device.npz`、冻结权重、容量预算与调度参数。原图、参考绑定和 CPU 快照只进入离线编译或事后验证进程。GPU 查询与构造查找直接解引用初始 Cell 的模板和实例参数，新增事实单独存储。[静态 lowering](lower.py) · [在线入口](run.py) · [Metal 执行](executor.metal)

| 检查 | sum-bits | dot-product |
| --- | ---: | ---: |
| 冻结初图：事实／有序参数 | 129／145 | 129／145 |
| 单成员 → 双成员布局的实例数 | 129 → 89 | 129 → 89 |
| 双成员布局中的共享模板／双成员实例 | 46／40 | 46／40 |
| 初始化后的实际事实／有序参数 | 223／342 | 320／583 |
| 分别重编码上述不同图，全部端口与事实正确 | 是 | 是 |

两个原始初图逐行完全相同；工作负载差异主要由初始化规则引入。单成员／双成员布局与精确／学习读取的四个组合均通过前 3 个实际 Run 的有序 RHS、有效函数写入、调度和全部序列化事实比对，这三步没有正 Spine 接续。第一个 Run 的 LHS 为空，所以还核对了随后真正读取绑定的 type-helpers。额外的跨图读取试验撤掉原图、打乱实例库位置、查询每个位置、结果及不存在的端口，并施加一个受控的同 sort union。在两个不同的初始化后图上，分别有 3、10 处解析结果改变，旧地址和原始字段保持逐项一致。这个合并是受控反例；该试验的重编码包没有进入正式 Pass 3。[四臂及首轮证据](results/ingress-and-pass3.json) · [不同图的独立验证](results/distinct-graphs.json)

## 图 22　初次集成记录

当前收敛方案采用共享模板／实例端口、packed 寻址、由实际绑定投影 RHS、基于已编译规则和原调度的精确枚举与关闭。全局闭包由设备程序计数器和变更 epoch 驱动。两个 row 从同一个 Run 的冻结图读取不重叠的入口见证范围，在 GPU 独立生成完整绑定 token，再按规则和输入排序去重，依原顺序提交。分工规则是确定的：首个关系原子的物理行号决定其负责的 row。这里观测到的是**两个设备 row 生成互补绑定**；尚未验证训练得到的自主多行策略能够覆盖全程序。

| 完整设备试跑 | sum-bits | dot-product |
| --- | ---: | ---: |
| GPU／Rust Cell CPU 的实际 Run 数 | 1,428／1,428 | 1,536／1,535 |
| 两个 row 各自提交的不同绑定 token | 3,747＋3,518 | 3,565＋3,138 |
| 一行与两行的有序绑定、写入日志和设备终图 | 相同 | 相同 |
| GPU／CPU 终态事实数 | 4,045／4,045 | 4,257／4,257 |
| 映射后多出／缺少的事实行 | 2／2 | 4／4 |
| 第一处有效写入数不同的 Run | 122 | 165 |
| 第一处必须接续的 Run | 9 | 11 |
| GPU／CPU 的正 Spine 接续总数 | 0／2,098 | 0／1,835 |

两负载行间重复 token 均为零。两种行数走完设备调度的结果相同；与源执行的差异都涉及 `Smaller` 和 `CellSpineView9`。dot-product 在第 898 Run 的绑定数已有差异，在第 1000 Run 的变更标志不同。源接续引用、根、生产者、消费者和深度尚未进入这个设备路径；当前完成该类工作靠通用关系查询。前 15 Run 的完整快照另行比对，不能用它们代替其后所有 Run 的有序验收。

两个实际案件从 `workloads/pass3` 经 Rust 离线 Bake，初始化作用域内的字段、所有键的参数位置、类型与 subsume 位均进入比对。终图比对固定原始类锚点，通过有序构造器键建立同 sort 双射，再对比完整事实多重集。执行器保留未满验收条件的计时原始样本；在差异解决前不将其作为等正确性吞吐结论。图 22 的原始版本容量固定，对不支持的操作和溢出显式失败。[终态审计](endpoint.py) · [逐 Run 前缀审计](audit.py)

## 在外接盘工作树复现

```sh
base=benchmarks/pass3-cell-gpu
root=/Volumes/EggFuseWorkspace/experiments/NEW-pass3
weights=/Volumes/EggFuseWorkspace/experiments/rotary-axes-20261119/packed-1703/final.pt
runner=/Volumes/EggFuseWorkspace/bin/run-eggfuse
q() { ~/.local/bin/eggfuse-job submit --kind compute -- "$runner" "$@"; }
q env PYTORCH_ENABLE_MPS_FALLBACK=0 python "$base/ports.py" "$root/ports-1703.pt"
for n in sum-bits dot-product; do
  q cargo cell-compile --case "$n" --output "$root/$n"
  q python "$base/codec.py" "$root/$n/program.json" "$root/input-$n"
  q python "$base/lower.py" "$root/input-$n/ingress.json"
  for rows in 1 2; do
    q env PYTORCH_ENABLE_MPS_FALLBACK=0 python "$base/run.py" "$root/input-$n/device.json" "$weights" "$root/final-$n-$rows" --port-weights "$root/ports-1703.pt" --rows "$rows" --runs 2000 --no-spine --union immediate --directory canonical --lookup scan --tiles 1 --arena private
  done
  q cargo run --release --locked -p eggfuse-cell-runtime --features slot-transfer-audit -- --program "$root/$n/program.json" --output "$root/oracle-$n" --audit-stages
  q python "$base/endpoint.py" "$root/input-$n/ingress.json" "$root/final-$n-2" "$root/oracle-$n" "$root/final-$n-2/check.json"
done
```

输入消融使用 `codec.py --singletons` 和 `run.py --reader exact`；前缀核验使用 `--runs 3 --capture-prefix`，再将程序、输入包、GPU 输出和独立 oracle 交给 `audit.py`。神经端与精确端均有相同的源语义验收。
