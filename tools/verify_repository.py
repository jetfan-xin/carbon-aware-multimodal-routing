"""Check published provenance, local documentation links and obvious disclosures.

This lightweight check is not a comprehensive secret scanner.
It prints locations, never matched credential values.
"""

import ast
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    errors = []
    checked = 0
    links = 0
    manifest = json.loads((root / "source-manifest.json").read_text(encoding="utf-8"))
    source_ids = {entry["id"] for entry in manifest["sources"]}
    if len(source_ids) != len(manifest["sources"]):
        errors.append("source-manifest.json: duplicate source identifier")

    def check_refs(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "source_id" and item not in source_ids:
                    errors.append(path + ": unknown source identifier")
                elif key == "source_ids" and not set(item).issubset(source_ids):
                    errors.append(path + ": unknown source identifiers")
                check_refs(item, path)
        elif isinstance(value, list):
            for item in value:
                check_refs(item, path)

    for entry in manifest["published_image_assets"]:
        target = (root / entry["path"]).resolve()
        if not target.is_relative_to(root.resolve()):
            errors.append("source-manifest.json: image path escapes repository")
        elif not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append(entry["path"] + ": image hash mismatch")

    patterns = [
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
        re.compile(r"\b(?:hf_|ghp_)[A-Za-z0-9]{20,}"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"/(?:Users|Volumes)/[^\s]+"),
    ]
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in (".git", "__pycache__") for part in path.relative_to(root).parts):
            continue
        checked += 1
        if path.suffix not in (".md", ".json", ".py"):
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        if any(pattern.search(content) for pattern in patterns):
            errors.append(relative + ": potential credential or private local path")
        if path.suffix == ".py":
            ast.parse(content, filename=relative)
        if path.suffix == ".json":
            check_refs(json.loads(content), relative)
        if path.suffix == ".md":
            if re.search(r"[\u4e00-\u9fff]", content):
                errors.append(relative + ": explanatory text is not entirely English")
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                links += 1
                resolved = (path.parent / unquote(target.split("#", 1)[0])).resolve()
                if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                    errors.append(relative + ": broken or out-of-repository local link")
    return {"files_checked": checked, "local_links_checked": links, "source_records": len(source_ids), "errors": errors}


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))
