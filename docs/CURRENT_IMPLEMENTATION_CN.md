# 当前维护实现：数据规模、算法与验证

日期：2026-09-27

## 1. 定位

当前维护版不是把后续代码倒填成“2022 年原代码”，而是在保留字节级历史快照的前提下，继续完成当年问题的工程化版本：可复现数据生成、完整输入验证、四组遗传算法消融、订单合单、动态边状态、容量约束、路线求解、成本/时间/排放核算和计算结果地图。

因此可以连续地讲述为：

1. **历史比赛实现**：本人设计算法并编写项目特有的路线规划和量化分析代码；队友共同参与案例数据收集；Geatpy 是第三方框架。
2. **当前维护实现**：在现代测试框架下补齐可复现、可扩展的端到端流程，并以独立目录保留历史代码原貌。

两部分都是本人工作，但时间、数据性质和验证强度必须分别标明。

## 2. 数据边界与规模

### 历史事实

- 原案例有 23 个基础城市。
- 距离工作簿中有 253 个非空城市对，合计 754 个模式距离：公路 253、铁路 250、水路 251。
- 原优化不是“几十万条企业订单”的训练或处理；它使用一张案例网络、参数表和三个需求情景。
- 100,000 次或更多目标函数计算是算法计算量，不等于 100,000 条源数据。

公开仓库只保留不可逆的汇总统计 [`historical_aggregate_profile.json`](../data/historical_aggregate_profile.json)，不重新分发原始工作簿。

### 合成规模扩展

[`synthetic.py`](../routing/synthetic.py) 生成明确标记为 `synthetic_calibrated` 的数据：

- 默认保持 23 城、253 城市对和 754 条模式边的历史规模结构；
- 距离分布以历史汇总的最小值、四分位数、中位数和最大值为校准依据，但每一条边距离均为可复现的合成值；
- 可以生成指定数量的合成订单；每条订单都含来源标签，不能误当作历史或真实交易；
- 支持更改节点数、网络密度和随机种子，用于压力测试，不用于声称真实业务覆盖。

这解决的是“如何证明系统能处理更大输入”的工程问题，而不是伪造 2022 数据规模。

## 3. 端到端调用链

```text
合成或外部授权订单
  -> validate_orders：字段、数值、OD、唯一 ID、来源标签
  -> consolidate_orders：相同 OD/截止时间合单并按容量拆批
  -> network_for_batch：注入吨位、截止时间、关闭边和可用性
  -> analyze_connectivity：DFS 可达性 + 有向无环图拓扑排序
  -> Network：验证图、参数、情景、费率、换装和容量
  -> exact / state-Dijkstra / native GA / optional Geatpy
  -> evaluate：运输、换装、时间、排放、碳成本和约束
  -> JSON 结果 + 基于实际解的自包含 SVG 路线图
```

面试中可以概括为“贪婪订单分批 + DFS 连通性搜索 + 拓扑顺序校验 + 灾变自适应遗传优化”。更精确地说，DFS 用于计算起点可达集合并判断终点是否连通；拓扑排序只在网络为 DAG 时给出合法节点顺序，并不是由拓扑排序“生成”连通图。

主要入口：

- [`run_full_pipeline.py`](../tools/run_full_pipeline.py)：订单到路线结果的批处理入口；
- [`pipeline.py`](../routing/pipeline.py)：验证、合单、网络状态和地图；
- [`model.py`](../routing/model.py)：图模型、解码与目标函数；
- [`native_ga.py`](../routing/native_ga.py)：无第三方二进制依赖的 GA 对照实验；
- [`geatpy_solver.py`](../routing/geatpy_solver.py)：可选的真实 Geatpy 集成。

## 4. 现代数据模型与目标函数

每条有向边包含起点、终点、模式、距离、可用性和可选容量。交通模式包含速度、单位吨公里排放和距离分段费率；换装参数按模式对定义成本、时间和排放。

候选路线对每个需求情景分别计算：

\[
C_s=C_{transport,s}+C_{transfer,s}+C_{time,s}+C_{carbon,s}
\]

其中碳费率采用累进边际区间积分。现代风险目标为：

\[
f=E[C]+\lambda(\max_s C_s-E[C]),\quad 0\le\lambda\le1
\]

截止时间、排放上限和边容量可以形成约束违反值；排序首先比较约束违反，再比较目标值。该风险式、累进碳价修正和约束体系属于当前维护版，不追溯为历史代码的精确行为。

## 5. 四种 GA 的公平比较

[`native_ga.py`](../routing/native_ga.py) 使用同一编码和同一候选评价预算，提供：

