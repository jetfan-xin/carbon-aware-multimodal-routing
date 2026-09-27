"""Dependency-free GA baselines for auditable ablation experiments.

The historical project used Geatpy.  This module does not replace or impersonate
that framework.  It provides a small, deterministic reference implementation so
that fixed-operator, adaptive-only, catastrophe-only and combined searches can
be compared with exactly the same candidate-evaluation budget on any platform.
The adaptive formula is a documented maintained-implementation choice.
"""

from dataclasses import dataclass
import math
import random
import statistics


@dataclass(frozen=True)
class Candidate:
    chromosome: tuple
    route: tuple | None
    result: dict | None

    @property
    def rank(self):
        if self.result is None:
            return (math.inf, math.inf)
        return (self.result["constraint_violation"], self.result["objective_cny"])


def _evaluate(network, chromosome, route_cache):
    route = network.decode(chromosome)
    if route is None:
        return Candidate(tuple(chromosome), None, None), False
    key = tuple(route)
    cached = key in route_cache
    if not cached:
        route_cache[key] = network.evaluate(key)
    return Candidate(tuple(chromosome), key, route_cache[key]), cached


def _tournament(population, rng, size=3):
    return min((population[rng.randrange(len(population))] for _ in range(size)), key=lambda x: x.rank)


def _offspring(population, count, dimension, crossover, mutation, rng):
    children = []
    while len(children) < count:
        a = list(_tournament(population, rng).chromosome)
        b = list(_tournament(population, rng).chromosome)
        if dimension > 1 and rng.random() < crossover:
            left = rng.randrange(dimension)
            right = rng.randrange(left + 1, dimension + 1)
            a[left:right], b[left:right] = b[left:right], a[left:right]
        for chromosome in (a, b):
            for i in range(dimension):
                if rng.random() < mutation:
                    chromosome[i] = rng.randrange(dimension)
            children.append(tuple(chromosome))
            if len(children) == count:
                break
    return children


def _adaptive_rates(population, dimension):
    feasible = [c.result["objective_cny"] for c in population
                if c.result is not None and c.result["constraint_violation"] <= 0]
    if len(feasible) > 1:
        spread = statistics.pstdev(feasible) / max(1.0, abs(statistics.fmean(feasible)))
    else:
        spread = 0.0
    convergence = 1 / (1 + spread)
    return 0.60 + 0.35 * convergence, min(0.50, (1 + 4 * convergence) / max(1, dimension))


def encode_route_seed(network, edge_indices):
    """Encode a continuous route for the priority decoder without NumPy."""
    chromosome = [0] * len(network.edges)
    for offset, edge_index in enumerate(edge_indices):
        chromosome[edge_index] = len(network.edges) - 1 - offset
    if tuple(network.decode(chromosome)) != tuple(edge_indices):
        raise ValueError("route cannot be represented by the priority decoder")
    return tuple(chromosome)


def solve_native_ga(network, population=80, generations=100, seed=42,
                    patience=20, adaptive=True, catastrophe=True,
                    heuristic_seed=False):
    """Run a reproducible priority GA with a fixed evaluation budget.

    Every generation evaluates exactly ``population`` candidates, including a
    restart generation.  A catastrophe preserves the best chromosome and
    replaces all other chromosomes with random candidates.  This makes the
    four ablation modes comparable by candidate evaluations.
    """
    for name, value, minimum in (("population", population, 4), ("generations", generations, 1),
                                 ("patience", patience, 1), ("seed", seed, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    dimension = len(network.edges)
    rng = random.Random(seed)
    route_cache = {}
    route_cache_hits = 0

    def evaluate_many(chromosomes):
        nonlocal route_cache_hits
        evaluated = []
        for chromosome in chromosomes:
            candidate, cached = _evaluate(network, chromosome, route_cache)
            route_cache_hits += int(cached)
            evaluated.append(candidate)
        return evaluated

    chromosomes = [tuple(rng.randrange(dimension) for _ in range(dimension)) for _ in range(population)]
    preprocessing_expanded_states = 0
    if heuristic_seed:
        from .model import solve_state_dijkstra
        heuristic = solve_state_dijkstra(network)
        preprocessing_expanded_states = heuristic.get("expanded_states", 0)
        if heuristic["solution"] is not None:
            chromosomes[0] = encode_route_seed(network, heuristic["solution"]["edge_indices"])
    current = evaluate_many(chromosomes)
    current.sort(key=lambda x: x.rank)
    best = current[0]
    stagnant = 0
    restarts = 0
    trace = []

    for generation in range(generations):
        crossover, mutation = _adaptive_rates(current, dimension) if adaptive else (0.70, 1 / dimension)
        restarted = generation > 0 and catastrophe and stagnant >= patience
        if generation > 0:
            if restarted:
                chromosomes = [best.chromosome]
                chromosomes.extend(tuple(rng.randrange(dimension) for _ in range(dimension))
                                   for _ in range(population - 1))
                offspring = evaluate_many(chromosomes)
                current = sorted(offspring, key=lambda x: x.rank)
                restarts += 1
                if current[0].rank < best.rank:
                    best = current[0]
                stagnant = 0
            else:
                offspring = evaluate_many(_offspring(current, population, dimension, crossover, mutation, rng))
                current = sorted(current + offspring, key=lambda x: x.rank)[:population]
                if current[0].rank < best.rank:
                    best = current[0]
                    stagnant = 0
                else:
                    stagnant += 1
        trace.append({
            "generation": generation,
            "best_violation": best.rank[0],
            "best_objective_cny": best.rank[1],
            "crossover_probability": crossover,
            "mutation_probability": mutation,
            "restarted": restarted,
        })

    variant = "hybrid-seeded" if heuristic_seed and adaptive and catastrophe else (
        "combined" if adaptive and catastrophe else (
        "adaptive-only" if adaptive else "catastrophe-only" if catastrophe else "baseline"
        )
    )
    solution = best.result if best.result is not None and best.result["feasible"] else None
    return {
        "solver": f"native-priority-ga-{variant}",
        "status": "feasible-heuristic" if solution else "no-feasible-route-found",
        "seed": seed,
        "population": population,
        "generations": generations,
        "restart_patience": patience,
        "adaptive": adaptive,
        "catastrophe": catastrophe,
        "heuristic_seed": heuristic_seed,
        "preprocessing_expanded_states": preprocessing_expanded_states,
        "restarts": restarts,
        "candidate_evaluations": population * generations,
        "unique_route_evaluations": len(route_cache),
        "route_cache_hits": route_cache_hits,
        "solution": solution,
        "trace": trace,
    }
