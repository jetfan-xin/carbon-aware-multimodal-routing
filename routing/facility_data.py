"""Validation and reporting for the evidence-backed facility network registry.

This registry is deliberately separate from :mod:`routing.model`.  A port plan
or a published service mention is not automatically a numeric optimizer edge.
Only records with resolved facilities, an operational date and the fields
required by the routing model may later be promoted into a runnable network.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "facility_network"
ALLOWED_MODES = {"road", "rail", "water"}
ALLOWED_RESOLUTION = {"exact_facility", "port_area_unresolved", "city_gateway"}
ALLOWED_DECISIONS = {"core", "conditional", "cargo_specific", "evidence_only", "excluded"}
ALLOWED_EVIDENCE = {"A", "B", "C"}
ALLOWED_FIELD_EVIDENCE = {
    "official_reported", "team_collected_model_input", "cross_corridor_proxy",
    "derived_from_official_lower_bound", "model_assumption",
    "operator_reported", "corridor_specific_historical_operation",
    "marketplace_observation", "official_market_index",
    "industry_association_reported",
}


def _read(name: str, data_dir: Path = DATA_DIR):
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


def load_registry(data_dir: Path = DATA_DIR):
    return {
        "sources": _read("sources.json", data_dir),
        "facilities": _read("facilities.json", data_dir),
        "services": _read("services.json", data_dir),
        "transfers": _read("transfers.json", data_dir),
        "model_inputs": _read("model_inputs.json", data_dir),
    }


def _require_date(value, field):
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date or null") from exc


def validate_registry(registry):
    """Validate provenance and prevent planning evidence becoming fake edges."""
    source_rows = registry["sources"]["sources"]
    facility_rows = registry["facilities"]["facilities"]
    service_rows = registry["services"]["services"]
    transfer_rows = registry["transfers"]["transfers"]

    source_ids = [row["id"] for row in source_rows]
    facility_ids = [row["id"] for row in facility_rows]
    service_ids = [row["id"] for row in service_rows]
    transfer_ids = [row["id"] for row in transfer_rows]
    for label, values in (("source", source_ids), ("facility", facility_ids),
                          ("service", service_ids), ("transfer", transfer_ids)):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} id")

    known_sources = set(source_ids)
    known_facilities = set(facility_ids)
    facility_by_id = {row["id"]: row for row in facility_rows}

    for source in source_rows:
        _require_date(source["published_at"], f"source {source['id']} published_at")
        if source["url"] is None:
            digest = source.get("sha256", "")
            if not source.get("private_source_id") or len(digest) != 64:
                raise ValueError(f"private source {source['id']} requires stable ID and SHA-256")
            try:
                bytes.fromhex(digest)
            except ValueError as exc:
                raise ValueError(f"invalid SHA-256 for {source['id']}") from exc
        elif not source["url"].startswith("https://"):
            raise ValueError(f"source {source['id']} must use an HTTPS URL")

    for facility in facility_rows:
        if facility["resolution"] not in ALLOWED_RESOLUTION:
            raise ValueError(f"invalid resolution for {facility['id']}")
        if facility["decision"] not in ALLOWED_DECISIONS:
            raise ValueError(f"invalid decision for {facility['id']}")
        if not set(facility["modes"]) <= ALLOWED_MODES:
            raise ValueError(f"invalid mode for {facility['id']}")
        if not set(facility["source_ids"]) <= known_sources:
            raise ValueError(f"unknown source for {facility['id']}")
        if facility["decision"] == "core" and facility["resolution"] != "exact_facility":
            raise ValueError(f"core facility {facility['id']} is not resolved")
        for snapshot, state in facility["snapshot_status"].items():
            if snapshot not in {"historical_2022", "current_reference"}:
                raise ValueError(f"unknown snapshot {snapshot}")
            if state not in {"operational", "planned", "unverified", "not_applicable"}:
                raise ValueError(f"invalid snapshot state for {facility['id']}")

    for service in service_rows:
        if service["evidence_grade"] not in ALLOWED_EVIDENCE:
            raise ValueError(f"invalid evidence grade for {service['id']}")
        if service["mode"] not in ALLOWED_MODES:
            raise ValueError(f"invalid service mode for {service['id']}")
        if not set(service["source_ids"]) <= known_sources:
            raise ValueError(f"unknown service source for {service['id']}")
        _require_date(service["valid_from"], f"service {service['id']} valid_from")
        _require_date(service.get("valid_to"), f"service {service['id']} valid_to")
        endpoints = (service.get("from_facility_id"), service.get("to_facility_id"))
        for endpoint in endpoints:
            if endpoint is not None and endpoint not in known_facilities:
                raise ValueError(f"unknown endpoint {endpoint} for {service['id']}")
        if service["optimizer_eligible"]:
            if None in endpoints:
                raise ValueError(f"optimizer service {service['id']} has unresolved endpoints")
            if service.get("service_hours") is None or service.get("distance_km") is None:
                raise ValueError(f"optimizer service {service['id']} lacks time or distance")
            if any(facility_by_id[x]["resolution"] != "exact_facility" for x in endpoints):
                raise ValueError(f"optimizer service {service['id']} uses unresolved facilities")

    for transfer in transfer_rows:
        if transfer["facility_id"] not in known_facilities:
            raise ValueError(f"unknown transfer facility for {transfer['id']}")
        if not set(transfer["modes"]) <= ALLOWED_MODES or len(set(transfer["modes"])) != 2:
            raise ValueError(f"invalid transfer modes for {transfer['id']}")
        if not set(transfer["source_ids"]) <= known_sources:
            raise ValueError(f"unknown transfer source for {transfer['id']}")
        if transfer["optimizer_eligible"] and (
                transfer.get("handling_hours") is None or transfer.get("handling_cost_cny") is None):
            raise ValueError(f"optimizer transfer {transfer['id']} lacks numeric handling data")
    validate_model_inputs(registry["model_inputs"], known_sources, known_facilities)
    return registry


def _validate_field_provenance(row, numeric_fields, known_sources):
    provenance = row.get("field_provenance", {})
    for field in numeric_fields:
        if field not in row:
            continue
        record = provenance.get(field)
        if not record or record.get("evidence_class") not in ALLOWED_FIELD_EVIDENCE:
            raise ValueError(f"{row['id']} lacks valid provenance for {field}")
        if not set(record.get("source_ids", ())) <= known_sources:
            raise ValueError(f"{row['id']} has unknown provenance source for {field}")
        if record["evidence_class"] == "model_assumption" and not record.get("assumption"):
            raise ValueError(f"{row['id']} must explain model assumption for {field}")


def validate_model_inputs(data, known_sources, known_facilities):
    """Validate the separate calibrated layer without upgrading raw evidence."""
    edge_rows = data["edges"]
    transfer_rows = data["transfers"]
    case_rows = data["cases"]
    edge_ids = [row["id"] for row in edge_rows]
    transfer_ids = [row["id"] for row in transfer_rows]
    case_ids = [row["id"] for row in case_rows]
    for label, values in (("model edge", edge_ids), ("model transfer", transfer_ids),
                          ("model case", case_ids)):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} id")
    for mode, record in data["mode_parameters"].items():
        if mode not in ALLOWED_MODES or record["source_id"] not in known_sources:
            raise ValueError("invalid model mode parameter")
        if record["emissions_kg_per_tonne_km"] < 0:
            raise ValueError("negative emission factor")
    for edge in edge_rows:
        if edge["from_facility_id"] not in known_facilities or edge["to_facility_id"] not in known_facilities:
            raise ValueError(f"unknown model edge endpoint for {edge['id']}")
        if edge["mode"] not in ALLOWED_MODES:
            raise ValueError(f"invalid mode for {edge['id']}")
        for field in ("distance_km", "quoted_cost_cny_per_20ft"):
            if not isinstance(edge[field], (int, float)) or isinstance(edge[field], bool) or edge[field] <= 0:
                raise ValueError(f"invalid {field} for {edge['id']}")
        times = edge["service_hours"]
        if set(times) != {"optimistic", "central", "conservative"} or any(value <= 0 for value in times.values()):
            raise ValueError(f"invalid time cases for {edge['id']}")
        _validate_field_provenance(
            edge, ("distance_km", "quoted_cost_cny_per_20ft", "service_hours",
                   "handling_hours", "scheduled_wait_hours"), known_sources)
    for transfer in transfer_rows:
        if transfer["facility_id"] not in known_facilities:
            raise ValueError(f"unknown facility for model transfer {transfer['id']}")
        if len(set(transfer["modes"])) != 2 or not set(transfer["modes"]) <= ALLOWED_MODES:
            raise ValueError(f"invalid modes for model transfer {transfer['id']}")
        _validate_field_provenance(
            transfer, ("hours_per_1000_tonnes", "cost_cny_per_tonne",
                       "emissions_kg_per_tonne"), known_sources)
    known_edges, known_transfers = set(edge_ids), set(transfer_ids)
    for case in case_rows:
        if case["origin"] not in known_facilities or case["destination"] not in known_facilities:
            raise ValueError(f"unknown case endpoint for {case['id']}")
        if not set(case["edge_ids"]) <= known_edges or not set(case["transfer_ids"]) <= known_transfers:
            raise ValueError(f"unknown model input in case {case['id']}")
        if not case["edge_ids"]:
            raise ValueError(f"empty model case {case['id']}")
    return data


def registry_summary(registry):
    validate_registry(registry)
    facilities = registry["facilities"]["facilities"]
    services = registry["services"]["services"]
    transfers = registry["transfers"]["transfers"]
    return {
        "facilities": len(facilities),
        "exact_facilities": sum(row["resolution"] == "exact_facility" for row in facilities),
        "core_facilities": sum(row["decision"] == "core" for row in facilities),
        "historical_operational_facilities": sum(
            row["snapshot_status"]["historical_2022"] == "operational" for row in facilities),
        "current_operational_facilities": sum(
            row["snapshot_status"]["current_reference"] == "operational" for row in facilities),
        "service_evidence_records": len(services),
        "optimizer_eligible_services": sum(row["optimizer_eligible"] for row in services),
        "transfer_evidence_records": len(transfers),
        "optimizer_eligible_transfers": sum(row["optimizer_eligible"] for row in transfers),
        "calibrated_model_edges": len(registry["model_inputs"]["edges"]),
        "runnable_model_cases": len(registry["model_inputs"]["cases"]),
    }
