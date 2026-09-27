"""Transparent synthetic benchmarks calibrated to the archived 23-city schema.

No generated row is presented as public or enterprise transaction data.  The
generator preserves only documented aggregate characteristics: city count,
mode availability, distance ranges, cost parameters and demand scenarios.
"""

import math
import random


HISTORICAL_CITY_ORDER = [
    "Chongqing", "Yichang", "Zhicheng", "Shashi", "Chenglingji", "Honghu",
    "Hankou", "Yangluo", "Huangshi", "Wuxue", "Jiujiang", "Anqing",
    "Chizhou", "Tongling", "Wuhu", "Maanshan", "Nanjing", "Zhenjiang",
    "Gaogang", "Jiangyin", "Zhangjiagang", "Nantong", "Shanghai",
]


def historical_profile():
    return {
        "source_type": "derived_aggregate",
        "base_cities": 23,
        "city_pairs": 253,
        "available_mode_distances": {"road": 253, "rail": 250, "water": 251},
        "distance_km_summary": {
            "road": {"min": 30, "q1": 242, "median": 464, "q3": 754, "max": 1695},
            "rail": {"min": 31, "q1": 257.75, "median": 503, "q3": 785.75, "max": 1754},
            "water": {"min": 18, "q1": 290.5, "median": 609, "q3": 1005, "max": 2399},
        },
        "notes": [
            "Aggregates were computed from an authorized read-only copy of the November 2022 workbook.",
            "They are not row-level freight transactions and do not redistribute the source distance table.",
        ],
    }


def generate_network(node_count=23, density=1.0, seed=42):
    if not isinstance(node_count, int) or isinstance(node_count, bool) or node_count < 3:
        raise ValueError("node_count must be an integer >= 3")
    if not isinstance(density, (int, float)) or isinstance(density, bool) or not 0 < density <= 1:
        raise ValueError("density must be in (0, 1]")
    rng = random.Random(seed)
    nodes = list(HISTORICAL_CITY_ORDER[:node_count])
    if node_count > len(nodes):
        nodes.extend(f"SyntheticHub{i:04d}" for i in range(len(nodes), node_count))
    nodes[-1] = "Shanghai"
    pairs = [(i, j) for i in range(node_count) for j in range(i + 1, node_count)
             if j == i + 1 or rng.random() <= density]
    rail_missing = set(rng.sample(pairs, min(len(pairs), max(1, round(len(pairs) * 3 / 253)))))
    water_missing = set(rng.sample(pairs, min(len(pairs), max(1, round(len(pairs) * 2 / 253)))))
    edges = []
    for i, j in pairs:
        fraction = (j - i) / (node_count - 1)
        road = max(30, round(30 + 1665 * fraction * rng.uniform(0.82, 1.18), 2))
        distances = {"road": road, "rail": round(road * rng.uniform(0.95, 1.12), 2),
                     "water": round(road * rng.uniform(1.05, 1.55), 2)}
        for mode in ("road", "rail", "water"):
            if (mode == "rail" and (i, j) in rail_missing) or (mode == "water" and (i, j) in water_missing):
                continue
            edges.append({
                "id": f"e{i:04d}-{j:04d}-{mode}", "from": nodes[i], "to": nodes[j],
                "mode": mode, "distance_km": distances[mode], "capacity_tonnes": 500,
                "available": True, "source_type": "synthetic_calibrated",
            })
    coordinates = {
        node: [round(106 + 16 * i / (node_count - 1), 5),
               round(29 + 3 * i / (node_count - 1) + math.sin(i / 2) * 0.35, 5)]
        for i, node in enumerate(nodes)
    }
    return {
        "schema_version": 2,
        "description": "Synthetic, reproducible benchmark calibrated only to archived aggregate characteristics.",
        "data_classification": "synthetic_calibrated",
        "generator": {"seed": seed, "node_count": node_count, "density": density},
        "nodes": nodes, "coordinates": coordinates, "origin": nodes[0], "destination": nodes[-1],
        "modes": {
            "road": {"speed_kmh": 80, "rate_bands_cny_per_tonne_km": [0.263, 0.2485, 0.1805], "emissions_kg_per_tonne_km": 0.071},
            "rail": {"speed_kmh": 60, "rate_bands_cny_per_tonne_km": [0.196, 0.170, 0.1365], "emissions_kg_per_tonne_km": 0.042},
            "water": {"speed_kmh": 30, "rate_bands_cny_per_tonne_km": [0.045, 0.0365, 0.0255], "emissions_kg_per_tonne_km": 0.012},
        },
        "rate_band_boundaries_km": [500, 1000],
        "transfers": [
            {"modes": ["road", "rail"], "hours_per_1000_tonnes": 50, "cost_cny_per_tonne": 2, "emissions_kg_per_tonne": 0.128},
            {"modes": ["road", "water"], "hours_per_1000_tonnes": 50, "cost_cny_per_tonne": 2.25, "emissions_kg_per_tonne": 0.117},
            {"modes": ["rail", "water"], "hours_per_1000_tonnes": 50, "cost_cny_per_tonne": 2.5, "emissions_kg_per_tonne": 0.113},
        ],
        "edges": edges, "time_window_hours": [0, 62],
        "storage_cny_per_tonne_hour": 15, "late_penalty_cny_per_tonne_hour": 30,
        "hard_deadline": False, "emission_cap_kg": None, "risk_weight": 0,
        "carbon_brackets": [
            {"lower_bound_kg": 0, "rate_cny_per_kg": 0.05},
            {"lower_bound_kg": 150000, "rate_cny_per_kg": 0.10},
            {"lower_bound_kg": 500000, "rate_cny_per_kg": 0.15},
            {"lower_bound_kg": 1000000, "rate_cny_per_kg": 0.20},
        ],
        "scenarios": [
            {"name": "high-demand", "tonnes": 150, "probability": 0.36, "speed_multiplier": 0.90, "rate_multiplier": 1.08},
            {"name": "medium-demand", "tonnes": 85, "probability": 0.50, "speed_multiplier": 1.00, "rate_multiplier": 1.00},
            {"name": "low-demand", "tonnes": 40, "probability": 0.14, "speed_multiplier": 1.08, "rate_multiplier": 0.96},
        ],
    }


def generate_orders(nodes, count=1000, seed=42):
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count must be a positive integer")
    rng = random.Random(seed)
    orders = []
    for i in range(count):
        origin_index = rng.randrange(len(nodes) - 1)
        destination_index = rng.randrange(origin_index + 1, len(nodes))
        orders.append({
            "order_id": f"SYN-{i:08d}", "origin": nodes[origin_index],
            "destination": nodes[destination_index], "tonnes": rng.choice((20, 40, 85, 100, 150)),
            "deadline_hours": rng.choice((48, 62, 72, 96)),
            "source_type": "synthetic_calibrated",
        })
    return orders
