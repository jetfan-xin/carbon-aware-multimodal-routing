#!/usr/bin/env python3
"""Build auditable tables and a schematic from the facility registry."""

import csv
import html
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routing.facility_data import load_registry, registry_summary, validate_registry  # noqa: E402


OUTPUT = ROOT / "benchmarks" / "facility-network"
MODE_COLOURS = {"road": "#d95f02", "rail": "#7570b3", "water": "#1b9e77"}
DECISION_COLOURS = {
    "core": "#2166ac", "conditional": "#67a9cf", "cargo_specific": "#fdae61",
    "evidence_only": "#bdbdbd", "excluded": "#737373",
}
LAYOUT = {
    "cq-guoyuan-port": (95, 110), "cq-tuanjiecun-rail": (95, 210),
    "hb-wuhan-yangluo-port": (245, 140),
    "jx-jiujiang-port-unresolved": (380, 140), "ah-anqing-port-unresolved": (520, 90),
    "ah-wuhu-zhujiaqiao-port": (520, 170), "ah-wuhu-yuxikou-port": (520, 250),
    "ah-maanshan-port-unresolved": (520, 330), "js-nanjing-longtan-port": (690, 90),
    "js-nanjing-qiba-port": (690, 170), "js-taicang-port": (835, 90),
    "js-taicang-shanggang-zhenghe": (835, 170), "js-nantong-tonghai-terminal": (835, 250),
    "sh-waigaoqiao-port": (1010, 70), "sh-luchaogang-rail": (1010, 150),
    "sh-yangshan-port": (1010, 230), "sh-yangpu-rail": (1010, 310),
    "zj-ningbo-chuanshan-port": (1180, 90),
    "zj-jiaxing-port-unresolved": (1180, 170), "zj-huzhou-port-unresolved": (1180, 250),
}


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_svg(path, registry):
    facilities = {row["id"]: row for row in registry["facilities"]["facilities"]}
    services = registry["services"]["services"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="520" viewBox="0 0 1320 520">',
        '<rect width="1320" height="520" fill="#fafafa"/>',
        '<text x="660" y="30" text-anchor="middle" font-family="sans-serif" font-size="21" font-weight="bold">Facility-level Yangtze / Yangtze River Delta evidence registry</text>',
        '<text x="660" y="52" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#555">Dashed lines are published service evidence, not yet numeric optimizer edges</text>',
    ]
    for service in services:
        start, end = service.get("from_facility_id"), service.get("to_facility_id")
        if start not in LAYOUT or end not in LAYOUT:
            continue
        x1, y1 = LAYOUT[start]; x2, y2 = LAYOUT[end]
        colour = MODE_COLOURS[service["mode"]]
        parts.append(f'<path d="M{x1},{y1} C{(x1+x2)/2},{y1-35} {(x1+x2)/2},{y2-35} {x2},{y2}" fill="none" stroke="{colour}" stroke-width="2.5" stroke-dasharray="7 5" opacity="0.75"><title>{html.escape(service["id"])}</title></path>')
    for facility_id, (x, y) in LAYOUT.items():
        row = facilities[facility_id]
        colour = DECISION_COLOURS[row["decision"]]
        stroke = "#111" if row["resolution"] == "exact_facility" else "#777"
        dash = "" if row["resolution"] == "exact_facility" else ' stroke-dasharray="4 3"'
        parts.append(f'<circle cx="{x}" cy="{y}" r="9" fill="{colour}" stroke="{stroke}" stroke-width="1.5"{dash}><title>{html.escape(row["id"])}: {html.escape(row["notes"])}</title></circle>')
        label = html.escape(row["name_zh"])
        parts.append(f'<text x="{x}" y="{y+24}" text-anchor="middle" font-family="sans-serif" font-size="10">{label}</text>')
    for x, label in ((95, "重庆"), (310, "中游走廊"), (520, "安徽"), (760, "江苏"), (1010, "上海"), (1180, "浙江")):
        parts.append(f'<text x="{x}" y="410" text-anchor="middle" font-family="sans-serif" font-size="13" font-weight="bold">{label}</text>')
    legends = [("#2166ac", "core"), ("#67a9cf", "conditional"), ("#fdae61", "cargo-specific"), ("#bdbdbd", "unresolved/evidence-only")]
    for index, (colour, label) in enumerate(legends):
        x = 120 + index * 190
        parts.append(f'<circle cx="{x}" cy="465" r="7" fill="{colour}"/><text x="{x+13}" y="469" font-family="sans-serif" font-size="11">{label}</text>')
    for index, mode in enumerate(("water", "rail", "road")):
        x = 855 + index * 120
        parts.append(f'<line x1="{x}" y1="465" x2="{x+24}" y2="465" stroke="{MODE_COLOURS[mode]}" stroke-width="3" stroke-dasharray="7 5"/><text x="{x+30}" y="469" font-family="sans-serif" font-size="11">{mode}</text>')
    parts.append('</svg>\n')
    path.write_text("".join(parts), encoding="utf-8")


def main():
    registry = validate_registry(load_registry())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    facilities = registry["facilities"]["facilities"]
    services = registry["services"]["services"]
    transfers = registry["transfers"]["transfers"]
    facility_rows = [{**row, "cargo_types": "|".join(row["cargo_types"]),
                      "modes": "|".join(row["modes"]), "source_ids": "|".join(row["source_ids"]),
                      "historical_2022": row["snapshot_status"]["historical_2022"],
                      "current_reference": row["snapshot_status"]["current_reference"]}
                     for row in facilities]
    write_csv(OUTPUT / "facilities.csv", facility_rows,
              ["id", "name_zh", "province", "yrd_scope", "resolution", "decision", "cargo_types", "modes",
               "historical_2022", "current_reference", "source_ids", "notes"])
    service_rows = [{**row, "source_ids": "|".join(row["source_ids"]),
                     "cargo_types": "|".join(row["cargo_types"]),
                     "missing_for_optimizer": "|".join(row["missing_for_optimizer"])} for row in services]
    write_csv(OUTPUT / "services.csv", service_rows,
              ["id", "from_facility_id", "to_facility_id", "from_area", "to_area", "mode", "cargo_types",
               "valid_from", "valid_to", "service_hours", "service_hours_range", "distance_km",
               "quoted_cost_cny", "quoted_cost_scope", "frequency",
               "evidence_grade", "optimizer_eligible", "missing_for_optimizer", "source_ids", "notes"])
    transfer_rows = [{**row, "source_ids": "|".join(row["source_ids"]), "modes": "|".join(row["modes"]),
                      "cargo_types": "|".join(row["cargo_types"]),
                      "missing_for_optimizer": "|".join(row["missing_for_optimizer"])} for row in transfers]
    write_csv(OUTPUT / "transfers.csv", transfer_rows,
              ["id", "facility_id", "modes", "cargo_types", "handling_hours", "handling_cost_cny",
               "evidence_grade", "optimizer_eligible", "missing_for_optimizer", "source_ids"])
    summary = registry_summary(registry)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_svg(OUTPUT / "facility-network.svg", registry)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
