#!/usr/bin/env python3
"""Validate selected allocation-GA controls on held-out random seeds."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import generate_candidate_pools
from routing.allocation_ga import solve_allocation_ga
from routing.synthetic import generate_network
from tools.run_synthetic_allocation_experiment import (
    generate_capacity_resources, generate_portfolio)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks" / "allocation-control-validation"
CONFIGS = {
    "fixed": {"adaptive": False, "catastrophe": False, "patience": 20},
    "legacy-combined": {
        "adaptive": True, "catastrophe": True, "patience": 20,
        "adaptive_control": "fitness-spread-v1", "restart_fraction": 1.0,
    },
    "legacy-hybrid": {
        "adaptive": True, "catastrophe": True, "patience": 20,
        "adaptive_control": "fitness-spread-v1", "restart_fraction": 1.0,
        "heuristic_seed": True, "heuristic_seed_mode": "population",
        "heuristic_seed_strategy": "deadline",
    },
    "selected-combined-v2": {
        "adaptive": True, "catastrophe": True, "patience": 30,
        "adaptive_control": "diversity-v2", "mutation_base": 1.25,
        "mutation_cap": 3.0, "restart_fraction": .25,
    },
    "selected-hybrid-v2": {
        "adaptive": True, "catastrophe": True, "patience": 30,
        "adaptive_control": "diversity-v2", "mutation_base": 1.25,
        "mutation_cap": 3.0, "restart_fraction": .25,
        "heuristic_seed": True, "heuristic_seed_mode": "archive",
        "heuristic_seed_strategy": "opportunity",
    },
}


def percentile(values, fraction):
    values = sorted(values)
    position = fraction * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def run(args):
    config = generate_network(23, .10, 42)
    orders = generate_portfolio(config["nodes"], 48, 31415)
    resources = generate_capacity_resources(config, 250, 4)
    generated = generate_candidate_pools(
        config, orders, resources, top_k=6, max_routes=80,
        route_strategy="beam", beam_width=300)
    solver_args = (generated["orders"], generated["candidate_pools"],
                   generated["departures"], config["carbon_brackets"])
    runs = []
    best_solution = best_record = None
    for name, controls in CONFIGS.items():
        for seed in args.seeds:
            result = solve_allocation_ga(
                *solver_args, population=args.population,
                generations=args.generations, seed=seed, **controls)
            solution = result["solution"] or result["best_infeasible"]
            record = {
                "configuration": name, "seed": seed, "status": result["status"],
                "feasible": result["solution"] is not None,
                "total_cost_cny": solution["total_cost_cny"],
                "emissions_kg": solution["emissions_kg"],
                "constraint_violation": solution["constraint_violation"],
                "restarts": result["restarts"],
                "ga_candidate_evaluations": result["candidate_evaluations"],
                "heuristic_seed_evaluations": result["heuristic_seed_evaluations"],
                "unique_assignment_evaluations": result["unique_assignment_evaluations"],
                "mean_expected_mutated_genes": statistics.fmean(
                    row["expected_mutated_genes"] for row in result["trace"]),
                "mean_population_diversity": statistics.fmean(
                    row["population_diversity"] for row in result["trace"]),
            }
            runs.append(record)
            if result["solution"] is not None and (
                    best_solution is None
                    or solution["total_cost_cny"] < best_solution["total_cost_cny"]):
                best_solution, best_record = solution, record
    summaries = []
    for name, controls in CONFIGS.items():
        selected = [row for row in runs if row["configuration"] == name]
        values = [row["total_cost_cny"] for row in selected if row["feasible"]]
        summaries.append({
            "configuration": name, "runs": len(selected),
            "feasible_runs": len(values), "best_cost_cny": min(values),
            "median_cost_cny": statistics.median(values),
            "mean_cost_cny": statistics.fmean(values),
            "stdev_cost_cny": statistics.pstdev(values),
            "q1_cost_cny": percentile(values, .25),
            "q3_cost_cny": percentile(values, .75),
            "mean_restarts": statistics.fmean(row["restarts"] for row in selected),
            "mean_expected_mutated_genes": statistics.fmean(
                row["mean_expected_mutated_genes"] for row in selected),
            "mean_population_diversity": statistics.fmean(
                row["mean_population_diversity"] for row in selected),
            "mean_heuristic_seed_evaluations": statistics.fmean(
                row["heuristic_seed_evaluations"] for row in selected),
            "controls": controls,
        })
    by_key = {(row["configuration"], row["seed"]): row["total_cost_cny"]
              for row in runs}
    comparisons = []
    for new, old in (("selected-combined-v2", "legacy-combined"),
                     ("selected-hybrid-v2", "legacy-hybrid"),
                     ("selected-combined-v2", "fixed"),
                     ("selected-hybrid-v2", "fixed")):
        differences = [by_key[new, seed] - by_key[old, seed] for seed in args.seeds]
        mean = statistics.fmean(differences)
        stdev = statistics.stdev(differences) if len(differences) > 1 else 0
        # Student-t 0.975 for df=29; approximation is intentionally labelled.
        critical = 2.045 if len(differences) == 30 else 2.0
        half_width = critical * stdev / math.sqrt(len(differences))
        comparisons.append({
            "new": new, "baseline": old,
            "wins": sum(value < 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "losses": sum(value > 0 for value in differences),
            "mean_paired_cost_change_cny": mean,
            "median_paired_cost_change_cny": statistics.median(differences),
            "approx_95_percent_interval_cny": [mean - half_width, mean + half_width],
        })

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(runs[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(runs)
    rows = [{key: value for key, value in row.items() if key != "controls"}
            for row in summaries]
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    report = {
        "experiment_id": "allocation-control-held-out-validation-v1",
        "purpose": "Held-out validation after selection on seeds 30-39.",
        "data_classification": "synthetic_calibrated",
        "seeds": args.seeds,
        "budget": {"population": args.population, "generations": args.generations},
        "summaries": summaries, "paired_comparisons": comparisons,
        "best_observed": {"run": best_record, "solution": best_solution},
    }
    (args.output / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8")
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--population", type=int, default=100)
    parser.add_argument("--generations", type=int, default=150)
    parser.add_argument("--seeds", default=",".join(str(value) for value in range(40, 70)))
    args = parser.parse_args()
    args.seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    return args


if __name__ == "__main__":
    report = run(parse_args())
    print(json.dumps({"best": report["best_observed"]["run"],
                      "comparisons": report["paired_comparisons"]},
                     indent=2, ensure_ascii=False))
