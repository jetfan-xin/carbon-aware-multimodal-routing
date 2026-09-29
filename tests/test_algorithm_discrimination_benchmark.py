"""Regression tests for the separate hard algorithm benchmark."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from tools.run_algorithm_discrimination_benchmark import (hard_config,
                                                            timed_clean_departures)


ROOT = Path(__file__).resolve().parents[1]


class AlgorithmDiscriminationBenchmarkTests(unittest.TestCase):
    def test_hard_instance_has_cost_emissions_conflict_and_scarce_timetable(self):
        config = hard_config()
        road = config["modes"]["road"]
        water = config["modes"]["water"]
        self.assertLess(road["rate_bands_cny_per_tonne_km"][0],
                        water["rate_bands_cny_per_tonne_km"][0])
        self.assertGreater(road["emissions_kg_per_tonne_km"],
                           water["emissions_kg_per_tonne_km"])
        departures = timed_clean_departures(config)
        self.assertTrue(departures)
        self.assertEqual({row["departure_hour"] for row in departures},
                         {0, 24, 48, 72, 96})
        self.assertEqual({row["capacity_tonnes"] for row in departures}, {20})

    def test_quick_run_outputs_active_caps_archive_ablation_and_oracle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run([
                sys.executable, "-B",
                str(ROOT / "tools" / "run_algorithm_discrimination_benchmark.py"),
                "--output", str(output), "--orders", "8",
                "--candidate-widths", "4", "--candidate-routes", "40",
                "--beam-width", "120", "--population", "12",
                "--generations", "8", "--patience", "3",
                "--seeds", "0", "--workers", "1", "--oracle-orders", "4",
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            report = json.loads((output / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(report["target_reference"],
                             "per-order minimum-cost single-trunk-mode emissions within the same candidate width")
            self.assertEqual(report["conflict_calibration"]["capacity_tonnes"], 20)
            with (output / "method-summary.csv").open(encoding="utf-8") as stream:
                methods = {row["method"] for row in csv.DictReader(stream)}
            self.assertEqual(methods, {"archive-only", "fixed", "adaptive",
                                       "catastrophe", "combined", "heuristic+ga"})
            oracle = report["micro_oracle"]["results"]
            self.assertEqual({row["reduction_target"] for row in oracle},
                             {0, .095, .2, .3})
            for name in ("cost-by-target-and-candidates.svg",
                         "cost-time-by-target.svg", "micro-optimality-gap.svg"):
                self.assertTrue(ET.parse(output / name).getroot().tag.endswith("svg"))
            for name in ("cost-by-target-and-candidates.png",
                         "cost-time-by-target.png", "micro-optimality-gap.png"):
                with Image.open(output / name) as image:
                    image.verify()


if __name__ == "__main__":
    unittest.main()
