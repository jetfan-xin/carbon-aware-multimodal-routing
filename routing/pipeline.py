"""End-to-end order consolidation, network-state filtering and route planning."""

from collections import deque
from copy import deepcopy
import html
import json
import math
from pathlib import Path

from .model import Network, solve_exact, solve_state_dijkstra
from .native_ga import solve_native_ga


def analyze_connectivity(network):
    """Report DFS reachability and a deterministic topological ordering when one exists."""
    adjacency = {node: set() for node in network.nodes}
    for edge in network.edges:
        if edge.get("available", True):
            adjacency[edge["from"]].add(edge["to"])
    visited = set()
    stack = [network.origin]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(reversed(sorted(adjacency[node] - visited)))
    indegree = {node: 0 for node in network.nodes}
    for targets in adjacency.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(node for node in network.nodes if indegree[node] == 0)
    order = []
    node_position = {node: index for index, node in enumerate(network.nodes)}
    while queue:
        node = queue.popleft()
        order.append(node)
        for target in sorted(adjacency[node], key=node_position.get):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    is_dag = len(order) == len(network.nodes)
    return {
        "dfs_reachable_nodes": [node for node in network.nodes if node in visited],
        "reachable_node_count": len(visited),
        "destination_reachable": network.destination in visited,
        "is_dag": is_dag,
        "topological_order": order if is_dag else None,
    }


def validate_orders(orders, nodes):
    seen = set()
    normalized = []
    for row in orders:
        required = ("order_id", "origin", "destination", "tonnes", "deadline_hours", "source_type")
        if any(key not in row for key in required):
            raise ValueError("orders require id, endpoints, tonnes, deadline and source_type")
        if row["order_id"] in seen:
            raise ValueError("duplicate order_id")
        seen.add(row["order_id"])
        if row["origin"] not in nodes or row["destination"] not in nodes or row["origin"] == row["destination"]:
            raise ValueError("invalid order endpoints")
        for field in ("tonnes", "deadline_hours"):
            value = row[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"order {field} must be positive and finite")
        if row["source_type"] not in {"public_aggregate", "manually_collected", "model_assumption",
                                      "derived", "synthetic_calibrated"}:
            raise ValueError("unrecognized order source_type")
        normalized.append(dict(row))
    return normalized


def consolidate_orders(orders, nodes, max_batch_tonnes=500):
    """Greedily consolidate compatible orders without changing their deadline."""
    if isinstance(max_batch_tonnes, bool) or not isinstance(max_batch_tonnes, (int, float)) or max_batch_tonnes <= 0:
        raise ValueError("max_batch_tonnes must be positive")
    rows = validate_orders(orders, nodes)
    rows.sort(key=lambda r: (r["origin"], r["destination"], r["deadline_hours"], r["order_id"]))
    batches = []
    for row in rows:
        remaining = float(row["tonnes"])
        while remaining > 0:
            key = (row["origin"], row["destination"], float(row["deadline_hours"]))
            batch = batches[-1] if batches and batches[-1]["key"] == key and batches[-1]["tonnes"] < max_batch_tonnes else None
            if batch is None:
                batch = {"key": key, "batch_id": f"BATCH-{len(batches):06d}", "origin": key[0],
                         "destination": key[1], "deadline_hours": key[2], "tonnes": 0.0,
                         "order_ids": [], "source_types": set()}
                batches.append(batch)
            quantity = min(remaining, max_batch_tonnes - batch["tonnes"])
            batch["tonnes"] += quantity
            remaining -= quantity
            if row["order_id"] not in batch["order_ids"]:
                batch["order_ids"].append(row["order_id"])
            batch["source_types"].add(row["source_type"])
    for batch in batches:
        batch.pop("key")
        batch["source_types"] = sorted(batch["source_types"])
    return batches


