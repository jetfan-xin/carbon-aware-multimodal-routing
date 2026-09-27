#!/usr/bin/env python3
"""Run and visualize a reproducible real-Geatpy ablation experiment."""

import argparse
import csv
import json
import math
from pathlib import Path
import platform
import statistics
import sys

import geatpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.geatpy_solver import solve_geatpy
from routing.model import Network, solve_state_dijkstra
from routing.pipeline import analyze_connectivity, write_route_svg
from routing.synthetic import generate_network


VARIANTS = (
    ("fixed", False, False, False),
    ("adaptive", True, False, False),
    ("catastrophe", False, True, False),
    ("combined", True, True, False),
    ("hybrid-seeded", True, True, True),
)
COLORS = {
    "fixed": "#4c78a8", "adaptive": "#f58518",
    "catastrophe": "#54a24b", "combined": "#b279a2", "hybrid-seeded": "#e45756",
}


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def summarize(runs):
    fixed = {row["seed"]: row["objective_cny"] for row in runs if row["variant"] == "fixed"}
    summaries = []
    for name, adaptive, catastrophe, heuristic_seed in VARIANTS:
        selected = [row for row in runs if row["variant"] == name]
        feasible = [row for row in selected if row["objective_cny"] is not None]
        objectives = [row["objective_cny"] for row in feasible]
        evaluations = [row["candidate_evaluations"] for row in selected]
        paired = [(fixed[row["seed"]] - row["objective_cny"]) / fixed[row["seed"]] * 100
                  for row in feasible if fixed.get(row["seed"]) is not None]
        tolerance = 1e-9
        summaries.append({
            "variant": name, "adaptive": adaptive, "catastrophe": catastrophe,
            "heuristic_seed": heuristic_seed,
            "runs": len(selected), "feasible_runs": len(feasible),
            "feasible_rate": len(feasible) / len(selected),
            "objective_min_cny": min(objectives), "objective_mean_cny": statistics.fmean(objectives),
            "objective_median_cny": statistics.median(objectives),
            "objective_q1_cny": percentile(objectives, 0.25),
            "objective_q3_cny": percentile(objectives, 0.75),
            "objective_stdev_cny": statistics.pstdev(objectives),
            "candidate_evaluations_mean": statistics.fmean(evaluations),
            "candidate_evaluations_min": min(evaluations),
            "candidate_evaluations_max": max(evaluations),
            "total_restarts": sum(row["restarts"] for row in selected),
            "paired_vs_fixed_mean_percent": statistics.fmean(paired),
            "paired_vs_fixed_median_percent": statistics.median(paired),
            "paired_wins_ties_losses": {
                "wins": sum(value > tolerance for value in paired),
                "ties": sum(abs(value) <= tolerance for value in paired),
                "losses": sum(value < -tolerance for value in paired),
            },
        })
    return summaries


