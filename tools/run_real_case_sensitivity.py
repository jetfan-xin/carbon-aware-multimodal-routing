#!/usr/bin/env python3
"""Run official-corridor sensitivity and five-method, 30-seed experiments."""

import argparse
import csv
import html
import json
import math
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.model import Network, solve_exact, solve_state_dijkstra
from routing.native_ga import solve_native_ga
from routing.portfolio import optimize_homogeneous_portfolio
from routing.real_world import (calibrated_23city_config, direct_corridor_config,
                                historical_progressive_schedule, load_benchmarks)
from routing.pipeline import write_route_svg


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = (
    ("fixed", False, False, False),
    ("adaptive", True, False, False),
    ("catastrophe", False, True, False),
    ("combined", True, True, False),
    ("hybrid-seeded", True, True, True),
)
COLORS = {"road": "#d95f02", "rail": "#1b6ca8", "water": "#1f9e89",
          "fixed": "#4c78a8", "adaptive": "#f58518", "catastrophe": "#54a24b",
          "combined": "#b279a2", "hybrid-seeded": "#e45756"}


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def svg_frame(title, body, width=960, height=560, description=None):
    desc = f"<desc>{html.escape(json.dumps(description, ensure_ascii=False))}</desc>" if description else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<title>{html.escape(title)}</title>{desc}<rect width="100%" height="100%" fill="white"/>'
            f'<text x="40" y="35" font-family="sans-serif" font-size="20" font-weight="bold">{html.escape(title)}</text>'
            f'{body}</svg>\n')


def write_phase_svg(path, rows, deadlines, prices):
    selected = [r for r in rows if r["payload_tonnes"] == 15 and r["time_case"] == "p50"]
    lookup = {(r["deadline_hours"], r["carbon_price_cny_per_tonne"]): r for r in selected}
    left, top, cell_w, cell_h = 105, 80, 58, 50
    body = []
    for j, price in enumerate(prices):
        x = left + j * cell_w
        body.append(f'<text x="{x + cell_w/2}" y="67" text-anchor="middle" font-family="sans-serif" font-size="11">{price:g}</text>')
    for i, deadline in enumerate(deadlines):
        y = top + i * cell_h
        body.append(f'<text x="95" y="{y + 32}" text-anchor="end" font-family="sans-serif" font-size="12">{deadline:g} h</text>')
        for j, price in enumerate(prices):
            row = lookup[(deadline, price)]
            mode = row["best_mode"] or "infeasible"
            color = COLORS.get(mode, "#cccccc")
            x = left + j * cell_w
            body.append(f'<rect x="{x}" y="{y}" width="{cell_w-2}" height="{cell_h-2}" fill="{color}" opacity="0.82"/>')
            body.append(f'<text x="{x + (cell_w-2)/2}" y="{y+31}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="white">{html.escape(mode)}</text>')
    body.append('<text x="480" y="735" text-anchor="middle" font-family="sans-serif" font-size="13">Carbon shadow price (CNY/tCO2e); payload 15 t/20-ft, central time case</text>')
    path.write_text(svg_frame("Deadline-carbon route phase map", "".join(body), height=760,
                              description={"data": "scenario-grid.csv"}), encoding="utf-8")


