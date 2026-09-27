#!/usr/bin/env python3
"""Benchmark global order allocation on the calibrated facility micro-network."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_exact_allocation, solve_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.facility_network import facility_case_config


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTANCE = ROOT / "data" / "allocation_instances" / "cq_shanghai_facility_scenario.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "global-order-allocation"
VARIANTS = {
    "fixed": {"adaptive": False, "catastrophe": False, "heuristic_seed": False},
    "adaptive": {"adaptive": True, "catastrophe": False, "heuristic_seed": False,
                 "adaptive_control": "diversity-v2", "mutation_base": 1.25,
                 "mutation_cap": 3.0},
    "catastrophe": {"adaptive": False, "catastrophe": True, "heuristic_seed": False,
                    "restart_fraction": .25},
    "combined": {"adaptive": True, "catastrophe": True, "heuristic_seed": False,
                 "adaptive_control": "diversity-v2", "mutation_base": 1.25,
                 "mutation_cap": 3.0, "restart_fraction": .25},
    "hybrid-seeded": {"adaptive": True, "catastrophe": True, "heuristic_seed": True,
                      "adaptive_control": "diversity-v2", "mutation_base": 1.25,
                      "mutation_cap": 3.0, "restart_fraction": .25,
                      "heuristic_seed_mode": "archive",
                      "heuristic_seed_strategy": "opportunity"},
}
COLORS = {"greedy": "#777777", "fixed": "#4c78a8", "adaptive": "#f58518",
          "catastrophe": "#54a24b", "combined": "#e45756", "hybrid-seeded": "#9467bd"}


def write_csv(path, rows, fieldnames=None):
    if not rows and not fieldnames:
        raise ValueError("fieldnames are required for an empty CSV")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames or list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg(title, body, *, width=1080, height=650, metadata=None):
    description = html.escape(json.dumps(metadata or {}, ensure_ascii=False))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>'
            f'<desc>{description}</desc><rect width="100%" height="100%" fill="white"/>'
            f'<text x="45" y="40" font-family="sans-serif" font-size="21" font-weight="bold">'
            f'{html.escape(title)}</text>{body}</svg>\n')


def percentile(values, fraction):
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def method_summary(runs):
    rows = []
    for method in ["greedy", *VARIANTS]:
        selected = [row for row in runs if row["method"] == method]
        feasible = [row for row in selected if row["feasible"]]
        objectives = [row["total_cost_cny"] for row in feasible]
        rows.append({
            "method": method,
            "runs": len(selected),
            "feasible_runs": len(feasible),
            "feasible_rate": len(feasible) / len(selected),
            "best_cost_cny": min(objectives) if objectives else None,
            "median_cost_cny": statistics.median(objectives) if objectives else None,
            "mean_cost_cny": statistics.fmean(objectives) if objectives else None,
            "stdev_cost_cny": statistics.pstdev(objectives) if len(objectives) > 1 else 0,
            "q1_cost_cny": percentile(objectives, .25) if objectives else None,
            "q3_cost_cny": percentile(objectives, .75) if objectives else None,
            "mean_restarts": statistics.fmean(row["restarts"] for row in selected),
            "ga_candidate_evaluations": selected[0]["ga_candidate_evaluations"],
            "mean_total_solver_evaluations": statistics.fmean(
                row["total_solver_evaluations"] for row in selected),
        })
    return rows


def write_objective_chart(path, summaries):
    data = [row for row in summaries if row["best_cost_cny"] is not None]
    low = min(row["best_cost_cny"] for row in data)
    high = max(row["q3_cost_cny"] for row in data)
    span = max(1, high - low)
    left, top, width, height = 105, 90, 1050, 440
    body = [f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" stroke="#333"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+height}" stroke="#333"/>']
    for index, row in enumerate(data):
        x = left + (index + .5) * width / len(data)
        y = lambda value: top + height - (value - low) / span * height
        q1, median, q3, best = (y(row[key]) for key in (
            "q1_cost_cny", "median_cost_cny", "q3_cost_cny", "best_cost_cny"))
        body.append(f'<line x1="{x:.1f}" y1="{best:.1f}" x2="{x:.1f}" y2="{q3:.1f}" stroke="{COLORS[row["method"]]}" stroke-width="3"/>')
        body.append(f'<rect x="{x-34:.1f}" y="{q3:.1f}" width="68" height="{max(2, q1-q3):.1f}" fill="{COLORS[row["method"]]}" opacity="0.45"/>')
        body.append(f'<line x1="{x-34:.1f}" y1="{median:.1f}" x2="{x+34:.1f}" y2="{median:.1f}" stroke="#111" stroke-width="3"/>')
        body.append(f'<circle cx="{x:.1f}" cy="{best:.1f}" r="5" fill="{COLORS[row["method"]]}"/>')
        body.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{row["method"]}</text>')
        body.append(f'<text x="{x:.1f}" y="{top+height+42}" text-anchor="middle" font-family="sans-serif" font-size="10">{row["feasible_runs"]}/{row["runs"]} feasible</text>')
    for fraction in (0, .25, .5, .75, 1):
        value = low + span * fraction
        y_value = top + height - height * fraction
        body.append(f'<text x="{left-10}" y="{y_value+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{value:.0f}</text>')
    body.append('<text x="32" y="310" transform="rotate(-90 32 310)" text-anchor="middle" font-family="sans-serif" font-size="13">Feasible portfolio cost (CNY)</text>')
    path.write_text(svg("Global allocation objective by method", "".join(body), width=1280,
                        metadata={"data": "method-summary.csv", "marks": "best, median, interquartile range"}), encoding="utf-8")


def write_assignment_chart(path, solution, orders):
    selected = solution["selected_candidates"]
    maximum = max(row["emissions_kg"] for row in selected)
    body = []
    for index, (order, candidate) in enumerate(zip(orders, selected)):
        y = 72 + index * 43
        mode = "+".join(candidate["modes"])
        width = 460 * candidate["emissions_kg"] / maximum
        color = "#1b6ca8" if "rail" in candidate["modes"] else (
            "#1f9e89" if candidate["modes"] == ["water"] else "#d95f02")
        label = f'{order["order_id"]}: {mode}; arrival {candidate["arrival_hour"]:.1f} h; {candidate["emissions_kg"]:.1f} kg'
        body.append(f'<text x="150" y="{y+17}" text-anchor="end" font-family="sans-serif" font-size="11">{order["order_id"]}</text>')
        body.append(f'<rect x="165" y="{y}" width="{width:.1f}" height="24" fill="{color}" opacity="0.82"/>')
        body.append(f'<text x="{175+width:.1f}" y="{y+17}" font-family="sans-serif" font-size="11">{html.escape(label)}</text>')
    path.write_text(svg("Best portfolio assignment and per-order emissions", "".join(body),
                        height=640, metadata={"data": "best-assignments.csv"}), encoding="utf-8")


def write_capacity_chart(path, solution):
    rows = [row for row in solution["capacity_usage"] if row["capacity_units"] is not None]
    body = []
    for index, row in enumerate(rows):
        y = 86 + index * 58
        ratio = row["used_shipment_units"] / row["capacity_units"]
        used = min(1, ratio) * 650
        body.append(f'<text x="245" y="{y+20}" text-anchor="end" font-family="sans-serif" font-size="11">{html.escape(row["departure_id"])}</text>')
        body.append(f'<rect x="260" y="{y}" width="650" height="28" fill="#eeeeee"/>')
        body.append(f'<rect x="260" y="{y}" width="{used:.1f}" height="28" fill="#4c78a8"/>')
        body.append(f'<text x="925" y="{y+20}" font-family="sans-serif" font-size="11">{row["used_shipment_units"]:g}/{row["capacity_units"]:g} units; {row["used_tonnes"]:g}/{row["capacity_tonnes"]:g} t</text>')
    path.write_text(svg("Shared departure capacity in best allocation", "".join(body),
                        metadata={"data": "best-capacity.csv"}), encoding="utf-8")


def run(args):
    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    config = facility_case_config(
        instance["model_case_id"], deadline_hours=max(row["deadline_hours"] for row in instance["orders"]),
        payload_tonnes=15, carbon_price_cny_per_tonne=instance["carbon_price_cny_per_tonne"],
        time_case=instance["time_case"])
    generated = generate_candidate_pools(
        config, instance["orders"], instance["departures"], top_k=args.top_k)
    brackets = config["carbon_brackets"]

    micro_ids = set(instance["exact_oracle_order_ids"])
    micro_orders = [row for row in generated["orders"] if row["order_id"] in micro_ids]
    exact_micro = solve_exact_allocation(
        micro_orders, generated["candidate_pools"], generated["departures"], brackets)
    if exact_micro["status"] != "optimal":
        raise RuntimeError("the exact micro-allocation oracle is infeasible")

    runs = []
    traces = []
    greedy = solve_greedy_allocation(
        generated["orders"], generated["candidate_pools"], generated["departures"], brackets)
    greedy_solution = greedy["solution"]
    runs.append({
        "method": "greedy", "seed": None, "status": greedy["status"],
        "feasible": greedy_solution["feasible"], "total_cost_cny": greedy_solution["total_cost_cny"],
        "emissions_kg": greedy_solution["emissions_kg"],
        "constraint_violation": greedy_solution["constraint_violation"], "restarts": 0,
        "ga_candidate_evaluations": 0, "heuristic_seed_evaluations": 0,
        "unique_assignment_evaluations": greedy["candidate_evaluations"],
        "total_solver_evaluations": greedy["candidate_evaluations"],
        "adaptive_control": "not-applicable", "restart_fraction": 0,
        "heuristic_seed_mode": "not-applicable",
        "heuristic_seed_strategy": "deadline",
        "solution": greedy_solution,
    })

    for method, controls in VARIANTS.items():
        for seed in args.seeds:
            result = solve_allocation_ga(
                generated["orders"], generated["candidate_pools"], generated["departures"], brackets,
                population=args.population, generations=args.generations, seed=seed,
                patience=args.patience, **controls)
            solution = result["solution"] or result["best_infeasible"]
            runs.append({
                "method": method, "seed": seed, "status": result["status"],
                "feasible": result["solution"] is not None,
                "total_cost_cny": solution["total_cost_cny"],
                "emissions_kg": solution["emissions_kg"],
                "constraint_violation": solution["constraint_violation"],
                "restarts": result["restarts"],
                "ga_candidate_evaluations": result["candidate_evaluations"],
                "heuristic_seed_evaluations": result["heuristic_seed_evaluations"],
                "unique_assignment_evaluations": result["unique_assignment_evaluations"],
                "total_solver_evaluations": result["candidate_evaluations"] + result["heuristic_seed_evaluations"],
                "adaptive_control": result["adaptive_control"],
                "restart_fraction": result["restart_fraction"],
                "heuristic_seed_mode": result["heuristic_seed_mode"],
                "heuristic_seed_strategy": result["heuristic_seed_strategy"],
                "solution": result["solution"],
            })
            for row in result["trace"]:
                traces.append({"method": method, "seed": seed, **row})

    feasible_runs = [row for row in runs if row["feasible"]]
    if not feasible_runs:
        raise RuntimeError("no method found a feasible portfolio")
    best_run = min(feasible_runs, key=lambda row: assignment_rank(row["solution"]))
    summaries = method_summary(runs)
    args.output.mkdir(parents=True, exist_ok=True)

    run_rows = [{key: value for key, value in row.items() if key != "solution"} for row in runs]
    assignment_rows = []
    for order, candidate in zip(generated["orders"], best_run["solution"]["selected_candidates"]):
        assignment_rows.append({
            "method": best_run["method"], "seed": best_run["seed"], "order_id": order["order_id"],
            "release_hour": order["release_hour"], "deadline_hour": order["deadline_hours"],
            "tonnes": order["tonnes"], "candidate_id": candidate["candidate_id"],
            "route": ">".join(candidate["route"]), "modes": "+".join(candidate["modes"]),
            "departure_ids": "+".join(candidate["departure_ids"]),
            "arrival_hour": candidate["arrival_hour"], "total_noncarbon_cost_cny": candidate["noncarbon_cost_cny"],
            "emissions_kg": candidate["emissions_kg"],
        })
    write_csv(args.output / "runs.csv", run_rows)
    write_csv(args.output / "method-summary.csv", summaries)
    write_csv(args.output / "traces.csv", traces)
    write_csv(args.output / "best-assignments.csv", assignment_rows)
    write_csv(args.output / "best-capacity.csv", best_run["solution"]["capacity_usage"])
    write_objective_chart(args.output / "objective-by-method.svg", summaries)
    write_assignment_chart(args.output / "best-assignment.svg", best_run["solution"], generated["orders"])
    write_capacity_chart(args.output / "capacity-use.svg", best_run["solution"])

    report = {
        "experiment_id": "global-order-allocation-cq-shanghai-v1",
        "instance": str(args.instance.relative_to(ROOT)),
        "scope": instance["evidence_boundary"],
        "network": {"nodes": len(config["nodes"]), "edges": len(config["edges"]),
                    "physical_routes_per_order": sorted(set(
                        generated["generation_stats"]["physical_routes_by_order"].values()))},
        "portfolio": {"orders": len(generated["orders"]), "tonnes": sum(row["tonnes"] for row in generated["orders"]),
                      "departures": len(generated["departures"]), "top_k": args.top_k},
        "algorithm_budget": {"seeds": args.seeds, "population": args.population,
                             "generations": args.generations, "patience": args.patience,
                             "variant_controls": VARIANTS},
        "candidate_generation": generated["generation_stats"],
        "exact_micro_oracle": {"order_ids": instance["exact_oracle_order_ids"],
                               "candidate_evaluations": exact_micro["candidate_evaluations"],
                               "solution": exact_micro["solution"]},
        "method_summary": summaries,
        "best_full_portfolio": {"method": best_run["method"], "seed": best_run["seed"],
                                "solution": best_run["solution"]},
        "claims": [
            "The exact result is an oracle only for the named four-order micro-instance.",
            "Full-portfolio GA results are heuristic and do not prove global optimality.",
            "Shared departure capacities make order choices interdependent; this is not repeated independent shortest-path search.",
            "The scenario orders and allocatable slot capacities are model inputs, not historical enterprise transactions.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "README.md").write_text(f"""# Global order-allocation experiment

