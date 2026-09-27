"""Genetic allocation of order batches to route-departure candidates."""

from __future__ import annotations

import math
import random
import statistics

from .allocation import (assignment_rank, evaluate_assignment,
                         solve_greedy_allocation,
                         solve_opportunity_greedy_allocation)


def _fitness_spread_rates(population, dimension):
    """Original aggressive controller retained for reproducible comparison."""
    feasible = [row[1]["total_cost_cny"] for row in population if row[1]["feasible"]]
    if len(feasible) > 1:
        spread = statistics.pstdev(feasible) / max(1.0, abs(statistics.fmean(feasible)))
    else:
        spread = 0.0
    convergence = 1 / (1 + spread)
    return 0.60 + 0.35 * convergence, min(0.50, (1 + 4 * convergence) / max(1, dimension))


def _genotype_diversity(population, dimension):
    """Mean locus impurity: zero for clones, larger for varied gene values."""
    if not population or dimension == 0:
        return 0.0
    size = len(population)
    locus_values = []
    for index in range(dimension):
        counts = {}
        for chromosome, _ in population:
            value = chromosome[index]
            counts[value] = counts.get(value, 0) + 1
        locus_values.append(1 - max(counts.values()) / size)
    return statistics.fmean(locus_values)


def _diversity_rates(population, dimension, stagnant, patience, *,
                     mutation_base=1.0, mutation_cap=2.5):
    """Bound adaptation by an interpretable expected mutated-gene budget."""
    diversity = _genotype_diversity(population, dimension)
    low_diversity = max(0.0, (0.25 - diversity) / 0.25)
    stagnation = min(1.0, stagnant / patience)
    pressure = max(low_diversity, stagnation)
    expected_mutations = min(
        mutation_cap, mutation_base + 0.75 * low_diversity + 0.75 * stagnation)
    crossover = 0.72 + 0.13 * pressure
    mutation = min(0.50, expected_mutations / max(1, dimension))
    return crossover, mutation, diversity, expected_mutations


def _tournament(population, rng, size=3):
    return min((population[rng.randrange(len(population))] for _ in range(size)),
               key=lambda row: assignment_rank(row[1]))


def _children(population, count, option_counts, crossover, mutation, rng):
    children = []
    dimension = len(option_counts)
    while len(children) < count:
        first = list(_tournament(population, rng)[0])
        second = list(_tournament(population, rng)[0])
        if dimension > 1 and rng.random() < crossover:
            left = rng.randrange(dimension)
            right = rng.randrange(left + 1, dimension + 1)
            first[left:right], second[left:right] = second[left:right], first[left:right]
        for chromosome in (first, second):
            for index, options in enumerate(option_counts):
                if rng.random() < mutation:
                    chromosome[index] = rng.randrange(options)
            children.append(tuple(chromosome))
            if len(children) == count:
                break
    return children


def _capacity_feasible_chromosome(orders, candidate_pools, departures, rng):
    """Build a varied chromosome without knowingly overbooking a departure.

    This is common constraint handling, not an objective-value seed. Candidate
    order is randomized and only local feasibility plus remaining capacity is
    considered. The hybrid variant separately injects the cost-aware greedy
    solution.
    """
    capacities = {row["departure_id"]: row for row in departures}
    usage = {key: {"tonnes": 0.0, "shipment_units": 0.0} for key in capacities}
    genes = [None] * len(orders)
    order_indices = list(range(len(orders)))
    rng.shuffle(order_indices)
    order_indices.sort(key=lambda index: (
        sum(candidate["intrinsic_violation"] == 0 and candidate["lateness_hours"] == 0
            for candidate in candidate_pools[orders[index]["order_id"]]),
        orders[index]["deadline_hours"],
    ))
    for index in order_indices:
        pool = candidate_pools[orders[index]["order_id"]]
        choices = list(range(len(pool)))
        rng.shuffle(choices)
        selected = None
        for gene in choices:
            candidate = pool[gene]
            if candidate["intrinsic_violation"] or candidate["lateness_hours"]:
                continue
            fits = True
            for claim in candidate["capacity_claims"]:
                capacity = capacities.get(claim["departure_id"])
                if capacity is None:
                    fits = False
                    break
                used = usage[claim["departure_id"]]
                if (capacity.get("capacity_tonnes") is not None
                        and used["tonnes"] + claim["tonnes"] > capacity["capacity_tonnes"]):
                    fits = False
                if (capacity.get("capacity_units") is not None
                        and used["shipment_units"] + claim["shipment_units"] > capacity["capacity_units"]):
                    fits = False
            if fits:
                selected = gene
                break
        if selected is None:
            selected = rng.randrange(len(pool))
        genes[index] = selected
        for claim in pool[selected]["capacity_claims"]:
            if claim["departure_id"] in usage:
                usage[claim["departure_id"]]["tonnes"] += claim["tonnes"]
                usage[claim["departure_id"]]["shipment_units"] += claim["shipment_units"]
    return tuple(genes)


