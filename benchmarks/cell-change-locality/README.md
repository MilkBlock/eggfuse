# Cell 变化局部性：Get / Expr-size 的实际传播

基线：`991896e8`。对象是 **standalone Cell CPU**，不是 native egglog。
本轮只增加现有 `slot-transfer-audit` 功能下的离线诊断；普通构建不包含
采集代码。没有新增优化接管，没有速度或全局稀疏性结论。

## 为什么检查这条关系

上一份完整执行的 `Expr-size` 规则族占约 46.81% 的查询计时。单独的
Get 规则有 957,754 次成功匹配、250,442 次实际函数更新。仅统计结果
未变，不能判断此前的匹配、发布或接续是否冗余。

本轮先全程按规则、Run 汇总实际成功实例和已提交属性变化，再选
14 个窗口观察输入证据。窗口覆盖早期传播、已有 Entry 的重新进入，
以及 Get 匹配最密集的 Run 10406–10452。它们是热点定向样本，不能
当作全图随机样本；窗口中的 Get 匹配约占全程的 5.70%。

采集沿用实际 Cell 实例，不重新执行查询：

- 查询前记录原规则增量水位；赢家确定后记录真实输入槽、源 ordinal
  和直接接续 token 是否存在。
- 在现有实际写入审计处记录 old/new、目标 key、源规则和 ordinal。
  repair 的写入单独标记，不能算作逻辑匹配的提交。
- 只在选定 Run 的前后读取表快照，记录当前值、见证、epoch 和可见性。
  普通执行始终不启用 `Executor.audit`。

## 结果

完整 census 再次得到 Get 的 **957,754 次匹配 / 250,442 次实际更新**，
发生在 1,637 个 Run；仅 2,971 个成功实例持有直接接续 token。
这个 token 计数不是“所有 Cell 覆盖率”，更不是并行覆盖率。

选定窗口的 Get 情况：

| 实际观察 | 次数 |
|---|---:|
| 成功匹配 | 54,587 |
| 实际函数更新 | 13,471 |
| 被 min 吸收的写入 | 41,116 |
| Run 开始前的值就足以吸收 | 41,106 |
| 被本 Run 较早 RHS 吸收 | 10 |
| 只有属性行是增量输入 | 53,121 |
| 只有构造子行是增量输入 | 1,411 |
| 两者都是增量输入 | 55 |
| 没有增量输入 | 0 |

按构造子见证比较这些窗口中再次出现的实例，46,349 次保持构造子字段
不变但属性值改变，16 次构造子字段改变；没有“输入值和 epoch 全部相同”
的重复。另有 8,222 次是首次观察。未采样的中间 Run 不作推断。

因此，普通的“上次匹配完成”缓存不能直接消掉这批工作。min 的吸收关系
才是尚未被 Cell 状态充分表达的候选信息。

每个新 `Expr-size` 行在当前 Run 触发的 Get 使用数：

| 分母 | 中位数 | P95 | P99 | 最大值 |
|---|---:|---:|---:|---:|
| 全部 60,967 个新属性行出现 | 0 | 2 | 12 | 22 |
| 确实有 Get 使用的 28,064 个行出现 | 1 | 4 | 15 | 22 |

这里统计的是行在 Run 中的出现，不是全程独立节点数。离线检查还枚举了
快照中每个新属性行的全部可见 Get 邻居，要求数量与实际匹配严格相等，
所以该扇出不是只采到了某条查询快路。其他运算符、失败查询和跨多轮的
传递闭包不在这个扇出结论内。

在 28,064 个有使用者的组中，**19,897 组的所有 Get 输出在 Run 开始前
就足以吸收本次输入值**，涉及 31,155 次匹配。当前分析是事后读取输出
得到这个事实，不能把这 31,155 次直接计作运行时可省工作。

## 下一项接管应证明什么