def write_cost_svg(path, rows):
    chosen = []
    for deadline in (60, 96, 204, 240):
        chosen.append(next(r for r in rows if r["deadline_hours"] == deadline and
                           r["carbon_price_cny_per_tonne"] == 97.49 and r["payload_tonnes"] == 15 and
                           r["time_case"] == "p50"))
    maximum = max(r["total_cost_cny"] for r in chosen)
    body = ['<rect x="300" y="54" width="14" height="14" fill="#4c78a8"/><text x="320" y="66" font-family="sans-serif" font-size="11">transport</text>',
            '<rect x="405" y="54" width="14" height="14" fill="#f58518"/><text x="425" y="66" font-family="sans-serif" font-size="11">time</text>',
            '<rect x="475" y="54" width="14" height="14" fill="#54a24b"/><text x="495" y="66" font-family="sans-serif" font-size="11">carbon</text>']
    colors = (("transport_cost_cny", "#4c78a8"), ("time_cost_cny", "#f58518"), ("carbon_cost_cny", "#54a24b"))
    for i, row in enumerate(chosen):
        y, x = 100 + i * 95, 190
        body.append(f'<text x="175" y="{y+24}" text-anchor="end" font-family="sans-serif" font-size="13">{row["deadline_hours"]} h / {row["best_service_id"]}</text>')
        for field, color in colors:
            width = row[field] / maximum * 500
            body.append(f'<rect x="{x}" y="{y}" width="{width}" height="36" fill="{color}"/>')
            x += width
        label_x = min(x + 8, 735)
        anchor = "end" if label_x == 735 else "start"
        body.append(f'<text x="{label_x}" y="{y+24}" text-anchor="{anchor}" font-family="sans-serif" font-size="12">{row["total_cost_cny"]:.0f}</text>')
    body.append('<text x="480" y="510" text-anchor="middle" font-family="sans-serif" font-size="13">CNY per 20-ft shipment; carbon price 97.49 CNY/tCO2e</text>')
    path.write_text(svg_frame("Best-route cost components by deadline", "".join(body), description={"data": "scenario-grid.csv"}), encoding="utf-8")


def write_frontier_svg(path):
    network = Network(direct_corridor_config(deadline_hours=360, payload_tonnes=15,
                                             carbon_price_cny_per_tonne=97.49))
    points = []
    for route in network.routes():
        result = network.evaluate(route)
        row = result["scenarios"][0]
        points.append((row["emissions_kg"], row["total_cost_cny"], network.edges[route[0]]["id"], result["modes"][0]))
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    sx = lambda value: 100 + (value-min_x)/max(1, max_x-min_x)*620
    sy = lambda value: 470 - (value-min_y)/max(1, max_y-min_y)*360
    body = ['<line x1="100" y1="470" x2="740" y2="470" stroke="#333"/><line x1="100" y1="80" x2="100" y2="470" stroke="#333"/>']
    for emissions, cost, label, mode in points:
        x, y = sx(emissions), sy(cost)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{COLORS[mode]}"/><text x="{x+10:.1f}" y="{y-8:.1f}" font-family="sans-serif" font-size="12">{label}</text>')
    body.append('<text x="480" y="525" text-anchor="middle" font-family="sans-serif" font-size="13">kg CO2e per shipment</text><text x="22" y="280" transform="rotate(-90 22 280)" text-anchor="middle" font-family="sans-serif" font-size="13">Total cost (CNY)</text>')
    path.write_text(svg_frame("Cost-emissions alternatives", "".join(body), description={"source": "direct corridor options"}), encoding="utf-8")


def write_portfolio_svg(path, rows):
    maximum = max(r["carbon_cost_cny"] for r in rows)
    left, top, width, height = 90, 80, 620, 380
    body = [f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" stroke="#333"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+height}" stroke="#333"/>']
    for fraction in (0, .25, .5, .75, 1):
        y = top + height - fraction * height
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+width}" y2="{y:.1f}" stroke="#ddd"/>')
        body.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{maximum*fraction:.0f}</text>')
    points = []
    for i, row in enumerate(rows):
        x = left + i / max(1, len(rows)-1) * width
        y = top + height - row["carbon_cost_cny"] / max(1, maximum) * height
        points.append(f"{x:.1f},{y:.1f}")
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#1f9e89"/><text x="{x:.1f}" y="{top+height+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{row["shipment_count"]}</text>')
    body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#1f9e89" stroke-width="3"/>')
    body.append('<text x="480" y="525" text-anchor="middle" font-family="sans-serif" font-size="13">20-ft shipments; historical progressive schedule applied once to aggregate emissions</text>')
    body.append('<text x="22" y="280" transform="rotate(-90 22 280)" text-anchor="middle" font-family="sans-serif" font-size="13">Carbon cost (CNY)</text>')
    path.write_text(svg_frame("Portfolio-level progressive carbon charge", "".join(body), description={"data": "portfolio-grid.csv"}), encoding="utf-8")


