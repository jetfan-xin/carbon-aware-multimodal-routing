#!/usr/bin/env python3
"""Run order consolidation, network-state filtering and route planning."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from routing.pipeline import plan_orders


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network", type=Path)
    parser.add_argument("orders", type=Path)
    parser.add_argument("--solver", choices=("dijkstra", "exact", "native-ga"), default="dijkstra")
    parser.add_argument("--max-batch-tonnes", type=float, default=500)
    parser.add_argument("--closed-edge-id", action="append", default=[])
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    network = json.loads(args.network.read_text(encoding="utf-8"))
    orders = json.loads(args.orders.read_text(encoding="utf-8"))
    options = ({"population": args.population, "generations": args.generations, "seed": args.seed}
               if args.solver == "native-ga" else {})
    result = plan_orders(network, orders, args.solver, args.max_batch_tonnes,
                         args.closed_edge_id, options)
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
