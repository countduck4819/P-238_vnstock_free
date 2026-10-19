import os
import threading
import time
import schedule
from core.paths import DATA_DIR, data_path
from core.fetchers import (
    fetch_vnindex,
    fetch_listing,
    fetch_industries,
    fetch_industries_for_code,
    fetch_stocks_by_industries,
    fetch_stocks_symbols,
)
from core.utils import save_json

STOCKS_DIR = data_path("stocks")

_export_lock = threading.Lock()
_scheduler_thread = None
_scheduler_thread_lock = threading.Lock()


def ensure_dirs():
    """Đảm bảo tồn tại data/ và data/stocks/"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(STOCKS_DIR, exist_ok=True)


def scheduled_export():
    if not _export_lock.acquire(blocking=False):
        print("⏭️ Scheduler đang cập nhật, bỏ qua lượt này.")
        return

    try:
        print("⏳ Bắt đầu cập nhật dữ liệu...")
        ensure_dirs()

        jobs = {
            "vnindex.json": fetch_vnindex,
            "listing.json": fetch_listing,
            "industries.json": fetch_industries,
            "industries_for_code.json": fetch_industries_for_code,
            "stocks_by_industries.json": fetch_stocks_by_industries,
            "stocks_symbols.json": fetch_stocks_symbols,
        }

        for filename, fetcher in jobs.items():
            try:
                data = fetcher()

                if not data:
                    print(f"Không có dữ liệu cho {filename}, bỏ qua.")
                    continue

                save_json(filename, data)
                print(f"✅ Đã cập nhật {filename}")
            except Exception as exc:
                print(f"❌ Cập nhật {filename} lỗi: {exc}")

        print("✅ Hoàn tất lượt cập nhật dữ liệu.\n")
    finally:
        _export_lock.release()


def schedule_loop():
    schedule.every(1).hours.do(scheduled_export)

    print(
        "🕒 Scheduler đã khởi động, "
        "lần cập nhật tiếp theo sau 1 giờ."
    )

    counter = 0
    while True:
        try:
            schedule.run_pending()
        except Exception as exc:
            print(f"❌ Scheduler loop lỗi: {exc}")

        counter += 1

        if counter % 120 == 0:
            print("💤 Scheduler vẫn đang chạy...")

        time.sleep(30)


def start_scheduler():
    global _scheduler_thread

    with _scheduler_thread_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return _scheduler_thread

        _scheduler_thread = threading.Thread(
            target=schedule_loop,
            name="fireant-scheduler",
            daemon=True,
        )
        _scheduler_thread.start()

        return _scheduler_thread