| 变体 | 自适应概率 | 20 代停滞灾变 |
| --- | --- | --- |
| fixed baseline | 否 | 否 |
| adaptive only | 是 | 否 |
| catastrophe only | 否 | 是 |
| combined | 是 | 是 |

共同部分为三元锦标赛选择、两点交叉、随机重置变异，以及父代/子代合并精英选择。灾变真正保留一个全局最优染色体并替换其余个体；灾变代也只评价一个种群，因此四组的候选评价数相同。

当前自适应公式基于可行种群目标值的相对离散度：

\[
spread=\frac{\sigma(f)}{\max(1,|\bar f|)},\quad convergence=\frac1{1+spread}
\]

\[
p_c=0.60+0.35\,convergence
\]

\[
p_m=\min\left(0.50,\frac{1+4\,convergence}{dimension}\right)
\]

这是当前维护版明确记录的公式，不冒充尚未找回源码的历史自适应公式。GA 输出始终标记为启发式结果，不提供全局最优证明。

## 6. 100,000 订单受控基准

完整机器可读结果保存在 [`synthetic_23city_100k_orders_30seeds.json`](../benchmarks/synthetic_23city_100k_orders_30seeds.json)。本次运行：

- 23 节点、754 条模式边；
- 生成并验证 100,000 条合成订单；
- 合单后得到 16,327 个批次；
- GA 路由消融只评测一个固定网络情景，并未逐一优化全部 16,327 批次；
- 每个变体 30 个随机种子，每次 20 个个体 × 40 代 = 800 次候选评价。

| 变体 | 平均目标值 | 中位数 | 标准差 | 总灾变次数 |
| --- | ---: | ---: | ---: | ---: |
| fixed baseline | 22,007.55 | 21,780.76 | 2,892.23 | 0 |
| adaptive only | 20,910.02 | 20,687.15 | 2,391.03 | 0 |
| catastrophe only | 20,042.21 | 19,760.54 | 2,958.83 | 29 |
| combined | 20,389.43 | 20,260.09 | 2,190.01 | 25 |

在这个预先定义的合成实验中，combined 相对 fixed baseline 的平均值降低 7.35%，中位数降低 6.98%，标准差降低 24.28%。catastrophe-only 的样本平均值低于 combined，而 combined 的离散度最低，所以不能声称 combined 在所有指标或问题上都必然最好。

这些结果只证明该实现能够生成、验证和合并 100,000 条合成订单，并在指定网络情景上完成可复现的多种子算法比较。它们不是历史比赛结果、生产吞吐量、企业数据经验或真实部署收益。

## 7. 验证范围

自动测试覆盖：

- 历史快照哈希和历史输出算术；
- 23 城/754 边结构和分段费率；
- 四种 GA 的等候选预算、确定性种子和灾变行为；
- 路径连续性、去环、不可达、截止时间、碳上限和容量；
- 订单来源标签、合单质量守恒、边关闭和 SVG 输出；
- 小图 exhaustive baseline 与独立枚举的一致性。

macOS ARM/Python 3.13 不能原生加载 Geatpy 2.7.0 的 x86-64 wheel。仓库现提供固定的 Linux amd64/Python 3.10 Docker 环境，安装官方 wheel 及其 `libgomp1` 系统依赖；12 项真实 Geatpy 集成测试和 CLI 算例已在该环境中全部运行通过。150 次真实 Geatpy 消融的结果、分析和图表见 [`GEATPY_RESULTS_ANALYSIS_CN.md`](GEATPY_RESULTS_ANALYSIS_CN.md)。它验证的是当前集成，不等同于复现未知的历史随机状态。

## 8. 简历和面试可用表述

技术报告必须保留版本和数据来源说明；简历项目栏则不需要把“恢复/审计”写成工作内容，也不必突出某一个合成订单数量。推荐中文表述：

> 设计并实现面向 23 城公铁水网络的低碳多式联运遗传算法，建立优先级路径编码及运输、转运、时间窗和碳成本模型；进一步完善可复现数据管线、约束验证和等预算算法对比，并通过可扩展合成情景测试端到端流程。

推荐英文表述：

> Designed and implemented a carbon-aware genetic-algorithm routing workflow for a 23-city road, rail and inland-water network, combining priority-based route encoding with transport, transfer, time-window and carbon costs. Extended it with reproducible data pipelines, constraint validation and equal-budget GA ablations across scalable synthetic scenarios.

面试被追问时，再主动说明扩展测试使用合成数据，历史案例数据是 23 城网络、参数表和需求情景。不能说“处理几十万条真实企业订单”“在生产环境降低成本 7.35%”或“证明算法达到全局最优”。
