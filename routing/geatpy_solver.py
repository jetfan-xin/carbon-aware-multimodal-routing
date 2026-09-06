"""Geatpy 2.7 integration with a new adaptive/restart policy (September 2026).

This code uses Geatpy's public Problem, Population and SEGA interfaces.
It does not copy a recovered historical algorithm or vendor Geatpy code.
"""

import geatpy as ea
import numpy as np


class FreightProblem(ea.Problem):
    def __init__(self, network):
        self.network = network
        dim = len(network.edges)
        super().__init__(name="CarbonAwareFreight2026", M=1, maxormins=[1],
                         Dim=dim, varTypes=[1] * dim, lb=[0] * dim,
                         ub=[dim - 1] * dim, lbin=[1] * dim, ubin=[1] * dim)

    def aimFunc(self, pop):
        objectives, constraints = [], []
        for priorities in pop.Phen:
            route = self.network.decode(priorities)
            if route is None:
                objectives.append([0.0])
                constraints.append([1.0])
            else:
                result = self.network.evaluate(route)
                objectives.append([result["objective_cny"]])
                constraints.append([result["constraint_violation"]])
        pop.ObjV = np.asarray(objectives, dtype=float)
        pop.CV = np.asarray(constraints, dtype=float)


class SearchController:
    """Population-level fitness-spread adaptation and elite-preserving restarts."""
    def __init__(self, patience=20, adaptive=True):
        self.patience = patience
        self.adaptive = adaptive
        self.best = (float("inf"), float("inf"))
        self.stagnant = 0
        self.restarts = 0
        self.trace = []

    def __call__(self, algorithm, population):
        ranks = [(float(population.CV[i, 0]), float(population.ObjV[i, 0])) for i in range(population.sizes)]
        elite = min(range(population.sizes), key=lambda i: ranks[i])
        current = ranks[elite]
        if current < self.best:
            self.best, self.stagnant = current, 0
        else:
            self.stagnant += 1
        feasible_costs = population.ObjV[population.CV[:, 0] <= 0, 0]
        spread = float(np.std(feasible_costs) / max(1.0, abs(np.mean(feasible_costs)))) if len(feasible_costs) else 0.0
        # Higher convergence increases exploration; these are new, explicit formulas.
        convergence = 1 / (1 + spread)
        if self.adaptive:
            algorithm.recOper.XOVR = 0.6 + 0.35 * convergence
            algorithm.mutOper.Pm = min(0.5, (1 + 4 * convergence) / algorithm.problem.Dim)
        restarted = False
        if self.adaptive and self.stagnant >= self.patience and algorithm.currentGen + 1 < algorithm.MAXGEN:
            fresh = ea.Population(Encoding="RI", Field=population.Field, NIND=population.sizes - 1)
            fresh.initChrom()
            algorithm.call_aimFunc(fresh)
            fresh.FitnV = ea.scaling(fresh.ObjV, fresh.CV, algorithm.problem.maxormins)
            indices = [i for i in range(population.sizes) if i != elite]
            population[indices] = fresh
            population.FitnV = ea.scaling(population.ObjV, population.CV, algorithm.problem.maxormins)
            self.restarts += 1
            self.stagnant = 0
            restarted = True
        self.trace.append(dict(generation=int(algorithm.currentGen),
                               best_violation=self.best[0], best_objective_cny=self.best[1],
                               crossover_probability=float(algorithm.recOper.XOVR),
                               mutation_probability=float(algorithm.mutOper.Pm), restarted=restarted))


class FreightSEGA(ea.soea_SEGA_templet):
    """Use the generation statistics hook instead of the wheel's broken outFunc."""
    def __init__(self, problem, population, controller, **kwargs):
        self.controller = controller
        super().__init__(problem, population, outFunc=None, **kwargs)

    def stat(self, population):
        super().stat(population)
        self.controller(self, population)


def solve_geatpy(network, population=80, generations=100, seed=42, patience=20, adaptive=True):
    for name, value, minimum in (("population", population, 4), ("generations", generations, 1), ("patience", patience, 1), ("seed", seed, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if seed >= 2**32:
        raise ValueError("seed must be below 2**32")
    problem = FreightProblem(network)
    controller = SearchController(patience, adaptive)

    algorithm = FreightSEGA(problem, ea.Population(Encoding="RI", NIND=population), controller,
                                    MAXGEN=generations, logTras=0, drawing=0,
                                    maxTrappedCount=generations + 1)
    result = ea.optimize(algorithm, seed=seed, verbose=False, drawing=0,
                         outputMsg=False, drawLog=False, saveFlag=False)
    solution = network.evaluate(network.decode(result["Vars"][0])) if result["success"] else None
    return dict(solver="geatpy-sega-adaptive" if adaptive else "geatpy-sega-baseline",
                status="feasible-heuristic" if solution else "no-feasible-route-found",
                seed=seed, population=population, generations=generations,
                restart_patience=patience, restarts=controller.restarts,
                route_evaluations=int(result["nfev"]), solution=solution, trace=controller.trace)
