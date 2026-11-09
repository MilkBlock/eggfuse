# Cell effect 收据槽

standalone Cell CPU，基线 `e8faa816`。普通、局部、闭合 handoff 和结构性 capture 共用 `cell::Effects`；删除各路径整 RHS 宽度的临时 receipt 数组。共享模板只为输出及确有后续使用的 effect 分配槽。已覆盖输出直接保留该槽，实际引用可以指向其他 Cell；单写和已证明的别名仍需填入。

源执行器独占借用输出 arena，执行中的后缀不可见。history 先读取原始执行结果，再补别名；合法发布边界仍由原调度决定。闭合预检失败或 RHS 中途停止会丢弃私有后缀、保留之前完成的 Cell 输出，不回滚已经发生的图效果。没有增加消费者订阅。

已完成的验证：219 项 compiler、52 项 runtime 全特性、33 项最小特性测试；另检查无全局审计栅栏的部分 scope 发布。新增中途停止用例比较顺序 RHS/write/resume-root。三个短 fixture 的逐阶段摘要一致；22 个重编译组件、1,428 个 Run、sum-bits 状态和顺序摘要一致，语义脚本 pass。

sum-bits 新观察：6,480 个 frame，12,190 个初始化槽，12,609 次槽探测、10,170 次目标命中；4,454 个输出直接保留，1,599 个输出仍需填入，58 次未完成 frame。既有工作指标不变。执行期 alloc 少 6,198 次、realloc 少 5 次、申请量少 386,804 bytes；setup 新增一份 4,656-byte 计划缓存。计划内容的延迟分配包含在执行期开销中。

沿用中断前已经完成的 7 对短测，不新增计时：推理中位数 24.667834 → 24.784958 ms，配对区间 [0.97719, 1.01768]；整进程中位数 127.888708 → 131.573750 ms，配对区间 [0.98925, 1.03142]。RSS 中位数不变。未证明加速，整进程中位数较高；不将分配减少当作耗时收益。

结果：[effects-results.json](effects-results.json)。复核现有产物：`python3 benchmarks/cell-unification/collect.py out/cell-effects-unified benchmarks/cell-unification/effects-results.json --part effects`。后续小步只做针对性检查，集中实测留到一组结构改动完成后。

尚未统一：效果执行器、单写/merge 控制、闭合 handoff 的 key 数组、必要 Results/history、未知边界和 legacy owner。此提交仅完成 receipt 数据流接管。
