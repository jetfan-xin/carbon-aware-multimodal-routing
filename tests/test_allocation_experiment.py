"""Smoke test for the checked-in global-allocation experiment entrypoint."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AllocationExperimentTests(unittest.TestCase):
    def test_small_experiment_writes_auditable_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([
                sys.executable, "-B", str(ROOT / "tools/run_allocation_experiment.py"),
                "--seeds", "0", "--population", "8", "--generations", "2",
                "--patience", "1", "--output", str(output),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["portfolio"]["orders"], 12)
            self.assertEqual(report["network"]["physical_routes_per_order"], [4])
            self.assertEqual(report["exact_micro_oracle"]["candidate_evaluations"], 3072)
            self.assertEqual(report["exact_micro_oracle"]["solution"]["constraint_violation"], 0)
            self.assertTrue(report["best_full_portfolio"]["solution"]["feasible"])
            for name in ("runs.csv", "method-summary.csv", "traces.csv",
                         "best-assignments.csv", "best-capacity.csv",
                         "objective-by-method.svg", "best-assignment.svg",
                         "capacity-use.svg"):
                self.assertTrue((output / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