当前证据支持“Get 的单步影响范围较小，但多轮标量传播反复被吸收”，
不支持“egraph 内部必然稠密”。也没有证明整个系统能达到 2×。

可由 Bake 尝试编译的是带标量范围条件的完成状态。例如静态 Cell 内：

```text
Expr-size(a) = x
Get(a, i1) -> u1; Expr-size(u1) <= T
Get(a, i2) -> u2; Expr-size(u2) <= T
...
x >= T  =>  这些 min 写入都不改变结果
```

在输出只允许 min 改进、成员和事实仍有效的区间内，旧上界 T 可以继续
有效，无须因为每次输出变小而重新维护它。结构 domination 负责这些
内部连接；标量条件负责判断本次变化是否仍被已完成状态吸收。

但这个状态还没有实现，以下义务仍然活着：

1. 从同一 Cell 定义证明 min、类型、纯效果及静态内部成员，不能从本次
   扫描得到的消费者列表另建运行时反向关系。
2. 证明或检查删除、重建、可见性、实际返回见证和 Eq 变化的有效性。
   新的外部消费者保持完整残余枚举，不能借旧组证书排除。
3. 原 Run 的时序继续生效。写入无变化不等于其发布责任、最后来源选择
   或后续接续可以丢掉；必须由原有实例/Entry 承接这些责任。
4. 计入取得上界、校验、状态保存及边界成本。只有实际删掉查询、绑定、
   RHS 或发布后才能给 Bake 记信用；本诊断一律不记优化收益。

相比继续压缩输入布局，下一轮优先验证这一类**吸收条件能否在展开前
成立，并由现有 Cell 状态保留**。若取得证据本身仍需逐个查输出，或者
发布责任没有更便宜的承接方式，就应拒绝该实现。

## 验证与范围

- 全程 census 与保存的普通 Raytrace 对照有相同完整状态 SHA-256、全部
  16,883 个 Run 记录、实际图操作计数及 2,584,660 次查询。
- 窗口观察与本提交的关闭观察对照，在 Run 10452 的完整状态、全部已执行
  Run 记录、图操作和查询数完全相同。14 个窗口的有序输入、实际写入、
  resume 摘要全部相同；窗口计数还逐项对上全程 census。
- 离线逐条验证可见输入、窄范围的纯标量 RHS、源顺序下的旧值和 min
  更新。8 个无 union 的窗口额外重放完整属性后状态；另外 6 个窗口
  不把最终 canonical ID 当作源时刻 ID，repair 另计。
- 这不是新的 Raytrace native 等价性证明。sum-bits 复用保存的导出，
  原 `choice_diagnosis.py` 验收通过，证明规则没有扩大。
- 97 个运行时单元测试、8 个离线正反例检查、无默认功能的审计编译通过。
  README 的 compile/run/bench（repeat 1）仅作命令冒烟，不作测速。

## 复现

`PROGRAM` 使用 cell-fixed-reads 的冻结 Raytrace 产物；`REFERENCE` 是
cell-publication-windows 的普通串行 Raytrace 导出目录，均由结果文件
记录摘要。输出目录必须新建。需要系统 `gzip`。

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,slot-transfer-audit --example cell_change_windows
BIN=target/release/examples/cell_change_windows
cp "$BIN" ROOT/observer
$BIN PROGRAM benchmarks/cell-change-locality/windows.json ROOT/census census
$BIN PROGRAM benchmarks/cell-change-locality/windows.json ROOT/observed observe
$BIN PROGRAM benchmarks/cell-change-locality/windows.json ROOT/control control
python3 benchmarks/cell-change-locality/collect.py ROOT PROGRAM REFERENCE RESULTS.json
python3 -m unittest discover -s benchmarks/cell-change-locality -p 'test_*.py'
```

原始快照和全程报告保留在忽略目录 `out/cell-change-locality`。只提交
诊断源、窗口选择和可核查的文本结果。采集时的耗时不用于任何性能结论。
