#!/usr/bin/env python3
"""Tune policy-matrix GA controls on seeds isolated from formal reporting."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation_ga import solve_allocation_ga
from routing.synthetic import generate_network
from tools.run_allocation_experiment import write_csv
from tools.run_synthetic_objective_matrix import filter_candidate_pools
from tools.run_synthetic_policy_matrix import (build_instance,
                                               solve_single_trunk_cost_baseline)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "data" / "policy_experiment.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "synthetic-23city-policy-tuning"

MUTATION_CONFIGS = {
    "m050-c100": {"mutation_base": .50, "mutation_cap": 1.00},
    "m075-c125": {"mutation_base": .75, "mutation_cap": 1.25},
    "m100-c150": {"mutation_base": 1.00, "mutation_cap": 1.50},
    "m100-c200": {"mutation_base": 1.00, "mutation_cap": 2.00},
    "m125-c200": {"mutation_base": 1.25, "mutation_cap": 2.00},
    "m125-c250": {"mutation_base": 1.25, "mutation_cap": 2.50},
    "m125-c300-current": {"mutation_base": 1.25, "mutation_cap": 3.00},
    "m150-c300": {"mutation_base": 1.50, "mutation_cap": 3.00},
}

RESTART_CONFIGS = {
    f"p{patience}-r{int(fraction*100):02d}": {
        "patience": patience, "restart_fraction": fraction,
    }
    for patience, fraction in (
        (4, .10), (4, .25), (4, .50),
        (8, .10), (8, .25), (8, .50),
        (12, .10), (12, .25), (12, .50),
        (20, .25),
    )
}

_WORKER_CONTEXT = None


def _initialize_worker(orders, pools, departures, brackets, baseline_emissions,
                       population, generations):
    global _WORKER_CONTEXT
    _WORKER_CONTEXT = (orders, pools, departures, brackets, baseline_emissions,
                       population, generations)


def _solve_task(task):
    family, configuration, controls, scope, reduction, seed = task
    (orders, pools, departures, brackets, baseline_emissions,
     population, generations) = _WORKER_CONTEXT
    cap = None if reduction == 0 else baseline_emissions * (1-reduction)
    result = solve_allocation_ga(
        orders, pools[scope], departures, brackets,
        population=population, generations=generations, seed=seed,
        emission_cap_kg=cap, **controls)
    solution = result["solution"] or result["best_infeasible"]
    return {
        "family": family,
        "configuration": configuration,
        "scope": scope,
        "reduction_target": reduction,
        "seed": seed,
        "feasible": result["solution"] is not None,
        "total_cost_cny": solution["total_cost_cny"],
        "emissions_kg": solution["emissions_kg"],
        "constraint_violation": solution["constraint_violation"],
        "restarts": result["restarts"],
        "candidate_evaluations": result["candidate_evaluations"],
    }


def run_tasks(generated, brackets, baseline_emissions, population, generations,
              tasks, workers):
    pools = {scope: filter_candidate_pools(generated["candidate_pools"], scope)
             for scope in sorted({task[3] for task in tasks})}
    initargs = (generated["orders"], pools, generated["departures"], brackets,
                baseline_emissions, population, generations)
    if workers == 1:
        _initialize_worker(*initargs)
        return list(map(_solve_task, tasks))
    with ProcessPoolExecutor(max_workers=workers, initializer=_initialize_worker,
                             initargs=initargs) as executor:
        return list(executor.map(_solve_task, tasks, chunksize=1))


def summarize(rows, controls_by_name):
    summaries = []
    for name, controls in controls_by_name.items():
        selected = [row for row in rows if row["configuration"] == name]
        feasible = [row for row in selected if row["feasible"]]
        costs = [row["total_cost_cny"] for row in feasible]
        summaries.append({
            "configuration": name,
            "runs": len(selected),
            "feasible_runs": len(feasible),
            "median_cost_cny": statistics.median(costs) if costs else None,
            "mean_cost_cny": statistics.fmean(costs) if costs else None,
            "best_cost_cny": min(costs) if costs else None,
            "mean_restarts": statistics.fmean(
                row["restarts"] for row in selected) if selected else None,
            "controls": controls,
        })
    return summaries


def ranking(summary):
    infeasible = summary["runs"] - summary["feasible_runs"]
    return (infeasible, summary["median_cost_cny"] or float("inf"),
            summary["mean_cost_cny"] or float("inf"),
            summary["best_cost_cny"] or float("inf"))


def tuning_tasks(family, configs, scopes, target, seeds):
    return [(family, name, controls, scope, target, seed)
            for name, controls in configs.items()
            for scope in scopes for seed in seeds]


def run(args):
    design = json.loads(args.design.read_text(encoding="utf-8"))
    extension = design["synthetic_23city_extension"]
    network = extension["network"]
    base = generate_network(network["nodes"], network["density"], network["seed"])
    config, generated = build_instance(
        base, design, "central", "balanced", 97.49,
        top_k=network["top_k"], candidate_routes=network["candidate_routes"],
        beam_width=network["beam_width"])
    baseline, _ = solve_single_trunk_cost_baseline(
        generated, config["carbon_brackets"])
    baseline_emissions = baseline["emissions_kg"]

    base_adaptive = {name: {
        "adaptive": True, "catastrophe": False, "heuristic_seed": False,
        "adaptive_control": "diversity-v2", "patience": 30, **values,
    } for name, values in MUTATION_CONFIGS.items()}
    adaptive_runs = run_tasks(
        generated, config["carbon_brackets"], baseline_emissions,
        args.population, args.generations,
        tuning_tasks("adaptive", base_adaptive, args.scopes,
                     args.tuning_target, args.tuning_seeds), args.workers)
    adaptive_summary = summarize(adaptive_runs, base_adaptive)
    top_adaptive = sorted(adaptive_summary, key=ranking)[:3]

    base_catastrophe = {name: {
        "adaptive": False, "catastrophe": True, "heuristic_seed": False,
        **values,
    } for name, values in RESTART_CONFIGS.items()}
    catastrophe_runs = run_tasks(
        generated, config["carbon_brackets"], baseline_emissions,
        args.population, args.generations,
        tuning_tasks("catastrophe", base_catastrophe, args.scopes,
                     args.tuning_target, args.tuning_seeds), args.workers)
    catastrophe_summary = summarize(catastrophe_runs, base_catastrophe)
    top_catastrophe = sorted(catastrophe_summary, key=ranking)[:3]

    combined_configs = {}
    for mutation in top_adaptive:
        mutation_values = MUTATION_CONFIGS[mutation["configuration"]]
        for restart in top_catastrophe:
            restart_values = RESTART_CONFIGS[restart["configuration"]]
            name = mutation["configuration"] + "-" + restart["configuration"]
            combined_configs[name] = {
                "adaptive": True, "catastrophe": True,
                "heuristic_seed": False, "adaptive_control": "diversity-v2",
                **mutation_values, **restart_values,
            }
    combined_runs = run_tasks(
        generated, config["carbon_brackets"], baseline_emissions,
        args.population, args.generations,
        tuning_tasks("combined", combined_configs, args.scopes,
                     args.tuning_target, args.tuning_seeds), args.workers)
    combined_summary = summarize(combined_runs, combined_configs)

    selected_adaptive = min(adaptive_summary, key=ranking)
    selected_catastrophe = min(catastrophe_summary, key=ranking)
    selected_combined = min(combined_summary, key=ranking)
    policy_variants = {
        "fixed": {"adaptive": False, "catastrophe": False,
                  "heuristic_seed": False},
        "adaptive": selected_adaptive["controls"],
        "catastrophe": selected_catastrophe["controls"],
        "combined": selected_combined["controls"],
        "hybrid-seeded": {
            **selected_combined["controls"], "heuristic_seed": True,
            "heuristic_seed_mode": "archive",
            "heuristic_seed_strategy": "opportunity",
        },
    }
    validation_tasks = [
        ("validation", method, controls, scope, target, seed)
        for method, controls in policy_variants.items()
        for scope in args.scopes for target in args.validation_targets
        for seed in args.validation_seeds
    ]
    validation_runs = run_tasks(
        generated, config["carbon_brackets"], baseline_emissions,
        args.population, args.generations, validation_tasks, args.workers)
    validation_summary = summarize(validation_runs, policy_variants)

    args.output.mkdir(parents=True, exist_ok=True)
    tuning_runs = adaptive_runs + catastrophe_runs + combined_runs
    tuning_summary = adaptive_summary + catastrophe_summary + combined_summary
    write_csv(args.output / "tuning-runs.csv", tuning_runs)
    write_csv(args.output / "tuning-summary.csv", [
        {key: value for key, value in row.items() if key != "controls"}
        for row in tuning_summary])
    write_csv(args.output / "validation-runs.csv", validation_runs)
    write_csv(args.output / "validation-summary.csv", [
        {key: value for key, value in row.items() if key != "controls"}
        for row in validation_summary])
    report = {
        "experiment_id": "synthetic-23city-policy-ga-tuning-v1",
        "data_classification": "policy_calibrated_synthetic",
        "separation": {
            "tuning_seeds": args.tuning_seeds,
            "validation_seeds": args.validation_seeds,
            "formal_report_seeds": list(range(30)),
        },
        "budget": {"population": args.population,
                   "generations": args.generations},
        "tuning_scenarios": {"scopes": args.scopes,
                             "reduction_target": args.tuning_target},
        "validation_scenarios": {"scopes": args.scopes,
                                 "reduction_targets": args.validation_targets},
        "emissions_target_reference": (
            "per-order minimum-cost single-trunk-mode emissions"),
        "selection_rule": "fewest infeasible runs, then lowest median, mean and best cost",
        "selected_policy_variants": policy_variants,
        "selected_configuration_names": {
            "adaptive": selected_adaptive["configuration"],
            "catastrophe": selected_catastrophe["configuration"],
            "combined": selected_combined["configuration"],
            "hybrid-seeded": selected_combined["configuration"] + "+opportunity-archive",
        },
        "tuning_summary": tuning_summary,
        "validation_summary": validation_summary,
        "claims": [
            "Tuning and validation seeds are disjoint from formal report seeds 0-29.",
            "The selected controls are instance-family settings, not universal GA optima.",
            "All topology, order and capacity inputs remain policy-calibrated synthetic data.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    validation_lines = "\n".join(
        f"| {row['configuration']} | {row['feasible_runs']}/{row['runs']} | "
        f"{row['median_cost_cny']:,.2f} | {row['mean_cost_cny']:,.2f} | "
        f"{row['mean_restarts']:.2f} |"
        for row in validation_summary)
    (args.output / "README.md").write_text(f"""# Synthetic 23-city policy GA tuning