def save_figures(output, runs):
    matplotlib.rcParams.update({"svg.hashsalt": "carbon-routing-geatpy", "font.size": 10})
    metadata = {"Date": None, "Creator": "carbon-aware-multimodal-routing"}

    fig, axis = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    groups = [[row["objective_cny"] for row in runs if row["variant"] == name] for name, _, _, _ in VARIANTS]
    boxes = axis.boxplot(groups, labels=[name for name, _, _, _ in VARIANTS], patch_artist=True,
                         showmeans=True, meanline=True)
    for box, (name, _, _, _) in zip(boxes["boxes"], VARIANTS):
        box.set_facecolor(COLORS[name]); box.set_alpha(0.28)
    for position, ((name, _, _, _), values) in enumerate(zip(VARIANTS, groups), 1):
        offsets = [((i % 7) - 3) * 0.018 for i in range(len(values))]
        axis.scatter([position + x for x in offsets], values, s=15, alpha=0.62, color=COLORS[name])
    axis.set_title("Real Geatpy final-objective distribution across seeds")
    axis.set_xlabel("GA variant")
    axis.set_ylabel("Final objective (CNY; lower is better)")
    axis.grid(axis="y", alpha=0.25)
    fig.savefig(output / "objective-distribution.svg", format="svg", metadata=metadata)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    for name, _, _, _ in VARIANTS:
        selected = [row for row in runs if row["variant"] == name]
        axis.scatter([row["candidate_evaluations"] for row in selected],
                     [row["objective_cny"] for row in selected], label=name,
                     color=COLORS[name], s=24, alpha=0.68)
    axis.set_title("Final objective versus actual candidate evaluations")
    axis.set_xlabel("Candidate evaluations, including restart injections")
    axis.set_ylabel("Final objective (CNY; lower is better)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncols=2)
    fig.savefig(output / "evaluation-efficiency.svg", format="svg", metadata=metadata)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
    for name, _, _, _ in VARIANTS:
        traces = [row["trace"] for row in runs if row["variant"] == name]
        generations = range(len(traces[0]))
        medians, q1, q3 = [], [], []
        for generation in generations:
            values = [trace[generation]["best_objective_cny"] for trace in traces]
            medians.append(statistics.median(values))
            q1.append(percentile(values, 0.25)); q3.append(percentile(values, 0.75))
        axis.plot(list(generations), medians, label=name, color=COLORS[name], linewidth=2)
        axis.fill_between(list(generations), q1, q3, color=COLORS[name], alpha=0.12)
    axis.set_title("Median convergence with interquartile bands")
    axis.set_xlabel("Generation")
    axis.set_ylabel("Best-so-far objective (CNY; lower is better)")
    axis.grid(alpha=0.25)
    axis.legend(frameon=False, ncols=2)
    fig.savefig(output / "convergence.svg", format="svg", metadata=metadata)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", default=",".join(str(i) for i in range(30)))
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--generations", type=int, default=40)
    parser.add_argument("--patience", type=int, default=20)
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be a nonempty unique comma-separated list")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    config = generate_network(node_count=23, density=1.0, seed=42)
    config["risk_weight"] = 0.30
    network = Network(config)
    connectivity = analyze_connectivity(network)
    dijkstra = solve_state_dijkstra(network)
    runs = []
    for seed in seeds:
        for name, adaptive, catastrophe, heuristic_seed in VARIANTS:
            result = solve_geatpy(network, population=args.population, generations=args.generations,
                                  seed=seed, patience=args.patience,
                                  adaptive=adaptive, catastrophe=catastrophe,
                                  heuristic_seed=heuristic_seed)
            solution = result["solution"]
            runs.append({
                "seed": seed, "variant": name, "adaptive": adaptive, "catastrophe": catastrophe,
                "heuristic_seed": heuristic_seed,
                "status": result["status"], "objective_cny": solution["objective_cny"] if solution else None,
                "constraint_violation": solution["constraint_violation"] if solution else None,
                "candidate_evaluations": result["route_evaluations"], "restarts": result["restarts"],
                "edge_indices": solution["edge_indices"] if solution else None,
                "route": solution["route"] if solution else None,
                "modes": solution["modes"] if solution else None,
                "trace": result["trace"],
            })
    summaries = summarize(runs)
    best = min((row for row in runs if row["objective_cny"] is not None), key=lambda row: row["objective_cny"])
    best_solution = network.evaluate(best["edge_indices"])
    report = {
        "experiment_id": "real-geatpy-23city-ablation-v1",
        "data_classification": "synthetic_calibrated",
        "scope": "One generated 23-city/754-edge network; not historical orders or production traffic.",
        "solver": "Geatpy 2.7.0 soea_SEGA_templet through the maintained routing integration",
        "environment": {"python": platform.python_version(), "machine": platform.machine(),
                        "geatpy": geatpy.__version__, "numpy": numpy.__version__,
                        "matplotlib": matplotlib.__version__},
        "network": {"nodes": len(network.nodes), "edges": len(network.edges),
                    "network_seed": 42, "origin": network.origin, "destination": network.destination,
                    "connectivity": connectivity},
        "objective": {"components": ["transport", "transfer", "time-window", "carbon"],
                      "risk_weight": config["risk_weight"],
                      "form": "expected_cost + risk_weight * (worst_cost - expected_cost)"},
        "search": {"seeds": seeds, "population": args.population, "generations": args.generations,
                   "patience": args.patience, "variants": [row[0] for row in VARIANTS]},
        "dijkstra_baseline": {"status": dijkstra["status"],
                              "objective_cny": dijkstra["solution"]["objective_cny"] if dijkstra["solution"] else None,
                              "note": "Deterministic additive-weight heuristic, not an exact optimum."},
        "summary": summaries, "best_run": {key: best[key] for key in
                                             ("seed", "variant", "objective_cny", "candidate_evaluations",
                                              "restarts", "edge_indices", "route", "modes")},
        "best_solution": best_solution,
        "warnings": [
            "GA results are heuristic and do not prove global optimality.",
            "Catastrophe variants perform extra evaluations when injecting random individuals; compare both quality and evaluation counts.",
            "No claim is made about historical competition performance, enterprise data or deployed savings.",
        ],
        "runs": runs,
    }
    (args.output_dir / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    with (args.output_dir / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("seed", "variant", "status", "objective_cny",
                                                    "constraint_violation", "candidate_evaluations",
                                                    "restarts", "route", "modes"), lineterminator="\n")
        writer.writeheader()
        for row in runs:
            writer.writerow({key: json.dumps(row[key], ensure_ascii=False) if key in ("route", "modes") else row[key]
                             for key in writer.fieldnames})
    save_figures(args.output_dir, runs)
    write_route_svg(network, best_solution, args.output_dir / "best-route.svg")
    for svg_path in args.output_dir.glob("*.svg"):
        lines = svg_path.read_text(encoding="utf-8").splitlines()
        svg_path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(args.output_dir), "runs": len(runs),
                      "best_run": report["best_run"], "summary": summaries}, indent=2))


if __name__ == "__main__":
    main()
