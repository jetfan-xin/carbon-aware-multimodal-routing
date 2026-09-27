"""Static and controlled checks for the byte-exact recovered GA_code snapshot."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
import unittest


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "historical" / "GA_code"
EXPECTED = {
    "calculate.py": "8f9e9a28c54b01cdec19f5168a41ed5702f776e61f9e5353871803acb3919887",
    "ga.py": "f85c7c19b429419342946c0d84af296b930049d2322b3e336c248f6c35507053",
    "input.py": "2b27a3be5c44c5a42941f98d837f134ebcdffbfb18e757b54b8c06511305d5d2",
    "main.py": "5320c431933769d16e3f5953012bd0b5bf2948b402dd354739814c837acb8543",
    "map.py": "4091ec1eb3829c65b8febcebfdeec08585463a25a1778accbbe8eaa5f1a98430",
    "readme.txt": "dcfb6bf25a7294f56c671f5c31d5fc3e91cb0d0a61768e578e3182ea2b77556d",
    "utils.py": "a085c9180e2de9e2df0ab16b27eb1045b18401fa007ea35235a17efbee628eef",
}


class MinimalNumpy(ModuleType):
    @staticmethod
    def array(values):
        return values

    @staticmethod
    def sum(values):
        return sum(values)


def load_archived_cost_modules():
    saved = {name: sys.modules.get(name) for name in ("numpy", "pandas", "utils")}
    try:
        sys.modules["numpy"] = MinimalNumpy("numpy")
        sys.modules["pandas"] = ModuleType("pandas")
        spec = importlib.util.spec_from_file_location("utils", SNAPSHOT / "utils.py")
        utils = importlib.util.module_from_spec(spec)
        sys.modules["utils"] = utils
        spec.loader.exec_module(utils)
        spec = importlib.util.spec_from_file_location("archived_calculate", SNAPSHOT / "calculate.py")
        calculate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(calculate)
        return calculate
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class HistoricalSnapshotTests(unittest.TestCase):
    def test_byte_exact_hashes(self):
        for name, expected in EXPECTED.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest(), expected)

    def test_saved_entry_configuration_is_recorded_without_historical_inference(self):
        source = (SNAPSHOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("NIND=100000", source)
        self.assertIn("MAXGEN=1", source)
        self.assertNotIn("seed=", source)

    def test_this_snapshot_does_not_embed_the_documented_custom_controller(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in SNAPSHOT.glob("*.py"))
        for token in ("outFunc", "XOVR", "mutOper", "20代", "灾变", "catastrophe", "restart"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_separate_artifacts_confirm_full_100_generation_runs(self):
        summaries = json.loads((ROOT / "data" / "terminal_summaries.json").read_text(encoding="utf-8"))
        full_runs = [run for run in summaries["runs"]
                     if run.get("generation_index") == 99 and run.get("reported_evaluations") == 100000]
        self.assertEqual(len(full_runs), 2)

    def test_combined_case_costs_through_unchanged_functions(self):
        calculate = load_archived_cost_modules()
        path = [0, 1, 2, 22]
        edges = [(46, 47), (24, 25), (25, 45)]
        distance = {str(edges[0]): 1543, str(edges[1]): 194, str(edges[2]): 96}
        args = {
            "CM_1": (0.263, 0.196, 0.045),
            "CM_2": (0.2485, 0.17, 0.0365),
            "CM_3": (0.1805, 0.1365, 0.0255),
            "V": (80, 60, 30),
            "CN": (2, 2.25, 2.5),
            "T2": (50, 50, 50),
            "P1": 15,
            "P2": 30,
            "Ta": 0,
            "Tb": 62,
            "EM": (0.071, 0.042, 0.012),
            "MIU": (0.128, 0.117, 0.113),
            "Zk": (0, 150000, 500000, 1000000),
            "W": (0.05, 0.1, 0.15, 0.2),
        }
        c1 = calculate.transport_cost(path, edges, 100, distance, args)
        c2, transfer_count = calculate.transit_cost(edges, 100, args)
        total_time, travel_time, transfer_time, c3 = calculate.time_cost(path, edges, 100, distance, args)
        transport_emissions, transfer_emissions, c4 = calculate.carbon_cost(path, edges, 100, distance, args)
        self.assertAlmostEqual(c1, 9618.65)
        self.assertAlmostEqual(c2, 500.0)
        self.assertEqual(transfer_count, 2)
        self.assertAlmostEqual(travel_time, 56.266666666666666)
        self.assertAlmostEqual(transfer_time, 5.0)
        self.assertAlmostEqual(total_time, 61.266666666666666)
        self.assertEqual(c3, 0)
        self.assertAlmostEqual(transport_emissions, 3069.6)
        self.assertAlmostEqual(transfer_emissions, 11.3)
        self.assertAlmostEqual(c4, 154.045)
        self.assertAlmostEqual(c1 + c2 + c3 + c4, 10272.695)

    def test_carbon_bracket_bug_is_preserved(self):
        calculate = load_archived_cost_modules()
        path = [0, 22]
        edges = [(0, 22)]
        args = {
            "EM": (0.071, 0.042, 0.012),
            "MIU": (0.128, 0.117, 0.113),
            "Zk": (0, 150000, 500000, 1000000),
            "W": (0.05, 0.1, 0.15, 0.2),
        }
        with self.assertRaises(IndexError):
            calculate.carbon_cost(path, edges, 10000, {str(edges[0]): 1695}, args)


if __name__ == "__main__":
    unittest.main()
