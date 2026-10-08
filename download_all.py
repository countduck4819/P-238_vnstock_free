from __future__ import annotations

import argparse
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from vnstock import Finance, Reference, register_user


# =========================
# PATHS
# =========================
PROJECT_ROOT = Path(__file__).resolve().parent
BASE_DIR = PROJECT_ROOT / "data" / "vnstock"
FINANCIAL_DIR = BASE_DIR / "raw" / "financial"
COMPANY_DIR = BASE_DIR / "raw" / "company"
METADATA_DIR = BASE_DIR / "metadata"
LOG_DIR = BASE_DIR / "logs"
TICKERS_FILE = METADATA_DIR / "tickers.csv"
MANIFEST_FILE = METADATA_DIR / "download_manifest.csv"
LOG_FILE = LOG_DIR / "downloader.log"

for folder in (FINANCIAL_DIR, COMPANY_DIR, METADATA_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)


# =========================
# CONFIG
# =========================
CALLS_PER_MINUTE = 45
MIN_INTERVAL = 60.0 / CALLS_PER_MINUTE  # 1 API-call start / second
MAX_WORKERS = 4
MAX_RETRIES = 4
FINANCIAL_SOURCE = "VCI"
FINANCIAL_PERIOD = "year"

RATE_LIMIT_BACKOFF = [65, 120, 300, 600]
NORMAL_ERROR_BACKOFF = [5, 15, 30, 60]


# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("vnstock_downloader")


# =========================
# AUTH
# =========================
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE)
API_KEY = os.getenv("VNSTOCK_API_KEY")
if not API_KEY:
    raise RuntimeError(f"Không tìm thấy VNSTOCK_API_KEY trong {ENV_FILE}")

register_user(api_key=API_KEY)
logger.info("VNStock authentication initialized")


# =========================
# GLOBAL RATE LIMITER
# =========================
class RateLimiter:
    """Giãn thời điểm bắt đầu API call trên toàn bộ worker."""

    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            scheduled = max(now, self._next_allowed)
            self._next_allowed = scheduled + self.min_interval

        wait_seconds = scheduled - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)


limiter = RateLimiter(MIN_INTERVAL)


