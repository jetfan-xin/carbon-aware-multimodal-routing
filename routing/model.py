"""Validated directed freight network, priority decoder and scenario costing.

Modelling conventions are documented in docs/implementation.md.
Only the Python standard library is required for this module.
"""

from copy import deepcopy
import math


def number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return float(value)


def carbon_cost(emissions, brackets):
    """Integrate a progressive marginal schedule; do not tax all kg at the top rate."""
    number(emissions, "emissions")
    return math.fsum(
        max(0, min(emissions, brackets[i + 1][0] if i + 1 < len(brackets) else emissions) - lower) * rate
        for i, (lower, rate) in enumerate(brackets)
    )


class Network:
    def __init__(self, config):
        self.config = deepcopy(config)
        c = self.config
        self.nodes = c["nodes"]
        if not self.nodes or any(not isinstance(n, str) or not n.strip() for n in self.nodes):
            raise ValueError("nodes must be nonempty names")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("duplicate nodes")
        self.origin, self.destination = c["origin"], c["destination"]
        if self.origin not in self.nodes or self.destination not in self.nodes or self.origin == self.destination:
            raise ValueError("origin and destination must be distinct network nodes")
        self.modes = c["modes"]
        if not self.modes or not set(self.modes) <= {"road", "rail", "water"}:
            raise ValueError("supported modes: road, rail, water")
        for mode, values in self.modes.items():
            for field in ("speed_kmh", "rate_cny_per_tonne_km", "emissions_kg_per_tonne_km"):
                number(values[field], f"{mode}.{field}", positive=field == "speed_kmh")
        self.transfers = {}
        for transfer in c["transfers"]:
            pair = frozenset(transfer["modes"])
            if len(transfer["modes"]) != 2 or len(pair) != 2 or not pair <= self.modes.keys() or pair in self.transfers:
                raise ValueError("invalid or duplicate symmetric transfer pair")
            for field in ("hours_per_1000_tonnes", "cost_cny_per_tonne", "emissions_kg_per_tonne"):
                number(transfer[field], field)
            self.transfers[pair] = transfer
        self.edges = c["edges"]
        if not self.edges:
            raise ValueError("at least one directed edge is required")
        self.outgoing = {n: [] for n in self.nodes}
        seen = set()
        for i, edge in enumerate(self.edges):
            a, b, mode = edge["from"], edge["to"], edge["mode"]
            if a not in self.nodes or b not in self.nodes or a == b or mode not in self.modes:
                raise ValueError("invalid edge endpoints or mode")
            key = (a, b, mode)
            if key in seen:
                raise ValueError("duplicate directed mode edge")
            seen.add(key)
            number(edge["distance_km"], "distance_km", positive=True)
            self.outgoing[a].append(i)
        self.window = c["time_window_hours"]
        if len(self.window) != 2:
            raise ValueError("time window requires two bounds")
        for value in self.window:
            number(value, "time window")
        if self.window[0] > self.window[1]:
            raise ValueError("reversed time window")
        for field in ("storage_cny_per_tonne_hour", "late_penalty_cny_per_tonne_hour", "risk_weight"):
            number(c[field], field)
        if c["risk_weight"] > 1:
            raise ValueError("risk_weight must be between zero and one")
        if not isinstance(c["hard_deadline"], bool):
            raise ValueError("hard_deadline must be boolean")
        if c["emission_cap_kg"] is not None:
            number(c["emission_cap_kg"], "emission cap")
        self.brackets = [(x["lower_bound_kg"], x["rate_cny_per_kg"]) for x in c["carbon_brackets"]]
        if not self.brackets or self.brackets[0][0] != 0:
            raise ValueError("carbon schedule must start at zero")
        for i, (lower, rate) in enumerate(self.brackets):
            number(lower, "carbon lower bound")
            number(rate, "carbon marginal rate")
            if i and (lower <= self.brackets[i - 1][0] or rate < self.brackets[i - 1][1]):
                raise ValueError("carbon bounds must increase and rates must not decrease")
        self.scenarios = c["scenarios"]
        if not self.scenarios:
            raise ValueError("at least one scenario is required")
        names = set()
        for scenario in self.scenarios:
            if not isinstance(scenario["name"], str) or not scenario["name"] or scenario["name"] in names:
                raise ValueError("scenario names must be unique and nonempty")
            names.add(scenario["name"])
            for field in ("tonnes", "probability", "speed_multiplier", "rate_multiplier"):
                number(scenario[field], field, positive=True)
        if not math.isclose(math.fsum(s["probability"] for s in self.scenarios), 1, rel_tol=0, abs_tol=1e-9):
            raise ValueError("scenario probabilities must sum to one")

    def _choices(self, node, previous_mode, visited):
        for i in self.outgoing[node]:
            edge = self.edges[i]
            if edge["to"] not in visited and (
                previous_mode is None or previous_mode == edge["mode"]
                or frozenset((previous_mode, edge["mode"])) in self.transfers
            ):
                yield i

    def routes(self, priorities=None, max_states=100000):
        """Iterative DFS over city-simple routes; missing transfers are forbidden.

        Higher edge priority is visited first; edge index breaks ties. DFS
        backtracking repairs dead ends without teleporting or revisiting cities.
        A search limit raises, rather than incorrectly declaring infeasibility.
        """
        if not isinstance(max_states, int) or isinstance(max_states, bool) or max_states < 1:
            raise ValueError("max_states must be a positive integer")
        if priorities is None:
            priorities = [0] * len(self.edges)
        if len(priorities) != len(self.edges) or any(not math.isfinite(float(p)) for p in priorities):
            raise ValueError("one finite priority per edge is required")
        stack = [(self.origin, None, frozenset((self.origin,)), ())]
        expanded = 0
        while stack:
            expanded += 1
            if expanded > max_states:
                raise RuntimeError("route enumeration limit reached; feasibility/optimality is unresolved")
            node, mode, visited, route = stack.pop()
            if node == self.destination:
                yield route
                continue
            choices = sorted(self._choices(node, mode, visited), key=lambda i: (-priorities[i], i))
            for i in reversed(choices):
                edge = self.edges[i]
                stack.append((edge["to"], edge["mode"], visited | {edge["to"]}, route + (i,)))

    def decode(self, priorities):
        return next(self.routes(priorities), None)

    def evaluate(self, route):
        if not route:
            raise ValueError("a nonempty route is required")
        node, previous, visited = self.origin, None, {self.origin}
        legs, changes = [], []
        for i in route:
            if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(self.edges):
                raise ValueError("invalid edge index")
            edge = self.edges[i]
            if edge["from"] != node or edge["to"] in visited or node == self.destination:
                raise ValueError("route must be continuous and city-simple")
            mode = edge["mode"]
            if previous is not None and previous != mode:
                transfer = self.transfers.get(frozenset((previous, mode)))
                if transfer is None:
                    raise ValueError("unavailable mode transfer")
                changes.append(transfer)
            legs.append(edge)
            node, previous = edge["to"], mode
            visited.add(node)
        if node != self.destination:
            raise ValueError("route does not reach the destination")
        results = []
        for s in self.scenarios:
            tonnes = s["tonnes"]
            transport = math.fsum(e["distance_km"] * self.modes[e["mode"]]["rate_cny_per_tonne_km"] for e in legs) * tonnes * s["rate_multiplier"]
            transfer_cost = math.fsum(t["cost_cny_per_tonne"] for t in changes) * tonnes
            travel = math.fsum(e["distance_km"] / self.modes[e["mode"]]["speed_kmh"] for e in legs) / s["speed_multiplier"]
            transfer_time = math.fsum(t["hours_per_1000_tonnes"] for t in changes) * tonnes / 1000
            arrival = travel + transfer_time
            waiting = max(0, self.window[0] - arrival)
            late = max(0, arrival - self.window[1])
            time_cost = tonnes * (waiting * self.config["storage_cny_per_tonne_hour"] + late * self.config["late_penalty_cny_per_tonne_hour"])
            transport_emissions = math.fsum(e["distance_km"] * self.modes[e["mode"]]["emissions_kg_per_tonne_km"] for e in legs) * tonnes
            transfer_emissions = math.fsum(t["emissions_kg_per_tonne"] for t in changes) * tonnes
            emissions = transport_emissions + transfer_emissions
            carbon = carbon_cost(emissions, self.brackets)
            result = dict(name=s["name"], probability=s["probability"], tonnes=tonnes,
                          transport_cost_cny=transport, transfer_cost_cny=transfer_cost,
                          time_cost_cny=time_cost, carbon_cost_cny=carbon,
                          total_cost_cny=transport + transfer_cost + time_cost + carbon,
                          travel_hours=travel, transfer_hours=transfer_time, arrival_hours=arrival,
                          waiting_hours=waiting, lateness_hours=late,
                          transport_emissions_kg=transport_emissions,
                          transfer_emissions_kg=transfer_emissions, emissions_kg=emissions)
            if any(not math.isfinite(v) for v in result.values() if isinstance(v, (int, float))):
                raise ValueError("numerical overflow in route evaluation")
            results.append(result)
        expected = math.fsum(r["probability"] * r["total_cost_cny"] for r in results)
        worst = max(r["total_cost_cny"] for r in results)
        cap = self.config["emission_cap_kg"]
        deadline_violation = max(r["lateness_hours"] for r in results) if self.config["hard_deadline"] else 0
        carbon_violation = max(0, max(r["emissions_kg"] for r in results) - cap) if cap is not None else 0
        # Normalize unlike units; feasibility requires both violations to be zero.
        violation = deadline_violation / max(1, self.window[1]) + carbon_violation / max(1, cap or 0)
        return dict(edge_indices=list(route), route=[self.origin] + [e["to"] for e in legs],
                    modes=[e["mode"] for e in legs], scenarios=results,
                    expected_cost_cny=expected, worst_cost_cny=worst,
                    objective_cny=expected + self.config["risk_weight"] * (worst - expected),
                    constraint_violation=violation, feasible=violation == 0)


def solve_exact(network, max_states=100000):
    """Exhaustive baseline for small networks; never return a partial optimum."""
    if len(network.nodes) > 8:
        raise ValueError("exact baseline is limited to eight cities")
    best, evaluated = None, 0
    for route in network.routes(max_states=max_states):
        evaluated += 1
        result = network.evaluate(route)
        if result["feasible"] and (best is None or result["objective_cny"] < best["objective_cny"]):
            best = result
    return dict(solver="exact-enumeration", status="optimal" if best else "infeasible",
                route_evaluations=evaluated, solution=best)
