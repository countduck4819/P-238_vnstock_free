"""Embed and upsert company knowledge documents using the approved BGE-M3 contract."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Iterator

from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
META = ROOT / "data" / "vnstock" / "metadata"
CONFIG = META / "company_knowledge_embedding_config.json"
PILOT = META / "company_knowledge_documents_pilot.jsonl"
ALL = META / "company_knowledge_documents.jsonl"
PAYLOAD_FIELDS = (
    "document_id", "ticker", "document_type", "source_provider",
    "source_files", "content_hash", "as_of_date",
)
APPROVED_CONTRACT = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_mode": "dense",
    "embedding_dimension": 1024,
    "normalize_embeddings": True,
    "distance": "cosine",
    "collection_name": "company_knowledge_v1",
}


def configured_value(name: str) -> str | None:
    """Read an environment value, falling back to the project .env file."""
    value = os.environ.get(name)
    if value:
        return value.strip().strip("\"'")
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*(.*)$", env_file.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None


def load_config() -> dict:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    drift = {
        key: {"expected": expected, "actual": cfg.get(key)}
        for key, expected in APPROVED_CONTRACT.items()
        if cfg.get(key) != expected
    }
    if drift:
        raise SystemExit(f"Approved embedding contract mismatch: {drift}")
    return cfg


def load_model(cfg: dict) -> SentenceTransformer:
    # Prevent an unnecessary model download on reruns.
    return SentenceTransformer(
        cfg["embedding_model"],
        revision=cfg.get("embedding_revision"),
        local_files_only=True,
    )


def iter_documents(path: Path, limit: int | None = None) -> Iterator[dict]:
    emitted = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if limit is not None and emitted >= limit:
                break
            yield json.loads(line)
            emitted += 1


def inspect_input(path: Path, limit: int | None) -> tuple[int, list[str]]:
    """Count selected documents and reject duplicate IDs before any write."""
    ids: list[str] = []
    seen: set[str] = set()
    for document in iter_documents(path, limit):
        point_id = str(document["document_id"])
        if point_id in seen:
            raise SystemExit(f"Duplicate document_id in input: {point_id}")
        seen.add(point_id)
        ids.append(point_id)
    return len(ids), ids


def payload_for(document: dict, cfg: dict) -> dict:
    payload = {key: document.get(key) for key in PAYLOAD_FIELDS}
    payload.update({
        "text": document["text"],
        "embedding_model": cfg["embedding_model"],
        "embedding_revision": cfg.get("embedding_revision"),
        "embedding_mode": "dense",
    })
    return payload


def batches(documents: Iterator[dict], size: int) -> Iterator[list[dict]]:
    batch: list[dict] = []
    for document in documents:
        batch.append(document)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--embedding-batch-size", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.batch_size < 1 or args.embedding_batch_size < 1:
        raise SystemExit("Batch sizes must be positive")
    if not 60 <= args.timeout <= 120:
        raise SystemExit("Timeout must be between 60 and 120 seconds")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("Limit must be positive")

    cfg = load_config()
    path = Path(args.input) if args.input else (ALL if args.all else PILOT)
    total, selected_ids = inspect_input(path, args.limit)
    if total == 0:
        raise SystemExit("No documents selected")

    client = QdrantClient(
        url=configured_value("QDRANT_URL") or cfg["qdrant_url"],
        api_key=configured_value("QDRANT_API_KEY") or None,
        timeout=args.timeout,
    )
    collections = {item.name for item in client.get_collections().collections}
    if cfg["collection_name"] in collections:
        info = client.get_collection(cfg["collection_name"])
        params = info.config.params.vectors
        if (
            not isinstance(params, models.VectorParams)
            or params.size != cfg["embedding_dimension"]
            or params.distance != models.Distance.COSINE
        ):
            raise SystemExit(
                "Existing collection vector contract is incompatible; refusing to recreate"
            )
    else:
        client.create_collection(
            cfg["collection_name"],
            vectors_config=models.VectorParams(
                size=cfg["embedding_dimension"], distance=models.Distance.COSINE
            ),
        )
        client.create_payload_index(
            cfg["collection_name"], "ticker", models.PayloadSchemaType.KEYWORD
        )
        client.create_payload_index(
            cfg["collection_name"], "document_type", models.PayloadSchemaType.KEYWORD
        )

    # Detailed before/after validation is intentionally bounded to small test runs.
    validate_small = total <= 128
    count_before = client.count(cfg["collection_name"], exact=True).count
    existing_before: set[str] = set()
    if validate_small:
        existing_before = {
            str(record.id)
            for record in client.retrieve(
                cfg["collection_name"], ids=selected_ids,
                with_payload=False, with_vectors=False,
            )
        }

    embedder = load_model(cfg)
    embedded = 0
    upserted = 0
    expected_payloads: dict[str, dict] = {}
    for document_batch in batches(iter_documents(path, args.limit), args.batch_size):
        vectors = embedder.encode(
            [document["text"] for document in document_batch],
            batch_size=args.embedding_batch_size,
            show_progress_bar=False,
            normalize_embeddings=cfg["normalize_embeddings"],
        )
        if len(vectors) != len(document_batch) or any(
            len(vector) != cfg["embedding_dimension"] for vector in vectors
        ):
            raise SystemExit("Embedding count/dimension mismatch")
        embedded += len(document_batch)
        print(f"embedded {embedded} / {total}", flush=True)

        points: list[models.PointStruct] = []
        for document, vector in zip(document_batch, vectors):
            payload = payload_for(document, cfg)
            point_id = str(document["document_id"])
            points.append(models.PointStruct(
                id=point_id, vector=vector.tolist(), payload=payload
            ))
            if validate_small:
                expected_payloads[point_id] = payload
        client.upsert(cfg["collection_name"], points=points, wait=True)
        upserted += len(points)
        print(f"upserted {upserted} / {total}", flush=True)
        del vectors, points, document_batch

    count_after = client.count(cfg["collection_name"], exact=True).count
    result = {
        "input": str(path),
        "documents_embedded": embedded,
        "batch_size": args.batch_size,
        "timeout_seconds": args.timeout,
        "dimension": cfg["embedding_dimension"],
        "collection": cfg["collection_name"],
        "point_count_before": count_before,
        "point_count_after": count_after,
        "duplicate_input_ids": 0,
    }

    if validate_small:
        records = client.retrieve(
            cfg["collection_name"], ids=selected_ids,
            with_payload=True, with_vectors=False,
        )
        returned = {str(record.id): record.payload for record in records}
        expected_count = count_before + total - len(existing_before)
        missing_ids = sorted(set(selected_ids) - set(returned))
        payload_mismatches = sorted(
            point_id
            for point_id, expected in expected_payloads.items()
            if returned.get(point_id) != expected
        )
        result.update({
            "expected_point_count_after": expected_count,
            "selected_ids_already_present": len(existing_before),
            "selected_ids_returned": len(returned),
            "missing_ids": len(missing_ids),
            "payload_mismatches": len(payload_mismatches),
            "small_validation_pass": (
                count_after == expected_count
                and len(returned) == total
                and not missing_ids
                and not payload_mismatches
            ),
        })
        if not result["small_validation_pass"]:
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit("Small-batch validation failed")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
