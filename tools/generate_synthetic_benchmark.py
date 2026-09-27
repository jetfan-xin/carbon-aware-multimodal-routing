#!/usr/bin/env python3
"""Generate explicitly labelled synthetic network and order benchmark files."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.synthetic import generate_network, generate_orders


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=23)
    parser.add_argument("--density", type=float, default=1.0)
    parser.add_argument("--orders", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--network-output", type=Path, required=True)
    parser.add_argument("--orders-output", type=Path, required=True)
    args = parser.parse_args()
    network = generate_network(args.nodes, args.density, args.seed)
    orders = generate_orders(network["nodes"], args.orders, args.seed)
    for path, value in ((args.network_output, network), (args.orders_output, orders)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"nodes": len(network["nodes"]), "edges": len(network["edges"]),
                      "orders": len(orders), "classification": "synthetic_calibrated"}))


if __name__ == "__main__":
    main()
