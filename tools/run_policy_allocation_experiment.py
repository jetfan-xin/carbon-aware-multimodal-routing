#!/usr/bin/env python3
"""Run the corridor-calibrated demand, time, carbon-price and cap experiment."""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from pathlib import Path
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_greedy_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.facility_network import facility_case_config
from routing.model import Network
from tools.run_allocation_experiment import COLORS, VARIANTS, percentile, svg


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "data" / "policy_experiment.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "policy-allocation"


def write_csv(path, rows, fields=None):
    if not rows and fields is None:
        raise ValueError("fields are required for an empty CSV")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def scenario_id(demand, time_profile, carbon_price, reduction):
    price = str(carbon_price).replace(".", "p")
    target = str(round(reduction * 100, 1)).replace(".", "p")
    return f"{demand}-{time_profile}-c{price}-r{target}"


def generate_orders(design, demand, time_profile):
    """Create deterministic model orders; no row is an observed transaction."""
    count = design["demand_profiles"][demand]
    rng = random.Random(design["portfolio_seed"] + {"low": 1, "central": 2, "high": 3}[demand]
                        + {"tight": 10, "balanced": 20, "relaxed": 30}[time_profile])
    lead_times = design["lead_time_profiles_hours"][time_profile]
    orders = []
    for index in range(count):
        release = rng.choice(design["release_hours"])
        lead_time = rng.choice(lead_times)
        orders.append({
            "order_id": f"POL-{demand[:1].upper()}{time_profile[:1].upper()}-{index:03d}",
            "origin": "cq-guoyuan-port",
            "destination": "sh-yangshan-port",
            "release_hour": release,
            "deadline_hours": release + lead_time,
            "tonnes": rng.choice(design["payload_tonnes"]),
            "shipment_units": 1,
            "container_type": "20ft-model-unit",
            "cargo_type": "general-model-cargo",
            "source_type": "deterministic_scenario_order",
        })
    return orders


def build_instance(design, demand, time_profile, carbon_price):
    orders = generate_orders(design, demand, time_profile)
    config = facility_case_config(
        design["facility_case_id"], payload_tonnes=15,
        deadline_hours=max(row["deadline_hours"] for row in orders),
        carbon_price_cny_per_tonne=carbon_price, time_case="central")
    generated = generate_candidate_pools(
        config, orders, design["capacity_resources"], top_k=4,
        route_strategy="enumerate")
    return config, generated


def run_hybrid_screen(generated, brackets, design, emission_cap_kg=None):
    settings = design["algorithm_screening"]
    results = []
    for seed in settings["seeds"]:
        result = solve_allocation_ga(
            generated["orders"], generated["candidate_pools"],
            generated["departures"], brackets,
            population=settings["population"], generations=settings["generations"],
            patience=20, seed=seed, emission_cap_kg=emission_cap_kg,
            **VARIANTS["hybrid-seeded"])
        results.append(result)
    feasible = [row for row in results if row["solution"] is not None]
    return min(feasible, key=lambda row: assignment_rank(row["solution"])) if feasible else min(
        results, key=lambda row: assignment_rank(row["best_infeasible"]))


def solution_metrics(solution, baseline=None):
    if solution is None:
        return {}
    abated = ((baseline["emissions_kg"] - solution["emissions_kg"])
              if baseline else 0.0)
    return {
        "feasible": solution["feasible"],
        "total_cost_cny": solution["total_cost_cny"],
        "noncarbon_cost_cny": solution["noncarbon_cost_cny"],
        "carbon_cost_cny": solution["carbon_cost_cny"],
        "emissions_kg": solution["emissions_kg"],
        "transport_work_tonne_km": solution["transport_work_tonne_km"],
        "emissions_kg_per_tonne_km": solution["emissions_kg_per_tonne_km"],
        "constraint_violation": solution["constraint_violation"],
        "emission_violation": solution["emission_violation"],
        "emissions_excess_kg": solution["emissions_excess_kg"],
        "cost_premium_percent": ((solution["total_cost_cny"] / baseline["total_cost_cny"] - 1) * 100
                                 if baseline else 0.0),
        "operating_cost_premium_percent": (
            (solution["noncarbon_cost_cny"] / baseline["noncarbon_cost_cny"] - 1) * 100
            if baseline else 0.0),
        "achieved_reduction_percent": (
            (baseline["emissions_kg"] - solution["emissions_kg"])
            / baseline["emissions_kg"] * 100 if baseline else 0.0),
        "average_abatement_cost_cny_per_tco2e": (
            (solution["noncarbon_cost_cny"] - baseline["noncarbon_cost_cny"])
            / abated * 1000 if baseline and abated > 1e-9 else None),
    }