Generated by `python3 -B tools/run_allocation_experiment.py`.

This experiment changes the decision from one shipment choosing one path to {len(generated['orders'])} indivisible orders competing for shared scheduled-departure capacity. Graph enumeration supplies each order's candidate route/departure labels; the allocation methods decide all genes jointly and apply progressive carbon pricing to portfolio emissions once.

- `results.json`: complete configuration summary, four-order exact oracle and best full-portfolio solution.
- `runs.csv`: greedy plus five GA variants across {len(args.seeds)} seeds.
- `method-summary.csv`: feasibility and objective distribution by method.
- `traces.csv`: generation-level GA trace.
- `best-assignments.csv` and `best-capacity.csv`: auditable selected alternatives and shared-resource use.
- `objective-by-method.svg`, `best-assignment.svg`, `capacity-use.svg`: result visualizations.

Evidence boundary: {instance['evidence_boundary']}

The full portfolio remains a heuristic benchmark; only the explicitly named four-order micro-instance is exhaustively enumerated.
""", encoding="utf-8")
    return report


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seeds", default=",".join(str(value) for value in range(30)))
    args = parser.parse_args()
    args.seeds = [int(value) for value in args.seeds.split(",") if value.strip()]
    if not args.seeds:
        parser.error("--seeds must contain at least one integer")
    return args


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({"experiment_id": result["experiment_id"],
                      "portfolio": result["portfolio"],
                      "best": {"method": result["best_full_portfolio"]["method"],
                               "seed": result["best_full_portfolio"]["seed"],
                               "cost_cny": result["best_full_portfolio"]["solution"]["total_cost_cny"]}},
                     indent=2, ensure_ascii=False))