# =========================
# HELPERS
# =========================
def file_ok(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def save_parquet_atomic(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def save_json_atomic(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_json(
        tmp,
        orient="records",
        force_ascii=False,
        indent=2,
        date_format="iso",
    )
    tmp.replace(path)


def normalize_dataframe(value):
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return value
    return pd.DataFrame(value)


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    patterns = [
        "429",
        "rate limit",
        "ratelimit",
        "too many request",
        "too many requests",
        "request limit",
        "quota",
    ]
    return any(pattern in text for pattern in patterns)


def call_api(label: str, func):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        limiter.wait()

        try:
            logger.info("REQUEST | %s | attempt=%d", label, attempt)
            result = func()
            df = normalize_dataframe(result)

            if df is None or df.empty:
                logger.warning("EMPTY | %s", label)
                return "empty", df, None

            logger.info(
                "SUCCESS | %s | rows=%d cols=%d",
                label,
                len(df),
                len(df.columns),
            )
            return "success", df, None

        except Exception as exc:
            last_error = str(exc)

            if is_rate_limit_error(exc):
                delay = RATE_LIMIT_BACKOFF[min(attempt - 1, len(RATE_LIMIT_BACKOFF) - 1)]
                delay += random.uniform(2, 8)
                logger.warning(
                    "RATE_LIMIT | %s | attempt=%d | sleep=%.1fs | %s",
                    label,
                    attempt,
                    delay,
                    exc,
                )
            else:
                delay = NORMAL_ERROR_BACKOFF[min(attempt - 1, len(NORMAL_ERROR_BACKOFF) - 1)]
                delay += random.uniform(1, 3)
                logger.warning(
                    "ERROR | %s | attempt=%d | sleep=%.1fs | %s",
                    label,
                    attempt,
                    delay,
                    exc,
                )

            if attempt < MAX_RETRIES:
                time.sleep(delay)

    return "error", None, last_error


# =========================
# TICKERS
# =========================
def load_tickers():
    if not TICKERS_FILE.exists():
        raise FileNotFoundError(f"Không tìm thấy {TICKERS_FILE}")

    df = pd.read_csv(TICKERS_FILE, encoding="utf-8-sig")
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    if "ticker" not in df.columns:
        raise ValueError(
            "tickers.csv phải có cột ticker. "
            f"Các cột hiện tại: {df.columns.tolist()}"
        )

    if "enabled" in df.columns:
        enabled = (
            df["enabled"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1", "yes", "y"])
        )
        df = df[enabled]

    tickers = (
        df["ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )
    return list(dict.fromkeys(tickers))


# =========================
# MANIFEST
# =========================
MANIFEST_COLUMNS = [
    "ticker",
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "financial_source",
    "profile",
    "overview",
    "officers",
    "last_error",
    "updated_at",
]


def load_manifest():
    if not MANIFEST_FILE.exists():
        return {}

    df = pd.read_csv(MANIFEST_FILE, dtype=str, encoding="utf-8-sig")
    if "ticker" not in df.columns:
        return {}

    manifest = {}
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).strip().upper()
        manifest[ticker] = row.fillna("").to_dict()
    return manifest


def save_manifest(manifest: dict):
    rows = []
    for ticker, data in manifest.items():
        row = {col: data.get(col, "") for col in MANIFEST_COLUMNS}
        row["ticker"] = ticker
        rows.append(row)

    df = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    tmp = MANIFEST_FILE.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    tmp.replace(MANIFEST_FILE)


# =========================
# SKIP / RESUME
# =========================
def should_skip(path: Path, force: bool = False):
    if force:
        return False, ""
    if file_ok(path):
        return True, "exists"
    # empty/error/missing => retry
    return False, ""


# =========================
# FINANCIAL — VCI ONLY
# =========================
def download_financial(symbol: str, manifest_row: dict):
    folder = FINANCIAL_DIR / symbol
    folder.mkdir(parents=True, exist_ok=True)

    previous_source = str(manifest_row.get("financial_source", "")).strip().upper()
    force_refresh = previous_source != FINANCIAL_SOURCE

    if force_refresh:
        logger.info(
            "FINANCIAL_SOURCE_REFRESH | %s | old=%s | new=%s",
            symbol,
            previous_source or "<unknown>",
            FINANCIAL_SOURCE,
        )

        # Xóa financial raw của source cũ trước khi tải VCI.
        # Nếu VCI trả empty/error thì file cũ không bị nhầm là dữ liệu VCI.
        for old_file in (
            folder / "balance_sheet.parquet",
            folder / "income_statement.parquet",
            folder / "cash_flow.parquet",
        ):
            if old_file.exists():
                old_file.unlink()
                logger.info(
                    "REMOVE_OLD_SOURCE_FILE | %s | %s",
                    symbol,
                    old_file.name,
                )

    finance = Finance(symbol=symbol, source=FINANCIAL_SOURCE)

    jobs = {
        "balance_sheet": (
            folder / "balance_sheet.parquet",
            lambda: finance.balance_sheet(period=FINANCIAL_PERIOD),
        ),
        "income_statement": (
            folder / "income_statement.parquet",
            lambda: finance.income_statement(period=FINANCIAL_PERIOD),
        ),
        "cash_flow": (
            folder / "cash_flow.parquet",
            lambda: finance.cash_flow(period=FINANCIAL_PERIOD),
        ),
    }

    statuses = {}
    errors = []

    for name, (path, func) in jobs.items():
        skip, status = should_skip(path, force=force_refresh)
        if skip:
            statuses[name] = status
            logger.info("SKIP | %s | %s | %s", symbol, name, status)
            continue

        status, df, error = call_api(f"{symbol}.{name}", func)

        if status == "success" and df is not None:
            save_parquet_atomic(df, path)

        statuses[name] = status
        if error:
            errors.append(f"{name}: {error}")

    statuses["financial_source"] = FINANCIAL_SOURCE
    return statuses, errors


# =========================
# COMPANY
# =========================
def download_company(symbol: str, manifest_row: dict):
    folder = COMPANY_DIR / symbol
    folder.mkdir(parents=True, exist_ok=True)

    profile_path = folder / "profile.json"
    overview_path = folder / "overview.json"
    officers_path = folder / "officers.json"

    statuses = {}
    errors = []
    reference = Reference()

    profile_skip, profile_status = should_skip(profile_path)
    overview_skip, overview_status = should_skip(overview_path)

    if profile_skip and overview_skip:
        statuses["profile"] = profile_status
        statuses["overview"] = overview_status
    else:
        company = reference.company(symbol)
        status, df, error = call_api(
            f"{symbol}.company_info",
            lambda: company.info(),
        )

        if status == "success" and df is not None:
            # 1 API call -> lưu 2 file để giữ contract thư mục hiện tại.
            save_json_atomic(df, profile_path)
            save_json_atomic(df, overview_path)

        statuses["profile"] = status
        statuses["overview"] = status
        if error:
            errors.append(f"company_info: {error}")

    skip, previous_status = should_skip(officers_path)
    if skip:
        statuses["officers"] = previous_status
        logger.info("SKIP | %s | officers | %s", symbol, previous_status)
    else:
        company = reference.company(symbol)
        status, df, error = call_api(
            f"{symbol}.officers",
            lambda: company.officers(),
        )

        if status == "success" and df is not None:
            save_json_atomic(df, officers_path)

        statuses["officers"] = status
        if error:
            errors.append(f"officers: {error}")

    return statuses, errors


# =========================
# ONE TICKER
# =========================
def process_ticker(symbol: str, row: dict):
    row = dict(row)
    errors = []

    try:
        statuses, current_errors = download_financial(symbol, row)
        row.update(statuses)
        errors.extend(current_errors)
    except Exception as exc:
        logger.exception("FINANCIAL_FATAL | %s", symbol)
        errors.append(f"financial: {exc}")

    try:
        statuses, current_errors = download_company(symbol, row)
        row.update(statuses)
        errors.extend(current_errors)
    except Exception as exc:
        logger.exception("COMPANY_FATAL | %s", symbol)
        errors.append(f"company: {exc}")

    row["ticker"] = symbol
    row["last_error"] = " | ".join(errors)
    row["updated_at"] = datetime.now().astimezone().isoformat()
    return symbol, row


# =========================
# CLI
# =========================
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Chỉ chạy một ticker, ví dụ --only ACB",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Chỉ chạy N ticker đầu tiên",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Số ticker xử lý đồng thời. Mặc định {MAX_WORKERS}",
    )
    return parser.parse_args()


# =========================
# MAIN
# =========================
def main():
    args = parse_args()
    tickers = load_tickers()

    if args.only:
        tickers = [args.only.strip().upper()]
    elif args.limit:
        tickers = tickers[: args.limit]

    manifest = load_manifest()
    total = len(tickers)

    if total == 0:
        print("Không có ticker nào để tải.")
        return

    workers = max(1, min(int(args.workers), total))
    started = time.time()

    print()
    print("=" * 72)
    print(f"Total tickers: {total}")
    print(f"Global API pacing: {CALLS_PER_MINUTE} calls/min")
    print(f"Workers: {workers}")
    print(f"Financial source: {FINANCIAL_SOURCE}")
    print("Financial period: YEAR")
    print("Batch cooldown: OFF")
    print("=" * 72)

    if total == 1:
        symbol = tickers[0]
        print(f"\n[1/1] {symbol}")
        row = manifest.get(symbol, {"ticker": symbol})
        symbol, row = process_ticker(symbol, row)
        manifest[symbol] = row
        save_manifest(manifest)

    else:
        futures = {}
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="vnstock",
        ) as executor:
            for symbol in tickers:
                row = manifest.get(symbol, {"ticker": symbol})
                future = executor.submit(process_ticker, symbol, row)
                futures[future] = symbol

            completed = 0
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    result_symbol, row = future.result()
                    manifest[result_symbol] = row
                except Exception as exc:
                    logger.exception("TICKER_FATAL | %s", symbol)
                    row = manifest.get(symbol, {"ticker": symbol})
                    row["last_error"] = f"ticker: {exc}"
                    row["updated_at"] = datetime.now().astimezone().isoformat()
                    manifest[symbol] = row

                # lưu progress sau từng ticker hoàn tất
                save_manifest(manifest)

                completed += 1
                elapsed = time.time() - started
                avg = elapsed / completed
                remaining = avg * (total - completed)
                print(
                    f"[{completed}/{total}] {symbol} completed | "
                    f"elapsed={elapsed / 60:.1f}m | ETA≈{remaining / 60:.1f}m"
                )

    runtime = time.time() - started
    print()
    print("=" * 72)
    print("DOWNLOAD COMPLETE")
    print(f"Runtime: {runtime / 60:.1f} minutes")
    print(f"Manifest: {MANIFEST_FILE}")
    print(f"Log: {LOG_FILE}")
    print("=" * 72)


if __name__ == "__main__":
    main()