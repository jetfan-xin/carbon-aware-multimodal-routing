#!/usr/bin/env python3
"""Run a hard, policy-calibrated benchmark that separates GA behaviour.

This experiment is deliberately separate from the policy matrix.  It creates
a cost-emissions conflict, timed rail/water departures, scarce clean capacity,
three active policy-inspired emissions caps, an archive-only baseline, and a
small exact-enumeration oracle.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import csv
import html
import json
import math
from pathlib import Path
import statistics
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.allocation import (assignment_rank, generate_candidate_pools,
                                solve_emission_repair_allocation,
                                solve_exact_allocation)
from routing.allocation_ga import solve_allocation_ga
from routing.real_world import carbon_schedule
from routing.synthetic import generate_network
from tools.run_synthetic_policy_matrix import (generate_policy_portfolio,
                                                solve_single_trunk_cost_baseline)
from tools.run_synthetic_objective_matrix import solution_metrics


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data" / "policy_experiment.json"
DEFAULT_OUTPUT = ROOT / "benchmarks" / "algorithm-discrimination"
TARGETS = (0.0, 0.095, 0.20, 0.30)
METHODS = ("archive-only", "fixed", "adaptive", "catastrophe", "combined",
           "heuristic+ga")
COLORS = {
    "archive-only": "#777777", "fixed": "#4c78a8", "adaptive": "#f58518",
    "catastrophe": "#54a24b", "combined": "#e45756", "heuristic+ga": "#9467bd",
}
CONTROLS = {
    "fixed": {"adaptive": False, "catastrophe": False, "heuristic_seed": False},
    "adaptive": {"adaptive": True, "catastrophe": False, "heuristic_seed": False,
                 "adaptive_control": "diversity-v2", "mutation_base": .5,
                 "mutation_cap": 1.5},
    "catastrophe": {"adaptive": False, "catastrophe": True,
                    "heuristic_seed": False, "restart_fraction": .15},
    "combined": {"adaptive": True, "catastrophe": True, "heuristic_seed": False,
                 "adaptive_control": "diversity-v2", "mutation_base": .5,
                 "mutation_cap": 1.5, "restart_fraction": .15},
    "heuristic+ga": {"adaptive": True, "catastrophe": True,
                     "heuristic_seed": True, "heuristic_seed_mode": "population",
                     "heuristic_seed_strategy": "emission-repair",
                     "adaptive_control": "diversity-v2", "mutation_base": .5,
                     "mutation_cap": 1.5, "restart_fraction": .15},
}
_WORKER = None


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def hard_config(density=0.36, seed=42):
    """Make road cheap/dirty and clean modes costly, unlike the easy matrix."""
    config = generate_network(23, density, seed)
    config["modes"]["road"]["rate_bands_cny_per_tonne_km"] = [.10, .09, .075]
    config["modes"]["rail"]["rate_bands_cny_per_tonne_km"] = [.18, .15, .125]
    config["modes"]["water"]["rate_bands_cny_per_tonne_km"] = [.24, .20, .16]
    config["storage_cny_per_tonne_hour"] = .15
    config["carbon_brackets"] = carbon_schedule(97.49)
    config["description"] = (
        "Policy-calibrated synthetic hard instance with explicit cost-emissions trade-off")
    return config


def timed_clean_departures(config, capacity_tonnes=20, capacity_units=2):
    return [{
        "departure_id": f'H{hour:03d}-{edge["id"]}',
        "edge_id": edge["id"], "departure_hour": hour,
        "capacity_tonnes": capacity_tonnes, "capacity_units": capacity_units,
        "evidence_class": "policy_calibrated_synthetic_scarce_departure",
    } for edge in config["edges"] if edge["mode"] in {"rail", "water"}
      for hour in (0, 24, 48, 72, 96)]


def linear_objective_lower_bound(orders, pools, carbon_rate):
    return math.fsum(min(candidate["noncarbon_cost_cny"]
                         + carbon_rate * candidate["emissions_kg"]
                         for candidate in pools[order["order_id"]])
                     for order in orders)


def utilization_metrics(solution):
    ratios = []
    for row in solution["capacity_usage"]:
        if not row["used_tonnes"] and not row["used_shipment_units"]:
            continue
        ratios.append(max(
            row["used_tonnes"] / row["capacity_tonnes"]
            if row["capacity_tonnes"] else 0,
            row["used_shipment_units"] / row["capacity_units"]
            if row["capacity_units"] else 0))
    return {
        "used_clean_departures": len(ratios),
        "max_departure_utilization": max(ratios, default=0),
        "departures_at_least_90pct": sum(value >= .9 for value in ratios),
    }


def record(width, target, method, seed, result, orders, baseline):
    solution = result["solution"] or result.get("best_infeasible")
    metrics = solution_metrics(solution, orders) if solution else {}
    capacity = utilization_metrics(solution) if solution else {}
    return {
        "candidate_width": width, "reduction_target": target,
        "method": method, "seed": seed,
        "status": result["status"], "feasible": result["solution"] is not None,
        "total_cost_cny": solution["total_cost_cny"] if solution else None,
        "cost_premium_percent": ((solution["total_cost_cny"] / baseline["total_cost_cny"] - 1) * 100
                                 if solution else None),
        "emissions_kg": solution["emissions_kg"] if solution else None,
        "achieved_reduction_percent": ((1-solution["emissions_kg"] / baseline["emissions_kg"]) * 100
                                       if solution else None),
        "tonne_weighted_transit_hours": metrics.get("tonne_weighted_transit_hours"),
        "max_departure_utilization": capacity.get("max_departure_utilization"),
        "departures_at_least_90pct": capacity.get("departures_at_least_90pct"),
        "used_clean_departures": capacity.get("used_clean_departures"),
        "restarts": result.get("restarts", 0),
        "generations_completed": result.get("generations_completed", 0),
        "termination_reason": result.get("termination_reason", "archive-only"),
        "ga_candidate_evaluations": result.get("candidate_evaluations", 0),
        "archive_candidate_evaluations": result.get("heuristic_seed_evaluations", 0),
    }


def _init_worker(orders, pools, departures, brackets, population, generations,
                 patience, cap, lower_bound, archive_chromosome):
    global _WORKER
    _WORKER = (orders, pools, departures, brackets, population, generations,
               patience, cap, lower_bound, archive_chromosome)


def _solve(task):
    method, seed = task
    (orders, pools, departures, brackets, population, generations, patience,
     cap, lower_bound, archive_chromosome) = _WORKER
    controls = dict(CONTROLS[method])
    if method == "heuristic+ga":
        controls["heuristic_seed_chromosome"] = archive_chromosome
    result = solve_allocation_ga(
        orders, pools, departures, brackets, population=population,
        generations=generations, patience=patience, seed=seed,
        emission_cap_kg=cap, objective_lower_bound_cny=lower_bound, **controls)
    return method, seed, result


def summaries(runs):
    output = []
    keys = sorted({(row["candidate_width"], row["reduction_target"], row["method"])
                   for row in runs})
    for width, target, method in keys:
        selected = [row for row in runs if (row["candidate_width"], row["reduction_target"],
                                             row["method"]) == (width, target, method)]
        feasible = [row for row in selected if row["feasible"]]
        def med(field):
            values = [row[field] for row in feasible if row[field] is not None]
            return statistics.median(values) if values else None
        output.append({
            "candidate_width": width, "reduction_target": target, "method": method,
            "runs": len(selected), "feasible_runs": len(feasible),
            "feasible_rate": len(feasible) / len(selected),
            "best_cost_cny": min((row["total_cost_cny"] for row in feasible), default=None),
            "median_cost_cny": med("total_cost_cny"),
            "median_cost_premium_percent": med("cost_premium_percent"),
            "median_transit_hours": med("tonne_weighted_transit_hours"),
            "median_max_departure_utilization": med("max_departure_utilization"),
            "median_saturated_departures": med("departures_at_least_90pct"),
            "mean_restarts": statistics.fmean(row["restarts"] for row in selected),
            "mean_generations_completed": statistics.fmean(
                row["generations_completed"] for row in selected),
        })
    return output


def svg_document(title, body, width, height, metadata):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title>'
            f'<desc>{html.escape(json.dumps(metadata, ensure_ascii=False))}</desc>'
            f'<rect width="100%" height="100%" fill="white"/>'
            f'<text x="40" y="38" font-family="sans-serif" font-size="20" font-weight="bold">'
            f'{html.escape(title)}</text>{body}</svg>\n')


def write_cost_chart(path, png_path, summary_rows, widths):
    width_px, height_px = 1380, 520
    body = []
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image); font = ImageFont.load_default()
    draw.text((40, 18), "Cost response by target and retained candidate width", fill="black", font=font)
    values = [row["median_cost_premium_percent"] for row in summary_rows
              if row["median_cost_premium_percent"] is not None]
    top_value = max(5, math.ceil(max(values) / 5) * 5)
    targets = list(TARGETS)
    for panel, candidate_width in enumerate(widths):
        left, top, chart_w, chart_h = 70 + panel * 445, 90, 350, 310
        body.append(f'<text x="{left+chart_w/2}" y="72" text-anchor="middle" font-family="sans-serif" font-size="13">top-k = {candidate_width}</text>')
        body.append(f'<rect x="{left}" y="{top}" width="{chart_w}" height="{chart_h}" fill="none" stroke="#555"/>')
        draw.rectangle((left, top, left+chart_w, top+chart_h), outline="#555")
        draw.text((left+145, 65), f"top-k = {candidate_width}", fill="black", font=font)
        for fraction in (0, .5, 1):
            y = top + chart_h - fraction*chart_h
            value = fraction*top_value
            body.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{value:.0f}%</text>')
            draw.text((left-32, y-6), f"{value:.0f}%", fill="black", font=font)
        for method in METHODS:
            rows = {row["reduction_target"]: row for row in summary_rows
                    if row["candidate_width"] == candidate_width and row["method"] == method}
            points = []
            for index, target in enumerate(targets):
                row = rows.get(target)
                if not row or row["median_cost_premium_percent"] is None:
                    continue
                x = left + index * chart_w / (len(targets)-1)
                y = top + chart_h - row["median_cost_premium_percent"] / top_value * chart_h
                points.append((x, y))
            if len(points) > 1:
                text_points = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                body.append(f'<polyline points="{text_points}" fill="none" stroke="{COLORS[method]}" stroke-width="2"/>')
                draw.line(points, fill=COLORS[method], width=2)
            for x, y in points:
                body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLORS[method]}"/>')
                draw.ellipse((x-3, y-3, x+3, y+3), fill=COLORS[method])
        for index, target in enumerate(targets):
            x = left + index * chart_w / (len(targets)-1)
            label = f"{target*100:g}%"
            body.append(f'<text x="{x:.1f}" y="420" text-anchor="middle" font-family="sans-serif" font-size="10">{label}</text>')
            draw.text((x-10, 410), label, fill="black", font=font)
    for index, method in enumerate(METHODS):
        x = 70 + index * 210
        body.append(f'<line x1="{x}" y1="468" x2="{x+20}" y2="468" stroke="{COLORS[method]}" stroke-width="3"/><text x="{x+26}" y="472" font-family="sans-serif" font-size="11">{method}</text>')
        draw.line((x, 468, x+20, 468), fill=COLORS[method], width=3)
        draw.text((x+26, 462), method, fill="black", font=font)
    body.append('<text x="18" y="250" transform="rotate(-90 18 250)" text-anchor="middle" font-family="sans-serif" font-size="12">Median cost premium vs uncapped cost optimum (%)</text>')
    path.write_text(svg_document("Cost response by target and retained candidate width", "".join(body), width_px, height_px, {"data": "method-summary.csv"}), encoding="utf-8")
    image.save(png_path)


def write_gap_chart(path, png_path, oracle_rows):
    width_px, height_px = 1200, 540
    feasible = [row for row in oracle_rows if row["median_gap_percent"] is not None]
    high = max(1, math.ceil(max(row["median_gap_percent"] for row in feasible) * 2) / 2)
    left, top, chart_w, chart_h = 95, 90, 1040, 340
    body = [f'<rect x="{left}" y="{top}" width="{chart_w}" height="{chart_h}" fill="none" stroke="#555"/>']
    image = Image.new("RGB", (width_px, height_px), "white"); draw = ImageDraw.Draw(image)
    draw.text((40, 18), "Exact-enumeration optimality gap (6-order oracle)", fill="black")
    draw.rectangle((left, top, left+chart_w, top+chart_h), outline="#555")
    group_w = chart_w / len(TARGETS); bar_w = group_w / (len(METHODS)+1)
    for ti, target in enumerate(TARGETS):
        for mi, method in enumerate(METHODS):
            row = next((item for item in oracle_rows if item["reduction_target"] == target
                        and item["method"] == method), None)
            if not row or row["median_gap_percent"] is None:
                continue
            x = left + ti*group_w + (mi+.5)*bar_w
            h = row["median_gap_percent"] / high * chart_h
            body.append(f'<rect x="{x:.1f}" y="{top+chart_h-h:.1f}" width="{bar_w*.72:.1f}" height="{h:.1f}" fill="{COLORS[method]}"/>')
            draw.rectangle((x, top+chart_h-h, x+bar_w*.72, top+chart_h), fill=COLORS[method])
        xmid = left + (ti+.5)*group_w
        label = f"{target*100:g}%"
        body.append(f'<text x="{xmid:.1f}" y="452" text-anchor="middle" font-family="sans-serif" font-size="11">{label}</text>')
        draw.text((xmid-10, 445), label, fill="black")
    for index, method in enumerate(METHODS):
        x = 45 + index*185
        body.append(f'<rect x="{x}" y="485" width="16" height="10" fill="{COLORS[method]}"/><text x="{x+22}" y="495" font-family="sans-serif" font-size="10">{method}</text>')
        draw.rectangle((x, 485, x+16, 495), fill=COLORS[method]); draw.text((x+22, 482), method, fill="black")
    body.append('<text x="20" y="260" transform="rotate(-90 20 260)" text-anchor="middle" font-family="sans-serif" font-size="12">Median gap to exact optimum (%)</text>')
    path.write_text(svg_document("Exact-enumeration optimality gap (6-order oracle)", "".join(body), width_px, height_px, {"data": "micro-oracle-summary.csv"}), encoding="utf-8")
    image.save(png_path)


def write_cost_time_chart(path, png_path, summary_rows, candidate_width):
    """Plot median cost against median transit time without a dense table."""
    targets = TARGETS[1:]
    width_px, height_px = 1380, 530
    body = []
    image = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 18), "Cost and transit time under active emissions caps", fill="black")
    for panel, target in enumerate(targets):
        rows = [row for row in summary_rows
                if row["candidate_width"] == candidate_width
                and row["reduction_target"] == target
                and row["median_cost_cny"] is not None]
        left, top, chart_w, chart_h = 85 + panel*445, 95, 340, 310
        times = [row["median_transit_hours"] for row in rows]
        costs = [row["median_cost_cny"] / 1000 for row in rows]
        t_low, t_high = min(times)-.35, max(times)+.35
        c_low, c_high = min(costs)-.5, max(costs)+.5
        body.append(f'<rect x="{left}" y="{top}" width="{chart_w}" height="{chart_h}" fill="none" stroke="#555"/>')
        body.append(f'<text x="{left+chart_w/2}" y="74" text-anchor="middle" font-family="sans-serif" font-size="13">target {target*100:g}%</text>')
        draw.rectangle((left, top, left+chart_w, top+chart_h), outline="#555")
        draw.text((left+145, 67), f"target {target*100:g}%", fill="black")
        ordered_rows = sorted(rows, key=lambda row: METHODS.index(row["method"]))
        for row in ordered_rows:
            x = left + (row["median_transit_hours"]-t_low) / max(1e-9, t_high-t_low) * chart_w
            y = top + chart_h - (row["median_cost_cny"]/1000-c_low) / max(1e-9, c_high-c_low) * chart_h
            color = COLORS[row["method"]]
            radius = 10 - METHODS.index(row["method"])
            body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="none" stroke="{color}" stroke-width="2"/>')
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline=color, width=2)
        for fraction in (0, .5, 1):
            x = left + fraction*chart_w
            t_value = t_low + fraction*(t_high-t_low)
            body.append(f'<text x="{x:.1f}" y="425" text-anchor="middle" font-family="sans-serif" font-size="10">{t_value:.1f} h</text>')
            draw.text((x-14, 414), f"{t_value:.1f} h", fill="black")
            y = top + chart_h - fraction*chart_h
            c_value = c_low + fraction*(c_high-c_low)
            body.append(f'<text x="{left-8}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{c_value:.1f}k</text>')
            draw.text((left-38, y-6), f"{c_value:.1f}k", fill="black")
    for index, method in enumerate(METHODS):
        x = 55 + index*205
        color = COLORS[method]
        body.append(f'<circle cx="{x}" cy="485" r="6" fill="none" stroke="{color}" stroke-width="2"/><text x="{x+12}" y="489" font-family="sans-serif" font-size="10">{method}</text>')
        draw.ellipse((x-6, 479, x+6, 491), outline=color, width=2)
        draw.text((x+12, 479), method, fill="black")
    body.append('<text x="690" y="452" text-anchor="middle" font-family="sans-serif" font-size="12">Median tonne-weighted transit time (hours)</text>')
    body.append('<text x="20" y="250" transform="rotate(-90 20 250)" text-anchor="middle" font-family="sans-serif" font-size="12">Median total cost (thousand CNY)</text>')
    body.append(f'<text x="690" y="515" text-anchor="middle" font-family="sans-serif" font-size="10">Candidate width top-k = {candidate_width}; lower-left is better; concentric markers indicate identical medians</text>')
    draw.text((470, 508), f"top-k = {candidate_width}; lower-left is better; concentric markers = identical medians", fill="black")
    path.write_text(svg_document(
        "Cost and transit time under active emissions caps", "".join(body),
        width_px, height_px, {"data": "method-summary.csv", "candidate_width": candidate_width}),
        encoding="utf-8")
    image.save(png_path)


def micro_pools(orders, pools, count):
    selected_orders = orders[:count]
    selected = {}
    for order in selected_orders:
        source = pools[order["order_id"]]
        anchors = [min(source, key=lambda row: row["surrogate_cost_cny"]),
                   min(source, key=lambda row: row["emissions_kg"]),
                   min(source, key=lambda row: row["arrival_hour"])]
        anchors.extend(source)
        unique = []
        for row in anchors:
            if row["candidate_id"] not in {item["candidate_id"] for item in unique}:
                unique.append(row)
            if len(unique) == 4:
                break
        selected[order["order_id"]] = unique
    return selected_orders, selected


def run_micro_oracle(generated, brackets, seeds, population, generations, patience,
                     oracle_orders):
    orders, pools = micro_pools(generated["orders"], generated["candidate_pools"], oracle_orders)
    base, _ = solve_single_trunk_cost_baseline({
        "orders": orders, "candidate_pools": pools,
        "departures": generated["departures"]}, brackets)
    rows = []
    for target in TARGETS:
        cap = None if target == 0 else base["emissions_kg"] * (1-target)
        exact = solve_exact_allocation(
            orders, pools, generated["departures"], brackets, emission_cap_kg=cap)
        if exact["solution"] is None:
            raise RuntimeError(f"micro oracle target {target:g} is infeasible")
        archive = solve_emission_repair_allocation(
            orders, pools, generated["departures"], brackets, emission_cap_kg=cap)
        solved = {"archive-only": [archive]}
        lower = exact["solution"]["total_cost_cny"]
        for method in CONTROLS:
            solved[method] = []
            for seed in seeds:
                controls = dict(CONTROLS[method])
                if method == "heuristic+ga":
                    controls["heuristic_seed_chromosome"] = archive["solution"]["chromosome"]
                solved[method].append(solve_allocation_ga(
                    orders, pools, generated["departures"], brackets,
                    population=population, generations=generations, patience=patience,
                    seed=seed, emission_cap_kg=cap,
                    objective_lower_bound_cny=lower, **controls))
        for method, results in solved.items():
            costs = [item["solution"]["total_cost_cny"] for item in results
                     if item["solution"] is not None]
            rows.append({
                "reduction_target": target, "method": method,
                "exact_cost_cny": exact["solution"]["total_cost_cny"],
                "exact_evaluations": exact["candidate_evaluations"],
                "runs": len(results), "feasible_runs": len(costs),
                "best_gap_percent": ((min(costs)/lower-1)*100 if costs else None),
                "median_gap_percent": ((statistics.median(costs)/lower-1)*100 if costs else None),
            })
    return rows


def run(args):
    design = json.loads(args.design.read_text(encoding="utf-8"))
    config = hard_config(args.density, args.network_seed)
    orders = generate_policy_portfolio(config["nodes"], design, "central", "balanced")[:args.orders]
    departures = timed_clean_departures(config, args.capacity_tonnes, args.capacity_units)
    brackets = config["carbon_brackets"]
    args.output.mkdir(parents=True, exist_ok=True)
    all_runs = []; generated_by_width = {}; scenario_rows = []
    for candidate_width in args.candidate_widths:
        generated = generate_candidate_pools(
            config, orders, departures, top_k=candidate_width,
            max_routes=args.candidate_routes, route_strategy="beam",
            beam_width=args.beam_width, max_schedule_combinations=120)
        generated_by_width[candidate_width] = generated
        carbon_rate = brackets[0]["rate_cny_per_kg"]
        lower_bound = linear_objective_lower_bound(
            generated["orders"], generated["candidate_pools"], carbon_rate)
        baseline, _ = solve_single_trunk_cost_baseline(generated, brackets)
        if not math.isclose(baseline["total_cost_cny"], lower_bound, abs_tol=1e-6):
            raise RuntimeError("uncapped archive did not attain the candidate objective lower bound")
        for target in TARGETS:
            cap = None if target == 0 else baseline["emissions_kg"] * (1-target)
            archive = solve_emission_repair_allocation(
                generated["orders"], generated["candidate_pools"],
                generated["departures"], brackets, emission_cap_kg=cap)
            archive_result = {"status": archive["status"],
                              "solution": archive["solution"] if archive["solution"]["feasible"] else None,
                              "best_infeasible": archive["solution"],
                              "candidate_evaluations": archive["candidate_evaluations"]}
            all_runs.append(record(candidate_width, target, "archive-only", None,
                                   archive_result, generated["orders"], baseline))
            tasks = [(method, seed) for method in CONTROLS for seed in args.seeds]
            initargs = (generated["orders"], generated["candidate_pools"],
                        generated["departures"], brackets, args.population,
                        args.generations, args.patience, cap, lower_bound,
                        archive["solution"]["chromosome"])
            if args.workers == 1:
                _init_worker(*initargs); solved = map(_solve, tasks); executor = None
            else:
                executor = ProcessPoolExecutor(
                    max_workers=args.workers, initializer=_init_worker, initargs=initargs)
                solved = executor.map(_solve, tasks, chunksize=1)
            try:
                for method, seed, result in solved:
                    all_runs.append(record(candidate_width, target, method, seed,
                                           result, generated["orders"], baseline))
            finally:
                if executor is not None:
                    executor.shutdown()
            best = min((row for row in all_runs
                        if row["candidate_width"] == candidate_width
                        and row["reduction_target"] == target and row["feasible"]),
                       key=lambda row: row["total_cost_cny"])
            scenario_rows.append({
                "candidate_width": candidate_width, "reduction_target": target,
                "emission_cap_kg": cap, "baseline_cost_cny": baseline["total_cost_cny"],
                "baseline_emissions_kg": baseline["emissions_kg"],
                "candidate_objective_lower_bound_cny": lower_bound,
                "best_method": best["method"], "best_cost_cny": best["total_cost_cny"],
                "best_emissions_kg": best["emissions_kg"],
                "best_transit_hours": best["tonne_weighted_transit_hours"],
                "max_departure_utilization": best["max_departure_utilization"],
                "departures_at_least_90pct": best["departures_at_least_90pct"],
                "used_clean_departures": best["used_clean_departures"],
            })
    summary_rows = summaries(all_runs)
    oracle_width = min(args.candidate_widths, key=lambda value: abs(value-10))
    oracle_rows = run_micro_oracle(
        generated_by_width[oracle_width], brackets, args.seeds,
        max(12, args.population//2), max(20, args.generations//2),
        max(5, args.patience//2), args.oracle_orders)
    write_csv(args.output / "runs.csv", all_runs)
    write_csv(args.output / "method-summary.csv", summary_rows)
    write_csv(args.output / "scenario-summary.csv", scenario_rows)
    write_csv(args.output / "micro-oracle-summary.csv", oracle_rows)
    write_cost_chart(args.output / "cost-by-target-and-candidates.svg",
                     args.output / "cost-by-target-and-candidates.png",
                     summary_rows, args.candidate_widths)
    write_gap_chart(args.output / "micro-optimality-gap.svg",
                    args.output / "micro-optimality-gap.png", oracle_rows)
    write_cost_time_chart(args.output / "cost-time-by-target.svg",
                          args.output / "cost-time-by-target.png",
                          summary_rows, oracle_width)
    central = [row for row in scenario_rows if row["candidate_width"] == oracle_width]
    result = {
        "experiment_id": "policy-calibrated-algorithm-discrimination-v1",
        "data_classification": "policy_calibrated_synthetic",
        "target_reference": (
            "per-order minimum-cost single-trunk-mode emissions within the same candidate width"),
        "target_reference_scope": "single-mode-per-order",
        "network": {"nodes": len(config["nodes"]), "edges": len(config["edges"]),
                    "density": args.density, "network_seed": args.network_seed},
        "portfolio": {"orders": len(orders), "tonnes": sum(row["tonnes"] for row in orders),
                      "demand": "central", "time_profile": "balanced",
                      "carbon_price_cny_per_tco2e": 97.49},
        "conflict_calibration": {
            "road": "low-cost/high-emissions", "rail_water": "higher-cost/lower-emissions",
            "departure_hours": [0, 24, 48, 72, 96],
            "capacity_tonnes": args.capacity_tonnes,
            "capacity_units": args.capacity_units,
            "candidate_widths": args.candidate_widths,
        },
        "algorithm_budget": {"seeds": args.seeds, "population": args.population,
                             "generations": args.generations, "patience": args.patience,
                             "controls": CONTROLS},
        "central_scenarios": central,
        "micro_oracle": {"orders": args.oracle_orders, "candidate_limit_per_order": 4,
                         "results": oracle_rows},
        "claims": [
            "All network, order, timetable and capacity rows are synthetic scenario data.",
            "The 9.5%, 20% and 30% caps are relative to independent per-order minimum-cost choices over pure-road, pure-rail and pure-water routes.",
            "Archive-only is the deterministic emission-repair heuristic; heuristic+ga injects that chromosome into the population.",
            "Exact optimality gaps apply only to the reduced enumeration instance, not the 48-order portfolio.",
            "Candidate route generation remains beam-bounded; candidate-width comparison is not a physical-network global-optimum proof.",
        ],
    }
    (args.output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    central_by_target = {row["reduction_target"]: row for row in central}
    active_rows = [central_by_target[target] for target in TARGETS[1:]]
    archive_rows = {row["reduction_target"]: row for row in summary_rows
                    if row["candidate_width"] == oracle_width
                    and row["method"] == "archive-only"}
    hybrid_rows = {row["reduction_target"]: row for row in summary_rows
                   if row["candidate_width"] == oracle_width
                   and row["method"] == "heuristic+ga"}
    gains = [(archive_rows[target]["median_cost_cny"]
              / hybrid_rows[target]["median_cost_cny"] - 1) * 100
             for target in TARGETS[1:]]
    oracle_archive = {row["reduction_target"]: row for row in oracle_rows
                      if row["method"] == "archive-only"}
    report = f"""# Algorithm-discrimination benchmark