def mode_tonnes(orders, solution):
    totals = {"road": 0.0, "rail+road": 0.0, "water": 0.0}
    if solution is None:
        return totals
    for order, candidate in zip(orders, solution["selected_candidates"]):
        modes = candidate["modes"]
        label = "rail+road" if modes == ["rail", "road"] else modes[0]
        totals[label] += order["tonnes"]
    return totals


def summarize_runs(runs):
    rows = []
    scenario_ids = list(dict.fromkeys(row["scenario_id"] for row in runs))
    for sid in scenario_ids:
        for method in ["greedy", *VARIANTS]:
            subset = [row for row in runs if row["scenario_id"] == sid and row["method"] == method]
            feasible = [row for row in subset if row["feasible"]]
            costs = [row["total_cost_cny"] for row in feasible]
            rows.append({
                "scenario_id": sid,
                "method": method,
                "runs": len(subset),
                "feasible_runs": len(feasible),
                "feasible_rate": len(feasible) / len(subset),
                "best_cost_cny": min(costs) if costs else None,
                "median_cost_cny": statistics.median(costs) if costs else None,
                "mean_cost_cny": statistics.fmean(costs) if costs else None,
                "stdev_cost_cny": statistics.pstdev(costs) if len(costs) > 1 else 0,
                "q1_cost_cny": percentile(costs, .25) if costs else None,
                "q3_cost_cny": percentile(costs, .75) if costs else None,
                "mean_restarts": statistics.fmean(row["restarts"] for row in subset),
            })
    return rows


def aggregate_methods(runs, solvable_scenarios):
    rows = []
    for method in ["greedy", *VARIANTS]:
        subset = [row for row in runs if row["method"] == method]
        feasible = [row for row in subset if row["feasible"]]
        conditional = [row for row in subset if row["scenario_id"] in solvable_scenarios]
        conditional_feasible = [row for row in conditional if row["feasible"]]
        rows.append({
            "method": method,
            "runs": len(subset),
            "feasible_runs": len(feasible),
            "feasible_rate": len(feasible) / len(subset),
            "runs_on_scenarios_with_known_feasible_solution": len(conditional),
            "feasible_runs_on_scenarios_with_known_feasible_solution": len(conditional_feasible),
            "conditional_feasible_rate": (
                len(conditional_feasible) / len(conditional) if conditional else None),
            "mean_restarts": statistics.fmean(row["restarts"] for row in subset),
            "median_feasible_cost_cny": (
                statistics.median(row["total_cost_cny"] for row in feasible)
                if feasible else None),
        })
    return rows


