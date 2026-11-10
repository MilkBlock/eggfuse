# Cell worker 临时帧与结果交回

实现对象是 **standalone Cell CPU**，不是 native egglog。基线为 `ae123cf9`；本轮只做短例与 Raytrace 前 128 个 Run 的语义/工作量检查，没有完整性能测量。上一轮完整实测仍是四 worker 9.706 s、同路径 inline 9.411 s，不能据此宣称多线程已经加速。

## 由上轮实际执行确定的机会

上轮完整 Raytrace 有 27,845 个 chunk、55,058 次值/见证帧分配，以及各 1,076,546 次中间结果槽初始化和写回；worker 成功结果只有 387,764 个。已有 Cell Query 的 point-only 类型证明每个 Entry 至多产生一个匹配结果，现有 `finish_worker_rule` 已根据源 ordinal 恢复胜者顺序。因此不需要新事实图或重新学习一套 marker，即可删除重复的结果物化和顺序搬运。

跨 Run 可保留的是临时向量的容量。函数当前值、Eq、watermark、存活状态以及下一个 Run 的 Entry 激活仍须重新验证；Run 切换不能把这些义务当作已完成。线程分配仍是同一 Run 中按实际 Cell 归组，未引入跨 Run 的线程亲和性或 CPU 查询权重。

## 已删除的工作

- 专用 Rayon worker 各持有一个临时帧；inline host 使用执行器自己的帧。值、见证和构造子候选复用容量，每个 chunk 完成、返回错误或 panic 展开时都清空有效内容。跨 Run 不缓存查询结果，也没有新增失效订阅。
- worker 只返回成功结果及原队列位置。每个任务首次命中时一次预留至多任务 Entry 数的容量；全负匹配任务不分配结果向量。不会因密集命中反复扩容。
- 协调线程从原队列取出成功结果对应的 Cursor，直接交给现有规则完成路径；删除按全部 Entry 创建、初始化和散写的 `completed` 数组。原规则 ordinal 排序仍是唯一的胜者顺序恢复点。源顺序中的第一个错误在任何结果交给 StageSpine 前选择，RHS 仍在全部查询成功后按原序执行。
- 所有队列项最终释放，包括整条规则没有成功结果的情况；不能让其 `rule_facts` 或 Cursor 阻止后续 Run 重试。

`cell-run/v3` 新增临时帧借用、正结果头、逐任务错误检查及保留容量指标。Bake work-credit 对前三项实际工作收费，保留原有任务、排序和缓冲增长收费；覆盖率及答案数不产生奖励。字段/见证帧的 `frame_allocations` 现在计实际容量增长，构造子候选仍在原 `candidate_growths` 中单独计量。容量指标不是总内存、总 allocator 调用数或硬件 cache miss。

## 短检查结果

均为相同程序、4 worker。sum-bits 用 grain 1 压力检查覆盖，短例用 grain 16，Raytrace 前缀用 grain 64。不是速度配置比较。

| 指标，旧版 → 本轮 | sum-bits | 短例 | Raytrace 前 128 Run |
|---|---:|---:|---:|
| 值/见证帧容量增长 | 2,816 → 14 | 134 → 14 | 847 → 10 |
| 结果向量分配/增长 | 1,450 → 685 | 33 → 33 | 436 → 128 |
| 结果向量累计容量（槽） | 1,915 → 931 | 255 → 255 | 21,186 → 6,454 |
| 中间结果槽初始化 | 1,907 → 0 | 131 → 0 | 21,186 → 0 |
| 中间结果槽写回 | 1,907 → 0 | 131 → 0 | 21,186 → 0 |
| 胜者顺序比较 | 1,814 → 2,790 | 128 → 128 | 3,926 → 3,926 |
| 净减少的等权操作 | 2,922 | 165 | 40,149 |

总查询调用、worker Entry 数、答案数、指令步数和任务归组比较数均保持一致。sum-bits 的胜者排序增加了 976 次比较，已计入净值；其构造子候选向量增长从 39 次降到 7 次。Raytrace 前缀只交回 2,560 个正结果，仍执行原来的 21,186 个查询 Entry，不能把未匹配的 Entry 算作被省略的查询。

sum-bits 四个 worker 保留的帧容量分别为 320、384、288、384 字节；短例四 worker 各 256 字节，inline host 184 字节；Raytrace 前缀四 worker 及 inline host 各 160 字节。容量增长数随线程实际分配略变，以上是本次保存的执行值。原 Cursor 队列的峰值容量未增加。没有将这些数字推算成完整 Raytrace 节省或运行时间。

第一版稀疏结果使用默认逐步扩容，在密集短例上把结果分配从 33 次增至 49 次。本轮接着利用 point Entry 的单结果上界，改为首次命中时一次预留；最终证据全部来自该修正后的同一份 release 二进制。

## 验证和复现

14 项 query worker/receipt 测试、62 项 runtime 单元测试与 5 项 work-credit 测试通过。新边界测试检查全负匹配后的函数更新与再次匹配；比较每个 Run 的完整图和有序绑定。帧生命周期测试验证普通错误和 panic 展开都释放字符串引用，只保留容量。

最终 release 的旧版、关闭 worker、inline 1、pool 2、pool 4 在 sum-bits、普通/强制 hash 碰撞短例中共 15 个执行，最终图和 Run 签名相同；短例还比较全部 Run 快照和有序绑定。指定 `choice_diagnosis.py` 使用已保存 native exports，返回 `status: pass` / exit 0，未放宽证明。Raytrace 仅比较前缀最终图与 128 个有序 Run 签名，不构成完整 workload 或 native Raytrace 语义证明。

默认/all-features `cargo check` 和 README 的 Cargo compile/run/bench 短例入口通过；bench 只执行一次 smoke，不用作速度证据。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib work_credit
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT/checks --baseline-commit ae123cf9
BASELINE_QUERY_PREFIX RAY_PROGRAM OUTPUT/ray-prefix-before 128 4 64
CANDIDATE_QUERY_PREFIX RAY_PROGRAM OUTPUT/ray-prefix-after 128 4 64
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --example compare_work -- OLD_REPORT NEW_REPORT WORK.json
python3 benchmarks/cell-worker-scratch/collect.py out/cell-constructor-queries OUTPUT benchmarks/cell-worker-scratch
python3 docs/optimization-catalog/catalog.py check
```

保留前版 `final/checks.json` 及其中指定的 report；分别生成 `work-sum.json`、`work-fixture.json` 和 `work-ray-prefix.json`。在 `OUTPUT/prefix-manifest.json` 保存前缀的程序/二进制 SHA-256、Runs、worker、grain 和 features；结构见 [results.json](results.json) 中的 `raytrace_prefix_manifest`。collector 验证前版二进制、保存 report 与本轮检查之间的哈希关联，只读取已有结果。详细计数和证明入口输出见同一文件，净工作账本见相邻三个 `work-*.json` 文件。完整图、构建和原始日志在未跟踪的 `out/cell-worker-scratch`。