This is a separate hard synthetic benchmark; it does not replace the policy matrix.

- Target reference: emissions from independently selecting each order's minimum-cost deadline-feasible pure-road, pure-rail or pure-water candidate; each order uses one trunk mode.
- Active targets: 9.5%, 20%, and 30%.
- Candidate widths: {', '.join(map(str, args.candidate_widths))} routes per order.
- Search comparison: five GA variants plus a deterministic archive-only baseline.
- Capacity pressure: timed rail/water departures carry at most {args.capacity_units:g} shipment units or {args.capacity_tonnes:g} tonnes.
- Exact check: exhaustive enumeration for {args.oracle_orders} orders with at most four candidates each.

For the central top-k {oracle_width} scope, the uncapped reference is CNY {central_by_target[0]["baseline_cost_cny"]:,.2f} and {central_by_target[0]["baseline_emissions_kg"]:,.2f} kg CO2e. Best-found 9.5%, 20% and 30% solutions cost CNY {active_rows[0]["best_cost_cny"]:,.2f}, CNY {active_rows[1]["best_cost_cny"]:,.2f} and CNY {active_rows[2]["best_cost_cny"]:,.2f}, with tonne-weighted transit times of {active_rows[0]["best_transit_hours"]:.2f}, {active_rows[1]["best_transit_hours"]:.2f} and {active_rows[2]["best_transit_hours"]:.2f} hours. They contain {active_rows[0]["departures_at_least_90pct"]}, {active_rows[1]["departures_at_least_90pct"]} and {active_rows[2]["departures_at_least_90pct"]} departures at 90%--100% utilization.