def write_frontier(path, rows):
    selected = [row for row in rows if row["time_profile"] == "balanced"
                and row["carbon_price_cny_per_tco2e"] == 97.49]
    left, top, width, height = 105, 78, 850, 440
    premiums = [row["operating_cost_premium_percent"] for row in selected
                if row["feasible"]]
    low, high = min(0, min(premiums)), max(1, max(premiums))
    sx = lambda value: left + value / 30 * width
    sy = lambda value: top + height - (value - low) / (high - low) * height
    colors = {"low": "#4c78a8", "central": "#f58518", "high": "#54a24b"}
    body = [f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#333"/>']
    for demand in ("low", "central", "high"):
        points = []
        for row in sorted((item for item in selected if item["demand"] == demand),
                          key=lambda item: item["reduction_target"]):
            if not row["feasible"]:
                continue
            x, y = sx(row["reduction_target"] * 100), sy(row["operating_cost_premium_percent"])
            points.append(f"{x:.1f},{y:.1f}")
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{colors[demand]}"/>')
        body.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[demand]}" stroke-width="3"/>')
    for value in (0, 9.5, 20, 30):
        x = sx(value)
        body.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{value:g}</text>')
    for fraction in (0, .25, .5, .75, 1):
        value = low + (high-low)*fraction
        y = sy(value)
        body.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{value:.1f}</text>')
    for index, demand in enumerate(("low", "central", "high")):
        x = 330 + index * 170
        body.append(f'<line x1="{x}" y1="570" x2="{x+24}" y2="570" stroke="{colors[demand]}" stroke-width="3"/><text x="{x+31}" y="574" font-family="sans-serif" font-size="11">{demand} demand</text>')
    body.append('<text x="530" y="550" text-anchor="middle" font-family="sans-serif" font-size="13">Hard emissions-reduction target relative to the scenario baseline (%)</text>')
    body.append('<text x="30" y="300" transform="rotate(-90 30 300)" text-anchor="middle" font-family="sans-serif" font-size="13">Non-carbon operating-cost premium (%)</text>')
    path.write_text(svg("Cost of corridor emissions targets", "".join(body),
                        metadata={"data": "screening-grid.csv", "price": 97.49,
                                  "deadline_profile": "balanced"}), encoding="utf-8")


