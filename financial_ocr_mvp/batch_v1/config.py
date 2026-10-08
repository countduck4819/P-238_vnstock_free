"""Configuration for the read-only batch-v1 scanner."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "financial_ocr_mvp" / "output" / "batch_v1"
load_dotenv(ROOT / ".env")

TICKERS = ("FPT", "HPG", "VNM", "MWG", "VCB")
YEAR = 2015
BUCKET = os.getenv("MINIO_BUCKET", "stock-data")
PREFIX = "financial-reports/consolidated/"


def minio_settings() -> dict[str, object]:
    endpoint = os.getenv("MINIO_ENDPOINT")
    access_key = os.getenv("MINIO_ACCESS_KEY")
    secret_key = os.getenv("MINIO_SECRET_KEY")
    if not endpoint or not access_key or not secret_key:
        raise RuntimeError("Thiếu MINIO_ENDPOINT, MINIO_ACCESS_KEY hoặc MINIO_SECRET_KEY trong .env")
    return {
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "secure": os.getenv("MINIO_SECURE", "false").lower() in {"1", "true", "yes"},
    }