def _low_emission_feasible_chromosome(orders, candidate_pools, departures, rng):
    """Construct one capacity-aware low-emission seed for hard-cap runs.

    This is common constraint handling used by every GA variant when an
    emissions cap is active.  It does not replace the hybrid variant's
    opportunity-cost archive and is not an optimality claim.
    """
    capacities = {row["departure_id"]: row for row in departures}
    usage = {key: {"tonnes": 0.0, "shipment_units": 0.0} for key in capacities}
    genes = [None] * len(orders)
    order_indices = list(range(len(orders)))
    rng.shuffle(order_indices)
    order_indices.sort(key=lambda index: (
        sum(candidate["intrinsic_violation"] == 0 and candidate["lateness_hours"] == 0
            for candidate in candidate_pools[orders[index]["order_id"]]),
        orders[index]["deadline_hours"],
    ))
    for index in order_indices:
        pool = candidate_pools[orders[index]["order_id"]]
        tie_breakers = {gene: rng.random() for gene in range(len(pool))}
        choices = sorted(range(len(pool)), key=lambda gene: (
            pool[gene]["intrinsic_violation"], pool[gene]["lateness_hours"],
            pool[gene]["emissions_kg"], pool[gene]["surrogate_cost_cny"],
            tie_breakers[gene]))
        selected = None
        for gene in choices:
            candidate = pool[gene]
            if candidate["intrinsic_violation"] or candidate["lateness_hours"]:
                continue
            if all(
                claim["departure_id"] in capacities
                and (capacities[claim["departure_id"]].get("capacity_tonnes") is None
                     or usage[claim["departure_id"]]["tonnes"] + claim["tonnes"]
                     <= capacities[claim["departure_id"]]["capacity_tonnes"])
                and (capacities[claim["departure_id"]].get("capacity_units") is None
                     or usage[claim["departure_id"]]["shipment_units"] + claim["shipment_units"]
                     <= capacities[claim["departure_id"]]["capacity_units"])
                for claim in candidate["capacity_claims"]
            ):
                selected = gene
                break
        if selected is None:
            selected = choices[0]
        genes[index] = selected
        for claim in pool[selected]["capacity_claims"]:
            if claim["departure_id"] in usage:
                usage[claim["departure_id"]]["tonnes"] += claim["tonnes"]
                usage[claim["departure_id"]]["shipment_units"] += claim["shipment_units"]
    return tuple(genes)