def write_feasibility(path, rows):
    left, top, width, height = 100, 85, 850, 400
    body = [f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#333"/>']
    for index, row in enumerate(rows):
        x = left + (index + .5) * width / len(rows)
        bar_height = row["conditional_feasible_rate"] * height
        body.append(f'<rect x="{x-35:.1f}" y="{top+height-bar_height:.1f}" width="70" height="{bar_height:.1f}" fill="{COLORS[row["method"]]}"/>')
        body.append(f'<text x="{x:.1f}" y="{top+height-bar_height-9:.1f}" text-anchor="middle" font-family="sans-serif" font-size="11">{row["conditional_feasible_rate"]*100:.1f}%</text>')
        body.append(f'<text x="{x:.1f}" y="{top+height+24}" text-anchor="middle" font-family="sans-serif" font-size="11">{html.escape(row["method"])}</text>')
    body.append('<text x="525" y="545" text-anchor="middle" font-family="sans-serif" font-size="13">Conditional on the 9 scenarios where at least one GA found a feasible solution</text>')
    body.append('<text x="28" y="285" transform="rotate(-90 28 285)" text-anchor="middle" font-family="sans-serif" font-size="13">Feasible-run rate</text>')
    path.write_text(svg("Feasibility under hard portfolio emissions caps", "".join(body),
                        metadata={"data": "aggregate-method-summary.csv"}), encoding="utf-8")


def write_mode_shift(path, rows):
    left, width = 230, 700
    maximum = max(sum(row["mode_tonnes"].values()) for row in rows)
    colors = {"road": "#d95f02", "rail+road": "#1b6ca8", "water": "#1f9e89"}
    body = []
    for index, row in enumerate(rows):
        y, x = 125 + index * 145, left
        label = f'{row["reduction_target"]*100:g}% target'
        body.append(f'<text x="{left-18}" y="{y+28}" text-anchor="end" font-family="sans-serif" font-size="13">{label}</text>')
        for mode in ("road", "rail+road", "water"):
            value = row["mode_tonnes"][mode]
            bar = value / maximum * width
            body.append(f'<rect x="{x:.1f}" y="{y}" width="{bar:.1f}" height="42" fill="{colors[mode]}"/>')
            if bar > 55:
                body.append(f'<text x="{x+bar/2:.1f}" y="{y+27}" text-anchor="middle" fill="white" font-family="sans-serif" font-size="11">{value:g} t</text>')
            x += bar
        body.append(f'<text x="{left}" y="{y+67}" font-family="sans-serif" font-size="11">CNY {row["total_cost_cny"]:,.0f}; {row["emissions_kg"]:,.0f} kg CO2e</text>')
    for index, mode in enumerate(("road", "rail+road", "water")):
        x = 300 + index * 190
        body.append(f'<rect x="{x}" y="480" width="18" height="18" fill="{colors[mode]}"/><text x="{x+25}" y="494" font-family="sans-serif" font-size="12">{mode}</text>')
    path.write_text(svg("Mode shift in the central balanced corridor portfolio", "".join(body),
                        metadata={"data": "representative-assignments.csv"}), encoding="utf-8")


def calibration_rows(design, synthetic_result, representative):
    network = Network(facility_case_config(
        design["facility_case_id"], payload_tonnes=15, deadline_hours=360,
        carbon_price_cny_per_tonne=0, time_case="central"))
    rows = []
    for route in network.routes():
        result = network.evaluate(route)
        scenario = result["scenarios"][0]
        ids = [network.edges[index]["id"] for index in route]
        name = ("rail-road" if len(ids) == 2 else "road" if "road" in ids[0]
                else "water-express" if "express" in ids[0] else "water-regular")
        rows.append({
            "benchmark": f"facility-{name}",
            "classification": "corridor_calibrated_single_shipment",
            "cost_cny_per_tonne": (scenario["transport_cost_cny"]
                                   + scenario["transfer_cost_cny"]) / 15,
            "emissions_kg_per_tonne": scenario["emissions_kg"] / 15,
            "comparison_limit": "One 15-t Chongqing-Yangshan model shipment; mixed quote scopes.",
        })
    best = synthetic_result["best_known_full_portfolio"]["solution"]
    tonnes = synthetic_result["portfolio"]["tonnes"]
    rows.append({
        "benchmark": "synthetic-23city-best-known",
        "classification": "synthetic_multi_od_algorithm_stress_test",
        "cost_cny_per_tonne": best["total_cost_cny"] / tonnes,
        "emissions_kg_per_tonne": best["emissions_kg"] / tonnes,
        "comparison_limit": "Multiple synthetic OD distances; not a Chongqing-Shanghai tariff observation.",
    })
    rep_tonnes = sum(row["tonnes"] for row in representative["orders"])
    for label, solution in (("corridor-policy-uncapped", representative["uncapped"]),
                            ("corridor-policy-20pct", representative["capped"])):
        rows.append({
            "benchmark": label,
            "classification": "corridor_calibrated_model_portfolio",
            "cost_cny_per_tonne": solution["total_cost_cny"] / rep_tonnes,
            "emissions_kg_per_tonne": solution["emissions_kg"] / rep_tonnes,
            "comparison_limit": "Model orders and planning-horizon capacities; not completed shipments.",
        })
    return rows


def write_calibration(path, rows):
    max_cost = max(row["cost_cny_per_tonne"] for row in rows) * 1.08
    max_emissions = max(row["emissions_kg_per_tonne"] for row in rows) * 1.08
    left, top, width, height = 105, 80, 850, 445
    sx = lambda value: left + value / max_emissions * width
    sy = lambda value: top + height - value / max_cost * height
    body = [f'<rect x="{left}" y="{top}" width="{width}" height="{height}" fill="none" stroke="#333"/>']
    for index, row in enumerate(rows):
        x, y = sx(row["emissions_kg_per_tonne"]), sy(row["cost_cny_per_tonne"])
        color = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#9467bd", "#72b7b2"][index % 6]
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}"/>')
        anchor = "end" if x > left + width * .7 else "start"
        dx = -10 if anchor == "end" else 10
        body.append(f'<text x="{x+dx:.1f}" y="{y-8:.1f}" text-anchor="{anchor}" font-family="sans-serif" font-size="10">{html.escape(row["benchmark"])}</text>')
    body.append('<text x="530" y="570" text-anchor="middle" font-family="sans-serif" font-size="13">Model emissions (kg CO2e/t)</text>')
    body.append('<text x="26" y="300" transform="rotate(-90 26 300)" text-anchor="middle" font-family="sans-serif" font-size="13">Model cost (CNY/t)</text>')
    path.write_text(svg("External plausibility context (not validation)", "".join(body),
                        metadata={"data": "calibration-context.csv",
                                  "warning": "different OD and quote scopes"}), encoding="utf-8")


