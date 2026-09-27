# 全局订单分配 GA：控制机制调参与独立验证

## 结论

这次改动不是把图的纵轴截短或只挑一个幸运种子，而是修正了三个可解释的搜索机制，并把参数选择与最终验证分离：

1. 用基因型多样性和停滞代数控制变异强度；正式参数的理论范围是每个48基因子代1.25--2.75个期望变异，另设3.0硬上限；
2. 灾变只替换25%种群，保留75%互不重复的精英，降低全量重启的信息损失；
3. hybrid 的机会损失贪婪解作为独立档案解，不占用随机初代位置。

在未用于选参的40--69种子上，selected hybrid 相对旧 hybrid 为23胜7负，平均成本变化为 -CNY 6,414.15，配对差值的近似95%区间为 [-9,333.41, -3,494.89]。这支持“在这一固定合成实例和预算上更稳健”，不支持跨网络普遍优越或真实运营收益。

## 1. 旧机制为什么容易表现差

旧控制器由可行种群成本的变异系数决定概率：

```text
s = std(cost) / max(1, abs(mean(cost)))
q = 1 / (1 + s)
pc = 0.60 + 0.35 q
pm = min(0.50, (1 + 4q) / n_orders)
```

48订单实验中，旧 combined/hybrid 平均每个子代约有4.94个基因发生变异。目标值接近不等于染色体已经相似；用成本离散程度替代基因多样性会在已经找到有用组合时持续进行偏强扰动。旧灾变还会保留一个全局最佳后重建几乎整个种群。旧 hybrid 把 deadline 贪婪解直接写入初代第一个个体，使第一代曲线受确定性种子主导，但并不保证这个种子对共享稀缺资源分配合理。

## 2. 新控制器

[`routing/allocation_ga.py`](../routing/allocation_ga.py) 的 `_genotype_diversity` 对每个基因位置计算 `1 - 众数频率` 并取平均。`_diversity_rates` 使用：

```text
D = mean_j(1 - max_value_frequency_j)
u_D = max(0, (0.25 - D) / 0.25)
u_S = min(1, stagnant_generations / patience)
E_mut = min(mutation_cap, mutation_base + 0.75 u_D + 0.75 u_S)
pm = min(0.50, E_mut / n_orders)
pc = 0.72 + 0.13 max(u_D, u_S)
```

正式设置为 `mutation_base=1.25`、`mutation_cap=3.0`、`patience=30`、`restart_fraction=0.25`。固定法仍使用 `pm=1/n_orders`、`pc=0.70`，所以方法差异没有被抹掉。

[`routing/allocation.py`](../routing/allocation.py) 的 `solve_opportunity_greedy_allocation` 先估计每个订单“最便宜局部可行候选”与“不占共享资源的最便宜兜底候选”之间的绝对成本差，优先分配损失最大的订单，再逐票选择当前容量下的最低边际组合成本。这仍是启发式，不是精确优化器。

## 3. 数据分割和选择规则

三个种子段使用同一个固定合成网络、订单集和候选池，只隔离随机搜索轨迹：

| 用途 | 种子 | 是否参与选参 |
| --- | --- | --- |
| 原正式报告/最终重跑 | 0--29 | 否；用于改动前后的同口径结果 |
| 控制器调参 | 30--39 | 是 |
| 独立验证 | 40--69 | 否 |

每次运行均为100个体 × 150代。选参比较12组配置，预先固定选择规则为最低中位成本、再最低平均成本、再最低最佳成本。调参集选中 `v2-r25-p30-m3`：中位 CNY 309,238.63、平均 CNY 314,981.76、最佳 CNY 303,957.88；旧 combined 的对应值为 CNY 325,098.45、324,096.55、313,321.45。十个种子只适合选择候选机制，不能单独作为强统计结论。

## 4. 未见种子验证

| 配置 | 最佳 | 中位 | 平均 | 标准差 |
| --- | ---: | ---: | ---: | ---: |
| fixed | 306,683.97 | 325,174.92 | 324,212.02 | 9,469.11 |
| legacy combined | 315,332.20 | 322,761.89 | 322,866.16 | 5,429.13 |
| legacy hybrid | 313,650.61 | 320,981.60 | 321,771.47 | 5,719.50 |
| selected combined v2 | 307,324.12 | 320,538.61 | 319,105.93 | 7,463.68 |
| selected hybrid v2 | **304,821.14** | **318,099.92** | **315,357.32** | **5,149.39** |

selected combined 相对 legacy combined 为18胜12负，平均配对成本减少 CNY 3,760.23；selected hybrid 相对 legacy hybrid 为23胜7负，平均减少 CNY 6,414.15。相对 fixed，selected hybrid 为25胜5负，平均减少 CNY 8,854.71。所有150次验证运行均可行。

这里使用相同种子的配对差值，以控制初始化随机序列的部分影响。近似区间采用30个配对差值、自由度29的 t 临界值；没有做多重比较校正，也没有测试其他网络实例，因此报告保留“本实例”限定。

## 5. 正式结果和可视化

使用所选机制重新运行0--29种子后：

| 方法 | 最佳 | 中位 | 平均 | 标准差 |
| --- | ---: | ---: | ---: | ---: |
| fixed | 309,974.93 | 324,683.26 | 323,955.47 | 8,141.37 |
| adaptive | 306,395.52 | 318,643.27 | 319,937.63 | 9,971.13 |
| catastrophe | 309,974.93 | 325,083.06 | 324,252.40 | 8,172.37 |
| combined | 306,395.52 | **318,643.27** | 319,875.05 | 9,933.01 |
| hybrid-seeded | **304,051.85** | 318,677.99 | **315,481.46** | **5,558.50** |

最佳 hybrid 比 deadline 贪婪基线 CNY 372,578.33 低18.39%。hybrid 的中位数比 combined 高 CNY 34.72，因此不能说 hybrid 在所有统计量上都赢；它的优势主要是平均值、最佳值和较低离散度。

正式方法分布、收敛轨迹、方式组合和容量占用图位于 [`benchmarks/synthetic-global-allocation`](../benchmarks/synthetic-global-allocation/README.md)。调参与验证原始表分别位于 [`benchmarks/allocation-control-tuning`](../benchmarks/allocation-control-tuning/README.md) 和 [`benchmarks/allocation-control-validation`](../benchmarks/allocation-control-validation/README.md)。

## 6. 可复现命令

```bash
python3 -B tools/tune_allocation_control.py
python3 -B tools/validate_allocation_control.py
python3 -B tools/run_synthetic_allocation_experiment.py
```

调参和验证脚本保存逐次运行CSV、汇总CSV和包含控制参数/最佳解的JSON。正式脚本另生成SVG图。所有金额都是模型输出，不是历史发票、承运商报价或部署节省。