Generated by `python3 -B tools/tune_synthetic_policy_ga.py`.

Mutation controls and restart controls are selected on seeds {args.tuning_seeds[0]}--{args.tuning_seeds[-1]}. The resulting five variants are evaluated on disjoint seeds {args.validation_seeds[0]}--{args.validation_seeds[-1]}. Formal report seeds 0--29 are not used for either selection step.

Selection and validation deliberately use the uncapped cost objective so hyperparameters are chosen on one fixed objective before the active 9.5%, 20% and 30% targets are evaluated in the formal matrix.

Selected controls:

```json
{json.dumps(policy_variants, ensure_ascii=False, indent=2)}
```

Held-out validation:

| Variant | Feasible runs | Median cost (CNY) | Mean cost (CNY) | Mean restarts |
| --- | ---: | ---: | ---: | ---: |
{validation_lines}

These are bounded hyperparameter-search results for the policy-calibrated synthetic instance family, not universal algorithm rankings.
""", encoding="utf-8")
    return report


def parse_ints(value):
    return [int(item) for item in value.split(",") if item.strip()]


def parse_floats(value):
    return [float(item) for item in value.split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=DESIGN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=60)
    parser.add_argument("--scopes", default="single-mode-per-order,multimodal-enabled")
    parser.add_argument("--tuning-target", type=float, default=0)
    parser.add_argument("--validation-targets", default="0")
    parser.add_argument("--tuning-seeds", default=",".join(str(x) for x in range(100, 108)))
    parser.add_argument("--validation-seeds", default=",".join(str(x) for x in range(110, 130)))
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    args.scopes = [item for item in args.scopes.split(",") if item.strip()]
    args.validation_targets = parse_floats(args.validation_targets)
    args.tuning_seeds = parse_ints(args.tuning_seeds)
    args.validation_seeds = parse_ints(args.validation_seeds)
    return args


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "selected": result["selected_configuration_names"],
        "validation": result["validation_summary"],
    }, indent=2, ensure_ascii=False))
