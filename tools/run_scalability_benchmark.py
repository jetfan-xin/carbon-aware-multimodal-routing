#!/usr/bin/env python3
"""Benchmark transparent synthetic data generation, batching and route search."""

import argparse
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.model import Network, solve_state_dijkstra
from routing.native_ga import solve_native_ga
from routing.pipeline import consolidate_orders
from routing.synthetic import generate_network, generate_orders


def timed(function, *args, **kwargs):
    started = time.perf_counter()
    value = function(*args, **kwargs)
    return value, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=23)
    parser.add_argument("--density", type=float, default=1.0)
    parser.add_argument("--orders", type=int, default=10000)
    parser.add_argument("--population", type=int, default=40)
    parser.add_argument("--generations", type=int, default=30)
    parser.add_argument("--seeds", default="0,7,42")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true", help="print only aggregate summary; output file remains complete")
    args = parser.parse_args()
    network_config, network_seconds = timed(generate_network, args.nodes, args.density, 42)
    orders, order_seconds = timed(generate_orders, network_config["nodes"], args.orders, 42)
    batches, batch_seconds = timed(consolidate_orders, orders, network_config["nodes"], 500)
    network = Network(network_config)
    baseline, baseline_seconds = timed(solve_state_dijkstra, network)
    runs = []
    for seed in (int(x) for x in args.seeds.split(",") if x.strip()):
        for adaptive, catastrophe in ((False, False), (True, False), (False, True), (True, True)):
            result, seconds = timed(solve_native_ga, network, args.population, args.generations,
                                    seed, 20, adaptive, catastrophe)
            runs.append({"seed": seed, "adaptive": adaptive, "catastrophe": catastrophe,
                         "seconds": seconds, "status": result["status"], "restarts": result["restarts"],
                         "candidate_evaluations": result["candidate_evaluations"],
                         "unique_route_evaluations": result["unique_route_evaluations"],
                         "objective_cny": result["solution"]["objective_cny"] if result["solution"] else None})
    summaries = []
    for adaptive, catastrophe in ((False, False), (True, False), (False, True), (True, True)):
        selected = [run for run in runs if run["adaptive"] == adaptive and run["catastrophe"] == catastrophe]
        objectives = [run["objective_cny"] for run in selected if run["objective_cny"] is not None]
        durations = sorted(run["seconds"] for run in selected)
        p95_index = max(0, math.ceil(0.95 * len(durations)) - 1)
        summaries.append({
            "adaptive": adaptive, "catastrophe": catastrophe, "runs": len(selected),
            "feasible_runs": len(objectives), "objective_min_cny": min(objectives) if objectives else None,
            "objective_mean_cny": statistics.fmean(objectives) if objectives else None,
            "objective_median_cny": statistics.median(objectives) if objectives else None,
            "objective_stdev_cny": statistics.pstdev(objectives) if len(objectives) > 1 else 0 if objectives else None,
            "runtime_p50_seconds": statistics.median(durations), "runtime_p95_seconds": durations[p95_index],
            "total_restarts": sum(run["restarts"] for run in selected),
        })
    report = {
        "data_classification": "synthetic_calibrated", "nodes": len(network.nodes),
        "edges": len(network.edges), "orders": len(orders), "consolidated_batches": len(batches),
        "timings_seconds": {"network_generation": network_seconds, "order_generation": order_seconds,
                            "order_consolidation": batch_seconds, "dijkstra": baseline_seconds},
        "dijkstra_status": baseline["status"], "ga_runs": runs, "ga_summary": summaries,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "scope": "All orders are generated and consolidated; routing benchmarks one 23-city scenario, not every batch.",
        "warning": "Synthetic benchmark performance; not historical deployment or enterprise production data.",
    }
    rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.quiet:
        print(json.dumps({"nodes": report["nodes"], "edges": report["edges"], "orders": report["orders"],
                          "consolidated_batches": report["consolidated_batches"],
                          "timings_seconds": report["timings_seconds"], "ga_summary": summaries}, indent=2))
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
