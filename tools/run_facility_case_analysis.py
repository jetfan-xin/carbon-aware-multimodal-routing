#!/usr/bin/env python3
"""Generate facility-level route, deadline and carbon-price analysis outputs."""

import csv
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing.facility_network import facility_case_config
from routing.model import Network, solve_exact
from routing.pipeline import write_route_svg


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "benchmarks" / "facility-case-analysis"
COLORS = {"road": "#d95f02", "rail": "#1b6ca8", "water": "#1f9e89",
          "infeasible": "#b8b8b8"}
DEADLINES = [48, 55, 60, 66, 72, 96, 120, 168, 192, 204, 216, 240, 276, 360]
CARBON_PRICES = [0, 62.36, 97.49, 500, 1000, 3000, 6000, 6500, 7000, 10000]
PAYLOADS = [10, 15, 20]
TIME_CASES = ["optimistic", "central", "conservative"]


def route_name(network, result):
    ids = [network.edges[index]["id"] for index in result["edge_indices"]]
    if len(ids) == 2:
        return "rail-road-via-luchaogang"
    if "road" in ids[0]:
        return "road-direct"
    if "express" in ids[0]:
        return "water-express-bundled"
    return "water-regular-bundled"


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg(title, body, width=1060, height=650, metadata=None):
    desc = html.escape(json.dumps(metadata or {}, ensure_ascii=False))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><title>{html.escape(title)}</title><desc>{desc}</desc>'
            '<rect width="100%" height="100%" fill="white"/>'
            f'<text x="40" y="38" font-family="sans-serif" font-size="21" font-weight="bold">{html.escape(title)}</text>'
            f'{body}</svg>\n')


def write_phase_map(path, rows):
    selected = [row for row in rows if row["time_case"] == "central" and row["payload_tonnes"] == 15]
    lookup = {(row["deadline_hours"], row["carbon_price_cny_per_tonne"]): row for row in selected}
    left, top, cw, ch = 142, 82, 82, 36
    body = []
    for column, price in enumerate(CARBON_PRICES):
        x = left + column * cw
        body.append(f'<text x="{x+cw/2}" y="70" text-anchor="middle" font-family="sans-serif" font-size="11">{price:g}</text>')
    for row_index, deadline in enumerate(DEADLINES):
        y = top + row_index * ch
        body.append(f'<text x="132" y="{y+23}" text-anchor="end" font-family="sans-serif" font-size="12">{deadline} h</text>')
        for column, price in enumerate(CARBON_PRICES):
            record = lookup[(deadline, price)]
            name = record["best_route"] or "infeasible"
            mode = "rail" if name and name.startswith("rail") else (
                "water" if name and name.startswith("water") else name.split("-")[0])
            x = left + column * cw
            body.append(f'<rect x="{x}" y="{y}" width="{cw-2}" height="{ch-2}" fill="{COLORS.get(mode, COLORS["infeasible"])}" opacity="0.84"/>')
            short = {"road-direct": "road", "rail-road-via-luchaogang": "rail+road",
                     "water-express-bundled": "fast water", "water-regular-bundled": "water"}.get(name, "none")
            body.append(f'<text x="{x+(cw-2)/2}" y="{y+22}" text-anchor="middle" font-family="sans-serif" font-size="9" fill="white">{short}</text>')
    body.append('<text x="552" y="625" text-anchor="middle" font-family="sans-serif" font-size="13">Carbon shadow price (CNY/tCO2e); 15 t per 20-ft container; central time case</text>')
    path.write_text(svg("Facility route switch map", "".join(body), metadata={"data": "scenario-grid.csv"}), encoding="utf-8")


