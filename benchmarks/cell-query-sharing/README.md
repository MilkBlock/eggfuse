# 同 Cell、同 Run 的查询重复诊断

对象是 standalone Cell CPU，基线 `114543ae`（`305b0903` 只记录计时）。
上次完整执行有 31,372 个多入口 Cell，但归组数量不能证明重复计算规模。
本步用显式 feature `cell-query-sharing-audit` 观察实际执行；所有查询照常读取，
未接管任何工作、未建立缓存或宣称加速。

诊断使用调度器相同的实际 producer Cell 身份，包含复用他处构造子的情况。
小 Run 虽然不建立生产归组索引，也纳入诊断。不同 Cell、不同 Run 隔离。
每个 chunk 的暂存 map 在结束或异常时释放，不附在 Cell 实例或生产者上；
普通构建不包含这些 map、额外任务字段或诊断代码。

编译期从原 Query 生成前缀身份：保留调用、参数投影、结果条件和此前全部
步骤，只忽略 source atom 标签。实际相同锚点、相同值和前缀的再次执行是
保守的直接共享候选；不同锚点间可由 Cell wiring 证明的共用不在这个下界里。
动态 `(table, args)` 重复另计；它不是静态证明，也不能和前缀重复相加。
原 watermark、delta、见证标签、拒绝条件和输出顺序仍逐入口有效。

| 观察 | sum-bits | Raytrace 前 128 Run |
|---|---:|---:|
| 实际 worker Entry | 1,907 | 21,186 |
| point read | 2,082 | 21,229 |
| 跨入口重复读取 | 24 | 734 |
| 同一入口内部重复读取 | 2 | 0 |
| 同锚点、同前缀重复步骤 | 0 | 0 |
| 可无歧义归于字面量查询键的跨入口重复 | 4 | 679 |

全部跨入口重复来自初始化模板 375；Raytrace 该模板拥有 14,091 个 fact
操作，不是一个很小的业务 Cell。主要重复为 `Write()` 的 439 次和 `Int(2)`
的 234 次。多入口不代表相同锚点，不能盲目给所有 Cell 加公共前缀缓存。

下一步可由原指令直接证明：入口第一条读取的 key 全为字面量或空参数时，
它与入口绑定无关，且每个已激活入口必定执行这条读取。同一封存 Run 可以
共同完成原始读取，各入口单独检查返回值和 delta。只读取被实际激活且重复
使用的前缀，不预执行后面的条件或 RHS；不得跨 Run 保留 mutable read、旧
Eq 结果或缺失结果。结果槽和分派收费，不能把上述机会直接计为已节省。

74 项诊断构建 runtime 测试、72 项普通构建测试和 README compile/run/bench
短例通过。20 个短例配置保持精确最终图和有序 Run 签名，fixture 另比较
阶段图及有序绑定，指定 sum-bits 语义验收 pass / 0。sum-bits inline 1 与
4 worker 的诊断计数一致；短 Raytrace 的图、Run 和原逻辑工作保持。

诊断累计复制的 Value 数为 9,444 / 113,203，chunk 最大记录数为 141 / 694；
这些是测量开销，不能用诊断构建测速。尚无完整 Raytrace 的重复读取分布。
详细来源、候选规则和 SHA256 见 [results.json](results.json)。

```sh
cargo test --locked -p eggfuse-cell-runtime --features cell-query-sharing-audit,view-ports,storage-metrics --lib
cargo build --release --locked -p eggfuse-cell-runtime --features cell-query-sharing-audit,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
AUDIT --program SUM --output OUT/sum4 --local-congruence --query-workers 4 --query-grain 64
AUDIT --program SUM --output OUT/sum1 --local-congruence --query-workers 1 --query-grain 64
BEFORE --program SUM --output OUT/sum-before --local-congruence --query-workers 4 --query-grain 64
PREFIX_AUDIT RAY OUT/ray128 128 4 64
python3 benchmarks/cell-query-workers/check.py AUDIT BEFORE SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit 114543ae --extra-fixture MIXED
python3 benchmarks/cell-query-sharing/collect.py OUT SUM RAY SAVED_RAY_PREFIX benchmarks/cell-query-sharing/results.json
```

保存二进制哈希到 `OUT/provenance.json`，格式见 results 中的 provenance。
完整导出、二进制和日志放忽略的 `out/cell-query-sharing`。