def write_algorithm_svg(path, summaries):
    maximum = max(row["gap_q3_percent"] for row in summaries) or 1
    body = ['<line x1="100" y1="470" x2="780" y2="470" stroke="#333"/>',
            '<line x1="100" y1="90" x2="100" y2="470" stroke="#333"/>']
    for fraction in (0, .25, .5, .75, 1):
        y = 450 - fraction * 340
        body.append(f'<line x1="100" y1="{y:.1f}" x2="780" y2="{y:.1f}" stroke="#ddd"/>')
        body.append(f'<text x="92" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{maximum*fraction:.0f}</text>')
    labels = {"fixed": "fixed", "adaptive": "adaptive", "catastrophe": "catastrophe",
              "combined": "combined", "hybrid-seeded": "hybrid"}
    for i, row in enumerate(summaries):
        x = 130 + i * 145
        scale = lambda value: 450 - value / maximum * 340
        y1, ym, y3 = scale(row["gap_q1_percent"]), scale(row["gap_median_percent"]), scale(row["gap_q3_percent"])
        body.append(f'<line x1="{x}" y1="{y1:.1f}" x2="{x}" y2="{y3:.1f}" stroke="{COLORS[row["variant"]]}" stroke-width="18" opacity="0.35"/>')
        body.append(f'<line x1="{x-18}" y1="{ym:.1f}" x2="{x+18}" y2="{ym:.1f}" stroke="{COLORS[row["variant"]]}" stroke-width="4"/>')
        body.append(f'<text x="{x}" y="500" text-anchor="middle" font-family="sans-serif" font-size="11">{labels[row["variant"]]}</text>')
    body.append('<text x="24" y="280" transform="rotate(-90 24 280)" text-anchor="middle" font-family="sans-serif" font-size="13">Gap from scenario best (%)</text>')
    path.write_text(svg_frame("Five-method quality across selected scenarios", "".join(body), description={"data": "algorithm-runs.csv"}), encoding="utf-8")


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows({key: row.get(key) for key in fields} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks" / "real-case-sensitivity")
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--population", type=int, default=16)
    parser.add_argument("--generations", type=int, default=25)
    parser.add_argument("--patience", type=int, default=8)
    args = parser.parse_args()
    if args.seeds != 30:
        raise ValueError("published experiment requires exactly 30 seeds")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    benchmark = load_benchmarks()
    prices = [row["value"] for row in json.loads((ROOT / "data" / "carbon_price_scenarios.json").read_text())["flat_prices"]]
    deadlines = json.loads((ROOT / "data" / "service_time_scenarios.json").read_text())["deadlines"]
    payloads = benchmark["payload_sensitivity_tonnes_per_20ft"]

    grid = []
    for time_case in ("p10", "p50", "p90"):
        for payload in payloads:
            for deadline in deadlines:
                for price in prices:
                    network = Network(direct_corridor_config(payload_tonnes=payload, deadline_hours=deadline,
                                                             carbon_price_cny_per_tonne=price, time_case=time_case))
                    solved = solve_exact(network)
                    solution = solved["solution"]
                    row = solution["scenarios"][0] if solution else {}
                    edge = network.edges[solution["edge_indices"][0]] if solution else {}
                    grid.append({
                        "time_case": time_case, "payload_tonnes": payload, "deadline_hours": deadline,
                        "carbon_price_cny_per_tonne": price, "status": solved["status"],
                        "best_service_id": edge.get("id"), "best_mode": solution["modes"][0] if solution else None,
                        "arrival_hours": row.get("arrival_hours"), "transport_cost_cny": row.get("transport_cost_cny"),
                        "time_cost_cny": row.get("time_cost_cny"), "carbon_cost_cny": row.get("carbon_cost_cny"),
                        "total_cost_cny": row.get("total_cost_cny"), "emissions_kg": row.get("emissions_kg"),
                    })

    portfolio_rows = []
    for deadline in deadlines:
        network = Network(direct_corridor_config(payload_tonnes=15, deadline_hours=deadline))
        network.brackets = [(row["lower_bound_kg"], row["rate_cny_per_kg"])
                            for row in historical_progressive_schedule()]
        routes = [network.evaluate(route) for route in network.routes()]
        for count in benchmark["portfolio_shipments"]:
            solved_portfolio = optimize_homogeneous_portfolio(routes, count, network.brackets)
            result = solved_portfolio["solution"]
            allocations = ([{"service_id": network.edges[route["edge_indices"][0]]["id"], "count": amount}
                            for route, amount in zip([r for r in routes if r["feasible"]], result["counts"]) if amount]
                           if result else [])
            portfolio_rows.append({"deadline_hours": deadline, "shipment_count": count,
                                   "payload_tonnes_each": 15, "status": solved_portfolio["status"],
                                   "total_cost_cny": result["total_cost_cny"] if result else None,
                                   "carbon_cost_cny": result["carbon_cost_cny"] if result else None,
                                   "emissions_kg": result["emissions_kg"] if result else None,
                                   "allocations_json": json.dumps(allocations, separators=(",", ":"))})

    # Fifteen scenarios span observed-price cells and the high-price structural switch boundary.
    selected_pairs = [(60, 0), (60, 5000), (60, 6000),
                      (96, 97.49), (192, 97.49),
                      (204, 0), (204, 97.49), (204, 5000), (204, 6000),
                      (240, 0), (240, 97.49), (240, 5000), (240, 6000),
                      (276, 97.49), (360, 6000)]
    selected = [{"scenario_id": f"d{deadline}-c{str(price).replace('.', '_')}",
                 "deadline_hours": deadline, "carbon_price_cny_per_tonne": price,
                 "selection_reason": "deadline boundary and/or carbon-price route-switch stress"}
                for deadline, price in selected_pairs]

    runs, traces = [], []
    for scenario in selected:
        network = Network(calibrated_23city_config(deadline_hours=scenario["deadline_hours"],
                                                   carbon_price_cny_per_tonne=scenario["carbon_price_cny_per_tonne"]))
        baseline = solve_state_dijkstra(network)
        scenario["dijkstra_status"] = baseline["status"]
        scenario["dijkstra_objective_cny"] = baseline["solution"]["objective_cny"] if baseline["solution"] else None
        scenario["dijkstra_expanded_states"] = baseline["expanded_states"]
        for seed in range(args.seeds):
            for variant, adaptive, catastrophe, heuristic_seed in VARIANTS:
                started = time.perf_counter()
                result = solve_native_ga(network, population=args.population, generations=args.generations,
                                         seed=seed, patience=args.patience, adaptive=adaptive,
                                         catastrophe=catastrophe, heuristic_seed=heuristic_seed)
                elapsed = time.perf_counter() - started
                solution = result["solution"]
                run = {"scenario_id": scenario["scenario_id"], "seed": seed, "variant": variant,
                       "status": result["status"], "objective_cny": solution["objective_cny"] if solution else None,
                       "emissions_kg": solution["scenarios"][0]["emissions_kg"] if solution else None,
                       "arrival_hours": solution["scenarios"][0]["arrival_hours"] if solution else None,
                       "candidate_evaluations": result["candidate_evaluations"],
                       "unique_route_evaluations": result["unique_route_evaluations"],
                       "preprocessing_expanded_states": result["preprocessing_expanded_states"],
                       "restarts": result["restarts"], "wall_seconds": elapsed,
                       "route_json": json.dumps(solution["route"], separators=(",", ":")) if solution else None,
                       "modes_json": json.dumps(solution["modes"], separators=(",", ":")) if solution else None}
                runs.append(run)
                for point in result["trace"]:
                    traces.append({"scenario_id": scenario["scenario_id"], "seed": seed,
                                   "variant": variant, **point})

    scenario_best = {scenario["scenario_id"]: min(row["objective_cny"] for row in runs
                     if row["scenario_id"] == scenario["scenario_id"] and row["objective_cny"] is not None)
                     for scenario in selected}
    for row in runs:
        row["gap_from_scenario_best_percent"] = ((row["objective_cny"] / scenario_best[row["scenario_id"]] - 1) * 100
                                                  if row["objective_cny"] is not None else None)
    summaries = []
    for variant, _, _, _ in VARIANTS:
        subset = [row for row in runs if row["variant"] == variant]
        feasible = [row for row in subset if row["objective_cny"] is not None]
        gaps = [row["gap_from_scenario_best_percent"] for row in feasible]
        summaries.append({"variant": variant, "runs": len(subset), "feasible_runs": len(feasible),
                          "feasible_rate": len(feasible)/len(subset),
                          "gap_mean_percent": statistics.fmean(gaps),
                          "gap_median_percent": statistics.median(gaps),
                          "gap_q1_percent": percentile(gaps, .25), "gap_q3_percent": percentile(gaps, .75),
                          "gap_stdev_percent": statistics.pstdev(gaps),
                          "candidate_evaluations": args.population * args.generations,
                          "preprocessing_expanded_states_mean": statistics.fmean(row["preprocessing_expanded_states"] for row in subset),
                          "wall_seconds_total": math.fsum(row["wall_seconds"] for row in subset),
                          "restarts_total": sum(row["restarts"] for row in subset)})

    grid_fields = list(grid[0]); portfolio_fields = list(portfolio_rows[0]); run_fields = list(runs[0]); trace_fields = list(traces[0])
    write_csv(args.output_dir / "scenario-grid.csv", grid, grid_fields)
    write_csv(args.output_dir / "portfolio-grid.csv", portfolio_rows, portfolio_fields)
    write_csv(args.output_dir / "algorithm-runs.csv", runs, run_fields)
    write_csv(args.output_dir / "algorithm-traces.csv", traces, trace_fields)
    report = {"experiment_id": "operator-calibrated-corridor-sensitivity-v2",
              "data_classification": "operator_reported_and_official_market_values_plus_labelled_model_assumptions",
              "source_file": "data/real_world_benchmarks.json",
              "grid": {"rows": len(grid), "deadlines": deadlines, "carbon_prices": prices,
                       "payloads": payloads, "time_cases": ["p10", "p50", "p90"]},
              "portfolio": {"rows": len(portfolio_rows), "carbon_application": "aggregate once per portfolio"},
              "algorithm_experiment": {"selected_scenarios": selected, "scenario_count": len(selected),
                                       "seeds": args.seeds, "population": args.population,
                                       "generations": args.generations, "candidate_budget_per_run": args.population*args.generations,
                                       "variants": [row[0] for row in VARIANTS], "summary": summaries},
              "warnings": ["Lane values have different or incompletely specified scope; they are not silently normalized.",
                           "Road time, payloads, endpoint mappings and 23-city edge allocation remain labelled assumptions.",
                           "Rail time is historical same-corridor evidence, not proof of a current train; water sailing time excludes unknown booking wait.",
                           "National ETS prices are shadow-price references; freight is not claimed to be directly covered.",
                           "GA outcomes are heuristic; scenario best means best observed in this experiment, not proven global optimum."]}
    (args.output_dir / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    (args.output_dir / "selected-scenarios.json").write_text(json.dumps(selected, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    write_phase_svg(args.output_dir / "deadline-carbon-phase.svg", grid, deadlines, prices)
    write_cost_svg(args.output_dir / "cost-components.svg", grid)
    write_frontier_svg(args.output_dir / "cost-emissions-frontier.svg")
    write_portfolio_svg(args.output_dir / "portfolio-carbon-brackets.svg",
                        [row for row in portfolio_rows if row["deadline_hours"] == 240])
    write_algorithm_svg(args.output_dir / "algorithm-quality.svg", summaries)
    for label, deadline, price in (("tight", 60, 97.49), ("balanced", 204, 97.49), ("green-stress", 240, 6000)):
        network = Network(direct_corridor_config(deadline_hours=deadline, carbon_price_cny_per_tonne=price))
        write_route_svg(network, solve_exact(network)["solution"], args.output_dir / f"route-{label}.svg")
    print(json.dumps({"output_dir": str(args.output_dir), "grid_rows": len(grid),
                      "selected_scenarios": len(selected), "algorithm_runs": len(runs),
                      "summary": summaries}, indent=2))


if __name__ == "__main__":
    main()