def run(args):
    design = json.loads(args.design.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    instance_cache = {}
    baselines = {}
    screening = []

    for demand in design["demand_profiles"]:
        for time_profile in design["lead_time_profiles_hours"]:
            for carbon_price in design["carbon_shadow_prices_cny_per_tco2e"]:
                key = (demand, time_profile, carbon_price)
                config, generated = build_instance(
                    design, demand, time_profile, carbon_price)
                instance_cache[key] = (config, generated)
                baseline_result = run_hybrid_screen(
                    generated, config["carbon_brackets"], design)
                if baseline_result["solution"] is None:
                    raise RuntimeError(f"no feasible uncapped screening solution for {key}")
                baseline = baseline_result["solution"]
                baselines[key] = baseline
                for reduction in design["emissions_reduction_targets"]:
                    cap = baseline["emissions_kg"] * (1 - reduction)
                    result = (baseline_result if reduction == 0 else run_hybrid_screen(
                        generated, config["carbon_brackets"], design,
                        emission_cap_kg=cap))
                    solution = result["solution"] or result["best_infeasible"]
                    screening.append({
                        "scenario_id": scenario_id(demand, time_profile, carbon_price, reduction),
                        "demand": demand,
                        "time_profile": time_profile,
                        "carbon_price_cny_per_tco2e": carbon_price,
                        "reduction_target": reduction,
                        "baseline_emissions_kg": baseline["emissions_kg"],
                        "emission_cap_kg": cap,
                        "orders": len(generated["orders"]),
                        "tonnes": sum(row["tonnes"] for row in generated["orders"]),
                        "screening_seed": result["seed"],
                        **solution_metrics(solution, baseline),
                    })

    runs, traces, best_by_scenario = [], [], {}
    selected_records = []
    settings = design["algorithm_comparison"]
    for demand, time_profile, carbon_price, reduction in settings["selected_scenarios"]:
        key = (demand, time_profile, carbon_price)
        config, generated = instance_cache[key]
        baseline = baselines[key]
        cap = baseline["emissions_kg"] * (1 - reduction)
        sid = scenario_id(demand, time_profile, carbon_price, reduction)
        selected_records.append({
            "scenario_id": sid, "demand": demand, "time_profile": time_profile,
            "carbon_price_cny_per_tco2e": carbon_price,
            "reduction_target": reduction, "emission_cap_kg": cap,
            "baseline_cost_cny": baseline["total_cost_cny"],
            "baseline_emissions_kg": baseline["emissions_kg"],
        })
        greedy = solve_greedy_allocation(
            generated["orders"], generated["candidate_pools"],
            generated["departures"], config["carbon_brackets"],
            emission_cap_kg=cap)
        runs.append({
            "scenario_id": sid, "method": "greedy", "seed": None,
            "feasible": greedy["solution"]["feasible"], "status": greedy["status"],
            "total_cost_cny": greedy["solution"]["total_cost_cny"],
            "emissions_kg": greedy["solution"]["emissions_kg"],
            "constraint_violation": greedy["solution"]["constraint_violation"],
            "emission_violation": greedy["solution"]["emission_violation"],
            "restarts": 0, "candidate_evaluations": greedy["candidate_evaluations"],
        })
        scenario_results = []
        for method, controls in VARIANTS.items():
            for seed in range(settings["seeds"]):
                result = solve_allocation_ga(
                    generated["orders"], generated["candidate_pools"],
                    generated["departures"], config["carbon_brackets"],
                    population=settings["population"], generations=settings["generations"],
                    patience=settings["patience"], seed=seed,
                    emission_cap_kg=cap, **controls)
                solution = result["solution"] or result["best_infeasible"]
                record = {
                    "scenario_id": sid, "method": method, "seed": seed,
                    "feasible": result["solution"] is not None, "status": result["status"],
                    "total_cost_cny": solution["total_cost_cny"],
                    "emissions_kg": solution["emissions_kg"],
                    "constraint_violation": solution["constraint_violation"],
                    "emission_violation": solution["emission_violation"],
                    "restarts": result["restarts"],
                    "candidate_evaluations": result["candidate_evaluations"],
                }
                runs.append(record)
                scenario_results.append((record, result["solution"]))
                for point in result["trace"]:
                    if point["generation"] % 5 == 0 or point["generation"] == settings["generations"] - 1:
                        traces.append({"scenario_id": sid, "method": method,
                                       "seed": seed, **point})
        feasible_results = [row for row in scenario_results if row[1] is not None]
        if feasible_results:
            best_record, best_solution = min(
                feasible_results, key=lambda row: assignment_rank(row[1]))
            best_by_scenario[sid] = {
                "method": best_record["method"], "seed": best_record["seed"],
                "solution": best_solution,
            }

    summaries = summarize_runs(runs)
    solvable_scenarios = {
        row["scenario_id"] for row in runs
        if row["method"] != "greedy" and row["feasible"]
    }
    aggregate = aggregate_methods(runs, solvable_scenarios)
    scenario_outcomes = []
    for record in selected_records:
        sid = record["scenario_id"]
        feasible_rows = [row for row in runs if row["scenario_id"] == sid
                         and row["method"] != "greedy" and row["feasible"]]
        scenario_outcomes.append({
            **record,
            "outcome": ("feasible_solution_found" if feasible_rows
                        else "no_feasible_solution_found_within_tested_methods"),
            "feasible_ga_runs": len(feasible_rows),
            "best_known_cost_cny": (
                min(row["total_cost_cny"] for row in feasible_rows)
                if feasible_rows else None),
            "methods_with_feasible_solution": sorted({
                row["method"] for row in feasible_rows
            }),
        })
    representative_ids = {
        reduction: scenario_id("central", "balanced", 97.49, reduction)
        for reduction in (0, .2)
    }
    representative = {
        "orders": instance_cache[("central", "balanced", 97.49)][1]["orders"],
        "uncapped": best_by_scenario[representative_ids[0]]["solution"],
        "capped": best_by_scenario[representative_ids[.2]]["solution"],
    }
    representative_rows = []
    mode_rows = []
    for reduction, label in ((0, "uncapped"), (.2, "20pct-cap")):
        sid = representative_ids[reduction]
        best = best_by_scenario[sid]
        solution = best["solution"]
        modes = mode_tonnes(representative["orders"], solution)
        mode_rows.append({
            "reduction_target": reduction, "mode_tonnes": modes,
            "total_cost_cny": solution["total_cost_cny"],
            "emissions_kg": solution["emissions_kg"],
        })
        for order, candidate in zip(representative["orders"], solution["selected_candidates"]):
            representative_rows.append({
                "case": label, "method": best["method"], "seed": best["seed"],
                "order_id": order["order_id"], "tonnes": order["tonnes"],
                "deadline_hours": order["deadline_hours"],
                "route": ">".join(candidate["route"]),
                "modes": "+".join(candidate["modes"]),
                "arrival_hour": candidate["arrival_hour"],
                "cost_cny": candidate["noncarbon_cost_cny"],
                "emissions_kg": candidate["emissions_kg"],
            })

    synthetic_result = json.loads(
        (ROOT / "benchmarks/synthetic-global-allocation/results.json").read_text(encoding="utf-8"))
    context = calibration_rows(design, synthetic_result, representative)
    write_csv(args.output / "screening-grid.csv", screening)
    write_csv(args.output / "selected-scenarios.csv", selected_records)
    write_csv(args.output / "algorithm-runs.csv", runs)
    write_csv(args.output / "algorithm-traces.csv", traces)
    write_csv(args.output / "method-summary.csv", summaries)
    write_csv(args.output / "aggregate-method-summary.csv", aggregate)
    write_csv(args.output / "representative-assignments.csv", representative_rows)
    write_csv(args.output / "calibration-context.csv", context)
    write_frontier(args.output / "abatement-frontier.svg", screening)
    write_feasibility(args.output / "method-feasibility.svg", aggregate)
    write_mode_shift(args.output / "mode-shift.svg", mode_rows)
    write_calibration(args.output / "calibration-context.svg", context)

    central_rows = [row for row in screening if row["demand"] == "central"
                    and row["time_profile"] == "balanced"
                    and row["carbon_price_cny_per_tco2e"] == 97.49]
    report = {
        "experiment_id": design["experiment_id"],
        "data_classification": "corridor_calibrated_inputs_plus_deterministic_model_orders",
        "evidence_boundary": design["evidence_boundary"],
        "design_file": str(args.design.relative_to(ROOT)),
        "screening_grid": {
            "rows": len(screening), "base_scenarios": len(baselines),
            "demand_profiles": design["demand_profiles"],
            "time_profiles": list(design["lead_time_profiles_hours"]),
            "carbon_prices": design["carbon_shadow_prices_cny_per_tco2e"],
            "emissions_targets": design["emissions_reduction_targets"],
            "controller": design["algorithm_screening"],
        },
        "formal_comparison": {
            "selected_scenarios": len(selected_records),
            "ga_runs": len([row for row in runs if row["method"] != "greedy"]),
            "greedy_runs": len([row for row in runs if row["method"] == "greedy"]),
            "settings": settings,
            "aggregate_method_summary": aggregate,
            "scenario_outcomes": scenario_outcomes,
            "scenarios_with_known_feasible_solution": len(solvable_scenarios),
            "scenarios_without_a_found_feasible_solution": (
                len(selected_records) - len(solvable_scenarios)),
        },
        "central_balanced_current_price_frontier": central_rows,
        "representative_mode_tonnes": mode_rows,
        "policy_anchors": design["policy_anchors"],
        "interpretation_rules": [
            "The hard cap is computed from the best feasible uncapped hybrid screening result under the same demand, deadline and carbon-price scenario.",
            "Because that reference is heuristic, a reduction target is relative to a reproducible best-known baseline, not a proven global cost optimum.",
            "Operating-cost premium excludes the model carbon charge; total-cost premium includes it. Average abatement cost uses the change in non-carbon operating cost.",
            "The 23-city stress test and the facility-calibrated corridor portfolio answer different questions and are compared only for scale and directional plausibility.",
        ],
        "warnings": [
            design["carbon_price_scope"]["limit"],
            "Policy percentages are transparent scenario anchors, not asserted shipment-level legal obligations.",
            "Order rows and shared capacities are experiment assumptions; the outputs are not quotes, timetables, completed orders or measured savings.",
            "All full-portfolio results are heuristic best-known solutions and do not certify global optimality.",
            "No-solution-found scenarios are search and model-capacity boundaries, not mathematical infeasibility certificates.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8")
    (args.output / "README.md").write_text(f"""# Corridor policy-allocation experiment

Generated by `python3 -B tools/run_policy_allocation_experiment.py`.

This experiment uses the field-level calibrated Chongqing-Guoyuan to Shanghai-Yangshan alternatives, then adds explicitly modelled orders and planning-horizon capacities. It first screens {len(screening)} demand, deadline, carbon-price and hard-cap cells. It then compares five GA variants over 30 seeds in twelve selected scenarios ({len([row for row in runs if row['method'] != 'greedy']):,} GA runs) plus one deterministic greedy run per scenario.

- `screening-grid.csv`: full 3 demand x 3 deadline-profile x 3 carbon-price x 4 cap-target grid.
- `selected-scenarios.csv`: the twelve formal comparison cells and their frozen best-known emissions baselines.
- `algorithm-runs.csv`, `algorithm-traces.csv`, `method-summary.csv`: formal run-level evidence.
- `representative-assignments.csv`: auditable central balanced assignments before and after the 20% cap.
- `calibration-context.csv`: corridor and 23-city normalized context with non-comparability warnings.
- `abatement-frontier.svg`, `method-feasibility.svg`, `mode-shift.svg`, `calibration-context.svg`: reproducible result figures.

The 9.5%, 20% and 30% values are policy-inspired stress targets, not direct legal caps on this domestic shipment. The national ETS price is a shadow price. Orders, capacity and savings are model outputs, not observed enterprise operations.
""", encoding="utf-8")
    return report


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=DESIGN_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    output = run(parse_args())
    print(json.dumps({
        "experiment_id": output["experiment_id"],
        "screening_rows": output["screening_grid"]["rows"],
        "formal_ga_runs": output["formal_comparison"]["ga_runs"],
        "aggregate": output["formal_comparison"]["aggregate_method_summary"],
    }, indent=2, ensure_ascii=False))
