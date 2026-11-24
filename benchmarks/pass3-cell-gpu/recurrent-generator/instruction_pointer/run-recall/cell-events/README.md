# Cell 事件驱动的 Primitive 生成

Neural Execution / exclusive。训练使用 MPS，独立执行使用 PyTorch CPU 和 standalone Rust Cell Runtime。CCP v0.1、发布边界、Higher Router、A 的本地前缀检查点沿用上一轮。训练程序、种子、验证程序和步数见三个 fit JSON 及 calibration.json。fact 和 sum-divisors 均有开发历史，但本次训练及校准均未使用它们。

A 为冻结的高覆盖基线。B 从已发布端口读取局部状态，通过模板树选择零个或多个规则角色，再用既有神经字段桶和递归父指针签发。C 用共享网络直接预测每步地址区间的两端，按页继续输出，单个区间可跨任意页数。单个连续区间难以表示分散在不同位置的合法地址。D 复用 C，增加按 teacher 轨迹训练的指令和操作数选择器，实际查询来自原生计算回执。树仍需维护调度掩码，地址表仍需读取端口并构建索引。每个机会可在伙伴表版本变化后重新激活，签发时检查 delta 所有权。零父初始化在验证阳性不足时放行可调度的空输入模板。

[paired.csv](paired.csv) 汇总 4 个 workload × 4 个方案 × 4 次独立执行。重复编号 4–7 轮换执行顺序。比较同图使用终态 SHA；EPT 为签名有效操作除以 CCP 付费请求，另列神经控制费用和计算请求。访问按打分、读源端口、建索引和读取 postings 分列。这些是逻辑访问计数。原始 JSON 保留核验原因、Run 数、同步及按阶段计时。部分批次与成本诊断共享机器。精确补全调用为零。[独立的原生神谕对照](../generation-frontier/README.md)

两份留出 grammar 只有 A、B 同图完全覆盖，B 各自 0/4 对快于 A。深布局上 D 的实际计算使 C 的 38/83 上升到 44/83，355 个计算请求产生 71 次回执查询，包含 284 个局部操作数引用。fact 的 B 最早在 Run 20 的父打分漏一项，C/D 在同一 Run 的地址选择漏两项。sum-divisors 的 B 在 Run 12 的父打分漏一项；C/D 在 Run 11 的地址选择漏四项，并在 Run 119 触发源程序类型检查。其覆盖仅计最后已发布状态，时间和成本包括失败 Run。相同终图上的 EPT、EPS 没有超过 A。

fact 全开末层的四次执行均复现参考 SHA，较冻结 A 多付 34,421 Token，多访问 57,425 个候选，中位墙钟 6.19 → 6.31 秒。sum-divisors 两次全开均在 1,200 秒预算耗尽时停在 Run 1145，最后发布状态为 5,340/8,018。完全饱和成本未知。加权计算是对单个未封存 Run 的离线诊断。Higher 审计另存，未部署新 Higher 模板。

从 instruction_pointer 目录复现，ROOT 为上一轮数据根，DONOR/DOT 分别为训练盘 sum 和 dot。使用含 PyTorch 的 Python。

```sh
O=run-recall/cell-events
python train_event_templates.py "$ROOT" "$O" "$DONOR" "$DOT"
python train_event_addresses.py "$ROOT" "$O" "$DONOR"
python event_calibration.py "$ROOT" "$O" "$DOT"
python train_event_computation.py "$ROOT" "$O"
python event_experiment.py "$ROOT" "$O" --cases fact sum-divisors grammar-36719037 grammar-benefit-held-deep-11901379 --modes local B C D --offset 4 --reps 4 --seconds 300
python event_omission.py "$ROOT" "$O" --cases fact sum-divisors grammar-36719037 grammar-benefit-held-deep-11901379
python summarize_events.py
```