def solve_allocation_ga(orders, candidate_pools, departures, brackets, *,
                        population=80, generations=100, seed=42, patience=30,
                        adaptive=True, catastrophe=True, heuristic_seed=False,
                        adaptive_control="diversity-v2", restart_fraction=.25,
                        heuristic_seed_mode="archive", mutation_base=1.25,
                        mutation_cap=3.0, heuristic_seed_strategy="opportunity",
                        emission_cap_kg=None):
    """Solve the globally coupled allocation with a fixed evaluation budget."""
    for name, value, minimum in (("population", population, 4),
                                 ("generations", generations, 1),
                                 ("seed", seed, 0), ("patience", patience, 1)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if adaptive_control not in {"fitness-spread-v1", "diversity-v2"}:
        raise ValueError("adaptive_control must be fitness-spread-v1 or diversity-v2")
    if (isinstance(restart_fraction, bool) or not isinstance(restart_fraction, (int, float))
            or not math.isfinite(restart_fraction) or not 0 < restart_fraction <= 1):
        raise ValueError("restart_fraction must be in (0, 1]")
    if heuristic_seed_mode not in {"population", "archive"}:
        raise ValueError("heuristic_seed_mode must be population or archive")
    if heuristic_seed_strategy not in {"deadline", "opportunity"}:
        raise ValueError("heuristic_seed_strategy must be deadline or opportunity")
    for name, value in (("mutation_base", mutation_base), ("mutation_cap", mutation_cap)):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError(f"{name} must be positive and finite")
    if mutation_base > mutation_cap:
        raise ValueError("mutation_base cannot exceed mutation_cap")
    option_counts = [len(candidate_pools.get(row["order_id"], ())) for row in orders]
    if any(count == 0 for count in option_counts):
        return {"solver": "allocation-ga", "status": "infeasible-no-candidates",
                "solution": None, "candidate_evaluations": 0, "trace": []}
    rng = random.Random(seed)
    cache = {}
    cache_hits = 0

    def evaluate(chromosome):
        nonlocal cache_hits
        key = tuple(chromosome)
        if key in cache:
            cache_hits += 1
        else:
            cache[key] = evaluate_assignment(
                orders, candidate_pools, departures, key, brackets,
                emission_cap_kg=emission_cap_kg)
        return key, cache[key]

    chromosomes = [_capacity_feasible_chromosome(
        orders, candidate_pools, departures, rng) for _ in range(population)]
    constraint_seeded = emission_cap_kg is not None
    if constraint_seeded:
        chromosomes[0] = _low_emission_feasible_chromosome(
            orders, candidate_pools, departures, rng)
    greedy_evaluations = 0
    greedy_pair = None
    if heuristic_seed:
        greedy_solver = (solve_opportunity_greedy_allocation
                         if heuristic_seed_strategy == "opportunity"
                         else solve_greedy_allocation)
        greedy = greedy_solver(
            orders, candidate_pools, departures, brackets,
            emission_cap_kg=emission_cap_kg)
        greedy_chromosome = tuple(greedy["solution"]["chromosome"])
        if heuristic_seed_mode == "population":
            chromosomes[0] = greedy_chromosome
        else:
            greedy_pair = evaluate(greedy_chromosome)
        greedy_evaluations = greedy["candidate_evaluations"]
    current = sorted((evaluate(row) for row in chromosomes),
                     key=lambda row: assignment_rank(row[1]))
    best = min((current[0], greedy_pair) if greedy_pair else (current[0],),
               key=lambda row: assignment_rank(row[1]))
    stagnant = 0
    restarts = 0
    trace = []
    for generation in range(generations):
        diversity = _genotype_diversity(current, len(option_counts))
        if adaptive and adaptive_control == "fitness-spread-v1":
            crossover, mutation = _fitness_spread_rates(current, len(option_counts))
            expected_mutations = mutation * len(option_counts)
        elif adaptive:
            crossover, mutation, diversity, expected_mutations = _diversity_rates(
                current, len(option_counts), stagnant, patience,
                mutation_base=mutation_base, mutation_cap=mutation_cap)
        else:
            crossover, mutation = 0.70, 1 / len(option_counts)
            expected_mutations = 1.0
        restarted = generation > 0 and catastrophe and stagnant >= patience
        if generation > 0:
            if restarted:
                replace_count = max(1, round(population * restart_fraction))
                keep_count = population - replace_count
                elites = []
                seen = set()
                for row in current:
                    if row[0] not in seen:
                        seen.add(row[0])
                        elites.append(row[0])
                    if len(elites) == keep_count:
                        break
                chromosomes = elites + [
                    _capacity_feasible_chromosome(
                        orders, candidate_pools, departures, rng)
                    for _ in range(population - len(elites))
                ]
                current = sorted((evaluate(row) for row in chromosomes),
                                 key=lambda row: assignment_rank(row[1]))
                restarts += 1
                stagnant = 0
            else:
                offspring = [evaluate(row) for row in _children(
                    current, population, option_counts, crossover, mutation, rng)]
                current = sorted(current + offspring,
                                 key=lambda row: assignment_rank(row[1]))[:population]
            if assignment_rank(current[0][1]) < assignment_rank(best[1]):
                best = current[0]
                stagnant = 0
            elif not restarted:
                stagnant += 1
        trace.append({
            "generation": generation,
            "candidate_evaluations": (generation + 1) * population,
            "best_violation": best[1]["constraint_violation"],
            "best_objective_cny": best[1]["total_cost_cny"],
            "crossover_probability": crossover,
            "mutation_probability": mutation,
            "expected_mutated_genes": expected_mutations,
            "population_diversity": diversity,
            "population_best_objective_cny": current[0][1]["total_cost_cny"],
            "stagnant_generations": stagnant,
            "restarted": restarted,
        })
    variant = "hybrid-seeded" if heuristic_seed and adaptive and catastrophe else (
        "combined" if adaptive and catastrophe else
        "adaptive" if adaptive else "catastrophe" if catastrophe else "fixed")
    solution = best[1] if best[1]["feasible"] else None
    return {
        "solver": f"allocation-ga-{variant}",
        "variant": variant,
        "status": "feasible-heuristic" if solution else "no-feasible-allocation-found",
        "seed": seed,
        "population": population,
        "generations": generations,
        "restart_patience": patience,
        "adaptive": adaptive,
        "adaptive_control": adaptive_control,
        "catastrophe": catastrophe,
        "restart_fraction": restart_fraction,
        "heuristic_seed": heuristic_seed,
        "heuristic_seed_mode": heuristic_seed_mode,
        "heuristic_seed_strategy": heuristic_seed_strategy,
        "mutation_base": mutation_base,
        "mutation_cap": mutation_cap,
        "emission_cap_kg": emission_cap_kg,
        "constraint_seeded": constraint_seeded,
        "heuristic_seed_evaluations": greedy_evaluations,
        "candidate_evaluations": population * generations,
        "unique_assignment_evaluations": len(cache),
        "assignment_cache_hits": cache_hits,
        "restarts": restarts,
        "solution": solution,
        "best_infeasible": None if solution else best[1],
        "trace": trace,
    }
