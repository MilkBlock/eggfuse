# 外部输入审计

Neural Compilation，离线结构研究。在冻结 10,000 项目录中，以 query、copy、constructor 和已具名的返回端口作前向分析。为外部构造子输入寻找更早的同表、同符号键的已知见证。即使键可计算，缺少构造或成功匹配记录的输入仍保留。候选改接需要逐 Run 重新核对实际返回、版本和可见性。

63,320 个源规则步骤含 138,091 个表输入角色。按每个模板去重边界引用，共 70,343 个外部槽。静态分析给出 102 项候选改写，至多省去其中的 115 个槽，留下 70,228 个。五份原始 tape 中，这 102 项在旧接线下同时满足边界就绪与首次调度条件的实例数均为零。原始目录含 38,565 次相邻 Run 组跨越。实际节省的签发、检索和同步均未建立；统计余额也不是理论最小外部输入数。

从 instruction_pointer 目录复现。ROOT 是含 sum、dot、fact、loopfact、sum-divisors 的 teacher 数据根。

```sh
python semantic_inputs.py "$ROOT/sum/program.json" run-recall/deep-ripsat-10000/catalog.json OUT --tapes "$ROOT"
```
