"""Redirect historical workbook paths and execute the unchanged GA entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "historical" / "GA_code"
DISTANCE_FILE = "长三角周边各转运点之间的距离.xlsx"
PARAMETER_FILES = {
    "不同运输方式的运输参数.xlsx",
    "不同运输方式转运相关数据.xlsx",
    "单位仓储和单位惩罚成本.xlsx",
    "碳政策.xlsx",
    "时间段.xlsx",
    "输入 情景-运货量-概率.xlsx",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distance-dir", required=True, type=Path)
    parser.add_argument("--parameter-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int, help="Optional compatibility override; the 2022 entry point set no seed.")
    parser.add_argument(
        "--acknowledge-large-run",
        action="store_true",
        help="Confirm that the original run prints 100,000 evaluations and writes plots/results.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.acknowledge_large_run:
        raise SystemExit("Refusing to run without --acknowledge-large-run; read compatibility/README.md first.")

    expected = {DISTANCE_FILE: args.distance_dir / DISTANCE_FILE}
    expected.update({name: args.parameter_dir / name for name in PARAMETER_FILES})
    missing = [str(path) for path in expected.values() if not path.is_file()]
    if missing:
        raise SystemExit("Missing historical workbook(s):\n" + "\n".join(missing))

    try:
        import geatpy
        import numpy as np
        import pandas as pd
    except ImportError as exc:
        raise SystemExit(f"Historical dependency unavailable: {exc}") from exc
    if getattr(geatpy, "__version__", None) != "2.7.0":
        raise SystemExit("The recovered framework version is Geatpy 2.7.0; refusing a silent version substitution.")

    original_read_excel = pd.read_excel

    def redirected_read_excel(path, *positional, **keywords):
        basename = str(path).replace("\\", "/").rsplit("/", 1)[-1]
        if basename not in expected:
            raise FileNotFoundError(f"Unrecognized historical workbook request: {path}")
        return original_read_excel(expected[basename], *positional, **keywords)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    previous_cwd = Path.cwd()
    previous_path = list(sys.path)
    try:
        pd.read_excel = redirected_read_excel
        if args.seed is not None:
            np.random.seed(args.seed)
        os.chdir(args.output_dir)
        sys.path.insert(0, str(SNAPSHOT))
        runpy.run_path(str(SNAPSHOT / "main.py"), run_name="__main__")
    finally:
        pd.read_excel = original_read_excel
        sys.path[:] = previous_path
        os.chdir(previous_cwd)


if __name__ == "__main__":
    main()