def network_for_batch(base_config, batch, closed_edge_ids=()):
    config = deepcopy(base_config)
    config["origin"], config["destination"] = batch["origin"], batch["destination"]
    config["time_window_hours"] = [0, batch["deadline_hours"]]
    config["scenarios"] = [{"name": "consolidated-batch", "tonnes": batch["tonnes"], "probability": 1,
                            "speed_multiplier": 1, "rate_multiplier": 1}]
    closed = set(closed_edge_ids)
    known = {edge.get("id") for edge in config["edges"]}
    if not closed <= known:
        raise ValueError("closed_edge_ids contains an unknown edge")
    for edge in config["edges"]:
        edge["available"] = edge.get("available", True) and edge.get("id") not in closed
    return Network(config)


def plan_orders(base_config, orders, solver="dijkstra", max_batch_tonnes=500,
                closed_edge_ids=(), solver_options=None):
    """Run the complete reproducible planning flow for a collection of orders."""
    solver_options = dict(solver_options or {})
    batches = consolidate_orders(orders, base_config["nodes"], max_batch_tonnes)
    plans = []
    for batch in batches:
        network = network_for_batch(base_config, batch, closed_edge_ids)
        connectivity = analyze_connectivity(network)
        if not connectivity["destination_reachable"]:
            result = {"solver": solver, "status": "infeasible-disconnected", "solution": None}
        elif solver == "dijkstra":
            result = solve_state_dijkstra(network)
        elif solver == "exact":
            result = solve_exact(network, **solver_options)
        elif solver == "native-ga":
            result = solve_native_ga(network, **solver_options)
        else:
            raise ValueError("solver must be dijkstra, exact or native-ga")
        plans.append({"batch": batch, "connectivity": connectivity, "routing": result})
    return {
        "pipeline": "order-consolidation-connectivity-routing-evaluation",
        "input_orders": len(orders), "consolidated_batches": len(batches),
        "closed_edges": sorted(closed_edge_ids), "solver": solver, "plans": plans,
    }


def write_route_svg(network, solution, output_path):
    """Write a self-contained schematic route map; no online tile service is used."""
    if not solution:
        raise ValueError("a solved route is required")
    if all(node in network.coordinates for node in solution["route"]):
        points = [network.coordinates[node] for node in solution["route"]]
        coordinate_source = "configured node coordinates"
    else:
        points = [[i, math.sin(i / 2)] for i in range(len(solution["route"]))]
        coordinate_source = "schematic fallback; no geographic coordinates supplied"
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    scale_x = lambda x: 40 + (x - min_x) / max(1e-9, max_x - min_x) * 720
    scale_y = lambda y: 360 - (y - min_y) / max(1e-9, max_y - min_y) * 320
    colors = {"road": "#d95f02", "rail": "#1b6ca8", "water": "#1f9e89"}
    lines = []
    for a, b, mode in zip(points, points[1:], solution["modes"]):
        lines.append(f'<line x1="{scale_x(a[0]):.1f}" y1="{scale_y(a[1]):.1f}" x2="{scale_x(b[0]):.1f}" y2="{scale_y(b[1]):.1f}" stroke="{colors[mode]}" stroke-width="5"/>')
    labels = []
    for index, (node, point) in enumerate(zip(solution["route"], points)):
        x, y = scale_x(point[0]), scale_y(point[1])
        anchor = "end" if index == len(points) - 1 else "start"
        label_x = x - 8 if anchor == "end" else x + 8
        labels.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#222"/><text x="{label_x:.1f}" y="{y - 8:.1f}" text-anchor="{anchor}" font-size="13">{html.escape(node)}</text>')
    metadata = html.escape(json.dumps({"route": solution["route"], "modes": solution["modes"],
                                       "coordinate_source": coordinate_source,
                                       "objective_cny": solution["objective_cny"]}, ensure_ascii=False))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400">'
           f'<title>Computed multimodal route</title><desc>{metadata}</desc><rect width="800" height="400" fill="white"/>'
           + "".join(lines + labels) + "</svg>\n")
    path = Path(output_path)
    path.write_text(svg, encoding="utf-8")
    return path
