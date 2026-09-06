"""Read an explicit JSON instance and print a machine-readable solution."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .model import Network, solve_exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("--solver", choices=("exact", "geatpy"), default="exact")
    parser.add_argument("--population", type=int, default=80)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--baseline", action="store_true", help="disable adaptive operators and restarts")
    args = parser.parse_args()
    try:
        raw = args.instance.read_bytes()
        network = Network(json.loads(raw))
        if args.solver == "exact":
            result = solve_exact(network)
        else:
            from .geatpy_solver import solve_geatpy
            result = solve_geatpy(network, args.population, args.generations, args.seed,
                                  args.patience, adaptive=not args.baseline)
        result["instance_sha256"] = hashlib.sha256(raw).hexdigest()
        result["implementation"] = "2026 reconstruction, not recovered historical source"
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if result["solution"] else 2
    except ImportError:
        print("Geatpy dependencies unavailable; see docs/reconstruction.md for the tested environment. The exact solver needs no packages.", file=sys.stderr)
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        print(f"Cannot solve instance: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