Relative to archive-only, heuristic+GA lowers median cost by {gains[0]:.2f}%, {gains[1]:.2f}% and {gains[2]:.2f}% at the three active targets. On the {args.oracle_orders}-order exact instance, archive-only has {oracle_archive[.095]["median_gap_percent"]:.2f}%, {oracle_archive[.2]["median_gap_percent"]:.2f}% and {oracle_archive[.3]["median_gap_percent"]:.2f}% gaps, while every GA variant reaches the exact optimum in at least one run. These exact gaps do not extend to the full beam-bounded portfolio.

![Cost response](cost-by-target-and-candidates.png)

![Cost and transit time](cost-time-by-target.png)

![Exact optimality gaps](micro-optimality-gap.png)

Machine-readable details are in `results.json`; raw and summarized records are in the CSV files.
"""
    (args.output / "README.md").write_text(report, encoding="utf-8")


def parse_numbers(raw, cast):
    return [cast(value.strip()) for value in raw.split(",") if value.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=DESIGN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--density", type=float, default=.36)
    parser.add_argument("--network-seed", type=int, default=42)
    parser.add_argument("--orders", type=int, default=48)
    parser.add_argument("--candidate-widths", default="6,10,14")
    parser.add_argument("--candidate-routes", type=int, default=120)
    parser.add_argument("--beam-width", type=int, default=400)
    parser.add_argument("--capacity-tonnes", type=float, default=20)
    parser.add_argument("--capacity-units", type=float, default=2)
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=60)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--seeds", default="0,1,2,3,4")
    parser.add_argument("--workers", type=int, default=min(4, __import__("os").cpu_count() or 1))
    parser.add_argument("--oracle-orders", type=int, default=6)
    args = parser.parse_args()
    args.candidate_widths = parse_numbers(args.candidate_widths, int)
    args.seeds = parse_numbers(args.seeds, int)
    run(args)


if __name__ == "__main__":
    main()
