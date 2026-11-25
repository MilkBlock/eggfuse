# 同一个 Higher Cell 的多入口契约

B 选择原来的模板主体。Bake 为它的根操作提供通用具名入口和可选的单生产者投影。一次投影只读取已发布实例的具名返回端口，或读取该实例原始 Request 签过的父引用。返回端口必须在当前快照可见，原始父引用还必须保持原版本。每次根提交和后续内部步骤仍经过原生核验与发布。

本实验在 sum-bits 的已接受轨迹中发现投影，按原生 Recipe 的输入表和可能输出端口做类型检查，在目标程序重新链接并检查。固定的 48 个模板主体共享 30 条投影，涉及 5 条根规则。每条投影都有原生接受的根实例。指定端口的类型匹配只证明这种读法能提供所需类型的操作数。guard、绑定、条件端口的存在、新旧版本和后续步骤的可执行性仍由实际回执决定。该编译器只覆盖能从一个已发布生产者读取全部根操作数的情形。

## 原生证据

在 sum-bits 之外，sum-divisors 也通过契约 0 和 1 各自执行完同一个模板 18。两个入口都从事件实例取其原输入 0、1，第三个操作数分别取相应生产者的具名返回 0 或 3。sum-bits 两条完整路径的原始 token 为 580→762 和 583→769。sum-divisors 为 1307→1748 和 1320→1763。两次审计分别有 32 和 8 个不同的（主体，契约）组合完成原生接管重放。重放逐项核对 state_sha、调度、写入、RHS、恢复与事件。只用原始签名父元组完全一致的见证认证完整主体。探针分母为 teacher 已接受根涉及的事件，不能直接用作线上成功率。

sum-bits Run 1045 的实例 5680 同时支持两种 Rule 328 绑定。契约 28 读取 input[0] 和 return[2]，命中 5689。契约 29 读取 return[3] 和 return[2]，命中 5692。只有前者在这条轨迹上完成模板 34。两个入口可能得到不同的根，重复检测按已接受的具名元组执行。未完成的分支、其他伙伴和以后 Run 的重新唤醒继续使用 B 的原路径。

## 独立执行

使用研究分支的 Rust 原生验证器和冻结 CCP v0.1。wired 和 projected 使用相同的 B、GNN、父指针、模板主体和权重。B 选择主体后，projected 按事件的静态生产者与端口选择最多一条投影。同一事件有多个适用契约时，默认先按训练程序中的完整主体见证数，再按根见证数选择。也可用 --entry-id 指定优先契约。优先级在执行前确定。实验没有训练入口选择策略。

| 程序 | 两组覆盖事实 | 投影请求 / 接受 / 完整主体 | 候选访问变化 | 付费请求变化 | EPT，原组 → 多入口 | EPS，原组 → 多入口 | 实测秒，原组 → 多入口 |
|---|---:|---:|---:|---:|---:|---:|---:|
| fact | 764 / 1,120 | 11 / 0 / 0 | +0 | +11 | 0.0036744 → 0.0036743 | 95.25 → 93.84 | 11.49 → 11.66 |
| loopfact | 944 / 1,112 | 16 / 1 / 0 | -1 | +15 | 0.0043106 → 0.0043103 | 107.49 → 104.74 | 10.57 → 10.85 |
| sum-divisors | 3,085 / 8,018 | 45 / 9 / 6 | -9 | +36 | 0.0008763 → 0.0008763 | 36.12 → 36.00 | 119.64 → 120.04 |

各程序两组的终图 SHA 完全相同。原生接受后只跳过同一个根元组在本 Run 的后续候选访问。sum-divisors 的 6 个完整主体已经包含在总数 392 里。保留剩余搜索时，三个程序合计少访问 10 个候选，多付费 62 个请求。计时各一对，仅记录成本。CPU 的 compile、run、bench 均通过，既有 sum-bits 语义验收用保存的导出重新验证为 pass。

## 复现

在 instruction_pointer 目录下，用与 entry-wiring 相同的 DATA 和程序快照 ROOT。sum 对应 sum-bits。以下命令复用冻结权重，默认执行线程数为一。

```sh
mkdir -p "$OUT"
cp run-recall/entry-first/entry/catalog.json "$OUT/"
cp run-recall/entry-wiring/{graph,wired}.pt "$OUT/"
python multi_entry.py "$DATA" "$ROOT/sum" "$OUT/catalog.json" "$OUT/entry-contracts.json"
for n in sum sum-divisors; do
  python audit_multi_entry.py "$DATA" "$ROOT/$n" "$OUT/catalog.json" \
    "$OUT/entry-contracts.json" "$OUT/$n-probes.json"
done
for n in fact loopfact sum-divisors; do
  python entry_rollout.py "$DATA" "$OUT" "$n" wired projected --rep 1
done
python -m unittest discover -p 'test_*.py'
```

结果文件中的 entry_events 依次为 Run、契约编号、模板编号、入口生产者、请求 token、原生状态码。published_bodies 记录完成后的发布 Run、契约编号、模板编号与原子 token 序列。每份独立结果保留 state_sha、参考分母、逐原因回执、实际同步、决策计数和墙钟。固定入口优先级时可加 --entry-id；各优先级实验使用各自的输出目录。