def write_frontier(path, options):
    max_cost = max(row["transport_plus_transfer_cost_cny"] for row in options)
    max_emissions = max(row["emissions_kg"] for row in options)
    cost_ceiling = max_cost * 1.1
    emissions_ceiling = max_emissions * 1.1
    left, top, width, height = 105, 82, 760, 455
    body = [f'<line x1="{left}" y1="{top+height}" x2="{left+width}" y2="{top+height}" stroke="#333"/>',
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+height}" stroke="#333"/>']
    for fraction in (0, .25, .5, .75, 1):
        x = left + fraction * width
        y = top + height - fraction * height
        body.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+height}" stroke="#e0e0e0"/>')
        body.append(f'<text x="{x:.1f}" y="{top+height+20}" text-anchor="middle" font-family="sans-serif" font-size="10">{emissions_ceiling*fraction:.0f}</text>')
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left+width}" y2="{y:.1f}" stroke="#e0e0e0"/>')
        body.append(f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-family="sans-serif" font-size="10">{cost_ceiling*fraction:.0f}</text>')
    for row in options:
        x = left + row["emissions_kg"] / emissions_ceiling * width
        y = top + height - row["transport_plus_transfer_cost_cny"] / cost_ceiling * height
        mode = "rail" if row["route_id"].startswith("rail") else row["modes"].split("+")[0]
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{COLORS[mode]}"/>')
        if row["route_id"] == "road-direct":
            label_x, label_y, anchor = x - 12, y + 22, "end"
        elif row["route_id"] == "water-express-bundled":
            label_x, label_y, anchor = x + 12, y - 14, "start"
        elif row["route_id"] == "water-regular-bundled":
            label_x, label_y, anchor = x + 12, y + 24, "start"
        else:
            label_x, label_y, anchor = x + 12, y - 8, "start"
        body.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" font-family="sans-serif" font-size="12">{row["route_id"]}</text>')
    body.append('<text x="490" y="604" text-anchor="middle" font-family="sans-serif" font-size="13">kg CO2e per 15-t shipment</text>')
    body.append('<text x="25" y="310" transform="rotate(-90 25 310)" text-anchor="middle" font-family="sans-serif" font-size="13">Transport + transfer cost (CNY)</text>')
    path.write_text(svg("Facility alternatives: cost and emissions", "".join(body), metadata={"data": "route-options.csv", "carbon_price": 0}), encoding="utf-8")


def write_components(path, options):
    maximum = max(row["transport_plus_transfer_cost_cny"] for row in options)
    body = []
    for index, row in enumerate(options):
        y = 92 + index * 112
        transport_w = row["transport_cost_cny"] / maximum * 650
        transfer_w = row["transfer_cost_cny"] / maximum * 650
        body.append(f'<text x="270" y="{y+22}" text-anchor="end" font-family="sans-serif" font-size="13">{row["route_id"]}</text>')
        body.append(f'<rect x="285" y="{y}" width="{transport_w:.1f}" height="34" fill="#4c78a8"/>')
        body.append(f'<rect x="{285+transport_w:.1f}" y="{y}" width="{transfer_w:.1f}" height="34" fill="#f58518"/>')
        bar_end = 285 + transport_w + transfer_w
        label_x = 920 if bar_end > 800 else bar_end + 15
        anchor = "end" if bar_end > 800 else "start"
        fill = "white" if bar_end > 800 else "#111"
        body.append(f'<text x="{label_x:.1f}" y="{y+23}" text-anchor="{anchor}" fill="{fill}" font-family="sans-serif" font-size="12">{row["transport_plus_transfer_cost_cny"]:.0f} CNY; {row["arrival_hours"]:.2f} h; {row["emissions_kg"]:.1f} kg</text>')
    body.append('<rect x="320" y="558" width="14" height="14" fill="#4c78a8"/><text x="340" y="570" font-family="sans-serif" font-size="12">transport</text>')
    body.append('<rect x="430" y="558" width="14" height="14" fill="#f58518"/><text x="450" y="570" font-family="sans-serif" font-size="12">facility transfer</text>')
    path.write_text(svg("Facility route cost, time and emissions", "".join(body), metadata={"data": "route-options.csv", "payload_tonnes": 15}), encoding="utf-8")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    grid = []
    for time_case in TIME_CASES:
        for payload in PAYLOADS:
            for deadline in DEADLINES:
                for carbon_price in CARBON_PRICES:
                    network = Network(facility_case_config(
                        payload_tonnes=payload, deadline_hours=deadline,
                        carbon_price_cny_per_tonne=carbon_price, time_case=time_case))
                    solved = solve_exact(network)
                    solution = solved["solution"]
                    scenario = solution["scenarios"][0] if solution else {}
                    grid.append({
                        "time_case": time_case,
                        "payload_tonnes": payload,
                        "deadline_hours": deadline,
                        "carbon_price_cny_per_tonne": carbon_price,
                        "status": solved["status"],
                        "best_route": route_name(network, solution) if solution else None,
                        "route_nodes": ">".join(solution["route"]) if solution else None,
                        "modes": "+".join(solution["modes"]) if solution else None,
                        "arrival_hours": scenario.get("arrival_hours"),
                        "transport_cost_cny": scenario.get("transport_cost_cny"),
                        "transfer_cost_cny": scenario.get("transfer_cost_cny"),
                        "carbon_cost_cny": scenario.get("carbon_cost_cny"),
                        "total_cost_cny": scenario.get("total_cost_cny"),
                        "emissions_kg": scenario.get("emissions_kg"),
                    })

    base = Network(facility_case_config(deadline_hours=360, payload_tonnes=15, time_case="central"))
    options = []
    named_solutions = {}
    for route in base.routes():
        result = base.evaluate(route)
        scenario = result["scenarios"][0]
        name = route_name(base, result)
        named_solutions[name] = result
        options.append({
            "route_id": name,
            "route_nodes": ">".join(result["route"]),
            "modes": "+".join(result["modes"]),
            "arrival_hours": scenario["arrival_hours"],
            "travel_hours": scenario["travel_hours"],
            "handling_hours": scenario["handling_hours"],
            "scheduled_wait_hours": scenario["scheduled_wait_hours"],
            "transfer_hours": scenario["transfer_hours"],
            "transport_cost_cny": scenario["transport_cost_cny"],
            "transfer_cost_cny": scenario["transfer_cost_cny"],
            "transport_plus_transfer_cost_cny": scenario["transport_cost_cny"] + scenario["transfer_cost_cny"],
            "emissions_kg": scenario["emissions_kg"],
            "edge_ids": ">".join(base.edges[index]["id"] for index in result["edge_indices"]),
        })
    options.sort(key=lambda row: row["arrival_hours"])

    rail = next(row for row in options if row["route_id"].startswith("rail"))
    express = next(row for row in options if row["route_id"].startswith("water-express"))
    regular = next(row for row in options if row["route_id"].startswith("water-regular"))
    threshold_express = ((rail["transport_plus_transfer_cost_cny"] - express["transport_plus_transfer_cost_cny"])
                         / ((express["emissions_kg"] - rail["emissions_kg"]) / 1000))
    threshold_regular = ((rail["transport_plus_transfer_cost_cny"] - regular["transport_plus_transfer_cost_cny"])
                         / ((regular["emissions_kg"] - rail["emissions_kg"]) / 1000))

    write_csv(OUTPUT / "scenario-grid.csv", grid)
    write_csv(OUTPUT / "route-options.csv", options)
    write_phase_map(OUTPUT / "deadline-carbon-phase.svg", grid)
    write_frontier(OUTPUT / "cost-emissions-frontier.svg", options)
    write_components(OUTPUT / "route-components.svg", options)
    for name, result in named_solutions.items():
        write_route_svg(base, result, OUTPUT / f"route-{name}.svg")

    report = {
        "experiment_id": "facility-calibrated-cq-yangshan-v2-operator-data",
        "model_case_id": "cq-guoyuan-to-yangshan-calibrated",
        "grid": {"rows": len(grid), "time_cases": TIME_CASES, "payloads_tonnes": PAYLOADS,
                 "deadlines_hours": DEADLINES, "carbon_prices_cny_per_tonne": CARBON_PRICES},
        "central_15t_routes": options,
        "switch_boundaries_central_15t": {
            "road_arrival_hours": next(row["arrival_hours"] for row in options if row["route_id"] == "road-direct"),
            "rail_road_arrival_hours": rail["arrival_hours"],
            "express_water_arrival_hours": express["arrival_hours"],
            "regular_water_arrival_hours": regular["arrival_hours"],
            "rail_beats_express_water_above_cny_per_tco2": threshold_express,
            "rail_beats_regular_water_above_cny_per_tco2": threshold_regular,
        },
        "interpretation": [
            "At observed-reference carbon prices around 62-97 CNY/tCO2e, carbon cost is too small to change the cost-minimizing route.",
            "Under the central cases, rail-road becomes feasible before the conservative road-time band; the selected route then changes to express water and current-reference regular water as deadlines relax.",
            "Rail has the lowest modeled emissions under the cited default factors; a route switch back from water occurs only at a stress-test carbon price around the reported thresholds.",
        ],
        "warnings": [
            "This is a calibrated analysis network, not an observed end-to-end operational dataset.",
            "The rail time is real historical Yangpu-Tuanjiecun operation mapped to Guoyuan-Luchaogang; current service and endpoint equivalence remain unverified.",
            "The CNY 200 Luchaogang-area drayage input is one public spot posting. The one-hour handling value follows an official greater-than-60-percent completion threshold, while scheduled waiting remains an explicit assumption.",
            "The CNY 180 loaded-TEU policy support is paid to eligible operators and is reported separately, not subtracted from the customer cost.",
            "Lane quotes mix publication dates and scopes: operator comparisons, FIO corridor averages and a spot drayage posting are not a single end-to-end invoice.",
            "Carbon prices are shadow prices; the national ETS is not represented as directly regulating freight shipments.",
            "Exact enumeration proves the best route only within this four-route model, not a global real-world optimum.",
        ],
    }
    (OUTPUT / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    readme = f"""# Facility-calibrated Chongqing-Yangshan analysis

This directory is generated by `python3 -B tools/run_facility_case_analysis.py`.

- `scenario-grid.csv`: {len(grid)} deterministic deadline, carbon-price, payload and time-case cells.
- `route-options.csv`: the four central 15-tonne alternatives and their component metrics.
- `results.json`: switch boundaries, interpretation and caveats.
- `deadline-carbon-phase.svg`: selected route over deadline and carbon-price cells.
- `cost-emissions-frontier.svg` and `route-components.svg`: cost/time/emissions trade-offs.
- `route-*.svg`: schematic route outputs; these are not GIS navigation maps.

The raw facility/service registry remains separate. This model combines operator disclosures, an official market index, one sanitized marketplace spot observation, team-collected distances and labelled remaining assumptions; consult `data/facility_network/model_inputs.json` for field-level provenance.
"""
    (OUTPUT / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps({"output_dir": str(OUTPUT), "grid_rows": len(grid),
                      "rail_express_threshold": threshold_express,
                      "rail_regular_threshold": threshold_regular}, indent=2))


if __name__ == "__main__":
    main()
