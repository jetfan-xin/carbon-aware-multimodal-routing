"""Validated directed freight network, priority decoder and scenario costing.

Modelling conventions are documented in docs/current-implementation.md.
Only the Python standard library is required for this module.
"""

from copy import deepcopy
import heapq
import itertools
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
            for field in ("speed_kmh", "emissions_kg_per_tonne_km"):
                number(values[field], f"{mode}.{field}", positive=field == "speed_kmh")
            if "rate_bands_cny_per_tonne_km" in values:
                rates = values["rate_bands_cny_per_tonne_km"]
                bounds = c.get("rate_band_boundaries_km", [500, 1000])
                if len(rates) != len(bounds) + 1:
                    raise ValueError("rate bands require one more rate than boundaries")
                if any(number(x, f"{mode}.rate band") < 0 for x in rates):
                    raise ValueError("rate bands must be nonnegative")
                if any(number(x, "rate boundary", positive=True) <= 0 for x in bounds):
                    raise ValueError("rate boundaries must be positive")
                if any(a >= b for a, b in zip(bounds, bounds[1:])):
                    raise ValueError("rate boundaries must strictly increase")
            else:
                number(values["rate_cny_per_tonne_km"], f"{mode}.rate_cny_per_tonne_km")
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
            if "capacity_tonnes" in edge and edge["capacity_tonnes"] is not None:
                number(edge["capacity_tonnes"], "capacity_tonnes", positive=True)
            if "available" in edge and not isinstance(edge["available"], bool):
                raise ValueError("edge availability must be boolean")
            self.outgoing[a].append(i)
        self.coordinates = c.get("coordinates", {})
        if not isinstance(self.coordinates, dict):
            raise ValueError("coordinates must be a node-to-[longitude, latitude] mapping")
        for node, coordinate in self.coordinates.items():
            if node not in self.nodes or not isinstance(coordinate, list) or len(coordinate) != 2:
                raise ValueError("invalid node coordinate")
            if any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in coordinate):
                raise ValueError("coordinates must be finite numbers")
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
            if edge.get("available", True) and edge["to"] not in visited and (
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
            transport = math.fsum(e["distance_km"] * self.mode_rate(e["mode"], e["distance_km"]) for e in legs) * tonnes * s["rate_multiplier"]
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
        capacity_violation = max(
            (max(0, s["tonnes"] - e["capacity_tonnes"]) / e["capacity_tonnes"]
             for s in self.scenarios for e in legs if e.get("capacity_tonnes") is not None),
            default=0,
        )
        # Normalize unlike units; feasibility requires both violations to be zero.
        violation = deadline_violation / max(1, self.window[1]) + carbon_violation / max(1, cap or 0) + capacity_violation
        return dict(edge_indices=list(route), route=[self.origin] + [e["to"] for e in legs],
                    modes=[e["mode"] for e in legs], scenarios=results,
                    expected_cost_cny=expected, worst_cost_cny=worst,
                    objective_cny=expected + self.config["risk_weight"] * (worst - expected),
                    constraint_violation=violation, feasible=violation == 0)

    def mode_rate(self, mode, distance_km):
        """Return the historical distance-banded rate or a configured flat rate."""
        values = self.modes[mode]
        if "rate_bands_cny_per_tonne_km" not in values:
            return values["rate_cny_per_tonne_km"]
        for boundary, rate in zip(self.config.get("rate_band_boundaries_km", [500, 1000]),
                                  values["rate_bands_cny_per_tonne_km"]):
            if distance_km < boundary:
                return rate
        return values["rate_bands_cny_per_tonne_km"][-1]


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


def solve_state_dijkstra(network):
    """Fast deterministic baseline on the (city, previous-mode) state graph.

    The queue weight is an additive expected-cost approximation.  The returned
    route is then evaluated with the complete scenario, time-window and carbon
    model.  It is a baseline heuristic, not an optimality certificate.
    """
    first_carbon_rate = network.brackets[0][1]

    def edge_weight(edge, previous_mode):
        expected_transport = math.fsum(
            s["probability"] * s["tonnes"] * s["rate_multiplier"]
            for s in network.scenarios
        ) * edge["distance_km"] * network.mode_rate(edge["mode"], edge["distance_km"])
        expected_emissions = math.fsum(s["probability"] * s["tonnes"] for s in network.scenarios) * (
            edge["distance_km"] * network.modes[edge["mode"]]["emissions_kg_per_tonne_km"]
        )
        transfer_cost = transfer_emissions = 0
        if previous_mode is not None and previous_mode != edge["mode"]:
            transfer = network.transfers.get(frozenset((previous_mode, edge["mode"])))
            if transfer is None:
                return math.inf
            expected_tonnes = math.fsum(s["probability"] * s["tonnes"] for s in network.scenarios)
            transfer_cost = expected_tonnes * transfer["cost_cny_per_tonne"]
            transfer_emissions = expected_tonnes * transfer["emissions_kg_per_tonne"]
        return expected_transport + transfer_cost + first_carbon_rate * (expected_emissions + transfer_emissions)

    tie_breaker = itertools.count()
    queue = [(0.0, next(tie_breaker), network.origin, None, (), frozenset((network.origin,)))]
    best_state = {(network.origin, None): 0.0}
    expanded = 0
    while queue:
        score, _, node, previous_mode, route, visited = heapq.heappop(queue)
        state = (node, previous_mode)
        if score > best_state.get(state, math.inf):
            continue
        expanded += 1
        if node == network.destination:
            result = network.evaluate(route)
            return {"solver": "state-dijkstra-baseline", "status": "feasible-heuristic" if result["feasible"] else "infeasible-candidate",
                    "expanded_states": expanded, "solution": result if result["feasible"] else None}
        for i in network._choices(node, previous_mode, visited):
            edge = network.edges[i]
            if edge.get("capacity_tonnes") is not None and any(s["tonnes"] > edge["capacity_tonnes"] for s in network.scenarios):
                continue
            candidate_score = score + edge_weight(edge, previous_mode)
            candidate_state = (edge["to"], edge["mode"])
            if candidate_score < best_state.get(candidate_state, math.inf):
                best_state[candidate_state] = candidate_score
                heapq.heappush(queue, (candidate_score, next(tie_breaker), edge["to"], edge["mode"], route + (i,),
                                       visited | {edge["to"]}))
    return {"solver": "state-dijkstra-baseline", "status": "infeasible", "expanded_states": expanded, "solution": None}
