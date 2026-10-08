"""Fail-closed preflight for Phase E refit/shadow activation.

Phase E is intentionally not a training shortcut: it is allowed only after a
human-reviewed, frozen Phase-C selection record explicitly authorizes refit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--dataset-run", type=Path, required=True)
    parser.add_argument("--selection-record", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol = __import__("yaml").safe_load(args.protocol.read_text(encoding="utf-8"))
    manifest = json.loads((args.dataset_run / "dataset_manifest.json").read_text(encoding="utf-8"))
    selection = json.loads(args.selection_record.read_text(encoding="utf-8"))
    expected_label = protocol["label_contract"]["label_version"]
    actual_label = manifest["label_dependency"]["version"]
    if actual_label != expected_label:
        raise ValueError(f"Dataset label version {actual_label} does not match {expected_label}.")
    if selection.get("status") != "configuration_frozen_research_eligible":
        raise ValueError("Phase E remains blocked: selection record is not frozen and approved.")
    if selection.get("protocol") != str(args.protocol).replace("\\", "/"):
        raise ValueError("Selection record references a different protocol.")
    if selection.get("trade_authorized", True):
        raise ValueError("Phase E must remain shadow-only; trade authorization is forbidden.")
    print(json.dumps({"status": "phase_e_preflight_passed", "trade_authorized": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
