"""Read an explicit JSON instance and print a machine-readable solution."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .model import Network, solve_exact, solve_state_dijkstra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("--solver", choices=("exact", "dijkstra", "native-ga", "geatpy"), default="exact")
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--baseline", action="store_true", help="disable both adaptive operators and catastrophes")
    parser.add_argument("--no-adaptive", action="store_true", help="disable only the maintained adaptive formula")
    parser.add_argument("--no-catastrophe", action="store_true", help="disable only elite-preserving catastrophes")
    parser.add_argument("--output-map", type=Path, help="write a self-contained SVG of the computed route")
    args = parser.parse_args()
    try:
        raw = args.instance.read_bytes()
        network = Network(json.loads(raw))
        adaptive = not (args.baseline or args.no_adaptive)
        catastrophe = not (args.baseline or args.no_catastrophe)
        if args.solver == "exact":
            result = solve_exact(network)
        elif args.solver == "dijkstra":
            result = solve_state_dijkstra(network)
        elif args.solver == "native-ga":
            from .native_ga import solve_native_ga
            result = solve_native_ga(network, args.population, args.generations, args.seed,
                                     args.patience, adaptive, catastrophe)
        else:
            from .geatpy_solver import solve_geatpy
            result = solve_geatpy(network, args.population, args.generations, args.seed,
                                  args.patience, adaptive, catastrophe)
        result["instance_sha256"] = hashlib.sha256(raw).hexdigest()
        result["implementation"] = "carbon-aware-multimodal-routing"
        if args.output_map and result["solution"]:
            from .pipeline import write_route_svg
            write_route_svg(network, result["solution"], args.output_map)
            result["map_output"] = str(args.output_map)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["solution"] else 2
    except ImportError:
        print("Geatpy dependencies unavailable; see docs/current-implementation.md for the tested environment. The exact solver needs no packages.", file=sys.stderr)
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        print(f"Cannot solve instance: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
