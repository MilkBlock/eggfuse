# 从实际 trace 选择跨阶段局部闭包

## 结论

优先实现以实际 `Get(x,i)=g` Entry 为入口的完成模板，覆盖规则
`58、143、137` 的内部匹配和交接。不要先为每个 `drop/context` 生产者
分配历史对象。两个不同生产者的实际后缀具有相同入口和内部操作，应该
共用一个模板；生产者原本的其他效果不属于这个模板。

证据来自已保存的 standalone Cell runtime trace：4,920 个完成事件，
零 archive 容量丢弃，117 个父链缺口被保留。全部 1,428 个 Run 的图和
有序效果校验已经通过。本次只做离线分析，没有重新执行 workload。

| 生产者 | 阶段转换 | 完整分叉实例 | 候选消费者逻辑执行 | 已有 137 直达计划 |
| --- | --- | ---: | ---: | ---: |
| 340：DropAtInternal/Get | drop → always-run | 45 | 135 | 45 |
| 324：AddContext/Get | context → always-run | 27 | 81 | 27 |

每个实例都是实际同一父事件及同一发布 witness 上的两个子分支，不是用
规则的边际频率拼出来的关系。消费者执行数是 72 × 3 = 216，不是已节省
工作、实例分配数或已提交 mutation 数。当前目录已为这 72 个规则 137
事件提供直达计划；其 RHS 复用不能再算新收益。下一步真正要删除的是
匹配、绑定、赢家整理及模板内部交接。

## 共同的完成程序

```text
合法阶段中的可见 Get(x,i)=g Entry
 ├─ 58：Add-Gets(x,x,0)
 └─ 143：s=Single(g), t=SubTuple(x,i,1), union(s,t)
            └─ 后续 Run 的 137：Get(x,i), Single(g)=t
```

58 和 143 在全部 72 个实例中位于同一个 source Run。顺序仍由原规则调度
决定；不能把分叉解释成可任意交换的效果。143 的 union 必须等原 source
Run 完成后才成为后续证明的事实。137 在这些实例中晚三个 Run，不能提前
发布；“三个”只是本次轨迹中的 ordinal 差，不应硬编码进模板。

现有 typed cross-Run 证明逐实例确认：

- 58：`internal_completion`，新增一个符号构造子事实，没有额外入口条件。
- 143：`internal_completion`，新增两个符号构造子事实及一个有序 union。
- 137：`saturated`，没有新增符号事实或未完成 union。

符号事实不意味着一定分配新节点；运行时仍可能复用已有构造子。137 的
逻辑效果已成立，不意味着其当前 publication/delta 元数据可以直接删除。
新完成程序必须承担仍有意义的对外发布及原阶段归属。

## 边界不能吃掉

这是相对于选定规则区域的局部闭包，不是整个 egraph 的饱和证书。

- 340 的 45 个实例中，还观察到 11 次规则 145 消费 SubTuple。
  145 依赖 `tuple-length` 条件，应保留边界查询。
- 该组还观察到 2 次规则 61 消费 Add-Gets；它还要求
  `Not-Just-Concat`，不能凭此闭包补全外部前提。
- 324 的选中实例中有 5 次规则 317 的 context 分支，属于外部工作。
- 某事件没有记录到子节点，不证明没有其他消费者或未来匹配。

所以需要导出 Get、Single、SubTuple、Add-Gets 中仍被外部使用的实际
结果，保留原阶段可见性、union 启用的新匹配、存活性和 delta ownership。
其他规则及未覆盖实例继续走完整枚举路径。

## 为什么以 Get Entry 激活，而不是生产者 root

340 实际执行 90 次，只有 45 个生产者事件进入这个观察到的完整分叉；
324 执行 274 次，只有 27 个进入。不能在全部生产者执行时就复制一份闭包
状态。应在相关消费 Run 的 Get Entry 已有合法激活时，建立或接续实例。
Entry 的实际字段提供 x、i、g，模板提供静态连接。

生产者到 143 的 Run 间隔：340 为 178，324 为 165–172。跨阶段间隔很长，
提前保留独立 producer history 会扩大存活区间。这支持复用既有 Entry
生命周期；仍需证明消费者激活不会漏掉后续外部输入或 Eq 引起的新匹配。

同阶段的 60 → {58,143→137} 只观察到一个完整分叉，且存在额外分支；
它不应优先于上面两个跨 ruleset 家族。

## 实现切口与验收

第一步应当在合法 Get Entry 激活后，用同一个已绑定实例承担 58/143 的
执行安排；137 的后续阶段由静态完成计划授权。新路径应替代这些匹配和
中间 handoff，而不是先尝试一次，随后又完整走旧路径。

必须保留原 rule/Run 的遍历及提交顺序，或另行证明改变顺序合法。对已经
由旧目录接管的 137，只能计入新删除的匹配、绑定或交接，不能重复计算
其现有 RHS 复用。

按如下指标验收：

- 合法 Entry 激活数、实际接管数及退回原因。
- 58/143/137 各自剩余的查询、绑定、赢家选择次数。
- 中间实例、历史 owner、内部 publication 记录及其峰值存活字节。
- 必需的构造、union、边界通知，以及新增阶段/存活检查。
- 逐 Run 图和有序效果检查，以及既定语义 acceptance。

本分析提供候选及局部证明，没有证明完整跨阶段调度替换已实现，也没有
证明压缩率或运行时间收益。

## 复现

```sh
python3 benchmarks/cell-structural-compression/analyze_cross_stage_closures.py out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/root-history-full.json benchmarks/cell-structural-compression/cross-stage-closure-candidates.json
```

JSON 保存每个实例的四个实际事件编号、Run、外部消费事件和 typed 证明，
可以回到原 trace 逐项复核。
