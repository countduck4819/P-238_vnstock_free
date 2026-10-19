"""Remove old daily-scoring runs while preserving rollback and serving data."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]


def _path(value: Path) -> Path:
    return value if value.is_absolute() else ROOT / value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _protected_run_dirs(pointer_paths: list[Path], run_root: Path) -> set[Path]:
    protected: set[Path] = set()
    run_root = run_root.resolve()
    for pointer in pointer_paths:
        payload = _read_json(pointer)
        for raw in _strings(payload):
            candidate = _path(Path(raw))
            try:
                relative = candidate.resolve().relative_to(run_root)
            except ValueError:
                continue
            if relative.parts:
                protected.add(run_root / relative.parts[0])
    return protected


def prune_runs(
    run_root: Path,
    *,
    keep_success: int = 14,
    failed_retention_days: int = 3,
    pointer_paths: list[Path] | None = None,
) -> list[Path]:
    if keep_success < 1 or failed_retention_days < 0:
        raise ValueError("keep_success must be positive and failed_retention_days non-negative.")
    run_root = run_root.resolve()
    if not run_root.is_dir():
        return []
    protected = _protected_run_dirs(pointer_paths or [], run_root)
    manifests: list[tuple[Path, dict[str, Any]]] = []
    for directory in run_root.iterdir():
        if not directory.is_dir() or directory in protected or directory.name.startswith("."):
            continue
        manifest = _read_json(directory / "orchestration_manifest.json")
        if manifest:
            manifests.append((directory, manifest))

    successful = sorted(
        ((path, manifest) for path, manifest in manifests if manifest.get("status") == "success"),
        key=lambda item: str(item[1].get("finished_at_utc", "")),
        reverse=True,
    )
    keep = {path for path, _ in successful[:keep_success]}
    cutoff = datetime.now(UTC) - timedelta(days=failed_retention_days)
    removed: list[Path] = []
    for directory, manifest in manifests:
        if directory in keep or manifest.get("status") == "running":
            continue
        if manifest.get("status") == "failed":
            finished = manifest.get("finished_at_utc")
            try:
                old = datetime.fromisoformat(str(finished).replace("Z", "+00:00")) < cutoff
            except (TypeError, ValueError):
                old = datetime.fromtimestamp(directory.stat().st_mtime, UTC) < cutoff
            if not old:
                continue
        elif manifest.get("status") != "success":
            continue
        # Every target was resolved as a direct child of the requested run root.
        if directory.parent != run_root:
            continue
        shutil.rmtree(directory)
        removed.append(directory)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=Path("runs/daily_model_scoring"))
    parser.add_argument("--keep-success", type=int, default=14)
    parser.add_argument("--failed-retention-days", type=int, default=3)
    parser.add_argument(
        "--pointer", type=Path, action="append",
        default=[Path("runs/wave_h120_shadow/serving_release.json")],
        help="Serving/release pointer whose referenced run must not be deleted; repeatable.",
    )
    args = parser.parse_args()
    removed = prune_runs(
        _path(args.run_root),
        keep_success=args.keep_success,
        failed_retention_days=args.failed_retention_days,
        pointer_paths=[_path(path) for path in args.pointer],
    )
    print(json.dumps({"removed": [str(path.relative_to(ROOT)) for path in removed], "count": len(removed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
