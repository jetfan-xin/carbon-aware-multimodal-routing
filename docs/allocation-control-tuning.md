# Allocation-GA controller selection and held-out validation

For locus `j`, let `f_j` be the most frequent gene share. Population diversity is:

```text
D   = mean_j(1 - f_j)
u_D = max(0, (0.25 - D) / 0.25)
u_S = min(1, stagnant_generations / patience)
```

The selected hybrid controller uses:

```text
expected mutations = min(2.5, 1.00 + 0.75 u_D + 0.75 u_S)
per-gene mutation  = min(0.50, expected mutations / number of orders)
crossover          = 0.72 + 0.13 max(u_D, u_S)
```

After 30 stagnant generations, catastrophe-enabled variants preserve ranked unique elites and regenerate the remainder, targeting a 25% partial restart. The hybrid keeps the opportunity-loss greedy solution in an external incumbent archive, so it does not make every first generation identical. The separately selected non-seeded combined control retains the 1.25 base and 3.0 cap; the five-method table therefore compares named mechanisms with their documented selected controls rather than forcing identical adaptive coefficients.

Controller selection used seeds 30--39, held-out paired validation used seeds 40--69, and the final benchmark used seeds 0--29. The predeclared median--mean--best rule selected `v2-hybrid-archive-r25`. On held-out seeds, the selected hybrid versus the legacy hybrid produced 23 wins, 0 ties and 7 losses. Mean paired cost change was -CNY 4,257.77 with an approximate 95% t interval of [-6,305.60, -2,209.93]. Against fixed it produced 27 wins and 3 losses, with a mean paired change of -CNY 7,662.38 and interval [-10,992.79, -4,331.97]. The selected combined controller's intervals against legacy combined and fixed both cross zero, so those comparisons do not support a stable advantage at this sample size.

These results support improved robustness on one fixed synthetic instance and evaluation budget. They do not establish universal superiority, real operational savings or the behavior of the 2022 controller whose exact source was not recovered.

Machine-readable records are in [`benchmarks/allocation-control-tuning`](../benchmarks/allocation-control-tuning/) and [`benchmarks/allocation-control-validation`](../benchmarks/allocation-control-validation/).
