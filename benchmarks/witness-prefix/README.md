# Cross-stage witnesses, fragment publication and wider completion reads

三条执行路径已接入，**本轮没有通过双工作负载的整体加速门槛**。
这是 standalone Cell CPU 的实验，不是 native egglog 的性能结果。

实现提交为 `094fb2ed`，指标目录及已有 alias counters 的报告导出在
`f5bc98ca`。前一版本是 `762beb0f`，两套冻结二进制、程序和代码哈希见
[普通计时记录](normal/README.md)。

## 执行路径与真实覆盖

| 路径 | 被替代的旧工作 | sum-bits / Raytrace 实际观察 |
|---|---|---|
| 完整 Spine 的当前 effect 见证 | history/cache 之后的完整查询 | donor 读取 25 / 1,380，命中均为 0 |
| register kernel 前缀接续 | PC=0 开始的重复完整 key 读取 | donor 读取 6 / 239，命中及实际接续均为 0 |
| 共享 anchor 片段发布 | 临时 receipt 哈希及重复 Entry 寻址 | 3,421 / 593,054 个 receipt 进入片段路径；这是事件数，不是独立 Cell 数 |
| 大形状的完整域读取批次 | 局部条件超过 16 sites 后截断批次 | 2 worker 诊断中，6 / 4,426 个 exact-domain task 进入并行读取 |

前两条的正向路径有专门回归样例，但**目前真实样例中的地址策略均回退**。
它们没有减少实际 `key_lookup_calls`，不能解释本轮时间变化。后续需要定位
失效的见证地址与 receipt/alias 的关系，不能仅增加模板数量。

片段路径只接管至少两个 anchor、全部永久可见且由共享 Entry 持有的规则。
静态 `anchor_ops` 描述发布位置，运行时保存紧凑 receipt 片段；完成修复后，
现有 Entry 槽位按 ordinal 选择最后写入者，只为胜出者构造发布上下文。
未就绪的 receipt 留在原片段；未知边界、可见性变化和缺失 receipt 仍有完整回退。
单 anchor 保留原快路。同一新 Entry 的待处理通知只登记一次。

大形状没有扩充二次方的局部条件代码。完整端口域给出所有候选，worker 执行
精确 key guard；原输入根 read set、双侧 union 失效、存活检查和按序提交继续生效。
此次没有重做普通构建的线程扩展性计时，诊断中的 worker 活动不能当成加速证据。

## 验证与成本

- 全工作区 all-features：357 项通过，4 项忽略；非 sparse：28 项通过；最小构建通过。
- sum-bits 的 1,428 个 Run、Raytrace 的 16,883 个 Run：当前单线程与 2 worker overlap 的状态、按序 RHS、写入、resume、调度及去除 program hash 的 Spine shape 一致，也与前一冻结版本一致。
- 执行期间分配次数：sum 203,944 → 203,945，Raytrace 45,700,561 → 45,700,562；没有减少分配次数。请求字节略降，完整数据及 setup 成本保存在 [validation.json](validation.json)。
- 并行诊断：prepared/committed/unused 分别为 sum 684/609/75、Raytrace 173,196/160,933/12,263；废弃工作没有从报告中扣掉。
- Bake credit 对新 context/route/donor/key 校验、片段状态、旧哈希与共同 Entry 寻址公平收费。hit 和 avoided 只是结果计数，不再作为第二份负成本。

[设计与证明](design.md) · [前缀接续约束](register-prefix-design.md) ·
[完整按序审计](audit-results.json) · [逐组分类及指标](../../docs/optimization-catalog/README.md)

普通计时为每样例每配置 1 次预热、3 次交错正式样本，全部保留：
sum 推理中位数 30.772 → 31.459 ms，Raytrace 12.557 → 12.335 s。
两个样例的整进程中位数均下降，但 sum 推理的方向不稳定；历史 fast 配置仍更快。
这是合并改动的小样本对照，没有给片段发布单独归因，也没有给前两条零命中路径记收益。

复现按序诊断需要独立构建包含
`sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics`
的 runtime，再运行：

```sh
python3 benchmarks/result-port-repair/audit.py \
  out/witness-prefix/runtime-diagnostic \
  benchmarks/witness-prefix/audit-manifest.json out/witness-prefix/audit-new
python3 benchmarks/witness-prefix/compact-audit.py \
  out/witness-prefix/audit-new/results.json \
  out/query-classes-final/final-audit/results.json out/witness-prefix/audit-compact.json
```

正常计时的构建和命令见 [normal/README.md](normal/README.md)，不要用诊断二进制替代。
