# RipSat Cell 浏览器

用 Python 3.8+ 生成单文件 HTML，打开后即可断网使用。无需启动服务，可同时加载多个目录。

```sh
python3 -m pip install .
ripsat-view /path/to/deep-event-10000 /path/to/unified-consumers --program /path/to/sum/program.json -o cells.html
```

也可以在这个目录直接运行 `python3 -m ripsat_view CATALOG`。命令默认打开浏览器，`--no-open` 只写文件。程序接口为 `from ripsat_view import render; render(catalogs, "cells.html", program=donor_path)`。

输入支持旧式布局数组和包含 signatures、layouts 的 Bake JSON。带签名时按规则指纹关联源程序，默认尝试同级 sum/program.json。旧式数组缺少可验证的 fixed.json 时，可以显式指定原 donor；此时规则编号按 donor 顺序解释。没有源程序也可以看拓扑和具名指令位置。

搜索框用 `#9999` 精确定位目录内的原始 ID，用 `R243` 搜含指定规则的 Cell。可按依赖深度、独立外部输入数量及 teacher 回放过滤，或者随机抽看当前结果。选中的模板可通过 HTML 地址末尾的 `#目录序号/模板编号` 定位。点击步骤查看完整规则文本和每条输入的来源。

深度以最长依赖链上的步骤数计。Run 组是布局里的相对调度分组。多个 atom 共用的外部输入槽只计一次。回放证据仅在 replay.json 的目录摘要匹配时显示，表示在对应 teacher 工作负载上至少完整回放过一次。运行时的接受率、独立覆盖率和加速比需从对应执行实验读取。

## RipenInput E-graph

安装 Graphviz（需要 PATH 中的 `dot`）。在 Python 3.8+ 环境运行：

```sh
ripsat-view --egraph /path/to/saturated-rule-composition/cells /path/to/deep-event-10000 --program /path/to/sum/program.json
```

该命令启动本机只读浏览器服务，逐 Cell 按需生成 SVG，Ctrl+C 退出。原生快照从 trigger-state.json 和 observed-saturated-state.json 的 values、rows 和 result 建立等价类，结构视图将整数字面量提升为有类型的 IntParam，保留同一值在计算字段间的共享。RipenInput 的存储槽号从计算图擦除，即使槽号和某个计算常量同值，两者也不会因此连边。原始数值留在源导出中。入口与 Ripen 后的类编号各自局部有效。

对于仅有布局的目录，视图展开 donor 的 query/effects、具名端口接线和显式 union，以参数化 RipenInput 标记外部字段。纯构造子执行同余闭包；图呈现条件成立的静态规则结构。mutable 写入的值表达式及其跨步接线表示配方里的写入意图。动态合并、guard 成败、可见性与修复后的返回值以实际运行快照为准。
